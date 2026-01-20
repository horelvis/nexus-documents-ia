"use client"

import { TextDisplay } from "./Generic/TextDisplay"
import { DocumentDisplay } from "./Document/DocumentDisplay"
import { InfoDisplay } from "./SystemMessages/InfoDisplay"
import { WorkflowProgress } from "./Generic/WorkflowProgress"
import { ThinkingIndicator } from "./Generic/ThinkingIndicator"
import { DelegationBadge } from "./Generic/DelegationBadge"
import { StreamingTextDisplay } from "./Generic/StreamingTextDisplay"
import { DisplayRendererProps, DocumentInfo } from "../types"

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
      const { metadata } = message
      const hasDelegations = metadata?.delegations && metadata.delegations.length > 0
      const hasStreamingText = metadata?.streamingText && metadata.streamingText.length > 0
      const hasWorkflowSteps = metadata?.workflow_steps && metadata.workflow_steps.length > 0

      // Priority 1: Show streaming text with delegations (ReAct agent response building)
      if (hasStreamingText) {
        return (
          <div className="space-y-3">
            {/* Delegations badges */}
            {hasDelegations && (
              <div className="flex flex-wrap gap-2">
                {metadata.delegations!.map((delegation, idx) => (
                  <DelegationBadge
                    key={`${delegation.agent}-${idx}`}
                    agent={delegation.agent}
                    message={delegation.message}
                    elapsedMs={delegation.elapsedMs}
                    isActive={idx === metadata.delegations!.length - 1 && metadata.isStreaming}
                  />
                ))}
              </div>
            )}
            {/* Streaming text with cursor */}
            <StreamingTextDisplay
              text={metadata.streamingText!}
              isStreaming={metadata.isStreaming || false}
            />
          </div>
        )
      }

      // Priority 2: Show workflow progress (PlanningFlow with steps)
      if (hasWorkflowSteps) {
        return (
          <WorkflowProgress
            message={message.content}
            progress={metadata?.progress || 0}
            currentStep={metadata?.step}
            totalSteps={metadata?.total_steps}
            currentAgent={metadata?.agent}
            steps={metadata?.workflow_steps}
            planId={metadata?.plan_id}
          />
        )
      }

      // Priority 3: Show thinking indicator with stage and delegations
      return (
        <div className="space-y-3">
          {/* Thinking indicator with stage */}
          <ThinkingIndicator
            stage={metadata?.stage}
            message={metadata?.stageMessage}
          />
          {/* Delegations if any (tool usage during thinking) */}
          {hasDelegations && (
            <div className="flex flex-col gap-2 ml-4">
              {metadata.delegations!.map((delegation, idx) => (
                <DelegationBadge
                  key={`${delegation.agent}-${idx}`}
                  agent={delegation.agent}
                  message={delegation.message}
                  elapsedMs={delegation.elapsedMs}
                  isActive={idx === metadata.delegations!.length - 1}
                />
              ))}
            </div>
          )}
        </div>
      )

    case "result":
      return (
        <div className="space-y-3">
          <TextDisplay content={message.content} />

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
