import { describe, expect, it } from 'vitest';

import { DisposableStore } from '#/_base/di/lifecycle';
import { createServices } from '#/_base/di/test';
import { UNKNOWN_CAPABILITY } from '#/kosong/contract/capability';
import { IModelCatalog } from '#/kosong/model/catalog';
import { ModelCatalog } from '#/kosong/model/catalogService';
import { IHostRequestHeaders } from '#/kosong/model/hostRequestHeaders';
import { IModelService } from '#/kosong/model/model';
import { IModelOAuthTokens } from '#/kosong/model/modelOAuth';
import { IProtocolAdapterRegistry } from '#/kosong/protocol/protocol';
import { IProviderService } from '#/kosong/provider/provider';

function createCatalog(disposables: DisposableStore) {
  const services = createServices(disposables, {
    additionalServices(reg) {
      reg.define(IModelCatalog, ModelCatalog);
      reg.definePartialInstance(IProviderService, {
        onDidChangeProviders: () => ({ dispose() {} }),
        get: () => ({ type: 'openai', apiKey: 'test-key', baseUrl: 'https://example.test/v1' }),
      });
      reg.definePartialInstance(IModelService, {
        onDidChangeModels: () => ({ dispose() {} }),
        get: () => ({ protocol: 'openai', provider: 'example', model: 'model', maxContextSize: 4096 }),
      });
      reg.definePartialInstance(IModelOAuthTokens, {});
      reg.definePartialInstance(IProtocolAdapterRegistry, {
        explainCapability: () => ({ capability: UNKNOWN_CAPABILITY, source: { kind: 'builtin' } }),
      });
      reg.defineInstance(IHostRequestHeaders, { headers: {}, thirdPartyHeaders: {} });
    },
  });
  return services.get(IModelCatalog);
}

describe('ModelCatalog ping conversation ids', () => {
  it('uses a fresh UUID for every connectivity probe', async () => {
    const disposables = new DisposableStore();
    const catalog = createCatalog(disposables);
    try {
      const ids: string[] = [];
      const requester = catalog.getRequester('example/model');
      requester.request = async function* (_request, _signal, params) {
        ids.push(params?.conversationId ?? '');
        yield {
          type: 'finish',
          message: { role: 'assistant', content: [], toolCalls: [] },
          providerFinishReason: 'completed',
          rawFinishReason: 'stop',
        };
      };

      await expect(catalog.ping('example/model')).resolves.toMatchObject({ ok: true });
      await expect(catalog.ping('example/model')).resolves.toMatchObject({ ok: true });

      expect(ids).toHaveLength(2);
      expect(ids[0]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      expect(ids[1]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      expect(ids[0]).not.toBe(ids[1]);
    } finally {
      disposables.dispose();
    }
  });
});
