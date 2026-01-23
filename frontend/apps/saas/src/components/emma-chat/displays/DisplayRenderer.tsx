"use client"

import { TextDisplay } from "./Generic/TextDisplay"
import { DocumentDisplay } from "./Document/DocumentDisplay"
import { InfoDisplay } from "./SystemMessages/InfoDisplay"
import { WorkflowProgress } from "./Generic/WorkflowProgress"
import { AgentProcessPanel } from "./Generic/AgentProcessPanel"
import { StreamingTextDisplay } from "./Generic/StreamingTextDisplay"
import { DelegationBadge } from "./Generic/DelegationBadge"
import { DisplayRendererProps, DocumentInfo, AgentProcessInfo } from "../types"

export function DisplayRenderer({
  message,
  onDocumentClick = () => {},
  onPreviewClick = () => {},
  isAdmin = false
}: DisplayRendererProps) {
  // Extract documents from tools_used or sources
  const extractDocuments = (): DocumentInfo[] | null => {
    const docs: DocumentInfo[] = []

    // From metadata.documents (if available)
    if (message.metadata?.documents) {
      docs.push(...message.metadata.documents)
    }

    // From metadata.sources
    if (message.metadata?.sources) {
      docs.push(...message.metadata.sources.map(source => ({
        name: source.document || source.title || 'Documento',
        relevanceScore: source.relevance,
        fileType: (source.document || '').split('.').pop() || 'unknown'
      })))
    }

    // From agent_flow (extract document names from weaviate_search results)
    if (message.metadata?.agent_flow) {
      message.metadata.agent_flow.forEach(step => {
        if (typeof step === 'string' && step.includes('weaviate_search:')) {
          const docInfo = step.replace('weaviate_search:', '')

          // Try to parse if it includes document ID: "title:documentId"
          const parts = docInfo.split(':')
          const docName = parts[0]
          const docId = parts[1] || undefined

          if (docName && !docs.find(d => d.name === docName)) {
            docs.push({
              name: docName,
              id: docId, // Include document ID if available
              fileType: docName.split('.').pop() || 'unknown',
              relevanceScore: 0.8 // Default relevance
            })
          }
        }
      })
    }

    return docs.length > 0 ? docs : null
  }

  const documents = extractDocuments()

  switch (message.type) {
    case "error":
      return <InfoDisplay content={message.content} type="error" />

    case "warning":
      return <InfoDisplay content={message.content} type="warning" />

    case "info":
      return <InfoDisplay content={message.content} type="info" />

    case "progress":
      // Build process info from metadata
      const processInfo: AgentProcessInfo | undefined = message.metadata?.process_info || (
        message.metadata?.delegations ? {
          reasoning_type: undefined,
          sil_used: false,
          active_tools: message.metadata.delegations.map(d => ({
            name: d.agent,
            status: 'running' as const,
            message: d.message,
            elapsed_ms: d.elapsedMs
          }))
        } : undefined
      )

      return (
        <div className="space-y-3">
          {/* Main workflow progress */}
          <WorkflowProgress
            message={message.content}
            progress={message.metadata?.progress || 0}
            currentStep={message.metadata?.step}
            totalSteps={message.metadata?.total_steps}
            currentAgent={message.metadata?.agent}
            steps={message.metadata?.workflow_steps}
            planId={message.metadata?.plan_id}
          />

          {/* Agent Process Panel - shows SIL reasoning, tools, legal context */}
          {processInfo && (
            <AgentProcessPanel
              processInfo={processInfo}
              isActive={true}
            />
          )}

          {/* Active delegations (tool calls) */}
          {message.metadata?.delegations && message.metadata.delegations.length > 0 && !processInfo && (
            <div className="flex flex-wrap gap-2">
              {message.metadata.delegations.slice(-3).map((delegation, idx) => (
                <DelegationBadge
                  key={idx}
                  agent={delegation.agent}
                  message={delegation.message}
                  elapsedMs={delegation.elapsedMs}
                  isActive={idx === message.metadata!.delegations!.length - 1}
                />
              ))}
            </div>
          )}

          {/* Streaming text display */}
          {message.metadata?.streamingText && (
            <StreamingTextDisplay
              text={message.metadata.streamingText}
              isStreaming={message.metadata.isStreaming || false}
              showCursor={true}
            />
          )}
        </div>
      )

    case "result":
      // Get process info from result metadata
      const resultProcessInfo: AgentProcessInfo | undefined = message.metadata?.process_info

      return (
        <div className="space-y-3">
          <TextDisplay content={message.content} />

          {/* Agent Process Panel - shows final metrics and reasoning used */}
          {resultProcessInfo && isAdmin && (
            <AgentProcessPanel
              processInfo={resultProcessInfo}
              isActive={false}
              className="opacity-80"
            />
          )}

          {/* Document Display */}
          {documents && (
            <DocumentDisplay
              documents={documents}
              onDocumentClick={onDocumentClick}
              onPreviewClick={onPreviewClick}
            />
          )}
        </div>
      )

    case "user":
    case "query":
    default:
      return <TextDisplay content={message.content} variant="secondary" />
  }
}
