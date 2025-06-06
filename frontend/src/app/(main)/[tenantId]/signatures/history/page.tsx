export default function SignatureHistoryPage() {
  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Signature History</h1>
          <p className="text-muted-foreground">
            View completed signatures and audit trail
          </p>
        </div>
        
        <div className="min-h-96 flex items-center justify-center border-2 border-dashed border-muted-foreground/25 rounded-lg">
          <p className="text-muted-foreground">Signature history coming soon...</p>
        </div>
      </div>
    </div>
  )
}