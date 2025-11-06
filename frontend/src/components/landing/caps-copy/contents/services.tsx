import Images from "../ui/images";
import AnimationContainer from "../utils/animation-container";

const Services = () => {
    return (
        <div className="flex items-center justify-center w-full py-20">
            <div className="flex flex-col items-center w-full">
                <AnimationContainer>
                    <div className="grid w-full place-items-center grid-cols-1 p-6 md:p-8 md:grid-cols-[.55fr_1fr] rounded-2xl bg-[#121212]/50 border border-border">
                        <div className="flex flex-col items-start justify-center lg:pl-6">
                            <h4 className="text-xl font-semibold lg:text-2xl">
                                Explore our AI-powered solutions
                            </h4>
                            <p className="mt-4 text-neutral-500 lg:text-lg">
                                Transform your document management with intelligent automation, advanced search capabilities, and seamless collaboration tools.
                            </p>
                        </div>
                        <div className="flex items-center justify-center w-full mt-8 sm:mt-0 lg:py-4 lg:px-10">
                            <Images.service className="w-full h-auto md:h-72" />
                        </div>
                    </div>
                </AnimationContainer>

                <AnimationContainer delay={0.1}>
                    <div className="grid grid-cols-1 lg:grid-cols-[1fr_.65fr] w-full gap-8 mt-8">
                        <div className="flex flex-col items-start w-full px-6 py-6 border border-border bg-[#121212]/50 rounded-2xl lg:px-8 lg:py-6">
                            <Images.service2 className="w-full h-auto px-8" />
                            <div className="flex flex-col items-start lg:pl-6">
                                <h5 className="mt-8 text-xl font-semibold lg:text-2xl">
                                    Boost your productivity
                                </h5>
                                <p className="mt-2 lg:max-w-sm text-neutral-500">
                                    Streamline your document workflows with AI-powered organization, automated categorization, and instant retrieval.
                                </p>
                            </div>
                        </div>
                        <div className="flex flex-col items-start w-full px-6 py-6 border border-border bg-[#121212]/50 rounded-2xl lg:px-8 lg:py-8">
                            <h5 className="text-xl font-semibold lg:text-2xl">
                                Intelligent automation
                            </h5>
                            <p className="mt-2 lg:max-w-xs text-neutral-500">
                                Automate document processing with smart extraction, classification, and workflow management.
                            </p>
                            <div className="flex items-center w-full px-16 lg:px-0">
                                <Images.service3 className="w-full h-auto mt-6" />
                            </div>
                        </div>
                    </div>
                </AnimationContainer>

                <AnimationContainer delay={0.2}>
                    <div className="grid grid-cols-1 lg:grid-cols-[0.55fr_1fr] w-full gap-8 mt-8">
                        <div className="flex flex-col items-start justify-center w-full p-6 border lg:p-8 xl:p-10 border-border bg-[#121212]/50 rounded-2xl">
                            <div className="flex items-center w-full px-16 lg:px-0">
                                <Images.service4 className="w-full h-full" />
                            </div>
                            <div className="flex flex-col items-start mt-4 lg:mt-auto lg:pl-2">
                                <h5 className="text-xl font-semibold lg:text-2xl">
                                    Secure and reliable
                                </h5>
                                <p className="mt-2 lg:max-w-sm text-neutral-500">
                                    Enterprise-grade security with end-to-end encryption, access controls, and compliance features.
                                </p>
                            </div>
                        </div>
                        <div className="flex flex-col items-start w-full p-6 border lg:p-8 border-border bg-[#121212]/50 rounded-2xl">
                            <div className="flex flex-col items-start lg:pl-2">
                                <h5 className="text-xl font-semibold lg:text-2xl">
                                    Advanced analytics
                                </h5>
                                <p className="mt-2 lg:max-w-sm text-neutral-500">
                                    Gain valuable insights from your documents with AI-powered analytics and reporting dashboards.
                                </p>
                            </div>
                            <div className="flex items-center w-full mt-8">
                                <Images.service5 className="w-full h-60 px-8" />
                            </div>
                        </div>
                    </div>
                </AnimationContainer>
            </div>
        </div>
    )
};

export default Services