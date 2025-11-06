import { HomeSection, CapsNavbar, SectionContainer } from "@/components/landing/caps-copy"

export default function CopyCapsPage() {
  return (
    <div className="min-h-screen bg-background">
      <CapsNavbar />
      <SectionContainer>
        <div className="relative flex flex-col items-center justify-center px-4 pt-20">
          <HomeSection />
        </div>
      </SectionContainer>
    </div>
  )
}