# Getting started

## What is Pythinker Code CLI

Pythinker Code CLI is an AI agent that runs in the terminal, helping you carry out software development tasks and day-to-day terminal operations — reading and modifying code, running shell commands, searching files, fetching web pages, and autonomously planning and adjusting its next steps based on feedback as it works.

It fits scenarios such as:

- **Writing and modifying code**: implementing new features, fixing bugs, completing refactors
- **Understanding a project**: exploring an unfamiliar codebase and answering questions about architecture and implementation
- **Automating tasks**: batch-processing files, running builds and tests, chaining multiple scripts together

The CLI is written in TypeScript, distributed via npm, and runs on Node.js.

## Installation

Two installation options are available: the official install script (recommended, no pre-installed Node.js required) and a global npm install.

Prefer a graphical application over the terminal? See the [Desktop App guide](./desktop.md) for the
macOS and Windows desktop application.

To use the local browser UI, see [Use Pythinker Code in a browser](./web.md).

::: tip Before you install
Pythinker Code CLI is a fully interactive TUI application. For the best visual experience, run it in a terminal with true-color and ligature support, such as [Kitty](https://sw.kovidgoyal.net/kitty/) or [Ghostty](https://ghostty.org/).
:::

### Install script (recommended)

- **macOS / Linux**:

```sh
curl -fsSL https://code.pythinker.com/pythinker-code/install.sh | bash
```

- **Windows (PowerShell)**:

```powershell
irm https://code.pythinker.com/pythinker-code/install.ps1 | iex
```

> On Windows, install [Git for Windows](https://gitforwindows.org/) before first launch. Pythinker Code CLI uses the bundled Git Bash as its shell environment; if Git Bash is installed in a custom location, set `PYTHINKER_SHELL_PATH` to the absolute path of `bash.exe`.

The script automatically downloads the latest release, verifies the checksum, and places the `pythinker` executable on your `PATH`.

### npm installation

Requires Node.js 22.19.0 or later:

```sh
node --version
npm install -g @pymodel/pythinker-code
```

Or with pnpm:

```sh
pnpm add -g @pymodel/pythinker-code
```

## Upgrade and uninstall

After installation, verify that the executable is ready:

```sh
pythinker --version
```

**Upgrade**: automatic updates are enabled by default. npm, pnpm, yarn, bun, and supported native installations update in the background. Homebrew installations download and verify the formula source in the background, then install it on the next interactive launch and restart into the new version. Run `pythinker upgrade` to check immediately. For npm, pnpm, yarn, bun, and macOS / Linux native installations it offers to install the update right away; for Homebrew and Windows native installations it prints the command to run. You can also upgrade directly via the package manager:

```sh
npm install -g @pymodel/pythinker-code@latest
```

**Uninstall**: if you installed via the script, delete the `pythinker` executable. If you installed via npm:

```sh
npm uninstall -g @pymodel/pythinker-code
```

## First launch

Move into your project directory and run `pythinker` to start the interactive UI:

```sh
cd your-project
pythinker
```

To run a single instruction without entering the interactive UI, use `-p`:

```sh
pythinker -p "Take a look at this project's directory structure"
```

To resume the previous session, add `-c`:

```sh
pythinker -c
```

On first launch you need to configure an API source. In the interactive UI, enter `/login` to begin the login flow:

```
/login
```

`/login` opens a platform selector supporting two options:

- **Pythinker Code (OAuth)** — device-code flow; open the link on any device, sign in, and enter the code to authorize
- **Pythinker Platform API key** — enter an API key from `pythinker.com/platform`

To sign out, enter `/logout` to clear the current credentials.

::: tip Using other AI providers
If you want to connect Anthropic, OpenAI, Google, or other providers, edit `~/.pythinker-code/config.toml` directly to configure the API key. See [Providers and models](../configuration/providers.md) for details. For the full reference of all config options, see [Configuration files](../configuration/config-files.md), [Environment variables](../configuration/env-vars.md), and [Configuration overrides](../configuration/overrides.md).
:::

## Your first conversation

Once logged in, describe a task in natural language. A good starting point is to let Pythinker Code CLI familiarize itself with the project:

```
Take a look at this project's directory structure and briefly describe what each directory is for.
```

Pythinker Code CLI automatically calls file-reading, search, and other tools to browse the relevant content before responding. Read-only operations are executed automatically by default without requiring confirmation. For operations that modify files or run shell commands, it asks for your confirmation before proceeding.

You can also describe a more concrete task directly:

```
Add a function in src/utils that converts any string to kebab-case, and add a unit test for it.
```

Pythinker Code CLI plans the steps, modifies the code, runs the tests, and tells you what it did at each step.

::: tip Not sure what to do? Type `/help`
Type `/help` at any time to open the built-in command and keyboard shortcut panel. Use `↑`/`↓` to browse and `Esc` to close. To exit, type `/exit`, press `Ctrl-C` twice, or press `Ctrl-D` with the input box empty.
:::

## Common commands and keyboard shortcuts

For a first-time user, the following is all you need to know:

**Session commands**

| Command | Description |
| --- | --- |
| `/new` | Start a new session, clearing the current context |
| `/sessions` | Browse session history and choose one to resume |
| `/model` | Switch the current model |
| `/compact` | Manually compress the context to free up tokens |
| `/fork` | Fork the current session into an independent copy with full history (you stay in the current session) |

**Most-used keyboard shortcuts**

| Shortcut | Description |
| --- | --- |
| `Esc` | Interrupt streaming output / close a popup |
| `Ctrl-C` | Interrupt output; press twice while idle to exit |
| `Shift-Tab` | Cycle thinking effort for the current model |
| `Ctrl-S` | Inject a message mid-stream without waiting for the current response to finish |
| `Ctrl-O` | Collapse / expand tool output and compaction summaries |

For the full list, type `/help` or visit [Slash commands reference](../reference/slash-commands.md) and [Keyboard shortcuts](../reference/keyboard.md).

## Where data is stored

Pythinker Code CLI stores its local data under `~/.pythinker-code/` by default — config files, session records, logs, and the update cache. To move it elsewhere, point to a new path via the `PYTHINKER_CODE_HOME` environment variable. For the full directory layout, see [Data locations](../configuration/data-locations.md) and [Environment variables](../configuration/env-vars.md).

## Next steps

- [Interaction and input](./interaction.md) — input box operations, approval flow, Plan mode, and Ask When Needed mode explained
- [Use in a browser](./web.md) — browser sessions and local-server safety
- [Sessions and context](./sessions.md) — resuming sessions, compressing context, exporting sessions
- [Common use cases](./use-cases.md) — prompt examples for typical tasks
