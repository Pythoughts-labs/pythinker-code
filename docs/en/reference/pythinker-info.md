# `pythinker info` Subcommand

`pythinker info` displays version and protocol information for Pythinker Code.

```sh
pythinker info [--json]
```

## Options

| Option | Description |
|--------|-------------|
| `--json` | Output in JSON format |

## Output

| Field | Description |
|-------|-------------|
| `pythinker_code_version` | Pythinker Code version number |
| `organization` | Developing organization |
| `agent_spec_versions` | List of supported agent spec versions |
| `wire_protocol_version` | Wire protocol version |
| `python_version` | Python runtime version |

## Examples

**Text output**

```sh
$ pythinker info
pythinker-code version: 1.20.0
developed by: Pythoughts-labs
agent spec versions: 1
wire protocol: 1.9
python version: 3.13.1
```

**JSON output**

```sh
$ pythinker info --json
{"pythinker_code_version": "1.20.0", "organization": "Pythoughts-labs", "agent_spec_versions": ["1"], "wire_protocol_version": "1.9", "python_version": "3.13.1"}
```
