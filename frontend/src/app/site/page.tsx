import { 
  Navbar,
  Hero,
  Companies,
  Services,
  Features,
  Offerings,
  Pricing,
  Banner,
  Testimonial,
  Tools,
  Newsletter,
  Footer,
  Background,
  SectionContainer
} from '@/components';

export default function SitePage() {
  return (
    <div className="relative">
      <Navbar />
      
      <Background>
        <main className="relative">
          <SectionContainer>
            <Hero />
          </SectionContainer>
          
          <SectionContainer>
            <Companies />
          </SectionContainer>
          
          <SectionContainer>
            <Services />
          </SectionContainer>
          
          <SectionContainer>
            <Features />
          </SectionContainer>
          
          <SectionContainer>
            <Offerings />
          </SectionContainer>
          
          <SectionContainer>
            <Pricing />
          </SectionContainer>
          
          <SectionContainer>
            <Banner />
          </SectionContainer>
          
          <SectionContainer>
            <Testimonial />
          </SectionContainer>
          
          <SectionContainer>
            <Tools />
          </SectionContainer>
          
          <SectionContainer>
            <Newsletter />
          </SectionContainer>
        </main>
        
        <Footer />
      </Background>
    </div>
  );
}