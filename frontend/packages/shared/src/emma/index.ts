// Emma Chat Components - Main exports
export { EmmaChat, type EmmaChatRef } from "./EmmaChat"
export { EmmaQueryInput } from "./EmmaQueryInput"
export { EmmaRenderChat } from "./EmmaRenderChat"
export { EmmaMarkdownFormat } from "./EmmaMarkdownFormat"

// Display Components
export { ThinkingIndicator } from "./displays/Generic/ThinkingIndicator"
export { WorkflowProgress } from "./displays/Generic/WorkflowProgress"
export { ReasoningDisplay, type ReasoningDisplayProps } from "./displays/Generic/ReasoningDisplay"
export { ExplanationPanel } from "./displays/Generic/ExplanationPanel"

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
  WorkflowStep,
  SLMPlanReady,
  ProgressStage,
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
