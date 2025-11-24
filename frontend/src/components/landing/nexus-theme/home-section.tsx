import { Hero, HeroImage, Features, Offerings, Tools, Banner } from "./index";
import { PricingSection } from "@/components/landing/pricing-section";

const HomeSection = () => {
    return (
        <div className="relative flex flex-col items-start justify-center w-full mx-auto z-10">

            <div className="mx-auto relative flex flex-col items-center justify-center w-full">

                <Hero />

                <HeroImage />

                <Features />

                <Offerings />

                <PricingSection />

                <Tools />

                <Banner />

            </div>

        </div>
    )
};

export default HomeSection
