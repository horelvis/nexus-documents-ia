import { Button } from '@/components/ui/button'
import Icons from '../ui/icons'
import AnimationContainer from "../utils/animation-container"
import { useDemoRequest } from '../demo-request-provider'

const Banner = () => {
    const { open } = useDemoRequest()

    return (
        <div className="flex flex-col relative items-center justify-center mx-auto max-w-5xl w-full py-20 lg:pb-40">

            <AnimationContainer className="flex relative items-center justify-center w-full border-2 border-b-[#8b6af6]/40 border-x-[#8b6af6]/30 border-t-[#8b6af6]/20 rounded-2xl p-5 md:p-8 lg:p-12 lg:rounded-3xl bg-background backdrop-blur-md overflow-hidden">

                <div className="absolute w-full h-4 rounded-full blur-[8.5rem] bg-purple-600 top-0 inset-x-0"></div>
                <div className="absolute w-full h-12 rounded-full blur-[10.5rem] bg-[#8b6af6] bottom-0 inset-x-0"></div>

                <div className="absolute blur-[10.5rem bottom-1/4 left-16 hidden lg:flex items-center justify-center">
                    <Icons.social1 className="w-10 h-10" />
                </div>
                <div className="absolute blur-[10.5rem top-1/4 left-28 hidden lg:flex items-center justify-center">
                    <Icons.social2 className="w-10 h-10" />
                </div>
                <div className="absolute blur-[10.5rem bottom-1/3 right-12 hidden lg:flex items-center justify-center">
                    <Icons.social3 className="w-10 h-10" />
                </div>
                <div className="absolute blur-[10.5rem top-1/3 right-32 hidden lg:flex items-center justify-center">
                    <Icons.social4 className="w-10 h-10" />
                </div>

                <div className="flex flex-col items-center justify-center max-w-2xl mx-auto py-5 lg:py-8">
                    <h2 className="text-2xl lg:text-4xl xl:text-5xl font-semibold text-center !leading-tight">
                        La plataforma IA que necesitan las asesorías laborales
                    </h2>
                    <p className="mt-6 text-center text-muted-foreground max-w-lg">
                        Digitaliza expedientes, vigila convenios y ofrece a tus clientes respuestas inmediatas. <span className="hidden lg:inline-flex">
                            Combina clasificación automática, firma electrónica y alertas inteligentes en un solo flujo.
                        </span>
                    </p>
                    <Button size="lg" className="mt-6" onClick={open}>
                        Agenda una demo
                    </Button>
                </div>
            </AnimationContainer>

        </div>
    )
}

export default Banner
