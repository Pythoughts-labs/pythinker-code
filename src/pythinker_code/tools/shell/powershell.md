Execute a ${SHELL} command. Use this tool to explore the filesystem, inspect or edit files, run Windows scripts, collect system information, etc., whenever the agent is running on Windows.

Note that you are running on Windows, so make sure to use Windows commands, paths, and conventions.

**Output:**
The stdout and stderr streams are combined and returned as a single string. Extremely long output may be truncated. When a command fails, the exit code is provided in a system tag.

If `run_in_background=true`, the command will be started as a background task and this tool will return a task ID instead of waiting for completion. When doing that, provide a short `description`; if omitted, a generic description is used. You will be automatically notified when the task completes. Use `TaskOutput` for a non-blocking status/output snapshot, and only set `block=true` when you explicitly want to wait for completion. Use `TaskStop` only if the task must be cancelled. For human users in the interactive shell, background tasks are managed through `/task` only; do not suggest `/task list`, `/task output`, `/task stop`, `/tasks`, or any other invented shell subcommands.

**Guidelines for safety and security:**
- Every tool call starts a fresh ${SHELL} session. Environment variables, `cd` changes, and command history do not persist between calls.
- Foreground commands must finish promptly and use `timeout <= 300`. For long-running builds, scans, test suites, watchers, or servers, set `run_in_background=true`, provide a concise `description`, and use a longer `timeout` up to 86400 seconds. If you accidentally request `timeout > 300` without `run_in_background`, the tool will automatically start it as a background task instead of failing validation.
- Avoid using `..` to leave the working directory, and never touch files outside that directory unless explicitly instructed.
- Never attempt commands that require elevated (Administrator) privileges unless explicitly authorized.

**Guidelines for efficiency:**
- Chain related commands with `;` and use `if ($?)` or `if (-not $?)` to conditionally execute commands based on the success or failure of previous ones.
- Redirect or pipe output with `>`, `>>`, `|`, and leverage `for /f`, `if`, and `set` to build richer one-liners instead of multiple tool calls.
- Reuse built-in utilities (e.g., `findstr`, `where`) to filter, transform, or locate data in a single invocation.
- Prefer `run_in_background=true` for long-running builds, scans, tests, watchers, or servers when you need the conversation to continue before the command finishes or when the command needs more than 300 seconds.
- After starting a background task, do not guess its outcome. Rely on the automatic completion notification whenever possible. Use `TaskOutput` for non-blocking progress snapshots by default, and set `block=true` only when you intentionally want to wait.
- If you need to tell a human shell user how to manage background tasks, only mention `/task`. Do not invent `/task list`, `/task output`, `/task stop`, or `/tasks`.

**Commands available:**
- Shell environment: `cd`, `dir`, `set`, `setlocal`, `echo`, `call`, `where`
- File operations: `type`, `copy`, `move`, `del`, `erase`, `mkdir`, `rmdir`, `attrib`, `mklink`
- Text/search: `find`, `findstr`, `more`, `sort`, `Get-Content`
- System info: `ver`, `systeminfo`, `tasklist`, `wmic`, `hostname`
- Archives/scripts: `tar`, `Compress-Archive`, `powershell`, `python`, `node`
- Other: Any other binaries available on the system PATH; run `where <command>` first if unsure.
