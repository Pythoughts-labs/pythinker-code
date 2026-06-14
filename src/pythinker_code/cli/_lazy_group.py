# pyright: reportAttributeAccessIssue=false, reportMissingParameterType=false, reportPrivateImportUsage=false, reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUntypedBaseClass=false
from __future__ import annotations

from importlib import import_module
from typing import Any, cast

import click
import typer
from click.core import HelpFormatter
from typer._click.core import Command as _TyperCommand  # typer 0.26 vendors its own click
from typer.main import get_command


class LazySubcommandGroup(typer.core.TyperGroup):
    """Load heavyweight subcommands only when they are actually invoked."""

    lazy_subcommands: dict[str, tuple[str, str, str]] = {
        "info": ("pythinker_code.cli.info", "cli", "Show version and protocol information."),
        "export": ("pythinker_code.cli.export", "cli", "Export session data."),
        "mcp": ("pythinker_code.cli.mcp", "cli", "Manage MCP server configurations."),
        "plugin": ("pythinker_code.cli.plugin", "cli", "Manage plugins."),
        "skill": ("pythinker_code.cli.skill", "cli", "Inspect and lock Pythinker skills."),
        "review": (
            "pythinker_code.cli.review",
            "cli",
            "Diff-focused code review (delegates to pythinker-review).",
        ),
        "secscan": (
            "pythinker_code.cli.secscan",
            "cli",
            "Diff-focused security review (delegates to pythinker-review).",
        ),
        "security-scan": (
            "pythinker_code.cli.security_scan",
            "cli",
            "Repo-wide Pythinker Security Scan pipeline (Python-native).",
        ),
        "debug": (
            "pythinker_code.cli.debug",
            "cli",
            "Failure/log root-cause analysis (delegates to pythinker-review).",
        ),
        "update": (
            "pythinker_code.cli.update",
            "cli",
            "Check for and install Pythinker CLI updates.",
        ),
        "dashboard": (
            "pythinker_code.cli.dashboard",
            "cli",
            "Run Pythinker Agent Tracing Visualizer.",
        ),
        "web": ("pythinker_code.cli.web", "cli", "Run Pythinker CLI web interface."),
    }
    lazy_command_order: tuple[str, ...] = (
        "info",
        "export",
        "mcp",
        "plugin",
        "skill",
        "review",
        "secscan",
        "security-scan",
        "debug",
        "update",
        "dashboard",
        "web",
    )

    # `--session`/`--resume` accept an *optional* value: with an ID they resume
    # that session, without one they open the interactive picker. Typer 0.26
    # reimplemented option parsing with a parser that always consumes the next
    # token as the value (no optional-value support), so we normalise argv before
    # parsing: when one of these flags is used without a usable value (it is the
    # last token, or is followed by another option) we inject an empty-string
    # sentinel that the root callback maps to picker mode.
    _optional_value_flags: frozenset[str] = frozenset({"--session", "--resume", "-S", "-r"})

    def make_context(
        self, info_name: str | None, args: list[str], parent: click.Context | None = None, **extra
    ) -> click.Context:
        args = self._inject_optional_value_sentinels(args)
        return super().make_context(info_name, args, parent=parent, **extra)

    def _inject_optional_value_sentinels(self, args: list[str]) -> list[str]:
        """Insert an empty-string value after optional-value flags used without one."""
        result: list[str] = []
        seen_terminator = False
        for i, arg in enumerate(args):
            result.append(arg)
            if seen_terminator:
                continue
            if arg == "--":
                seen_terminator = True
                continue
            if arg in self._optional_value_flags:
                nxt = args[i + 1] if i + 1 < len(args) else None
                if nxt is None or nxt.startswith("-"):
                    result.append("")
        return result

    def list_commands(self, ctx: click.Context) -> list[str]:
        commands = list(super().list_commands(ctx))
        for name in self.lazy_command_order:
            if name not in commands:
                commands.append(name)
        return commands

    def get_command(self, ctx: click.Context, cmd_name: str) -> _TyperCommand | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command

        lazy_spec = self.lazy_subcommands.get(cmd_name)
        if lazy_spec is None:
            return None

        module_name, attribute_name, _ = lazy_spec
        command = get_command(getattr(import_module(module_name), attribute_name))
        command.name = cmd_name
        self.commands[cmd_name] = command
        return command

    def format_help(self, ctx: click.Context, formatter: HelpFormatter) -> None:
        if not typer.core.HAS_RICH or self.rich_markup_mode is None:
            return super().format_help(ctx, formatter)

        from typer import rich_utils

        rich_utils_any = cast(Any, rich_utils)
        console = rich_utils_any._get_rich_console()
        console.print(
            rich_utils_any.Padding(
                rich_utils_any.highlighter(self.get_usage(ctx)),
                1,
            ),
            style=rich_utils_any.STYLE_USAGE_COMMAND,
        )

        if self.help:
            console.print(
                rich_utils_any.Padding(
                    rich_utils_any.Align(
                        rich_utils_any._get_help_text(
                            obj=self,
                            markup_mode=self.rich_markup_mode,
                        ),
                        pad=False,
                    ),
                    (0, 1, 1, 1),
                )
            )

        panel_to_arguments: dict[str, list[click.Argument]] = {}
        panel_to_options: dict[str, list[click.Option]] = {}
        for param in self.get_params(ctx):
            if getattr(param, "hidden", False):
                continue
            if isinstance(param, click.Argument):
                panel_name = (
                    getattr(param, rich_utils_any._RICH_HELP_PANEL_NAME, None)
                    or rich_utils_any.ARGUMENTS_PANEL_TITLE
                )
                panel_to_arguments.setdefault(panel_name, []).append(param)
            elif isinstance(param, click.Option):
                panel_name = (
                    getattr(param, rich_utils_any._RICH_HELP_PANEL_NAME, None)
                    or rich_utils_any.OPTIONS_PANEL_TITLE
                )
                panel_to_options.setdefault(panel_name, []).append(param)

        default_arguments = panel_to_arguments.get(rich_utils_any.ARGUMENTS_PANEL_TITLE, [])
        rich_utils_any._print_options_panel(
            name=rich_utils_any.ARGUMENTS_PANEL_TITLE,
            params=default_arguments,
            ctx=ctx,
            markup_mode=self.rich_markup_mode,
            console=console,
        )
        for panel_name, arguments in panel_to_arguments.items():
            if panel_name == rich_utils_any.ARGUMENTS_PANEL_TITLE:
                continue
            rich_utils_any._print_options_panel(
                name=panel_name,
                params=arguments,
                ctx=ctx,
                markup_mode=self.rich_markup_mode,
                console=console,
            )

        default_options = panel_to_options.get(rich_utils_any.OPTIONS_PANEL_TITLE, [])
        rich_utils_any._print_options_panel(
            name=rich_utils_any.OPTIONS_PANEL_TITLE,
            params=default_options,
            ctx=ctx,
            markup_mode=self.rich_markup_mode,
            console=console,
        )
        for panel_name, options in panel_to_options.items():
            if panel_name == rich_utils_any.OPTIONS_PANEL_TITLE:
                continue
            rich_utils_any._print_options_panel(
                name=panel_name,
                params=options,
                ctx=ctx,
                markup_mode=self.rich_markup_mode,
                console=console,
            )

        panel_to_commands: dict[str, list[click.Command]] = {}
        for command_name in self.list_commands(ctx):
            command = self.commands.get(command_name)
            if command is None:
                lazy_spec = self.lazy_subcommands.get(command_name)
                if lazy_spec is None:
                    continue
                command = click.Command(command_name, help=lazy_spec[2])
            if command.hidden:
                continue
            panel_name = (
                getattr(command, rich_utils_any._RICH_HELP_PANEL_NAME, None)
                or rich_utils_any.COMMANDS_PANEL_TITLE
            )
            panel_to_commands.setdefault(panel_name, []).append(command)

        max_cmd_len = max(
            (
                len(command.name or "")
                for commands in panel_to_commands.values()
                for command in commands
            ),
            default=0,
        )
        default_commands = panel_to_commands.get(rich_utils_any.COMMANDS_PANEL_TITLE, [])
        rich_utils_any._print_commands_panel(
            name=rich_utils_any.COMMANDS_PANEL_TITLE,
            commands=default_commands,
            markup_mode=self.rich_markup_mode,
            console=console,
            cmd_len=max_cmd_len,
        )
        for panel_name, commands in panel_to_commands.items():
            if panel_name == rich_utils_any.COMMANDS_PANEL_TITLE:
                continue
            rich_utils_any._print_commands_panel(
                name=panel_name,
                commands=commands,
                markup_mode=self.rich_markup_mode,
                console=console,
                cmd_len=max_cmd_len,
            )

        if self.epilog:
            lines = self.epilog.split("\n\n")
            epilogue = "\n".join(x.replace("\n", " ").strip() for x in lines)
            epilogue_text = rich_utils_any._make_rich_text(
                text=epilogue,
                markup_mode=self.rich_markup_mode,
            )
            console.print(rich_utils_any.Padding(rich_utils_any.Align(epilogue_text, pad=False), 1))

    def format_commands(self, ctx: click.Context, formatter: HelpFormatter) -> None:
        entries: list[tuple[str, str | None]] = []
        for subcommand in self.list_commands(ctx):
            command = self.commands.get(subcommand)
            if command is not None:
                if command.hidden:
                    continue
                entries.append((subcommand, None))
                continue

            lazy_spec = self.lazy_subcommands.get(subcommand)
            if lazy_spec is None:
                continue
            entries.append((subcommand, lazy_spec[2]))

        if not entries:
            return

        limit = formatter.width - 6 - max(len(name) for name, _ in entries)
        rows: list[tuple[str, str]] = []
        for subcommand, short_help in entries:
            command = self.commands.get(subcommand)
            if command is not None:
                rows.append((subcommand, command.get_short_help_str(limit)))
                continue
            rows.append((subcommand, short_help or ""))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)
