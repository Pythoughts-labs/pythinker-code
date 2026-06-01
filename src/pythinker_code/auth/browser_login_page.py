from __future__ import annotations

import base64
import html
from functools import cache
from pathlib import Path

_PYTHINKER_BRAND_DIR = Path(__file__).resolve().parents[1] / "web" / "static" / "brand"
_PYTHINKER_LOGO_PATH = _PYTHINKER_BRAND_DIR / "icon.svg"
_PYTHINKER_FAVICON_PATH = _PYTHINKER_BRAND_DIR / "favicon.ico"


@cache
def browser_login_asset_data_uri(path: Path, media_type: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{media_type};base64,{encoded}"


def browser_login_logo_data_uri() -> str:
    return browser_login_asset_data_uri(_PYTHINKER_LOGO_PATH, "image/svg+xml")


def browser_login_favicon_data_uri() -> str:
    return browser_login_asset_data_uri(_PYTHINKER_FAVICON_PATH, "image/x-icon")


def build_browser_login_result_html(
    *,
    ok: bool,
    success_title: str,
    failure_title: str,
    success_heading: str,
    failure_heading: str,
    success_body: str,
    failure_body: str | None,
    fallback_failure_body: str,
) -> str:
    title = success_title if ok else failure_title
    heading = success_heading if ok else failure_heading
    body = success_body if ok else failure_body
    escaped_title = html.escape(title)
    escaped_heading = html.escape(heading)
    escaped_body = html.escape(body or fallback_failure_body)
    favicon = html.escape(browser_login_favicon_data_uri(), quote=True)
    logo = html.escape(browser_login_logo_data_uri(), quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <link rel="icon" type="image/x-icon" href="{favicon}">
  <style>
    :root {{ color-scheme: light dark; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #1e293b 0, #0f172a 42%, #020617 100%);
      color: #f8fafc;
    }}
    main {{
      width: min(440px, calc(100vw - 48px));
      padding: 40px 32px;
      border: 1px solid rgba(148, 163, 184, 0.25);
      border-radius: 28px;
      background: rgba(15, 23, 42, 0.82);
      box-shadow: 0 24px 80px rgba(2, 6, 23, 0.45);
      text-align: center;
    }}
    .logo {{ width: 82px; height: auto; margin-bottom: 22px; }}
    h1 {{ margin: 0 0 12px; font-size: 2rem; line-height: 1.15; }}
    p {{ margin: 0; color: #cbd5e1; font-size: 1.05rem; line-height: 1.6; }}
  </style>
</head>
<body>
  <main>
    <img class="logo" src="{logo}" alt="Pythinker logo">
    <h1>{escaped_heading}</h1>
    <p>{escaped_body}</p>
  </main>
</body>
</html>"""
