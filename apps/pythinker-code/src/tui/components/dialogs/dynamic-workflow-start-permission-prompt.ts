import {
  StartPermissionPromptComponent,
  type StartPermissionOption,
} from './start-permission-prompt';

export type DynamicWorkflowStartPermissionChoice = 'auto' | 'yolo' | 'manual';

export interface DynamicWorkflowStartPermissionPromptOptions {
  readonly onSelect: (choice: DynamicWorkflowStartPermissionChoice) => void;
  readonly onCancel: () => void;
}

const OPTIONS: readonly StartPermissionOption<DynamicWorkflowStartPermissionChoice>[] = [
  {
    value: 'auto',
    label: 'Switch to Never Ask and start',
    description:
      'Best for dynamic_workflow tasks. Tools are approved automatically, and questions are skipped.',
  },
  {
    value: 'yolo',
    label: 'Switch to Ask When Needed and start',
    description:
      'Tools and plan changes are approved automatically. Pythinker Code may still ask you questions.',
  },
  {
    value: 'manual',
    label: 'Start in Always Ask',
    description:
      'Keep approvals on. Pythinker Code may stop and wait for you during the dynamic_workflow task.',
  },
];

const NOTICE_LINES = [
  'Always Ask mode asks you before Pythinker Code runs commands, edits files, or takes other risky actions.',
  'Always Ask mode can block dynamic_workflow work while agents are running.',
  'You can go back without losing your command.',
] as const;

export class DynamicWorkflowStartPermissionPromptComponent extends StartPermissionPromptComponent<DynamicWorkflowStartPermissionChoice> {
  constructor(opts: DynamicWorkflowStartPermissionPromptOptions) {
    super({
      title: 'Start a dynamic_workflow task with approvals on?',
      noticeLines: NOTICE_LINES,
      options: OPTIONS,
      onSelect: opts.onSelect,
      onCancel: opts.onCancel,
    });
  }
}
