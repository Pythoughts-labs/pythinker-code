# @pymodel/pythinker-desktop

## 0.10.1

### Patch Changes

- [#295](https://github.com/PyModel/pythinker-code/pull/295) [`481db17`](https://github.com/PyModel/pythinker-code/commit/481db1722fffb27648d73b832098a71f6c67739b) Thanks [@elkaix](https://github.com/elkaix)! - Enable automatic updates by default for native CLI installations.

## 0.10.0

### Minor Changes

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Add OAuth sign-in for Kimi For Coding and MiniMax (global and China) to the login flow.

### Patch Changes

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Keep the stored refresh token when a provider refresh response omits a replacement.

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Stop blocking dangerous Bash commands in Never Ask mode.

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Prevent concurrent sessions from overwriting each other's refreshed sign-in tokens.

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Bound OAuth refresh requests with a timeout and reject tokens that arrive after expiry.

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Send OpenCode Go requests with a per-conversation session header.

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Rename the permission modes to Always Ask, Ask When Needed, and Never Ask, and open the mode list for /yolo and /auto.

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Default the workspace trust prompt to Trust this folder and require Enter to confirm.

- [#291](https://github.com/PyModel/pythinker-code/pull/291) [`54ac427`](https://github.com/PyModel/pythinker-code/commit/54ac427c3798840cf8165ff98eb39d558c37dca4) Thanks [@elkaix](https://github.com/elkaix)! - Fix OpenAI Codex sign-in on Windows and show the complete sign-in link when automatic login fails.

## 0.9.3

### Patch Changes

- [#290](https://github.com/PyModel/pythinker-code/pull/290) [`7acd42a`](https://github.com/PyModel/pythinker-code/commit/7acd42a5839c5f70e65a9ad4127673dddd7ec8e8) Thanks [@elkaix](https://github.com/elkaix)! - Write files atomically so an interrupted write leaves the previous content intact.

- [#290](https://github.com/PyModel/pythinker-code/pull/290) [`7acd42a`](https://github.com/PyModel/pythinker-code/commit/7acd42a5839c5f70e65a9ad4127673dddd7ec8e8) Thanks [@elkaix](https://github.com/elkaix)! - Allow cancelling a prompt while it is still starting.

- [#290](https://github.com/PyModel/pythinker-code/pull/290) [`7acd42a`](https://github.com/PyModel/pythinker-code/commit/7acd42a5839c5f70e65a9ad4127673dddd7ec8e8) Thanks [@elkaix](https://github.com/elkaix)! - Fix DSML and Hermes tool calls in streamed responses being dropped, split, or mistaken for quoted documentation depending on how the response was chunked.

- [#288](https://github.com/PyModel/pythinker-code/pull/288) [`b12dfa1`](https://github.com/PyModel/pythinker-code/commit/b12dfa14c5c22669f467ae563e39d53c61686c72) Thanks [@elkaix](https://github.com/elkaix)! - Fix unparsed DSML tool call markup leaked into model text responses.

- [#290](https://github.com/PyModel/pythinker-code/pull/290) [`7acd42a`](https://github.com/PyModel/pythinker-code/commit/7acd42a5839c5f70e65a9ad4127673dddd7ec8e8) Thanks [@elkaix](https://github.com/elkaix)! - Block file reads and writes that reach a sensitive file through a symlink alias.

- [#290](https://github.com/PyModel/pythinker-code/pull/290) [`7acd42a`](https://github.com/PyModel/pythinker-code/commit/7acd42a5839c5f70e65a9ad4127673dddd7ec8e8) Thanks [@elkaix](https://github.com/elkaix)! - Report each subagent run's own token usage instead of the agent's lifetime total.

- [#290](https://github.com/PyModel/pythinker-code/pull/290) [`7acd42a`](https://github.com/PyModel/pythinker-code/commit/7acd42a5839c5f70e65a9ad4127673dddd7ec8e8) Thanks [@elkaix](https://github.com/elkaix)! - Keep a cancelled tool that ignores the stop signal from overlapping with the next tool on the same file.

- [#290](https://github.com/PyModel/pythinker-code/pull/290) [`7acd42a`](https://github.com/PyModel/pythinker-code/commit/7acd42a5839c5f70e65a9ad4127673dddd7ec8e8) Thanks [@elkaix](https://github.com/elkaix)! - Stop downloading a web page as soon as it exceeds the size limit instead of buffering it first.

## 0.9.2

### Patch Changes

- [#286](https://github.com/PyModel/pythinker-code/pull/286) [`08b2be6`](https://github.com/PyModel/pythinker-code/commit/08b2be61427245bfb8c078fd73a1da68c14f13d2) Thanks [@elkaix](https://github.com/elkaix)! - Fix deleting a provider in the web and desktop settings: the provider and its models now disappear from the model picker, a failed delete shows an error, and a background catalog refresh no longer brings a deleted provider back.

- [#285](https://github.com/PyModel/pythinker-code/pull/285) [`3b6d4d0`](https://github.com/PyModel/pythinker-code/commit/3b6d4d0dc424b550381c2926ee6c5b30bb1b1797) Thanks [@elkaix](https://github.com/elkaix)! - Restore `pythinker update` and `pythinker upgrade`: version checks read code.pythinker.com again and native installs download the release archive from GitHub.

## 0.9.1

### Patch Changes

- [#282](https://github.com/PyModel/pythinker-code/pull/282) [`6b15308`](https://github.com/PyModel/pythinker-code/commit/6b1530866e965455b7a565fedca39e793b1e5792) Thanks [@elkaix](https://github.com/elkaix)! - Show the sidebar update icon fully instead of a clipped half circle, and slightly shrink the sidebar logo.

## 0.9.0

### Minor Changes

- [#280](https://github.com/PyModel/pythinker-code/pull/280) [`ecdde9d`](https://github.com/PyModel/pythinker-code/commit/ecdde9d954ed2edc4c30220fd8b623682eb0f69b) Thanks [@elkaix](https://github.com/elkaix)! - Redesign the Providers settings: each provider shows its own config first with models in a collapsible section, and a delete icon sits next to every provider.

### Patch Changes

- [#280](https://github.com/PyModel/pythinker-code/pull/280) [`ecdde9d`](https://github.com/PyModel/pythinker-code/commit/ecdde9d954ed2edc4c30220fd8b623682eb0f69b) Thanks [@elkaix](https://github.com/elkaix)! - Allow the Bash tool to run with a working directory outside the workspace roots.

- [#280](https://github.com/PyModel/pythinker-code/pull/280) [`ecdde9d`](https://github.com/PyModel/pythinker-code/commit/ecdde9d954ed2edc4c30220fd8b623682eb0f69b) Thanks [@elkaix](https://github.com/elkaix)! - Handle heredocs when scanning Bash commands so quoted heredoc content no longer forces extra approval prompts.

- [#280](https://github.com/PyModel/pythinker-code/pull/280) [`ecdde9d`](https://github.com/PyModel/pythinker-code/commit/ecdde9d954ed2edc4c30220fd8b623682eb0f69b) Thanks [@elkaix](https://github.com/elkaix)! - Keep the gateway server running after an unexpected error instead of exiting the process.

- [#280](https://github.com/PyModel/pythinker-code/pull/280) [`ecdde9d`](https://github.com/PyModel/pythinker-code/commit/ecdde9d954ed2edc4c30220fd8b623682eb0f69b) Thanks [@elkaix](https://github.com/elkaix)! - Fetch the current event position with session details so clients resume without replaying past events.

## 0.8.0

### Minor Changes

- [#278](https://github.com/PyModel/pythinker-code/pull/278) [`77c1128`](https://github.com/PyModel/pythinker-code/commit/77c1128564b1a4c117eff8331402d37a4245553e) Thanks [@elkaix](https://github.com/elkaix)! - Add an option to permanently delete a session from the sidebar menu.

## 0.7.0

### Minor Changes

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - The pythinker acp subcommand no longer honors PYTHINKER_CODE_LEGACY_FLAG; it always runs on the default agent engine.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Add the pythinker session list subcommand to list saved sessions. Run pythinker session list --all --json for machine-readable output.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Enter tower mode with /tower <base-branch> to pick the base branch yourself, and see when a tower worker dies in the status view.

### Patch Changes

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Re-remind the model about subdirectory AGENTS.md files after context compaction.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Compact the Discussion exchange: reasoning shows its first two sentences with a Show reasoning toggle, tool calls collapse to one summary line, and the Fusion answer streams as text instead of its raw JSON envelope. Take now loads an answer into the composer to edit, while Build from Fusion sends it as the implementation brief at once.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Fix the transcript not scrolling up after a Discussion finishes, and show "Discussion" on the composer model pill while a Discussion is armed or running.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Forking a session no longer loads the whole session first, so large sessions fork in well under a second.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - An explicit [experimental] entry in config.toml now takes precedence over PYTHINKER_CODE_EXPERIMENTAL_FLAG.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Fix git status parsing for file paths that contain non-ASCII characters.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Fix sessions failing to start when the subagent model pool in config.toml is incomplete.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Shorten the default system prompt.

- [#275](https://github.com/PyModel/pythinker-code/pull/275) [`27393b3`](https://github.com/PyModel/pythinker-code/commit/27393b3a3fdcc0d8ac58f4e8912ee97822365799) Thanks [@elkaix](https://github.com/elkaix)! - Interrupted steps keep their reason after a session is reloaded.

## 0.6.1

### Patch Changes

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Add OpenAI Responses support to the Pythinker provider.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Enable configured secondary-model routing by default.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Place action and stopped notices above the composer.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Add per-role thinking effort controls and preserve saved model pairs in Discussion.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Preserve usable Discussion responses across transient provider and workflow failures.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Align Dynamic Workflow status dots with their subagent row titles.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Keep active and undone turns aligned after session reloads.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Ask before dangerous shell commands in interactive modes and block them in Auto mode.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Preserve comments and formatting when Pythinker updates config.toml.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Preserve staged, unstaged, and untracked workspace changes when Tower agents start and merge work.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Show agreement, differences, and uncertainty in completed Discussion results.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Rename Expert Talk to Discussion and keep `/expert-talk` and `/expert-opinion` as command aliases.

- [#273](https://github.com/PyModel/pythinker-code/pull/273) [`65f31a8`](https://github.com/PyModel/pythinker-code/commit/65f31a8cc59b90d6182a82e07c82098bf7b308fe) Thanks [@elkaix](https://github.com/elkaix)! - Stream live model reasoning in Discussion exchanges.

## 0.6.0

### Minor Changes

- [#265](https://github.com/PyModel/pythinker-code/pull/265) [`8ac20f0`](https://github.com/PyModel/pythinker-code/commit/8ac20f0b34039824770b83b15b825939e717c661) Thanks [@elkaix](https://github.com/elkaix)! - Add experimental Expert Talk for automatic two-model analysis, reciprocal review, and fused answers.

- [#263](https://github.com/PyModel/pythinker-code/pull/263) [`7563f66`](https://github.com/PyModel/pythinker-code/commit/7563f668ac6910a7253d93351e823940091ac07c) Thanks [@elkaix](https://github.com/elkaix)! - Add a sidebar Explorer for browsing and opening workspace files.

### Patch Changes

- [#263](https://github.com/PyModel/pythinker-code/pull/263) [`7563f66`](https://github.com/PyModel/pythinker-code/commit/7563f668ac6910a7253d93351e823940091ac07c) Thanks [@elkaix](https://github.com/elkaix)! - Make `pythinker doctor` validate `config.toml` with the current schema in every engine mode.

- [#261](https://github.com/PyModel/pythinker-code/pull/261) [`e6cb84e`](https://github.com/PyModel/pythinker-code/commit/e6cb84e8855a9722850e59e0469684b8237415fc) Thanks [@elkaix](https://github.com/elkaix)! - Use a stable dot in the tab title while the agent is running.

- [#261](https://github.com/PyModel/pythinker-code/pull/261) [`e6cb84e`](https://github.com/PyModel/pythinker-code/commit/e6cb84e8855a9722850e59e0469684b8237415fc) Thanks [@elkaix](https://github.com/elkaix)! - Keep task output previews responsive for large logs and valid at UTF-8 byte boundaries.

- [#265](https://github.com/PyModel/pythinker-code/pull/265) [`8ac20f0`](https://github.com/PyModel/pythinker-code/commit/8ac20f0b34039824770b83b15b825939e717c661) Thanks [@elkaix](https://github.com/elkaix)! - Update the terminal interface colors, transcript hierarchy, welcome panel, and workflow progress states.

- [#265](https://github.com/PyModel/pythinker-code/pull/265) [`8ac20f0`](https://github.com/PyModel/pythinker-code/commit/8ac20f0b34039824770b83b15b825939e717c661) Thanks [@elkaix](https://github.com/elkaix)! - Use a refreshed New Chat icon across desktop and mobile navigation.

## 0.5.0

### Minor Changes

- [#250](https://github.com/PyModel/pythinker-code/pull/250) [`5a71940`](https://github.com/PyModel/pythinker-code/commit/5a71940f4ef3265c6f2f050b38644f02e274c5af) Thanks [@elkaix](https://github.com/elkaix)! - Download desktop updates from the sidebar pill with inline progress, move the panel toggle to the header's right edge, and reuse the update icon in Settings.

### Patch Changes

- [#246](https://github.com/PyModel/pythinker-code/pull/246) [`d72066a`](https://github.com/PyModel/pythinker-code/commit/d72066ae562c456e6d511e8ddd3e00da8fe6afae) Thanks [@elkaix](https://github.com/elkaix)! - Align tool-call icons and completion indicators with their labels in web conversations.

- [#250](https://github.com/PyModel/pythinker-code/pull/250) [`5a71940`](https://github.com/PyModel/pythinker-code/commit/5a71940f4ef3265c6f2f050b38644f02e274c5af) Thanks [@elkaix](https://github.com/elkaix)! - Animate tool icons on hover and while the agent works.

- [#246](https://github.com/PyModel/pythinker-code/pull/246) [`d72066a`](https://github.com/PyModel/pythinker-code/commit/d72066ae562c456e6d511e8ddd3e00da8fe6afae) Thanks [@elkaix](https://github.com/elkaix)! - Brand the macOS installer with the Pythinker Code drag-to-Applications layout.

- [#250](https://github.com/PyModel/pythinker-code/pull/250) [`5a71940`](https://github.com/PyModel/pythinker-code/commit/5a71940f4ef3265c6f2f050b38644f02e274c5af) Thanks [@elkaix](https://github.com/elkaix)! - Copy only the assistant's final answer from the web message copy button, not the interim progress lines.

- [#246](https://github.com/PyModel/pythinker-code/pull/246) [`d72066a`](https://github.com/PyModel/pythinker-code/commit/d72066ae562c456e6d511e8ddd3e00da8fe6afae) Thanks [@elkaix](https://github.com/elkaix)! - Fix Dynamic Workflow subagent selection, recovery, and progress reporting during partial failures.

- [#245](https://github.com/PyModel/pythinker-code/pull/245) [`99e728d`](https://github.com/PyModel/pythinker-code/commit/99e728dbbecb366b7b89647e9c7d88a7e43d385b) Thanks [@elkaix](https://github.com/elkaix)! - Reduce interface slowdowns during long conversations with many background tasks and show a static running marker in the browser tab title.

- [#246](https://github.com/PyModel/pythinker-code/pull/246) [`d72066a`](https://github.com/PyModel/pythinker-code/commit/d72066ae562c456e6d511e8ddd3e00da8fe6afae) Thanks [@elkaix](https://github.com/elkaix)! - Fix models and providers briefly disappearing when an external editor saves the configuration.

- [#249](https://github.com/PyModel/pythinker-code/pull/249) [`622dbe9`](https://github.com/PyModel/pythinker-code/commit/622dbe9d0a4104687672380913d92a06bf7d2650) Thanks [@elkaix](https://github.com/elkaix)! - Prevent cron ticks from continuing after an agent shuts down.

- [#246](https://github.com/PyModel/pythinker-code/pull/246) [`d72066a`](https://github.com/PyModel/pythinker-code/commit/d72066ae562c456e6d511e8ddd3e00da8fe6afae) Thanks [@elkaix](https://github.com/elkaix)! - Use the login shell's executable order for tools started by the desktop app.

- [#249](https://github.com/PyModel/pythinker-code/pull/249) [`622dbe9`](https://github.com/PyModel/pythinker-code/commit/622dbe9d0a4104687672380913d92a06bf7d2650) Thanks [@elkaix](https://github.com/elkaix)! - Use the Unicode ellipsis in terminal status and truncation text.

## 0.4.0

### Minor Changes

- [#243](https://github.com/PyModel/pythinker-code/pull/243) [`d389e4d`](https://github.com/PyModel/pythinker-code/commit/d389e4d800902a99a8732ff918f594585ec48242) Thanks [@elkaix](https://github.com/elkaix)! - The desktop app ships the updated web workspace: the Dynamic Workflow card with per-subagent routing details, Subagent Model Routing settings, attachment previews, panel tabs, message folding, and session permission controls.

- [#239](https://github.com/PyModel/pythinker-code/pull/239) [`fdaf83d`](https://github.com/PyModel/pythinker-code/commit/fdaf83d1c19e25acac740054d2226d66db7e8133) Thanks [@elkaix](https://github.com/elkaix)! - The Dynamic Workflow card shows each subagent's profile, model, thinking effort, elapsed time, and routing source, groups rows by phase with failures first, and notes when running subagents were created under an earlier routing.

- [#241](https://github.com/PyModel/pythinker-code/pull/241) [`b891de7`](https://github.com/PyModel/pythinker-code/commit/b891de704e0c484070d61d1b9ffe4b199a1c658b) Thanks [@elkaix](https://github.com/elkaix)! - AgentDynamicWorkflow accepts a `tasks` list where each entry sets its own subagent type, model, and thinking effort. Pass `tasks` instead of `items`, with optional `defaults.subagent_type`.

- [#235](https://github.com/PyModel/pythinker-code/pull/235) [`03d9835`](https://github.com/PyModel/pythinker-code/commit/03d98350ccaa9caae1a286f95870ecb760249e79) Thanks [@elkaix](https://github.com/elkaix)! - The Lab settings show when an experimental flag is controlled by the environment and when the saved setting is overridden.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Attach files from server-local paths in Web prompts.

- [#240](https://github.com/PyModel/pythinker-code/pull/240) [`55d12a2`](https://github.com/PyModel/pythinker-code/commit/55d12a2cde76f2c034666a08378a329dd4c85074) Thanks [@elkaix](https://github.com/elkaix)! - Settings gains a Subagent Model Routing control with Inherit, Default, Pool, and Force modes and shows the saved policy next to the routing that currently applies.

- [#236](https://github.com/PyModel/pythinker-code/pull/236) [`faeb195`](https://github.com/PyModel/pythinker-code/commit/faeb1954b267a1a817926d61ace38db5e55e0738) Thanks [@elkaix](https://github.com/elkaix)! - Add a subagent model policy setting with inherit, default, pool, and force modes that rejects models that are not configured.

- [#237](https://github.com/PyModel/pythinker-code/pull/237) [`a60a427`](https://github.com/PyModel/pythinker-code/commit/a60a427f447a3ff36e0af59a5b7bba2344f1a7ef) Thanks [@elkaix](https://github.com/elkaix)! - Subagent tasks and Dynamic Workflow results now record the profile, model, and routing source of each subagent, and a resumed subagent keeps the binding it was created with.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Show file, folder, image, and video attachments as compact composer pills with media previews.

- [#238](https://github.com/PyModel/pythinker-code/pull/238) [`7b00f1f`](https://github.com/PyModel/pythinker-code/commit/7b00f1ff2dcc2aa2566eb1af9f4bb016ca8a5b97) Thanks [@elkaix](https://github.com/elkaix)! - Add word-wrap and line-number toggles to every code block and diff block in the web chat.

- [#238](https://github.com/PyModel/pythinker-code/pull/238) [`7b00f1f`](https://github.com/PyModel/pythinker-code/commit/7b00f1ff2dcc2aa2566eb1af9f4bb016ca8a5b97) Thanks [@elkaix](https://github.com/elkaix)! - Add a Message folding settings section that turns off auto-folded turns and the tool call summary row.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Open multiple detail views as tabs in the Web panel.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Add selected conversation or panel text to the composer as quoted context.

- [#238](https://github.com/PyModel/pythinker-code/pull/238) [`7b00f1f`](https://github.com/PyModel/pythinker-code/commit/7b00f1ff2dcc2aa2566eb1af9f4bb016ca8a5b97) Thanks [@elkaix](https://github.com/elkaix)! - Move a running Bash command or foreground subagent to the background from its row in the web chat.

### Patch Changes

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Remind the agent about unfinished background tasks when work continues in a later turn.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Redact service credentials and raw configuration from config API responses.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Accept MCP tool results that contain text content or structured content.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Refresh model authentication readiness after provider configuration changes.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Show the complete remote-control link after startup.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Keep configured secondary model aliases unchanged when provider catalogs refresh.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Warn before sending arguments to a slash command that does not accept them.

- [#234](https://github.com/PyModel/pythinker-code/pull/234) [`8959522`](https://github.com/PyModel/pythinker-code/commit/89595222c4e7fa8984ef597f888769ce7ef665d9) Thanks [@elkaix](https://github.com/elkaix)! - Subagent model settings no longer keep stale force or pool values after a change.

- [#232](https://github.com/PyModel/pythinker-code/pull/232) [`974da73`](https://github.com/PyModel/pythinker-code/commit/974da731db454a1f25e32e00a5b7d54db104c2c2) Thanks [@elkaix](https://github.com/elkaix)! - Keep the file preview close button in the top-right corner at every panel width, remove the unused download action, and stop the running-task indicator from overlapping a collapsed Task row title.

- [#238](https://github.com/PyModel/pythinker-code/pull/238) [`7b00f1f`](https://github.com/PyModel/pythinker-code/commit/7b00f1ff2dcc2aa2566eb1af9f4bb016ca8a5b97) Thanks [@elkaix](https://github.com/elkaix)! - Resize the web panels with the arrow keys, and show the description for a question's free-text answer.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Keep each Web session's permission mode separate when switching sessions.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Show the Web session list after its first workspace-group page loads.

- [#238](https://github.com/PyModel/pythinker-code/pull/238) [`7b00f1f`](https://github.com/PyModel/pythinker-code/commit/7b00f1ff2dcc2aa2566eb1af9f4bb016ca8a5b97) Thanks [@elkaix](https://github.com/elkaix)! - Show a subagent's originating prompt above its transcript, centre the transcript, and add a Back to bottom shortcut.

- [#231](https://github.com/PyModel/pythinker-code/pull/231) [`26cd4ac`](https://github.com/PyModel/pythinker-code/commit/26cd4ac1d07cd9e1ea0edc4b3c1e4ab025f5d2d9) Thanks [@elkaix](https://github.com/elkaix)! - Align the file-type icon with the text in Read and Edit tool rows.

- [#238](https://github.com/PyModel/pythinker-code/pull/238) [`7b00f1f`](https://github.com/PyModel/pythinker-code/commit/7b00f1ff2dcc2aa2566eb1af9f4bb016ca8a5b97) Thanks [@elkaix](https://github.com/elkaix)! - Recover from a crashed view instead of a blank screen, name a cancelled sign-in, keep the composer toolbar readable at very narrow widths, and stop the sidebar settings label from pushing the footer row.

- [#242](https://github.com/PyModel/pythinker-code/pull/242) [`254be65`](https://github.com/PyModel/pythinker-code/commit/254be65b4be89dcf6ca439ee8468d69472623fb7) Thanks [@elkaix](https://github.com/elkaix)! - Resolve renamed workspaces correctly after restarting the server.

## 0.3.9

### Patch Changes

- [#228](https://github.com/PyModel/pythinker-code/pull/228) [`62e2e75`](https://github.com/PyModel/pythinker-code/commit/62e2e7519eba322efef292e0e8e74b13fcdd1274) Thanks [@elkaix](https://github.com/elkaix)! - Lay out the update release notes as a readable list with the build reference as a footnote, and show when there is more to scroll.

- [#226](https://github.com/PyModel/pythinker-code/pull/226) [`e9ebda6`](https://github.com/PyModel/pythinker-code/commit/e9ebda62179656ebdac87a529e903ffaf0cdcdcd) Thanks [@elkaix](https://github.com/elkaix)! - Show the changelog for the new version in the update dialog instead of a build stamp with raw HTML tags.

## 0.3.8

### Patch Changes

- [#225](https://github.com/PyModel/pythinker-code/pull/225) [`f27686a`](https://github.com/PyModel/pythinker-code/commit/f27686ac14eb82b7b2a7773cf936269522479f6c) Thanks [@elkaix](https://github.com/elkaix)! - Install Windows updates in the background instead of opening the installer wizard, and report an update that did not take effect.

## 0.3.1

### Patch Changes

- [#190](https://github.com/PyModel/pythinker-code/pull/190) [`ddf4b88`](https://github.com/PyModel/pythinker-code/commit/ddf4b882e4dd8ea5c5198ebcae8704565708371d) Thanks [@elkaix](https://github.com/elkaix)! - Restore downloadable desktop releases for macOS and Windows.

## 0.3.0

### Minor Changes

- [#185](https://github.com/PyModel/pythinker-code/pull/185) [`283020c`](https://github.com/PyModel/pythinker-code/commit/283020c9138ec1a0fa809b3f4794d6a0e882ebd7) Thanks [@elkaix](https://github.com/elkaix)! - Add signed Beta and Nightly desktop update feeds.

## 0.2.1

### Patch Changes

- [#166](https://github.com/PyModel/pythinker-code/pull/166) [`5560aec`](https://github.com/PyModel/pythinker-code/commit/5560aec41997b522058fc2aeb8af2e29c6d8cc7a) Thanks [@elkaix](https://github.com/elkaix)! - Remove duplicate live activity and keep narrow subagent panel controls visible.

- [#166](https://github.com/PyModel/pythinker-code/pull/166) [`5560aec`](https://github.com/PyModel/pythinker-code/commit/5560aec41997b522058fc2aeb8af2e29c6d8cc7a) Thanks [@elkaix](https://github.com/elkaix)! - Show task outcome cards with subagent model and thinking-effort details in conversations.

## 0.2.0

### Minor Changes

- [#151](https://github.com/PyModel/pythinker-code/pull/151) [`535b2a9`](https://github.com/PyModel/pythinker-code/commit/535b2a94bfc0e614dfeda754da174db9b9a5378e) Thanks [@elkaix](https://github.com/elkaix)! - Say when a new version is found, while it downloads, and when a download fails, instead of only once it is ready to install.

- [#151](https://github.com/PyModel/pythinker-code/pull/151) [`535b2a9`](https://github.com/PyModel/pythinker-code/commit/535b2a94bfc0e614dfeda754da174db9b9a5378e) Thanks [@elkaix](https://github.com/elkaix)! - Give the Windows window its own title bar, so the window controls no longer sit on top of the conversation header and the window can be dragged again.

### Patch Changes

- [#151](https://github.com/PyModel/pythinker-code/pull/151) [`535b2a9`](https://github.com/PyModel/pythinker-code/commit/535b2a94bfc0e614dfeda754da174db9b9a5378e) Thanks [@elkaix](https://github.com/elkaix)! - Remove the "Internal testing only" tag.

## 0.1.6

### Patch Changes

- [#149](https://github.com/PyModel/pythinker-code/pull/149) [`45d1c0a`](https://github.com/PyModel/pythinker-code/commit/45d1c0a49c99cb67c67b4bfa4671d7ef0216865e) Thanks [@elkaix](https://github.com/elkaix)! - Stop a second, unnamed Pythinker icon appearing in the macOS Dock while the app runs.

- [#145](https://github.com/PyModel/pythinker-code/pull/145) [`a0c2705`](https://github.com/PyModel/pythinker-code/commit/a0c2705cf7be9d4d0680aa8f35982a30f7678baa) Thanks [@elkaix](https://github.com/elkaix)! - Stop the desktop app writing its server access token to the log.

## 0.1.3

### Patch Changes

- [#97](https://github.com/PyModel/pythinker-code/pull/97) [`7dd68cb`](https://github.com/PyModel/pythinker-code/commit/7dd68cba572576616dfca1730e79c5e650006508) - Make the workspace header, session timestamps, and the settings row legible in dark mode on the translucent desktop sidebar.

- [#97](https://github.com/PyModel/pythinker-code/pull/97) [`7dd68cb`](https://github.com/PyModel/pythinker-code/commit/7dd68cba572576616dfca1730e79c5e650006508) - Publish desktop releases to a dedicated update channel so update checks resolve a desktop build instead of an unrelated release, and fail the release when a packaged build carries no update feed.

- [#97](https://github.com/PyModel/pythinker-code/pull/97) [`7dd68cb`](https://github.com/PyModel/pythinker-code/commit/7dd68cba572576616dfca1730e79c5e650006508) - Pin the Host port so the desktop app reconnects to its own Host, and stop reporting builds that cannot self-update as update errors.

## 0.1.2

### Patch Changes

- [#82](https://github.com/PyModel/pythinker-code/pull/82) [`1cd8682`](https://github.com/PyModel/pythinker-code/commit/1cd868296da9507cbb28768f71b2611f5ad8a813) - Sign the Windows installer through Azure Artifact Signing when the signing environment is configured

- [#82](https://github.com/PyModel/pythinker-code/pull/82) [`1cd8682`](https://github.com/PyModel/pythinker-code/commit/1cd868296da9507cbb28768f71b2611f5ad8a813) - Render the Windows desktop window opaquely so the theme colours are not blended with the desktop wallpaper

## 0.1.1

### Patch Changes

- [#81](https://github.com/PyModel/pythinker-code/pull/81) [`8717330`](https://github.com/PyModel/pythinker-code/commit/8717330b22049faf1d45be97dfee814b5272a33b) - Bound the Windows process-tree kill so a stalled taskkill cannot freeze desktop shutdown

- [#81](https://github.com/PyModel/pythinker-code/pull/81) [`8717330`](https://github.com/PyModel/pythinker-code/commit/8717330b22049faf1d45be97dfee814b5272a33b) - Fix Windows runtime staging and skip empty signing credentials in the desktop release workflow

- [#81](https://github.com/PyModel/pythinker-code/pull/81) [`8717330`](https://github.com/PyModel/pythinker-code/commit/8717330b22049faf1d45be97dfee814b5272a33b) - Stage the desktop Host closure inside the workspace so pnpm deploy resolves the target on Windows

- [#81](https://github.com/PyModel/pythinker-code/pull/81) [`8717330`](https://github.com/PyModel/pythinker-code/commit/8717330b22049faf1d45be97dfee814b5272a33b) - Add the Windows NSIS installer target, release script, and release workflow job

- [#81](https://github.com/PyModel/pythinker-code/pull/81) [`8717330`](https://github.com/PyModel/pythinker-code/commit/8717330b22049faf1d45be97dfee814b5272a33b) - Fix Windows process-tree shutdown, packaged-runtime guards, and taskbar identity in the desktop app
