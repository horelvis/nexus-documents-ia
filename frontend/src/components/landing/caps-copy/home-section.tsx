import { Hero, HeroImage, Services, Features, Offerings, Pricing, Testimonial, Tools, Banner } from "./index";

const HomeSection = () => {
    return (
        <div className="relative flex flex-col items-start justify-center w-full mx-auto z-10">

            <div className="mx-auto relative flex flex-col items-center justify-center w-full">

                <Hero />

                <HeroImage />

                <Services />

                <Features />

                <Offerings />

                <Pricing />

                <Testimonial />

                <Tools />

                <Banner />

            </div>

        </div>
    )
};

export default HomeSection