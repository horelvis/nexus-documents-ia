"use client"

import { TextDisplay } from "./Generic/TextDisplay"
import { DocumentDisplay } from "./Document/DocumentDisplay"
import { InfoDisplay } from "./SystemMessages/InfoDisplay"
import { WorkflowProgress } from "./Generic/WorkflowProgress"
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
