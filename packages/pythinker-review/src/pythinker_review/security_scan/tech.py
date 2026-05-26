"""Pure-Python technology detector used to scope Pythinker Security Scan matchers and prompts."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from pythinker_review.security_scan.models import DetectedTech, now_iso
from pythinker_review.security_scan.paths import data_dir

LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "typescript": (".ts", ".tsx", ".cts", ".mts"),
    "javascript": (".js", ".jsx", ".cjs", ".mjs"),
    "python": (".py",),
    "ruby": (".rb",),
    "php": (".php",),
    "go": (".go",),
    "rust": (".rs",),
    "java": (".java",),
    "kotlin": (".kt", ".kts"),
    "csharp": (".cs",),
    "lua": (".lua",),
    "terraform": (".tf",),
    "swift": (".swift",),
    "elixir": (".ex", ".exs"),
    "dart": (".dart",),
}

COMMON_SENTINELS = (
    "package.json",
    "composer.json",
    "artisan",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "manage.py",
    "Pipfile",
    "Gemfile",
    "Gemfile.lock",
    "config/routes.rb",
    "bin/rails",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "mix.exs",
    "rebar.config",
    "shard.yml",
    "project.clj",
    "deps.edn",
    "Package.swift",
    "Info.plist",
    "pubspec.yaml",
    "sfdx-project.json",
    "AndroidManifest.xml",
    "serverless.yml",
    "serverless.yaml",
    "template.yaml",
    "template.yml",
    "samconfig.toml",
    "host.json",
    "cloudbuild.yaml",
    "cloudbuild.yml",
    "global.json",
    "Dockerfile",
    "wrangler.toml",
    "wrangler.jsonc",
    "deno.json",
    "deno.jsonc",
    "deno.lock",
    "bun.lockb",
    "bun.lock",
    "next.config.js",
    "next.config.ts",
    "next.config.mjs",
    "wp-config.php",
    ".github/workflows",
)


def detect_tech(root_path: Path, *, file_paths: Iterable[str] | None = None) -> DetectedTech:
    root = root_path.resolve()
    cache: dict[str, str | None] = {}
    tags: set[str] = set()
    sentinels: set[str] = {rel for rel in COMMON_SENTINELS if (root / rel).exists()}

    _detect_node(root, cache, tags)
    _detect_bun_deno_workers(root, tags)
    _detect_php(root, cache, tags)
    _detect_python(root, cache, tags)
    _detect_ruby(root, cache, tags)
    _detect_go(root, cache, tags)
    _detect_rust(root, cache, tags)
    _detect_jvm(root, cache, tags)
    _detect_dotnet(root, tags)
    _detect_other_ecosystems(root, cache, tags)
    _detect_infra(root, tags)

    languages = sorted(_languages_from_tags(tags) | _languages_from_files(root, file_paths))
    return DetectedTech.model_validate(
        {
            "tags": sorted(tags),
            "languages": languages,
            "sentinels": sorted(sentinels),
            "detectedAt": now_iso(),
            "rootPath": str(root),
        }
    )


def write_tech_json(project_id: str, detected: DetectedTech, *, data_root: Path) -> Path:
    out = data_dir(project_id, data_root=data_root) / "tech.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(detected.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    return out


def read_tech_json(project_id: str, *, data_root: Path) -> DetectedTech | None:
    path = data_dir(project_id, data_root=data_root) / "tech.json"
    if not path.exists():
        return None
    try:
        return DetectedTech.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def language_for_path(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    for language, extensions in LANGUAGE_EXTENSIONS.items():
        if suffix in extensions:
            return language
    if Path(path).name in {"Dockerfile"} or ".Dockerfile" in path:
        return "dockerfile"
    return None


def languages_for_paths(paths: list[str]) -> list[str]:
    return sorted({lang for path in paths if (lang := language_for_path(path)) is not None})


def _read_text(root: Path, rel: str, cache: dict[str, str | None]) -> str | None:
    if rel in cache:
        return cache[rel]
    try:
        value = (root / rel).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        value = None
    cache[rel] = value
    return value


def _read_json(root: Path, rel: str, cache: dict[str, str | None]) -> dict[str, object] | None:
    text = _read_text(root, rel, cache)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _deps(pkg: dict[str, object]) -> set[str]:
    names: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        value = pkg.get(key)
        if isinstance(value, dict):
            names.update(str(name) for name in value)
    return names


def _detect_node(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    pkg = _read_json(root, "package.json", cache)
    if not pkg:
        return
    tags.add("node")
    deps = _deps(pkg)
    has = deps.__contains__

    def starts(prefix: str) -> bool:
        return any(dep.startswith(prefix) for dep in deps)

    mapping = {
        "next": "nextjs",
        "react": "react",
        "react-dom": "react",
        "express": "express",
        "fastify": "fastify",
        "hono": "hono",
        "koa": "koa",
        "@koa/router": "koa",
        "@hapi/hapi": "hapi",
        "@remix-run/server-runtime": "remix",
        "@remix-run/node": "remix",
        "@sveltejs/kit": "sveltekit",
        "nuxt": "nuxt",
        "nuxt3": "nuxt",
        "h3": "nuxt",
        "astro": "astro",
        "@solidjs/start": "solidstart",
        "@trpc/server": "trpc",
        "@modelcontextprotocol/sdk": "mcp",
        "@connectrpc/connect": "connectrpc",
        "graphql": "graphql",
        "apollo-server": "graphql",
        "socket.io": "socketio",
        "bullmq": "bullmq",
        "drizzle-orm": "drizzle",
        "@prisma/client": "prisma",
        "prisma": "prisma",
    }
    for dep, tag in mapping.items():
        if has(dep):
            tags.add(tag)
    if starts("@nestjs/"):
        tags.add("nestjs")
    if starts("@apollo/"):
        tags.add("graphql")


def _detect_bun_deno_workers(root: Path, tags: set[str]) -> None:
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        tags.add("bun")
    if any((root / rel).exists() for rel in ("deno.json", "deno.jsonc", "deno.lock")):
        tags.add("deno")
    if any((root / rel).exists() for rel in ("wrangler.toml", "wrangler.jsonc")):
        tags.add("workers")


def _detect_php(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    composer = _read_json(root, "composer.json", cache)
    if not composer:
        return
    tags.add("php")
    deps = set()
    for key in ("require", "require-dev"):
        value = composer.get(key)
        if isinstance(value, dict):
            deps.update(str(dep) for dep in value)
    if any(dep.startswith("laravel/") for dep in deps) or (root / "artisan").exists():
        tags.add("laravel")
    for prefix, tag in (
        ("symfony/", "symfony"),
        ("yiisoft/", "yii"),
        ("wordpress/", "wordpress"),
        ("drupal/", "drupal"),
        ("magento/", "magento"),
    ):
        if any(dep.startswith(prefix) for dep in deps):
            tags.add(tag)
    if "slim/slim" in deps:
        tags.add("slim")
    if "cakephp/cakephp" in deps:
        tags.add("cakephp")
    if "codeigniter4/framework" in deps:
        tags.add("codeigniter")
    if (root / "wp-config.php").exists():
        tags.add("wordpress")


def _detect_python(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    py_sources = [
        text
        for rel in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile")
        if (text := _read_text(root, rel, cache))
    ]
    py_text = "\n".join(py_sources).lower()
    if not py_sources and not (root / "manage.py").exists():
        return
    tags.add("python")
    if (root / "manage.py").exists() or re.search(r"\bdjango\b", py_text):
        tags.add("django")
    checks = (
        (r"\bdjangorestframework\b|\brest_framework\b", "djangorestframework"),
        (r"\bflask\b", "flask"),
        (r"\bfastapi\b", "fastapi"),
        (r"\bstarlette\b", "starlette"),
        (r"\baiohttp\b", "aiohttp"),
        (r"\btornado\b", "tornado"),
        (r"\bsanic\b", "sanic"),
        (r"\bbottle\b", "bottle"),
        (r"\bfalcon\b", "falcon"),
        (r"\bcelery\b", "celery"),
        (r"\bairflow\b|\bapache-airflow\b", "airflow"),
    )
    for pattern, tag in checks:
        if re.search(pattern, py_text):
            tags.add(tag)


def _detect_ruby(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    gemfile = _read_text(root, "Gemfile", cache)
    lock = _read_text(root, "Gemfile.lock", cache)
    if not gemfile and not lock:
        return
    tags.add("ruby")
    haystack = f"{gemfile or ''}\n{lock or ''}".lower()
    if re.search(r"[\s'\"]rails[\s'\"]", haystack) or (root / "config/routes.rb").exists():
        tags.add("rails")
    for pattern, tag in (
        (r"\bsinatra\b", "sinatra"),
        (r"\bgrape\b", "grape"),
        (r"\bhanami\b", "hanami"),
        (r"\broda\b", "roda"),
    ):
        if re.search(pattern, haystack):
            tags.add(tag)


def _detect_go(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    gomod = _read_text(root, "go.mod", cache)
    if not gomod:
        return
    tags.add("go")
    lower = gomod.lower()
    for pattern, tag in (
        (r"github\.com/gin-gonic/gin\b", "gin"),
        (r"github\.com/labstack/echo\b", "echo"),
        (r"github\.com/gofiber/fiber\b", "fiber"),
        (r"github\.com/go-chi/chi\b", "chi"),
        (r"github\.com/gorilla/mux\b", "gorilla"),
        (r"github\.com/gobuffalo/buffalo\b", "buffalo"),
        (r"google\.golang\.org/grpc\b", "grpc"),
        (r"connectrpc\.com/connect\b", "connectrpc"),
        (r"github\.com/spf13/cobra\b", "cobra"),
    ):
        if re.search(pattern, lower):
            tags.add(tag)


def _detect_rust(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    cargo = _read_text(root, "Cargo.toml", cache)
    if not cargo:
        return
    tags.add("rust")
    lower = cargo.lower()
    for pattern, tag in (
        (r"\bactix-web\b", "actix"),
        (r"\baxum\b", "axum"),
        (r"\brocket\b", "rocket"),
        (r"\bwarp\b", "warp"),
        (r"\btide\b", "tide"),
        (r"\bpoem\b", "poem"),
        (r"\btonic\b", "tonic"),
        (r"\blambda_runtime\b", "lambda-rs"),
    ):
        if re.search(pattern, lower):
            tags.add(tag)


def _detect_jvm(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    jvm_sources = [
        text
        for rel in ("pom.xml", "build.gradle", "build.gradle.kts")
        if (text := _read_text(root, rel, cache))
    ]
    haystack = "\n".join(jvm_sources).lower()
    if not jvm_sources:
        return
    tags.add("jvm")
    for pattern, tag in (
        (r"\borg\.springframework\b|\bspring-boot\b", "spring"),
        (r"\bktor\b", "ktor"),
        (r"\bmicronaut\b", "micronaut"),
        (r"\bjavax\.ws\.rs\b|\bjakarta\.ws\.rs\b", "jaxrs"),
    ):
        if re.search(pattern, haystack):
            tags.add(tag)


def _detect_dotnet(root: Path, tags: set[str]) -> None:
    if any(root.glob("*.csproj")) or (root / "global.json").exists():
        tags.add("dotnet")


def _detect_other_ecosystems(root: Path, cache: dict[str, str | None], tags: set[str]) -> None:
    mix = _read_text(root, "mix.exs", cache)
    if mix:
        tags.add("elixir")
        if re.search(r":phoenix\b|\"phoenix\"|phoenix,", mix.lower()):
            tags.add("phoenix")
    rebar = _read_text(root, "rebar.config", cache)
    if rebar or any((root / "src").glob("*.erl")):
        tags.add("erlang")
        if rebar and "cowboy" in rebar.lower():
            tags.add("cowboy")
    shard = _read_text(root, "shard.yml", cache)
    if shard:
        tags.add("crystal")
        if "kemal" in shard.lower():
            tags.add("kemal")
    if _read_text(root, "project.clj", cache) or _read_text(root, "deps.edn", cache):
        tags.add("clojure")
    package_swift = _read_text(root, "Package.swift", cache)
    has_xcode = any(root.glob("*.xcodeproj")) or any(root.glob("*.xcworkspace"))
    if package_swift or has_xcode or (root / "Info.plist").exists():
        tags.add("swift")
        if has_xcode or (root / "Info.plist").exists():
            tags.add("ios")
        if package_swift and "vapor" in package_swift.lower():
            tags.add("vapor")
    pubspec = _read_text(root, "pubspec.yaml", cache)
    if pubspec:
        tags.add("dart")
        if re.search(r"^\s*flutter\s*:\s*$", pubspec, re.M) or "sdk: flutter" in pubspec:
            tags.add("flutter")
        if re.search(r"\bshelf\s*:", pubspec, re.I):
            tags.add("shelf")
    if (root / "sfdx-project.json").exists() or (root / "force-app").exists():
        tags.update({"apex", "salesforce"})
    if any((root / rel).exists() for rel in ("AndroidManifest.xml", "app/AndroidManifest.xml")):
        tags.add("android")
    if (root / "app/src/main/AndroidManifest.xml").exists():
        tags.add("android")


def _detect_infra(root: Path, tags: set[str]) -> None:
    if (root / "Dockerfile").exists() or any(root.glob("Dockerfile.*")):
        tags.add("docker")
    if (root / "terraform").exists() or any(root.glob("*.tf")):
        tags.add("terraform")
    if (root / ".github/workflows").exists():
        tags.add("github-actions")
    if any(
        (root / rel).exists() for rel in ("serverless.yml", "serverless.yaml", "samconfig.toml")
    ):
        tags.add("aws-lambda")
    if any((root / rel).exists() for rel in ("cloudbuild.yaml", "cloudbuild.yml")):
        tags.add("gcp-cloud-functions")
    if (root / "host.json").exists():
        tags.add("azure-functions")


def _languages_from_tags(tags: set[str]) -> set[str]:
    out: set[str] = set()
    mapping = {
        "node": {"javascript", "typescript"},
        "python": {"python"},
        "ruby": {"ruby"},
        "php": {"php"},
        "go": {"go"},
        "rust": {"rust"},
        "jvm": {"java"},
        "dotnet": {"csharp"},
        "terraform": {"terraform"},
        "swift": {"swift"},
        "elixir": {"elixir"},
        "dart": {"dart"},
    }
    for tag in tags:
        out.update(mapping.get(tag, set()))
    return out


def _languages_from_files(root: Path, file_paths: Iterable[str] | None = None) -> set[str]:
    if file_paths is not None:
        return {lang for path in file_paths if (lang := language_for_path(path)) is not None}

    out: set[str] = set()
    for language, extensions in LANGUAGE_EXTENSIONS.items():
        for ext in extensions:
            if next(root.glob(f"**/*{ext}"), None) is not None:
                out.add(language)
                break
    return out
