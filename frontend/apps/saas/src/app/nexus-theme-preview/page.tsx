import { HomeSection, NexusNavbar, SectionContainer } from "@/components/landing/nexus-theme"
import { DemoRequestProvider } from "@/components/landing/nexus-theme/demo-request-provider"

export default function NexusThemePreviewPage() {
  return (
    <DemoRequestProvider>
      <div className="min-h-screen bg-background">
        <NexusNavbar />
        <SectionContainer>
          <div className="relative flex flex-col items-center justify-center px-4 pt-20">
            <HomeSection />
          </div>
        </SectionContainer>
      </div>
    </DemoRequestProvider>
  )
}
