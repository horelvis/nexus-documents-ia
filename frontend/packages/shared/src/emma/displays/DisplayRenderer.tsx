"use client"

import { TextDisplay } from "./Generic/TextDisplay"
import { DocumentDisplay } from "./Document/DocumentDisplay"
import { InfoDisplay } from "./SystemMessages/InfoDisplay"
import { WorkflowProgress } from "./Generic/WorkflowProgress"
import { ReasoningDisplay } from "./Generic/ReasoningDisplay"
import { ExplanationPanel } from "./Generic/ExplanationPanel"
import { DisplayRendererProps, DocumentInfo, Citation } from "../types"

export function DisplayRenderer({
  message,
  onDocumentClick = () => {},
  onPreviewClick = () => {},
  isAdmin = false
}: DisplayRendererProps) {
  // Extract documents from metadata.documents or metadata.sources
  const extractDocuments = (): DocumentInfo[] | null => {
    const docs: DocumentInfo[] = []

    if (message.metadata?.documents) {
      docs.push(...message.metadata.documents)
    }

    if (message.metadata?.sources) {
      docs.push(...message.metadata.sources.map(source => ({
        name: source.document || source.title || 'Documento',
        relevanceScore: source.relevance,
        fileType: (source.document || '').split('.').pop() || 'unknown'
      })))
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
      return (
        <WorkflowProgress
          message={message.content}
          progress={message.metadata?.progress || 0}
          currentStep={message.metadata?.step}
          totalSteps={message.metadata?.total_steps}
          currentAgent={message.metadata?.agent}
          steps={message.metadata?.workflow_steps}
          planId={message.metadata?.plan_id}
        />
      )

    case "result":
      const resultSources: Citation[] = [
        ...(message.metadata?.sources || []),
        ...(message.metadata?.citations || [])
      ]

      return (
        <div className="space-y-3">
          <TextDisplay content={message.content} />

          {documents && (
            <DocumentDisplay
              documents={documents}
              onDocumentClick={onDocumentClick}
              onPreviewClick={onPreviewClick}
            />
          )}

          <ReasoningDisplay
            workflowSteps={message.metadata?.workflow_steps}
            sources={resultSources.length > 0 ? resultSources : undefined}
            decisionPath={message.metadata?.decision_path}
            slmPlan={message.metadata?.slmPlan || undefined}
            executionTimeMs={message.metadata?.execution_time_ms}
            confidence={message.metadata?.confidence_score}
            defaultExpanded={false}
          />

          {message.metadata?.explanation && (
            <ExplanationPanel explanation={message.metadata.explanation} />
          )}
        </div>
      )

    case "user":
    case "query":
    default:
      return <TextDisplay content={message.content} variant="secondary" />
  }
}
