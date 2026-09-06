import type { PermissionMode } from '@pymodel/pythinker-code-sdk';

import {
  DynamicWorkflowStartPermissionPromptComponent,
  type DynamicWorkflowStartPermissionChoice,
} from '../components/dialogs/dynamic-workflow-start-permission-prompt';
import {
  DynamicWorkflowModeMarkerComponent,
  type DynamicWorkflowModeMarkerState,
} from '../components/messages/dynamic-workflow-markers';
import { LLM_NOT_SET_MESSAGE, NO_ACTIVE_SESSION_MESSAGE } from '../constant/pythinker-tui';
import { formatErrorMessage } from '../utils/event-payload';
import { PERMISSION_MODE_DESCRIPTIONS, PERMISSION_MODE_DISPLAY_NAMES } from '../utils/permission-mode';
import type { SlashCommandHost } from './dispatch';

export async function handleDynamicWorkflowCommand(host: SlashCommandHost, args: string): Promise<void> {
  if (host.session === undefined) {
    host.showError(NO_ACTIVE_SESSION_MESSAGE);
    return;
  }

  const prompt = args.trim();
  const mode = dynamicWorkflowModeSubcommand(prompt);
  if (mode !== undefined) {
    await applyDynamicWorkflowMode(host, mode, `/dynamic_workflow ${prompt}`);
    return;
  }

  if (prompt.length === 0) {
    await applyDynamicWorkflowMode(host, !host.state.appState.dynamicWorkflowMode, '/dynamic_workflow');
    return;
  }

  if (host.state.appState.model.trim().length === 0) {
    host.showError(LLM_NOT_SET_MESSAGE);
    return;
  }

  if (host.state.appState.permissionMode === 'manual') {
    showDynamicWorkflowStartPermissionPrompt(host, `/dynamic_workflow ${prompt}`, 'DynamicWorkflow task not started.', (choice) =>
      startDynamicWorkflowWithPermission(host, prompt, choice),
    );
    return;
  }

  await startDynamicWorkflowTask(host, prompt);
}

function showDynamicWorkflowStartPermissionPrompt(
  host: SlashCommandHost,
  commandText: string,
  cancelStatus: string,
  onSelect: (choice: DynamicWorkflowStartPermissionChoice) => Promise<void>,
): void {
  const cancelStart = (): void => {
    host.restoreInputText(commandText);
    host.showStatus(cancelStatus);
  };
  host.mountEditorReplacement(
    new DynamicWorkflowStartPermissionPromptComponent({
      onSelect: (choice) => {
        host.restoreEditor();
        void onSelect(choice);
      },
      onCancel: cancelStart,
    }),
  );
}

async function startDynamicWorkflowWithPermission(
  host: SlashCommandHost,
  prompt: string,
  choice: DynamicWorkflowStartPermissionChoice,
): Promise<void> {
  if (choice === 'auto' || choice === 'yolo') {
    if (!(await setPermissionForDynamicWorkflow(host, choice))) return;
  }
  await startDynamicWorkflowTask(host, prompt);
}

async function setPermissionForDynamicWorkflow(host: SlashCommandHost, mode: PermissionMode): Promise<boolean> {
  try {
    await host.requireSession().setPermission(mode);
  } catch (error) {
    host.showError(`Failed to set permission mode: ${formatErrorMessage(error)}`);
    return false;
  }
  host.setAppState({ permissionMode: mode });
  host.showNotice(`Permission mode: ${PERMISSION_MODE_DISPLAY_NAMES[mode]}`);
  host.showStatus(PERMISSION_MODE_DESCRIPTIONS[mode], 'warning');
  return true;
}

async function startDynamicWorkflowTask(host: SlashCommandHost, prompt: string): Promise<void> {
  if (!host.state.appState.dynamicWorkflowMode && !(await setDynamicWorkflowMode(host, true, 'task'))) {
    return;
  }
  renderDynamicWorkflowModeMarker(host, 'active');
  host.sendNormalUserInput(prompt);
}

async function applyDynamicWorkflowMode(
  host: SlashCommandHost,
  enabled: boolean,
  commandText: string,
): Promise<void> {
  if (enabled && host.state.appState.dynamicWorkflowMode) {
    host.showStatus('DynamicWorkflow mode is already on.');
    return;
  }
  if (!enabled && !host.state.appState.dynamicWorkflowMode) {
    host.showStatus('DynamicWorkflow mode is already off.');
    return;
  }
  if (enabled && host.state.appState.permissionMode === 'manual') {
    showDynamicWorkflowStartPermissionPrompt(host, commandText, 'DynamicWorkflow mode not enabled.', async (choice) => {
      if ((choice === 'auto' || choice === 'yolo') && !(await setPermissionForDynamicWorkflow(host, choice))) {
        return;
      }
      if (!(await setDynamicWorkflowMode(host, true, 'manual'))) return;
      renderDynamicWorkflowModeMarker(host, 'active');
    });
    return;
  }
  if (!(await setDynamicWorkflowMode(host, enabled, 'manual'))) return;
  renderDynamicWorkflowModeMarker(host, enabled ? 'active' : 'inactive');
}

async function setDynamicWorkflowMode(
  host: SlashCommandHost,
  enabled: boolean,
  trigger: 'manual' | 'task',
): Promise<boolean> {
  try {
    await host.requireSession().setDynamicWorkflowMode(enabled, trigger);
  } catch (error) {
    host.showError(
      `Failed to ${enabled ? 'enable' : 'disable'} dynamic_workflow mode: ${formatErrorMessage(error)}`,
    );
    return false;
  }
  host.setAppState({ dynamicWorkflowMode: enabled });
  host.state.dynamicWorkflowModeEntry = enabled ? trigger : undefined;
  return true;
}

function dynamicWorkflowModeSubcommand(input: string): boolean | undefined {
  const command = input.toLowerCase();
  if (command === 'on') return true;
  if (command === 'off') return false;
  return undefined;
}

function renderDynamicWorkflowModeMarker(host: SlashCommandHost, state: DynamicWorkflowModeMarkerState): void {
  host.state.transcriptContainer.addChild(
    new DynamicWorkflowModeMarkerComponent(state),
  );
  host.state.ui.requestRender();
}
