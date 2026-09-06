export { renderOpenAICodexOAuthSuccessPage } from './oauth-pages';

export {
  applyOpenAICodexOAuthConfig,
  buildOpenAICodexAuthorizeUrl,
  createOpenAICodexPkcePair,
  exchangeOpenAICodexAuthorizationCode,
  extractOpenAICodexAccountId,
  fetchOpenAICodexModels,
  OPENAI_CODEX_CLI_CLIENT_VERSION,
  OPENAI_CODEX_OAUTH_PLATFORM_ID,
  OPENAI_CODEX_PROVIDER_ID,
  OAuthAccessDeniedError,
  OPENAI_CODEX_REDIRECT_URI,
  OpenAICodexApiError,
  parseOpenAICodexAuthorizationInput,
  runOpenAICodexOAuthFlow,
  startOpenAICodexCallbackServer,
} from './openai-codex-oauth';
export type {
  ApplyOpenAICodexOAuthResult,
  OpenAICodexCallbackResult,
  FetchOpenAICodexModelsOptions,
  OpenAICodexCallbackServer,
  OpenAICodexConfigShape,
  OpenAICodexModelInfo,
  OpenAICodexPkcePair,
  OpenAICodexTokenBundle,
  RunOpenAICodexOAuthFlowOptions,
} from './openai-codex-oauth';

export type { TokenInfo, TokenInfoWire } from './types';
export { tokenFromWire, tokenToWire } from './types';
export type { TokenStorage } from './storage';
export { FileTokenStorage, resolveOAuthTokenStorageName } from './storage';

export {
  DeviceCodeExpiredError,
  DeviceOAuthApiError,
  pollForDeviceToken,
  requestDeviceCode,
  runDeviceOAuthFlow,
} from './device-oauth';
export type {
  DeviceCodeInfo,
  PollDeviceTokenOptions,
  RunDeviceOAuthFlowOptions,
} from './device-oauth';

export {
  applyKimiOAuthConfig,
  fetchKimiCodingModels,
  KIMI_CODING_BASE_URL,
  KIMI_CODING_PROVIDER_ID,
  KIMI_OAUTH_PLATFORM_ID,
  refreshKimiOAuthToken,
  runKimiOAuthFlow,
} from './kimi-oauth';
export type {
  ApplyKimiOAuthResult,
  KimiOAuthTokenBundle,
  RunKimiOAuthFlowOptions,
} from './kimi-oauth';

export {
  applyMiniMaxOAuthConfig,
  miniMaxCodingModels,
  minimaxCodingProviderId,
  minimaxOAuthPlatformId,
  minimaxRegionLabel,
  MINIMAX_OAUTH_PLATFORM_ID_CN,
  MINIMAX_OAUTH_PLATFORM_ID_GLOBAL,
  refreshMiniMaxOAuthToken,
  runMiniMaxOAuthFlow,
} from './minimax-oauth';
export type {
  ApplyMiniMaxOAuthResult,
  MiniMaxOAuthTokenBundle,
  MiniMaxRegion,
  RunMiniMaxOAuthFlowOptions,
} from './minimax-oauth';

export {
  assertPythinkerHostIdentity,
  createPythinkerDefaultHeaders,
  createPythinkerDeviceId,
  createPythinkerUserAgent,
  PYTHINKER_CODE_CUSTOM_HEADERS_ENV,
  PYTHINKER_CODE_PLATFORM,
  parsePythinkerCodeCustomHeaders,
  readPythinkerDeviceId,
  replaceUserAgentProduct,
} from './identity';
export type { PythinkerHostIdentity, PythinkerIdentityOptions } from './identity';

export {
  applyOpenPlatformConfig,
  capabilitiesForModel,
  fetchOpenPlatformModels,
  filterModelsByPrefix,
  getOpenPlatformById,
  isOpenPlatformId,
  OPEN_PLATFORMS,
  OpenPlatformApiError,
  removeOpenPlatformConfig,
} from './open-platform';
export type { ApplyOpenPlatformResult, OpenPlatformDefinition } from './open-platform';

export {
  applyCustomRegistryEntries,
  applyCustomRegistryProvider,
  capabilitiesFromCustomEntry,
  CustomRegistryApiError,
  CUSTOM_REGISTRY_DEFAULT_CAPABILITIES,
  CUSTOM_REGISTRY_DEFAULT_MAX_CONTEXT,
  fetchCustomRegistry,
  removeCustomRegistryProvider,
} from './custom-registry';
export type {
  CustomRegistryModelEntry,
  CustomRegistryProviderEntry,
  CustomRegistryProviderType,
  CustomRegistrySource,
  FetchCustomRegistryOptions,
} from './custom-registry';

export {
  parseModelProtocol,
  parseStringArray,
  parseSupportsThinkingType,
  parseThinkEfforts,
} from './provider-config';
export type {
  ModelAlias,
  ModelAliasOverrides,
  ModelProtocol,
  OAuthRef,
  OAuthRefInput,
  ProviderConfig,
  ProviderModelInfo,
  PythinkerConfigShape,
  SecondaryModelShape,
  ServiceConfig,
  ServicesConfig,
  SupportsThinkingType,
  ThinkingShape,
} from './provider-config';

export { refreshProviderModels } from './refreshProviderModels';
export type {
  ProviderChange,
  RefreshProviderHost,
  RefreshProviderOptions,
  RefreshResult,
} from './refreshProviderModels';

export type { OAuthTokenTransactionOptions } from './oauth-token-transaction';
export { OAuthTokenTransaction } from './oauth-token-transaction';
