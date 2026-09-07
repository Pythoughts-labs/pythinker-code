import { emptyUsage } from '#/kosong/contract/usage';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { IAgentLLMRequesterService } from '#/agent/llmRequester/llmRequester';
import { IAgentProfileService } from '#/agent/profile/profile';
import { IAgentTelemetryContextService } from '#/app/telemetry/agentTelemetryContext';
import type { ModelRecord } from '#/kosong/model/model';
import {
  configServices,
  createTestAgent,
  InMemoryWireRecordPersistence,
  llmGenerateServices,
  modelProviderOptionServices,
  telemetryServices,
  wireRecordPersistenceServices,
  type TestAgentContext,
} from '../../harness';
import { recordingTelemetry, type TelemetryRecord } from '../../app/telemetry/stubs';

type TestPythinkerConfig = ReturnType<Parameters<typeof configServices>[0]>;
type TestProtocolModelConfig = NonNullable<TestPythinkerConfig['models']>[string] &
  Pick<ModelRecord, 'protocol'>;
type GenerateFn = Parameters<typeof llmGenerateServices>[0];

function defaultGenerate(): ReturnType<GenerateFn> {
  throw new Error('generate should not be called');
}

describe('ConfigState model capabilities', () => {
  let ctx: TestAgentContext;
  let profile: IAgentProfileService;
  let requester: IAgentLLMRequesterService;
  let pythinkerConfig: TestPythinkerConfig;
  let generate: GenerateFn;
  let records: TelemetryRecord[];

  beforeEach(() => {
    pythinkerConfig = {
      providers: {},
    };
    generate = defaultGenerate;
    records = [];
    ctx = createTestAgent(
      configServices(() => pythinkerConfig),
      llmGenerateServices((...args) => generate(...args)),
      telemetryServices(recordingTelemetry(records)),
    );
    profile = ctx.get(IAgentProfileService);
    requester = ctx.get(IAgentLLMRequesterService);
  });

  afterEach(async () => {
    try {
      await ctx.expectResumeMatches();
    } finally {
      await ctx.dispose();
    }
  });

  it('computes provider and model capabilities from config metadata', () => {
    pythinkerConfig = {
      providers: {
        pythinker: {
          type: 'pythinker',
          apiKey: 'test-key',
          baseUrl: 'https://api.example.test/v1',
        },
      },
      models: {
        'example/test-model': {
          provider: 'pythinker',
          model: 'kimi-for-coding',
          maxContextSize: 1_000_000,
          supportEfforts: ['low', 'high'],
          capabilities: ['image_in', 'video_in', 'thinking', 'tool_use'],
        },
      },
    };

    profile.update({ modelAlias: 'example/test-model' });

    expect(profile.getModel()).toBe('example/test-model');
    expect(ctx.modelResolver.get('example/test-model').name).toBe('kimi-for-coding');
    expect(profile.getModelCapabilities()).toMatchObject({
      image_in: true,
      video_in: true,
      audio_in: false,
      thinking: true,
      tool_use: true,
      max_context_tokens: 1_000_000,
    });
  });

  it('republishes the model status slice on demand', () => {
    pythinkerConfig = {
      providers: {
        pythinker: {
          type: 'pythinker',
          apiKey: 'test-key',
          baseUrl: 'https://api.example.test/v1',
        },
      },
      models: {
        'example/test-model': {
          provider: 'pythinker',
          model: 'kimi-for-coding',
          maxContextSize: 1_000_000,
          supportEfforts: ['low', 'high'],
        },
      },
    };
    profile.update({ modelAlias: 'example/test-model' });
    const before = ctx.allEvents.filter((entry) => entry.event === 'agent.status.updated').length;

    profile.republishStatus();

    const statuses = ctx.allEvents.filter((entry) => entry.event === 'agent.status.updated');
    expect(statuses).toHaveLength(before + 1);
    expect(statuses.at(-1)?.args).toMatchObject({
      model: 'example/test-model',
      maxContextTokens: 1_000_000,
    });
  });

  it('omits maxContextTokens when the bound model no longer resolves', () => {
    profile.update({ modelAlias: 'ghost/model' });

    const statuses = ctx.allEvents.filter((entry) => entry.event === 'agent.status.updated');
    expect(statuses.length).toBeGreaterThan(0);
    const last = statuses.at(-1)?.args as { model?: string; maxContextTokens?: number };
    expect(last.model).toBe('ghost/model');
    expect(last.maxContextTokens).toBeUndefined();
  });

  it('tracks thinking_toggle with the effort payload when effort changes', () => {
    pythinkerConfig = {
      providers: {
        pythinker: {
          type: 'pythinker',
          apiKey: 'test-key',
          baseUrl: 'https://api.example.test/v1',
        },
      },
      models: {
        'example/test-model': {
          provider: 'pythinker',
          model: 'kimi-for-coding',
          maxContextSize: 1_000_000,
          capabilities: ['thinking'],
          supportEfforts: ['low', 'high'],
        },
      },
    };
    profile.update({ modelAlias: 'example/test-model' });
    profile.setThinking('off');
    records.length = 0;

    profile.setThinking('low');

    expect(records).toContainEqual({
      event: 'thinking_toggle',
      properties: { agent_id: 'main', enabled: true, effort: 'low', from: 'off' },
    });
  });

  it('writes the bound model into the ambient telemetry context', () => {
    pythinkerConfig = {
      providers: {
        pythinker: {
          type: 'pythinker',
          apiKey: 'test-key',
          baseUrl: 'https://api.example.test/v1',
        },
      },
      models: {
        'example/test-model': {
          provider: 'pythinker',
          model: 'kimi-for-coding',
          maxContextSize: 1_000_000,
        },
      },
    };

    profile.update({ modelAlias: 'example/test-model' });

    expect(ctx.get(IAgentTelemetryContextService).get()).toMatchObject({
      model: 'example/test-model',
      provider_type: 'pythinker',
      protocol: 'openai',
    });
  });

  it('keeps the alias as ambient model when the bound model does not resolve', () => {
    profile.update({ modelAlias: 'ghost/model' });

    expect(ctx.get(IAgentTelemetryContextService).get()).toMatchObject({
      model: 'ghost/model',
    });
  });

  it('restores the ambient model after a cold resume', async () => {
    pythinkerConfig = {
      providers: {
        pythinker: {
          type: 'pythinker',
          apiKey: 'test-key',
          baseUrl: 'https://api.example.test/v1',
        },
      },
      models: {
        'example/test-model': {
          provider: 'pythinker',
          model: 'kimi-for-coding',
          maxContextSize: 1_000_000,
        },
      },
    };
    const resumedRecords: TelemetryRecord[] = [];
    const resumed = createTestAgent(
      { autoConfigure: false },
      configServices(() => pythinkerConfig),
      llmGenerateServices((...args) => generate(...args)),
      telemetryServices(recordingTelemetry(resumedRecords)),
      wireRecordPersistenceServices(
        new InMemoryWireRecordPersistence([
          { type: 'config.update', agentId: 'main', modelAlias: 'example/test-model' },
        ]),
      ),
    );
    try {
      await resumed.restorePersisted();

      expect(resumed.get(IAgentTelemetryContextService).get()).toMatchObject({
        model: 'example/test-model',
        provider_type: 'pythinker',
        protocol: 'openai',
      });
    } finally {
      await resumed.dispose();
    }
  });

  it('does not infer Pythinker capabilities from the provider catalogue', () => {
    pythinkerConfig = {
      providers: {
        pythinker: {
          type: 'pythinker',
          apiKey: 'test-key',
          baseUrl: 'https://api.example.test/v1',
        },
      },
      models: {
        'pythinker-code': {
          provider: 'pythinker',
          model: 'pythinker-code',
          maxContextSize: 128_000,
        },
      },
    };

    profile.update({ modelAlias: 'pythinker-code' });

    expect(profile.getModelCapabilities()).toMatchObject({
      image_in: false,
      video_in: false,
      audio_in: false,
      max_context_tokens: 128_000,
    });
  });

  it('uses model max output size as the LLM completion cap', async () => {
    let requestMaxTokens: unknown;
    pythinkerConfig = {
      providers: {
        deepseek: {
          type: 'openai',
          apiKey: 'test-key',
          baseUrl: 'https://api.deepseek.example/v1',
        },
      },
      models: {
        'deepseek/deepseek-v4-flash': {
          provider: 'deepseek',
          model: 'deepseek-v4-flash',
          maxContextSize: 1_000_000,
          maxOutputSize: 384_000,
        },
      },
    };
    generate = async (_provider, _systemPrompt, _tools, _history, _callbacks, options) => {
      requestMaxTokens = options?.maxCompletionTokens;
      return {
        id: 'response-1',
        message: { role: 'assistant', content: [], toolCalls: [] },
        usage: emptyUsage(),
        finishReason: 'completed',
        rawFinishReason: 'stop',
      };
    };

    profile.update({
      modelAlias: 'deepseek/deepseek-v4-flash',
      systemPrompt: 'system',
      thinkingLevel: 'off',
    });
    await requester.request({}, undefined, new AbortController().signal);

    expect(requestMaxTokens).toBe(384000);
  });
});

describe('ConfigState prompt cache hint', () => {
  let ctx: TestAgentContext;
  let profile: IAgentProfileService;
  let pythinkerConfig: TestPythinkerConfig;

  beforeEach(() => {
    pythinkerConfig = {
      providers: {
        pythinker: {
          type: 'pythinker',
          apiKey: 'test-key',
          baseUrl: 'https://api.example.test/v1',
        },
      },
      models: {
        'pythinker-code': {
          provider: 'pythinker',
          model: 'pythinker-code',
          maxContextSize: 128_000,
        },
      },
    };
    ctx = createTestAgent(
      configServices(() => pythinkerConfig),
      modelProviderOptionServices({ promptCacheKey: 'session-test' }),
    );
    profile = ctx.get(IAgentProfileService);
  });

  afterEach(async () => {
    try {
      await ctx.expectResumeMatches();
    } finally {
      await ctx.dispose();
    }
  });

  it('uses session id as a provider prompt cache hint without storing it on Agent', () => {
    profile.update({ modelAlias: 'pythinker-code' });

    const model = ctx.modelResolver.get('pythinker-code');
    expect(model.protocol).toBe('openai');
    expect(model.providerType).toBe('pythinker');
    expect('sessionId' in ctx).toBe(false);
  });
});

describe('ConfigState thinking clamp for always-thinking models', () => {
  let ctx: TestAgentContext;
  let profile: IAgentProfileService;
  let requester: IAgentLLMRequesterService;
  let pythinkerConfig: TestPythinkerConfig;
  let capturedThinking: unknown;

  beforeEach(() => {
    pythinkerConfig = {
      providers: { pythinker: { type: 'pythinker', apiKey: 'test-key', baseUrl: 'https://api.example.test/v1' } },
      models: {
        'pythinker-code/deep': {
          provider: 'pythinker',
          model: 'pythinker-deep-coder',
          maxContextSize: 128_000,
          capabilities: ['thinking', 'always_thinking', 'tool_use'],
          supportEfforts: ['low', 'high', 'max'],
        },
        'pythinker-code/toggle': {
          provider: 'pythinker',
          model: 'kimi-for-coding',
          maxContextSize: 128_000,
          capabilities: ['thinking'],
        },
        'pythinker-code/custom': {
          provider: 'pythinker',
          model: 'pythinker-custom-coder',
          maxContextSize: 128_000,
          capabilities: ['thinking'],
          supportEfforts: ['low', 'medium', 'max'],
          defaultEffort: 'max',
        },
        'pythinker-code/ultra': {
          provider: 'pythinker',
          model: 'pythinker-ultra',
          maxContextSize: 128_000,
          capabilities: ['thinking'],
          supportEfforts: ['low', 'high', 'ultra'],
          defaultEffort: 'ultra',
        },
        'pythinker-code/compatible': {
          provider: 'pythinker',
          protocol: 'anthropic',
          model: 'compatible-model',
          maxContextSize: 128_000,
          capabilities: ['thinking', 'always_thinking'],
          supportEfforts: ['max'],
          defaultEffort: 'max',
        } as TestProtocolModelConfig,
      },
    };
    capturedThinking = undefined;
    ctx = createTestAgent(
      configServices(() => pythinkerConfig),
      llmGenerateServices(async (_provider, _systemPrompt, _tools, _history, _callbacks, options) => {
        capturedThinking = options?.thinking;
        return {
          id: 'response-1',
          message: { role: 'assistant', content: [], toolCalls: [] },
          usage: emptyUsage(),
          finishReason: 'completed',
          rawFinishReason: 'stop',
        };
      }),
    );
    profile = ctx.get(IAgentProfileService);
    requester = ctx.get(IAgentLLMRequesterService);
  });

  afterEach(async () => {
    try {
      await ctx.expectResumeMatches();
    } finally {
      await ctx.dispose();
    }
  });

  it('clamps thinkingLevel off to the configured effort', () => {
    profile.update({ modelAlias: 'pythinker-code/deep', thinkingLevel: 'off' });

    expect(profile.data().thinkingLevel).toBe('high');
  });

  it('sends the clamped thinking effort in the per-turn intent after thinking was set off', async () => {
    profile.update({ modelAlias: 'pythinker-code/deep', thinkingLevel: 'off' });

    await requester.request({}, undefined, new AbortController().signal);

    expect(capturedThinking).toMatchObject({ effort: 'high' });
  });

  it('keeps thinking off working for toggleable models', () => {
    profile.update({ modelAlias: 'pythinker-code/toggle', thinkingLevel: 'off' });

    expect(profile.data().thinkingLevel).toBe('off');
  });

  it('resolves an explicit on request to the model default effort', () => {
    profile.update({ modelAlias: 'pythinker-code/custom', thinkingLevel: 'on' });

    expect(profile.data().thinkingLevel).toBe('max');
  });

  it('re-clamps when switching to an always-on model after thinking was off', () => {
    profile.update({ modelAlias: 'pythinker-code/toggle', thinkingLevel: 'off' });
    expect(profile.data().thinkingLevel).toBe('off');

    profile.update({ modelAlias: 'pythinker-code/deep' });
    expect(profile.data().thinkingLevel).toBe('high');
  });

  it('falls back to the target default when a model switch carries an unsupported effort', () => {
    profile.update({ modelAlias: 'pythinker-code/ultra', thinkingLevel: 'ultra' });

    profile.update({ modelAlias: 'pythinker-code/custom' });

    expect(profile.data().thinkingLevel).toBe('max');
  });

  it('projects an inherited concrete effort to on when switching to a boolean model', () => {
    profile.update({ modelAlias: 'pythinker-code/ultra', thinkingLevel: 'ultra' });

    profile.update({ modelAlias: 'pythinker-code/toggle' });

    expect(profile.data().thinkingLevel).toBe('on');
  });

  it('rejects an unsupported effort explicitly set on the current Pythinker model', () => {
    profile.update({ modelAlias: 'pythinker-code/custom' });

    expect(() => {
      profile.setThinking('ultra');
    }).toThrow(
      'Thinking effort "ultra" is not supported by model "pythinker-code/custom"',
    );
  });

  it.each([
    [' HIGH ', 'high'],
    ['OFF', 'off'],
  ])('normalizes runtime effort %j to %s before validation', (input, expected) => {
    profile.update({ modelAlias: 'pythinker-code/ultra' });

    profile.setThinking(input);

    expect(profile.data().thinkingLevel).toBe(expected);
  });

  it('uses the model default when the runtime effort is blank', () => {
    profile.update({ modelAlias: 'pythinker-code/custom', thinkingLevel: 'low' });

    profile.setThinking('   ');

    expect(profile.data().thinkingLevel).toBe('max');
  });

  it('preserves unlisted efforts with a warning for Pythinker-managed Anthropic models', () => {
    profile.update({ modelAlias: 'pythinker-code/compatible', thinkingLevel: 'max' });

    expect(() => {
      profile.setThinking('high');
    }).not.toThrow();
    expect(profile.data().thinkingLevel).toBe('high');
    expect(ctx.allEvents).toContainEqual({
      type: '[rpc]',
      event: 'warning',
      args: expect.objectContaining({
        code: 'anthropic-thinking-effort-not-listed',
        message:
          'Thinking effort "high" is not listed for model "compatible-model" (known: max). The configured value will be sent unchanged to the Anthropic-compatible backend.',
      }),
    });
  });

  it('clamps off to the model default for always-on models, on any transport', () => {
    profile.update({ modelAlias: 'pythinker-code/compatible', thinkingLevel: 'max' });

    expect(() => {
      profile.setThinking('off');
    }).not.toThrow();
    expect(profile.data().thinkingLevel).toBe('max');
  });
});

describe('ConfigState.provider applies global PYTHINKER_MODEL_* request config', () => {
  let ctx: TestAgentContext | undefined;
  let profile: IAgentProfileService;
  let requester: IAgentLLMRequesterService;
  let pythinkerConfig: TestPythinkerConfig;
  let capturedProvider: unknown;
  let capturedOptions: Parameters<GenerateFn>[5];

  beforeEach(() => {
    pythinkerConfig = {
      providers: { pythinker: { type: 'pythinker', apiKey: 'test-key', baseUrl: 'https://api.example.test/v1' } },
      models: {
        'pythinker-code': {
          provider: 'pythinker',
          model: 'pythinker-code',
          maxContextSize: 128_000,
          capabilities: ['thinking'],
        },
        'pythinker-code-anthropic': {
          provider: 'pythinker',
          protocol: 'anthropic',
          model: 'pythinker-code-anthropic',
          maxContextSize: 128_000,
          capabilities: ['thinking'],
          supportEfforts: ['low', 'high'],
        } as TestProtocolModelConfig,
      },
    };
    capturedProvider = undefined;
  });

  afterEach(async () => {
    try {
      await ctx?.expectResumeMatches();
    } finally {
      await ctx?.dispose();
      ctx = undefined;
      vi.unstubAllEnvs();
    }
  });

  function createAgentWithEnv(): void {
    ctx = createTestAgent(
      configServices(() => pythinkerConfig),
      llmGenerateServices(async (provider, _systemPrompt, _tools, _history, _callbacks, options) => {
        capturedProvider = provider;
        capturedOptions = options;
        return {
          id: 'response-1',
          message: { role: 'assistant', content: [], toolCalls: [] },
          usage: emptyUsage(),
          finishReason: 'completed',
          rawFinishReason: 'stop',
        };
      }),
    );
    profile = ctx.get(IAgentProfileService);
    requester = ctx.get(IAgentLLMRequesterService);
  }

  it('injects PYTHINKER_MODEL_TEMPERATURE into the per-turn sampling intent (the compaction request also uses)', async () => {
    vi.stubEnv('PYTHINKER_MODEL_TEMPERATURE', '0.3');
    createAgentWithEnv();

    profile.update({ modelAlias: 'pythinker-code' });
    await requester.request({}, undefined, new AbortController().signal);

    expect(capturedOptions?.sampling).toMatchObject({
      temperature: 0.3,
    });
  });

  it('injects PYTHINKER_MODEL_THINKING_KEEP into the per-turn thinking intent when thinking is on (so compaction keeps it)', async () => {
    vi.stubEnv('PYTHINKER_MODEL_THINKING_KEEP', 'all');
    createAgentWithEnv();

    profile.update({ modelAlias: 'pythinker-code', thinkingLevel: 'high' });
    await requester.request({}, undefined, new AbortController().signal);

    expect(capturedOptions?.thinking).toMatchObject({ effort: 'on', keep: 'all' });
  });

  it('does NOT inject thinking.keep into the per-turn intent when thinking is off', async () => {
    vi.stubEnv('PYTHINKER_MODEL_THINKING_KEEP', 'all');
    createAgentWithEnv();

    profile.update({ modelAlias: 'pythinker-code', thinkingLevel: 'off' });
    await requester.request({}, undefined, new AbortController().signal);

    expect(capturedOptions?.thinking?.effort).toBe('off');
    expect(capturedOptions?.thinking?.keep).toBeUndefined();
  });

  it('injects forced effort through the Anthropic protocol for a Pythinker provider', async () => {
    vi.stubEnv('PYTHINKER_MODEL_THINKING_EFFORT', 'max');
    createAgentWithEnv();

    profile.update({ modelAlias: 'pythinker-code-anthropic', thinkingLevel: 'high' });
    expect(profile.data().thinkingLevel).toBe('high');
    expect(profile.resolveModelContext().thinkingLevel).toBe('max');
    const statusEvent = ctx?.allEvents.findLast(
      (event) =>
        event.event === 'agent.status.updated' &&
        (event.args as { thinkingEffort?: unknown } | undefined)?.thinkingEffort !== undefined,
    );
    expect(statusEvent?.args).toMatchObject({
      model: 'pythinker-code-anthropic',
      thinkingEffort: 'max',
    });

    await requester.request({}, undefined, new AbortController().signal);

    expect(capturedProvider).toMatchObject({ name: 'anthropic' });
    expect(capturedOptions?.thinking?.effort).toBe('max');
  });
});
