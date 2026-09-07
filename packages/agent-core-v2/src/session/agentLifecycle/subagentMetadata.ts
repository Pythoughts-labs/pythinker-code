import type { AgentMeta } from '#/session/sessionMetadata/sessionMetadata';

export function subagentLabels(
  parentAgentId: string,
  options: { readonly dynamicWorkflowItem?: string } = {},
): Readonly<Record<string, string>> {
  const labels: Record<string, string> = { parentAgentId };
  if (options.dynamicWorkflowItem !== undefined) {
    labels['dynamicWorkflowItem'] = options.dynamicWorkflowItem;
  }
  return labels;
}

export function labelsFromAgentMeta(
  meta: AgentMeta,
): Readonly<Record<string, string>> | undefined {
  const labels: Record<string, string> = { ...meta.labels };
  const parentAgentId = subagentParentAgentId(meta);
  if (parentAgentId !== undefined) {
    labels['parentAgentId'] = parentAgentId;
  }
  const dynamicWorkflowItem = subagentDynamicWorkflowItem(meta);
  if (dynamicWorkflowItem !== undefined) {
    labels['dynamicWorkflowItem'] = dynamicWorkflowItem;
  }
  return Object.keys(labels).length > 0 ? labels : undefined;
}

export function withSubagentProfile(
  labels: Readonly<Record<string, string>> | undefined,
  profileName: string | undefined,
): Readonly<Record<string, string>> | undefined {
  if (profileName === undefined || profileName.length === 0) return labels;
  return { ...labels, profileName };
}

export function isSubagentMeta(meta: AgentMeta | undefined): boolean {
  if (meta === undefined) return false;
  if (subagentParentAgentId(meta) !== undefined) return true;
  return meta.type === 'sub';
}

export function subagentParentAgentId(meta: AgentMeta | undefined): string | undefined {
  if (meta === undefined) return undefined;
  return firstNonEmpty(meta.labels?.['parentAgentId'], meta.parentAgentId ?? undefined);
}

export function subagentDynamicWorkflowItem(meta: AgentMeta | undefined): string | undefined {
  if (meta === undefined) return undefined;
  return firstNonEmpty(meta.labels?.['dynamicWorkflowItem'], meta.dynamicWorkflowItem);
}

export function subagentProfileName(meta: AgentMeta | undefined): string | undefined {
  if (meta === undefined) return undefined;
  return firstNonEmpty(meta.labels?.['profileName']);
}

function firstNonEmpty(...values: readonly (string | undefined)[]): string | undefined {
  return values.find((value) => value !== undefined && value.length > 0);
}
