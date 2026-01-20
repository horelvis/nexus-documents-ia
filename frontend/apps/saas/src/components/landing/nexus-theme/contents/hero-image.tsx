'use client';
import StaticImages from "../ui/png-images";
import AnimationContainer from "../utils/animation-container";

const HeroImage = () => {
    return (
        <AnimationContainer delay={0.4} className="relative flex items-center justify-center w-full pb-20 mx-auto">
            <div className="flex items-center justify-center max-w-4xl mx-auto">
                <div className="w-full h-full transform hover:scale-105 transition-transform duration-500">
                    <StaticImages.dashboard className="w-full h-full" />
                </div>
            </div>
            <div className="absolute hidden lg:flex items-center justify-center max-w-md bottom-[5%] left-[5%]">
                <StaticImages.leftboard className="w-full h-full" />
            </div>
            <div className="absolute hidden lg:flex items-center justify-center max-w-xs bottom-[15%] right-[5%]">
                <StaticImages.rightboard className="w-full h-full" />
            </div>
        </AnimationContainer>
    )
};

export default HeroImage