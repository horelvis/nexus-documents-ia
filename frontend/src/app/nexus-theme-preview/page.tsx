import { HomeSection, NexusNavbar, SectionContainer } from "@/components/landing/nexus-theme"

export default function NexusThemePreviewPage() {
  return (
    <div className="min-h-screen bg-background">
      <NexusNavbar />
      <SectionContainer>
        <div className="relative flex flex-col items-center justify-center px-4 pt-20">
          <HomeSection />
        </div>
      </SectionContainer>
    </div>
  )
}