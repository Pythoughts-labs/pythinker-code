import { describe, expect, it } from 'vitest';

import { emptyUsage } from '#/kosong/contract/usage';
import type { ChatProvider, GenerateOptions, StreamedMessage } from '#/kosong/contract/provider';
import type { Model } from '#/kosong/model/catalog';
import { ModelRequesterImpl } from '#/kosong/model/modelRequesterImpl';
import { OPENCODE_SESSION_HEADER } from '#/kosong/model/opencodeSession';
import type { IProtocolAdapterRegistry } from '#/kosong/protocol/protocol';

const INPUT = {
  systemPrompt: 'system',
  tools: [],
  messages: [{ role: 'user' as const, content: [{ type: 'text' as const, text: 'hello' }], toolCalls: [] }],
};

function streamOf(
  parts: readonly { type: 'text'; text: string }[] = [],
  overrides: Partial<StreamedMessage> = {},
): StreamedMessage {
  return {
    id: 'msg-1',
    usage: emptyUsage(),
    finishReason: 'completed',
    rawFinishReason: 'stop',
    traceId: null,
    async *[Symbol.asyncIterator]() {
      yield* parts;
    },
    ...overrides,
  };
}

class FakeChatProvider implements ChatProvider {
  readonly name = 'fake';
  readonly modelName = 'fake-model';
  readonly thinkingEffort = null;
  readonly calls: Array<{ options?: GenerateOptions }> = [];
  handler: () => Promise<StreamedMessage> = () => Promise.resolve(streamOf());

  generate(
    _systemPrompt: string,
    _tools: never[],
    _history: never[],
    options?: GenerateOptions,
  ): Promise<StreamedMessage> {
    this.calls.push({ options });
    return this.handler();
  }
}

function staticAuth(apiKey?: string) {
  return apiKey === undefined
    ? undefined
    : {
        getAuth: async () => ({ apiKey }),
      };
}

function modelWith(
  authProvider?: Model['authProvider'],
  baseUrl = 'https://example.test/v1',
): Model {
  return {
    id: 'test-model',
    name: 'fake-model',
    displayName: 'Fake',
    providerName: 'test',
    providerType: 'openai',
    protocol: 'openai',
    baseUrl,
    maxContextSize: 128000,
    capabilities: {
      image_in: false,
      video_in: false,
      audio_in: false,
      thinking: true,
      tool_use: true,
      max_context_tokens: 128000,
    },
    traits: [],
    authProvider,
  };
}

function registryReturning(provider: ChatProvider): IProtocolAdapterRegistry {
  return {
    _serviceBrand: undefined,
    supportedProtocols: () => ['openai'],
    resolveAdapterIdentity: () => ({ protocol: 'openai', providerBaseId: 'openai' }),
    resolveProviderBaseId: () => 'openai',
    resolveCapability: () => modelWith().capabilities,
    explainCapability: () => ({ capability: modelWith().capabilities, source: { kind: 'none' } }),
    createChatProvider: () => provider,
  } as IProtocolAdapterRegistry;
}

async function collect(iterable: AsyncIterable<unknown>): Promise<unknown[]> {
  const items: unknown[] = [];
  for await (const item of iterable) items.push(item);
  return items;
}

describe('ModelRequesterImpl', () => {
  it('forwards auth, cache, sampling, thinking, context, and signal options', async () => {
    const provider = new FakeChatProvider();
    const requester = new ModelRequesterImpl(modelWith(staticAuth('sk-1')), registryReturning(provider));
    const signal = new AbortController().signal;
    await collect(
      requester.request(
        INPUT,
        signal,
        {
          cacheKey: 'session-1',
          sampling: { temperature: 0.5, topP: 0.9 },
          thinking: { effort: 'high', keep: 'all' },
          responseFormat: { type: 'json_object' },
          maxCompletionTokens: 1024,
          usedContextTokens: 5000,
          maxContextTokens: 128000,
        },
      ),
    );

    expect(provider.calls).toHaveLength(1);
    const options = provider.calls[0]!.options;
    expect(options?.signal).toBe(signal);
    expect(options?.auth).toEqual({ apiKey: 'sk-1' });
    expect(options?.cacheKey).toBe('session-1');
    expect(options?.sampling).toEqual({ temperature: 0.5, topP: 0.9 });
    expect(options?.thinking).toEqual({ effort: 'high', keep: 'all' });
    expect(options?.maxCompletionTokens).toBe(1024);
    expect(options?.usedContextTokens).toBe(5000);
    expect(options?.maxContextTokens).toBe(128000);
    expect(options?.responseFormat).toEqual({ type: 'json_object' });
  });

  it('omits the thinking intent when no effort is requested', async () => {
    const provider = new FakeChatProvider();
    const requester = new ModelRequesterImpl(modelWith(staticAuth()), registryReturning(provider));
    await collect(requester.request(INPUT));
    expect(provider.calls[0]?.options?.thinking).toBeUndefined();
    expect(provider.calls[0]?.options?.auth).toBeUndefined();
  });

  it('sends the OpenCode session header only for OpenCode gateways with a conversation id', async () => {
    const capture = new FakeChatProvider();
    const capturing = new ModelRequesterImpl(
      modelWith(staticAuth(), 'https://gateway.opencode.ai/zen/v1'),
      registryReturning(capture),
    );
    await collect(capturing.request(INPUT, undefined, { conversationId: 'conv-1' }));
    expect(capture.calls).toHaveLength(1);
    expect(capture.calls[0]?.options?.extraHeaders).toEqual({
      [OPENCODE_SESSION_HEADER]: 'conv-1',
    });

    const other = new FakeChatProvider();
    await collect(
      new ModelRequesterImpl(
        modelWith(staticAuth(), 'https://api.openai.com/v1'),
        registryReturning(other),
      ).request(INPUT, undefined, { conversationId: 'conv-1' }),
    );
    expect(other.calls).toHaveLength(1);
    expect(other.calls[0]?.options?.extraHeaders).toBeUndefined();

    const noConversation = new FakeChatProvider();
    await collect(
      new ModelRequesterImpl(
        modelWith(staticAuth(), 'https://opencode.ai/zen/go/v1'),
        registryReturning(noConversation),
      ).request(INPUT),
    );
    expect(noConversation.calls).toHaveLength(1);
    expect(noConversation.calls[0]?.options?.extraHeaders).toBeUndefined();
  });

  it('streams part, usage, finish, and timing events', async () => {
    const provider = new FakeChatProvider();
    provider.handler = () =>
      Promise.resolve(
        streamOf([{ type: 'text', text: 'hi' }], {
          usage: { ...emptyUsage(), output: 7 },
          id: 'msg-42',
          traceId: 'trace-1',
        }),
      );
    const traceIds: Array<string | null> = [];
    const requester = new ModelRequesterImpl(modelWith(staticAuth()), registryReturning(provider));
    const events = await collect(
      requester.request(INPUT, undefined, { onTraceId: (id) => traceIds.push(id) }),
    );

    const types = events.map((e) => (e as { type: string }).type);
    expect(types).toEqual(['part', 'usage', 'finish', 'timing']);
    expect(traceIds).toEqual(['trace-1']);
  });
});
