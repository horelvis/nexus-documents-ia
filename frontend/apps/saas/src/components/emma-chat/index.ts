// Emma Chat Components - Main exports
export { EmmaChat, type EmmaChatRef } from "./EmmaChat"
export { EmmaQueryInput } from "./EmmaQueryInput"
export { EmmaRenderChat } from "./EmmaRenderChat"
export { EmmaMarkdownFormat } from "./EmmaMarkdownFormat"

// Display Components
export { ThinkingIndicator } from "./displays/Generic/ThinkingIndicator"
export { WorkflowProgress } from "./displays/Generic/WorkflowProgress"

// Voice Mode Components
export {
  EmmaVoiceMode,
  AudioVisualizer,
  VoiceControls,
  VoiceStatus,
  TTSSelector,
  useGeminiVoice,
} from "./voice"

// Types
export type {
  EmmaMessage,
  EmmaMessageType,
  EmmaChatProps,
  EmmaQueryInputProps,
  EmmaRenderChatProps,
  EmmaMarkdownFormatProps,
  EmmaSession,
  EmmaApiResponse,
  Citation,
  DocumentInfo,
  ChainOfThoughtData,
  DisplayRendererProps,
} from "./types"

// Voice Types
export type {
  TTSProvider,
  VoiceConnectionState,
  VoiceState,
  AudioVisualizerProps,
  VoiceControlsProps,
  TTSSelectorProps,
  VoiceModeProps,
} from "./voice"

// Backward compatibility aliases (Elysia -> Emma)
export { EmmaChat as ElysiaChat } from "./EmmaChat"
export { EmmaQueryInput as ElysiaQueryInput } from "./EmmaQueryInput"
export { EmmaRenderChat as ElysiaRenderChat } from "./EmmaRenderChat"
export { EmmaMarkdownFormat as ElysiaMarkdownFormat } from "./EmmaMarkdownFormat"

export type {
  ElysiaMessage,
  ElysiaMessageType,
  ElysiaChatProps,
  ElysiaQueryInputProps,
  ElysiaRenderChatProps,
  ElysiaMarkdownFormatProps,
  ElysiaSession,
  ElysiaApiResponse,
} from "./types"
