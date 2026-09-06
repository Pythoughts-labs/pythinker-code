import {
  FileTokenStorage,
  refreshKimiOAuthToken,
  refreshMiniMaxOAuthToken,
  resolveOAuthTokenStorageName,
  type TokenInfo,
} from '@pymodel/pythinker-code-oauth';
import { join } from 'pathe';

import { ScopeActivation, registerScopedService } from '#/_base/di/scope';
import { type ILogger, ILogService } from '#/_base/log/log';
import { IBootstrapService } from '#/app/bootstrap/bootstrap';
import { IConfigService } from '#/app/config/config';
import { LifecycleScope } from '#/app/scopes';
import { IModelService, type ModelRecord } from '#/kosong/model/model';
import {
  effectiveModelConfig,
  nonEmpty,
  providerNameFromFlatModel,
  resolveModelAuthMaterial,
  resolveModelForReady,
} from '#/kosong/model/modelAuth';
import { IProviderService, type OAuthRef } from '#/kosong/provider/provider';

import {
  AuthModelNotResolvedError,
  AuthProvisioningRequiredError,
  AuthTokenMissingError,
  type AuthStatus,
  type OAuthBearerTokenProvider,
  IAuthSummaryService,
  IOAuthTokenService,
} from './auth';

const REFRESH_BUFFER_SECONDS = 5 * 60;

export class OAuthTokenService implements IOAuthTokenService {
  declare readonly _serviceBrand: undefined;

  private readonly storage: FileTokenStorage;
  private readonly refreshInflight = new Map<string, Promise<TokenInfo>>();

  constructor(@IBootstrapService bootstrap: IBootstrapService) {
    this.storage = new FileTokenStorage(join(bootstrap.homeDir, bootstrap.scope('credentials')));
  }

  async status(provider: string, oauthRef: OAuthRef): Promise<AuthStatus> {
    return {
      loggedIn: (await this.getCachedAccessToken(provider, oauthRef)) !== undefined,
      provider,
    };
  }

  resolveTokenProvider(provider: string, oauthRef: OAuthRef): OAuthBearerTokenProvider | undefined {
    if (oauthRef.storage !== 'file') return undefined;
    return {
      getAccessToken: async (options) =>
        this.getAccessToken(provider, oauthRef, options?.force === true),
    };
  }

  async getCachedAccessToken(
    _provider: string,
    oauthRef: OAuthRef,
  ): Promise<string | undefined> {
    if (oauthRef.storage !== 'file') return undefined;
    const token = await this.storage.load(resolveOAuthTokenStorageName(oauthRef.key));
    if (token === undefined || token.accessToken.trim().length === 0) return undefined;
    if (token.expiresAt <= Math.floor(Date.now() / 1000)) return undefined;
    return token.accessToken;
  }

  private async getAccessToken(provider: string, oauthRef: OAuthRef, force: boolean): Promise<string> {
    const storageName = resolveOAuthTokenStorageName(oauthRef.key);
    const token = await this.storage.load(storageName);
    if (token === undefined || token.accessToken.trim().length === 0) throw loginRequired(provider);

    const nowSeconds = Math.floor(Date.now() / 1000);
    const shouldRefresh = force || token.expiresAt - nowSeconds <= REFRESH_BUFFER_SECONDS;
    if (!shouldRefresh) return token.accessToken;

    if (token.refreshToken.trim().length === 0 || token.metadata?.['provider'] === undefined) {
      if (!force && token.expiresAt > nowSeconds) return token.accessToken;
      throw loginRequired(provider);
    }

    try {
      const refreshed = await this.refreshSingleFlight(storageName, token);
      return refreshed.accessToken;
    } catch (error) {
      // A proactive refresh may fail transiently while the current token is still
      // valid. A forced refresh follows a 401 and must not replay the stale token.
      if (!force && token.expiresAt > nowSeconds) return token.accessToken;
      throw error;
    }
  }

  private refreshSingleFlight(storageName: string, token: TokenInfo): Promise<TokenInfo> {
    const existing = this.refreshInflight.get(storageName);
    if (existing !== undefined) return existing;
    const refresh = this.refreshToken(token)
      .then(async (next) => {
        await this.storage.save(storageName, next);
        return next;
      })
      .finally(() => {
        if (this.refreshInflight.get(storageName) === refresh) this.refreshInflight.delete(storageName);
      });
    this.refreshInflight.set(storageName, refresh);
    return refresh;
  }

  private async refreshToken(token: TokenInfo): Promise<TokenInfo> {
    const provider = token.metadata?.['provider'];
    if (provider === 'kimi') {
      const deviceId = token.metadata?.['deviceId'];
      if (deviceId === undefined || deviceId.length === 0) throw new Error('Kimi OAuth credential is missing deviceId metadata.');
      const refreshed = await refreshKimiOAuthToken(token.refreshToken, deviceId);
      return {
        accessToken: refreshed.accessToken,
        refreshToken: refreshed.refreshToken,
        expiresAt: Math.floor(refreshed.expiresAtMs / 1000),
        expiresIn: Math.max(1, Math.floor((refreshed.expiresAtMs - Date.now()) / 1000)),
        scope: refreshed.scope,
        tokenType: refreshed.tokenType,
        metadata: token.metadata,
      };
    }
    if (provider === 'minimax') {
      const region = token.metadata?.['region'];
      if (region !== 'global' && region !== 'cn') throw new Error('MiniMax OAuth credential has invalid region metadata.');
      const refreshed = await refreshMiniMaxOAuthToken(region, token.refreshToken);
      return {
        accessToken: refreshed.accessToken,
        refreshToken: refreshed.refreshToken,
        expiresAt: Math.floor(refreshed.expiresAtMs / 1000),
        expiresIn: Math.max(1, Math.floor((refreshed.expiresAtMs - Date.now()) / 1000)),
        scope: refreshed.scope,
        tokenType: refreshed.tokenType,
        metadata: token.metadata,
      };
    }
    throw new Error(`OAuth provider "${provider ?? 'unknown'}" does not support token refresh.`);
  }
}

export class AuthSummaryService implements IAuthSummaryService {
  declare readonly _serviceBrand: undefined;

  constructor(
    @IProviderService private readonly providerService: IProviderService,
    @IModelService private readonly modelService: IModelService,
    @IConfigService private readonly config: IConfigService,
    @IOAuthTokenService private readonly oauth: IOAuthTokenService,
    @ILogService private readonly log: ILogger,
  ) {}

  async summarize(): Promise<readonly AuthStatus[]> {
    const statuses: AuthStatus[] = [];
    for (const [name, provider] of Object.entries(this.providerService.list())) {
      if (provider.oauth === undefined) continue;
      try {
        statuses.push(await this.oauth.status(name, provider.oauth));
      } catch (error) {
        this.log.warn('OAuth credential status failed', {
          provider: name,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
    return statuses;
  }

  async ensureReady(modelOverride?: string): Promise<void> {
    await this.config.reload();
    const providers = this.providerService.list();
    const models = this.modelService.list();
    const modelId = modelOverride ?? this.modelService.getDefaultModel();
    const configured = modelId === undefined || modelId === '' ? undefined : models[modelId];
    if (Object.keys(providers).length === 0 && !isProviderlessModel(configured)) {
      throw new AuthProvisioningRequiredError();
    }
    const resolution = resolveModelForReady(
      modelId,
      models,
      providers,
      this.providerService.getDefaultProvider(),
    );
    if (!resolution.resolved) {
      if (resolution.reason === 'no-default') {
        throw new AuthModelNotResolvedError(undefined);
      }
      const effective = configured === undefined ? undefined : effectiveModelConfig(configured);
      const providerId =
        effective?.providerId ?? effective?.provider ?? this.providerService.getDefaultProvider();
      throw new AuthModelNotResolvedError(
        modelId,
        resolution.reason === 'provider-missing' ? providerId : undefined,
      );
    }

    const model = effectiveModelConfig(configured as ModelRecord);
    const providerId =
      model.providerId ?? model.provider ?? this.providerService.getDefaultProvider();
    const provider = providerId === undefined ? undefined : this.providerService.get(providerId);
    const providerName = (providerId ?? providerNameFromFlatModel(model)) as string;

    const auth = resolveModelAuthMaterial({
      modelId: modelId as string,
      model,
      provider,
      providerName,
    });
    if (auth.apiKey !== undefined) return;
    if (auth.oauth !== undefined) {
      const providerKey = auth.oauthProviderKey ?? providerName;
      const token = await this.oauth.getCachedAccessToken(providerKey, auth.oauth);
      if (nonEmpty(token) !== undefined) return;
      const tokenProvider = this.oauth.resolveTokenProvider(providerKey, auth.oauth);
      if (tokenProvider !== undefined) {
        try {
          const refreshed = await tokenProvider.getAccessToken();
          if (nonEmpty(refreshed) !== undefined) return;
        } catch {
          // Normalize below to the existing login-required contract.
        }
      }
      throw new AuthTokenMissingError(providerKey);
    }
    throw new AuthTokenMissingError(providerName);
  }
}

function loginRequired(providerKey: string): Error2 {
  return new Error2(
    AuthErrors.codes.AUTH_LOGIN_REQUIRED,
    `OAuth provider "${providerKey}" has no usable stored credential.`,
  );
}

function isProviderlessModel(model: ModelRecord | undefined): boolean {
  if (model === undefined) return false;
  const effective = effectiveModelConfig(model);
  return (
    effective.providerId === undefined &&
    effective.provider === undefined &&
    providerNameFromFlatModel(effective) !== undefined
  );
}

registerScopedService(
  LifecycleScope.App,
  IOAuthTokenService,
  OAuthTokenService,
  ScopeActivation.OnScopeCreated,
  'auth',
);
registerScopedService(
  LifecycleScope.App,
  IAuthSummaryService,
  AuthSummaryService,
  ScopeActivation.OnScopeCreated,
  'auth',
);
