"use client";

import { motion } from 'framer-motion';
import { CreditCard, History, Play, FileText, Sheet, Presentation, FileImage } from 'lucide-react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import Icons from '../ui/icons';
import AnimationContainer from "../utils/animation-container";

const Hero = () => {

    const leftVariants = {
        hidden: { x: -100, opacity: 0 },
        visible: { x: 0, opacity: 1 },
    };

    const rightVariants = {
        hidden: { x: 100, opacity: 0 },
        visible: { x: 0, opacity: 1 },
    };

    return (
        <div className="relative flex flex-col items-center justify-center w-full py-20">

            {/* Background dots pattern - only in hero section */}
            <div className="absolute inset-0 bg-[radial-gradient(rgba(255,255,255,0.2)_1px,transparent_1px)] [background-size:16px_16px] [mask-image:radial-gradient(ellipse_at_center,white_20%,transparent)] hidden lg:flex"></div>

            <div className="absolute flex sm:hidden w-72 h-72 rounded-full bg-primary blur-[10rem] -top-16 left-0 -z-10"></div>

            <div className="flex flex-col items-center justify-center max-w-3xl gap-y-8">
                <div className="flex flex-col items-center justify-center gap-y-4">
                    <AnimationContainer className="relative hidden lg:block overflow-hidden">
                        <Badge size="sm" variant="outline" className="px-3 cursor-pointer">
                            <span className="px-2 py-[0.5px] h-[18px] tracking-wide flex items-center justify-center rounded-full bg-gradient-to-r from-orange-400 to-orange-600 text-[9px] font-medium mr-2 text-white">
                                NEW
                            </span>
                            <span>
                                Discover our latest AI-powered document analysis
                            </span>
                        </Badge>
                    </AnimationContainer>
                    <AnimationContainer delay={0.15}>
                        <h1 className="text-3xl md:text-4xl lg:text-5xl xl:text-6xl font-bold text-center !leading-tight">
                            <span className="text-transparent bg-gradient-to-b from-neutral-50 to-neutral-500 bg-clip-text font-bold !leading-tight">
                                Transform your {" "}
                            </span>
                            <span className="text-transparent bg-gradient-to-b from-primary to-primaryLight bg-clip-text">
                                document management {" "}
                            </span>
                            <span className="text-transparent bg-gradient-to-b from-neutral-50 to-neutral-500 bg-clip-text font-bold !leading-tight">
                                with intelligent AI
                            </span>
                        </h1>
                    </AnimationContainer>
                    <AnimationContainer delay={0.2}>
                        <p className="max-w-xl mt-2 text-base text-center text-accent-foreground/60">
                            Revolutionize your document workflow with AI-powered organization, analysis, and search. <span className="hidden lg:inline">NexusDocs360 provides intelligent document management with semantic search, automated categorization, and real-time insights.</span>
                        </p>
                        <div className="items-center justify-center hidden mt-6 lg:flex gap-x-4">
                            <Button size="lg" asChild>
                                <Link href="/auth/sign-up">
                                    Start for free
                                </Link>
                            </Button>
                            <Button size="lg" variant="secondary" asChild>
                                <Link href="/" className="flex items-center">
                                    See demo
                                    <Play className="w-4 h-4 ml-2" />
                                </Link>
                            </Button>
                        </div>
                    </AnimationContainer>
                    <AnimationContainer delay={0.3}>
                        <div className="flex items-center justify-center mt-6 lg:hidden gap-x-4">
                            <Button asChild>
                                <Link href="/auth/sign-up">
                                    Start for free
                                </Link>
                            </Button>
                            <Button variant="secondary" asChild>
                                <Link href="/" className="flex items-center">
                                    See demo
                                    <Play className="w-4 h-4 ml-2" />
                                </Link>
                            </Button>
                        </div>
                        <div className="flex items-center justify-center mt-2 gap-x-4">
                            <div className="flex items-center gap-x-2">
                                <History className="w-4 h-4 text-muted-foreground" />
                                <span className="text-sm text-muted-foreground">
                                    30-day free trial
                                </span>
                                <span className="text-muted-foreground">
                                    •
                                </span>
                            </div>
                            <div className="flex items-center gap-x-2">
                                <CreditCard className="w-4 h-4 text-muted-foreground" />
                                <span className="text-sm text-muted-foreground">
                                    No card required
                                </span>
                            </div>
                        </div>
                    </AnimationContainer>
                    <div className="hidden w-full lg:block">
                        <motion.div
                            variants={leftVariants}
                            initial="hidden"
                            animate="visible"
                            className="absolute left-1/4 flex items-center justify-center opacity-50 group top-1/4"
                        >
                            <div className="relative p-2 bg-blue-500/20 rounded-lg backdrop-blur-sm">
                                <FileText className="w-6 h-6 text-blue-400" />
                            </div>
                        </motion.div>
                        <motion.div
                            variants={leftVariants}
                            initial="hidden"
                            animate="visible"
                            className="absolute flex items-center justify-center opacity-50 left-1/3 group bottom-1/4"
                        >
                            <div className="relative p-2 bg-green-500/20 rounded-lg backdrop-blur-sm">
                                <Sheet className="w-6 h-6 text-green-400" />
                            </div>
                        </motion.div>
                        <motion.div
                            variants={rightVariants}
                            initial="hidden"
                            animate="visible"
                            className="absolute right-1/4 flex items-center justify-center opacity-50 group top-1/4"
                        >
                            <div className="relative p-2 bg-orange-500/20 rounded-lg backdrop-blur-sm">
                                <Presentation className="w-6 h-6 text-orange-400" />
                            </div>
                        </motion.div>
                        <motion.div
                            variants={rightVariants}
                            initial="hidden"
                            animate="visible"
                            className="absolute flex items-center justify-center opacity-50 right-1/3 group bottom-1/4"
                        >
                            <div className="relative p-2 bg-purple-500/20 rounded-lg backdrop-blur-sm">
                                <FileImage className="w-6 h-6 text-purple-400" />
                            </div>
                        </motion.div>
                    </div>
                </div>
            </div>
        </div>
    )
};

export default Hero