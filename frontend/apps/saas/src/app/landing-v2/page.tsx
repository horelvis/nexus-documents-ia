import { HomeSection } from "@/components/landing/nexus-theme"
import { DemoRequestProvider } from "@/components/landing/nexus-theme/demo-request-provider"

export default function LandingV2Page() {
  return (
    <DemoRequestProvider>
      <div className="min-h-screen bg-background">
        <HomeSection />
      </div>
    </DemoRequestProvider>
  )
}
