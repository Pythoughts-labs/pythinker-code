# `pythinker term` Subcommand

The `pythinker term` command launches the [Toad](https://github.com/batrachianai/toad) terminal UI, a modern terminal interface built with [Textual](https://textual.textualize.io/).

```sh
pythinker term [OPTIONS]
```

## Description

[Toad](https://github.com/batrachianai/toad) is a graphical terminal interface for Pythinker Code that communicates with the Pythinker Code backend via the ACP protocol. It provides a richer interactive experience with better output rendering and layout.

When you run `pythinker term`, it automatically starts a `pythinker acp` server in the background, and Toad connects to it as an ACP client.

## Options

`pythinker term` reads the working directory from extra arguments and opens Toad there. For example:

```sh
pythinker term --work-dir /path/to/project
```

| Option | Short | Description |
|--------|-------|-------------|
| `--work-dir PATH` | `-w` | Specify working directory (passed to Toad as the project directory) |

Other options are not forwarded to the internal `pythinker acp` server; only the working directory is honored.

## System requirements

::: warning Note
`pythinker term` requires Python 3.14+. If you installed Pythinker Code with an older Python version, you need to reinstall with Python 3.14:

```sh
uv tool install --python 3.14 pythinker-code
```
:::
