export { PythinkerHarness } from '#/pythinker-harness';
export type { PythinkerHarnessRuntimeOptions } from '#/pythinker-harness';
export { Session } from '#/session';
export { PythinkerAuthFacade } from '#/auth';
export { createPythinkerHarness, SDKRpcClient, type SDKRpcClientOptions } from '#/sdk-rpc-client';
export {
  createPythinkerHarnessV2,
  SDKRpcClientV2,
  type SDKRpcClientV2Options,
} from '#/sdk-rpc-client-v2';
export {
  createPythinkerConfigRpc,
  PythinkerConfigRpcClient,
  type PythinkerConfigRpc,
  type PythinkerConfigValidationIssue,
  type PythinkerConfigValidationPathSegment,
  type ResolvePythinkerConfigPathInput,
  type ValidatePythinkerConfigTomlInput,
} from '#/config-rpc';
export { SDKRpcClientBase } from '#/rpc';
export { removeProviderFromConfig } from '#/v2/config-mapper';

export {
  applyCatalogProvider,
  catalogBaseUrl,
  catalogModelToAlias,
  catalogProviderModels,
  CatalogFetchError,
  CatalogProviderError,
  DEFAULT_CATALOG_URL,
  fetchCatalog,
  importCatalogProvider,
  inferWireType,
  loadBuiltInCatalog,
  resolveCatalogImport,
} from '#/catalog';
export type {
  ApplyCatalogProviderOptions,
  Catalog,
  CatalogImportInvalidReason,
  CatalogImportResolution,
  CatalogModel,
  CatalogProviderEntry,
  FetchCatalogOptions,
  ImportCatalogProviderOptions,
  ImportCatalogProviderResult,
} from '#/catalog';

export { buildSkillSlashCommands, isUserActivatableSkill } from '#/skill-commands';
export type { SkillSlashCommand, SkillSlashCommands } from '#/skill-commands';

export { formatErrorMessage, formatErrorPayload } from '#/error-format';
export {
  buildPlatformOptions,
  isOAuthPlatformId,
  resolvePlatformOption,
  type PlatformOption,
} from '#/login/platform-options';
export {
  CATALOG_PLATFORM_VALUE_PREFIX,
  catalogProviderIdFromPlatformValue,
} from '#/login/platform-values';
export { connectCatalogProvider, runLogin } from '#/login/flows';
export {
  CANONICAL_EFFORT_ORDER,
  coerceEffortForModel,
  DEFAULT_SUPPORTED_EFFORTS,
  effortLevelsForModel,
  thinkingAvailability,
  type ThinkingAvailability,
} from '#/thinking-levels';
export type {
  ApiKeyPromptOptions,
  LoginPlatformDefinition,
  LoginPlatformModelInfo,
  LoginProgressSpinnerHandle,
  LoginUi,
  PlatformSelection,
} from '#/login/types';

export {
  ErrorCodes,
  PythinkerError,
  type PythinkerErrorCode,
  type PythinkerErrorInfo,
  type PythinkerErrorOptions,
  type PythinkerErrorPayload,
  PYTHINKER_ERROR_INFO,
  fromPythinkerErrorPayload,
  isPythinkerError,
  toPythinkerErrorPayload,
} from '@pymodel/agent-core';

// Diagnostic logging — public surface only.
// RootLogger / getRootLogger / LoggingConfig stay inside agent-core.
export {
  flushDiagnosticLogs,
  flushDiagnosticLogsSync,
  log,
  redact,
  resolveGlobalLogPath,
  resolvePythinkerHome,
} from '@pymodel/agent-core';
export type { LogContext, LogLevel, LogPayload, Logger } from '@pymodel/agent-core';

// Host-side config helpers — safe config reader + config path resolution, used
// by hosts (e.g. the CLI's server telemetry bootstrap) that need to inspect
// config without spinning up a full PythinkerCore.
export { effectiveModelAlias, loadRuntimeConfigSafe, resolveConfigPath } from '@pymodel/agent-core';
export { limitAgentReplayByTurns } from '@pymodel/agent-core';
export { parseAgentFileText, resolveAgentPath } from '@pymodel/agent-core';
// The synthesized `[models]` alias a `[secondary_model]` recipe with patch
// fields materializes at runtime — hosts filter it out of model pickers.
export { SECONDARY_DERIVED_MODEL_ALIAS } from '@pymodel/agent-core';
// Reserved key of the v2 engine's subagent model pool: it always binds the
// caller's own model, so hosts must not offer a user alias named `primary`
// as the subagent default model.
export { PRIMARY_SUBAGENT_MODEL_CHOICE } from '@pymodel/agent-core-v2/session/subagent/configSection';
// Remaps secondary-model aliases during provider renames without deleting
// user-owned references that no longer resolve.
export { cascadeSubagentModelPool } from '@pymodel/agent-core-v2/session/subagent/configSection';

// Process-wide HTTP proxy bootstrap — installed once at CLI startup so all
// outbound fetch honors HTTP_PROXY / HTTPS_PROXY / NO_PROXY.
export { installGlobalProxyDispatcher } from '@pymodel/agent-core';

// Image compression — ingestion sites (e.g. the CLI's clipboard paste, the ACP
// adapter) shrink oversized images while constructing the content part, before
// it enters a prompt. Best effort: returns the original on any failure.
// Compression is never silent: buildImageCompressionCaption renders the note
// placed next to a compressed image, and persistOriginalImage keeps the
// pre-compression bytes readable (ReadMediaFile + region) for detail.
export {
  buildImageCompressionCaption,
  buildUnsupportedImageNotice,
  compressImageForModel,
  compressBase64ForModel,
  gateImageFormatParts,
  isModelAcceptedImageMime,
  normalizeImageMime,
  parseImageDataUrl,
  persistOriginalImage,
  sessionMediaOriginalsDir,
  IMAGE_BYTE_BUDGET,
  MAX_IMAGE_EDGE_PX,
} from '@pymodel/agent-core';
export { ImageLimits } from '@pymodel/agent-core';
export type {
  CompressImageOptions,
  CompressImageResult,
  CompressBase64Result,
  ImageCompressionCaptionInput,
  ImageCompressionTelemetry,
} from '@pymodel/agent-core';

// Experimental feature flags — types only. Resolved values come from
// `PythinkerHarness.getExperimentalFeatures()` over RPC, not from a re-exported runtime value.
export type {
  ExperimentalFeatureState,
  ExperimentalFlagMap,
  ExperimentalFlagSource,
  FlagDefinition,
  FlagDefinitionInput,
  FlagId,
  FlagSurface,
} from '@pymodel/agent-core';

// Daemon file references (agent-core-v2) — pure helpers for the internal
// `pythinker-file://` media URLs and the model-facing `<image|video|file>` path
// tags. A daemon-ref media part is self-contained (kind from the part type,
// file id from the url) — there is no tag+ref pairing to fold.
// Hosts must not import agent-core-v2 directly; `FileMeta` and
// `UploadFileOptions` ride the `export type * from '#/types'` below.
export {
  buildDaemonFileUrl,
  buildMediaPathTag,
  isDaemonFileUrl,
  matchSingleMediaPathTag,
  parseDaemonFileUrl,
} from '@pymodel/agent-core-v2/agent/media/mediaRef';
export type {
  DaemonFileRef,
  MediaKind,
} from '@pymodel/agent-core-v2/agent/media/mediaRef';

export * from '#/events';
export type * from '#/types';
