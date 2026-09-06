import { describe, expect, it } from 'vitest';

import { createScopedTestHost } from '#/_base/di/test';
import { IConfigService } from '#/app/config/config';
import { HostRequestHeadersAdapter } from '#/app/kosongConfig/hostRequestHeadersAdapter';
import { IModelCatalog } from '#/kosong/model/catalog';
import { ModelCatalog } from '#/kosong/model/catalogService';
import { IHostRequestHeaders } from '#/kosong/model/hostRequestHeaders';
import { IModelOAuthTokens } from '#/kosong/model/modelOAuth';
import type { ModelRequester } from '#/kosong/model/modelRequester';
import '#/kosong/model/modelService';
import '#/kosong/protocol/protocol';
import '#/kosong/provider/bases/openai/index';
import '#/kosong/provider/protocolAdapterRegistry';
import '#/kosong/provider/providerService';
import '#/kosong/provider/providers/pythinker/pythinker.contrib';
import '#/kosong/provider/providers/standard.contrib';

import { stubAgentIdentity } from '../../app/agentIdentity/stubs';
import { stubBootstrap } from '../../app/bootstrap/stubs';
import { StubConfigService, stubModelOAuthTokens } from '../stubs';

function createCatalog(): { catalog: ModelCatalog; dispose(): void } {
  const config = new StubConfigService({
    providers: { pythinker: { type: 'pythinker', apiKey: 'sk-test', baseUrl: 'https://example.test/v1' } },
    models: { k1: { provider: 'pythinker', model: 'kimi-k2', maxContextSize: 262144 } },
  });
  const headers = { 'User-Agent': 'pythinker-test/1.0' };
  const host = createScopedTestHost([
    [IConfigService, config],
    [IModelOAuthTokens, stubModelOAuthTokens()],
    [
      IHostRequestHeaders,
      new HostRequestHeadersAdapter(
        stubBootstrap('/home', {}, { requestHeaders: headers }),
        stubAgentIdentity({ hostRequestHeaders: headers }),
      ),
    ],
  ]);
  return { catalog: host.app.accessor.get(IModelCatalog) as ModelCatalog, dispose: () => host.dispose() };
}

describe('ModelCatalog ping conversation ids', () => {
  it('uses a fresh UUID for every connectivity probe', async () => {
    const { catalog, dispose } = createCatalog();
    try {
      const ids: string[] = [];
      const requester = catalog.getRequester('k1') as ModelRequester & {
        request: ModelRequester['request'];
      };
      requester.request = (async function* (_request, _signal, params) {
        ids.push(params?.conversationId ?? '');
        yield { type: 'finish', providerFinishReason: 'completed', rawFinishReason: 'stop' } as never;
      }) as ModelRequester['request'];

      await catalog.ping('k1');
      await catalog.ping('k1');

      expect(ids).toHaveLength(2);
      expect(ids[0]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      expect(ids[1]).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
      expect(ids[0]).not.toBe(ids[1]);
    } finally {
      dispose();
    }
  });
});
