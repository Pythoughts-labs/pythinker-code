Write text to the stdin of a running background shell task.

Use this only for commands that are explicitly waiting for input. Provide the task_id from Shell(run_in_background=true), the text to send, and whether to append a newline. This tool is only available to the root agent and only for non-terminal bash background tasks.
