export default function ConversationsPage() {
  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Agent Conversations</h1>
          <p className="text-muted-foreground">
            View and manage conversations with your AI agents
          </p>
        </div>
        
        <div className="min-h-96 flex items-center justify-center border-2 border-dashed border-muted-foreground/25 rounded-lg">
          <p className="text-muted-foreground">Conversation history coming soon...</p>
        </div>
      </div>
    </div>
  )
}