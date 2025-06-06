export default function HelpPage() {
  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Help & Support</h1>
          <p className="text-muted-foreground">
            Documentation, tutorials, and support resources
          </p>
        </div>
        
        <div className="min-h-96 flex items-center justify-center border-2 border-dashed border-muted-foreground/25 rounded-lg">
          <p className="text-muted-foreground">Help documentation coming soon...</p>
        </div>
      </div>
    </div>
  )
}