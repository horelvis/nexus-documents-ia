"use client";

import { ArrowRight } from 'lucide-react';
import Link from 'next/link';
import { Button } from '../ui/button';
import Icons from '../ui/icons';
import Menu from './menu';
import MobileNavbar from './mobile-navbar';
import { UserButton } from '@clerk/nextjs';
import { useAuth } from '@clerk/nextjs';

const Navbar = () => {
    const { isSignedIn, isLoaded } = useAuth();

    // Use `isLoaded` to check if Clerk is loaded (following official pattern)
    if (!isLoaded) {
        return (
            <header className="fixed inset-x-0 top-0 z-[999] w-full h-16 backdrop-blur-md b-background/50 bg-[rgba(4,1,2,0.2)] flex">
                {/* Desktop */}
                <div className="hidden lg:flex items-center justify-between w-full px-4 mx-auto lg:px-8 max-w-7xl">
                    <div className="flex items-center justify-between w-full flex-nowrap">
                        <div className="flex items-center flex-1 lg:flex-none">
                            <Link href="/" className="text-lg font-semibold text-primary">
                                <Icons.logo className="w-auto h-6" />
                            </Link>
                            <div className="items-center hidden ml-4 lg:flex">
                                <Menu />
                            </div>
                        </div>
                        <div className="items-center hidden lg:flex gap-x-4">
                            {/* Loading skeleton */}
                            <div className="w-16 h-8 bg-muted/50 rounded animate-pulse" />
                            <div className="w-24 h-8 bg-muted/50 rounded animate-pulse" />
                        </div>
                    </div>
                </div>
                {/* Mobile */}
                <MobileNavbar />
            </header>
        );
    }

    return (
        <header className="fixed inset-x-0 top-0 z-[999] w-full h-16 backdrop-blur-md b-background/50 bg-[rgba(4,1,2,0.2)] flex">

            {/* Desktop */}
            <div className="hidden lg:flex items-center justify-between w-full px-4 mx-auto lg:px-8 max-w-7xl">
                <div className="flex items-center justify-between w-full flex-nowrap">
                    <div className="flex items-center flex-1 lg:flex-none">
                        <Link href="/" className="text-lg font-semibold text-primary">
                            <Icons.logo className="w-auto h-6" />
                        </Link>
                        <div className="items-center hidden ml-4 lg:flex">
                            <Menu />
                        </div>
                    </div>
                    <div className="items-center hidden lg:flex gap-x-4">
                        {isSignedIn ? (
                           <UserButton />
                        ) : (
                            <>
                                <Button size="sm" variant="secondary" asChild>
                                    <Link href="/auth/login">
                                        Login
                                    </Link>
                                </Button>
                                <Button size="sm" variant="white" asChild>
                                    <Link href="/dashboard">
                                        Get Started
                                        <ArrowRight className="w-4 h-4 ml-2" />
                                    </Link>
                                </Button>
                            </>
                        )}
                    </div>
                </div>
            </div>

            {/* Mobile */}
            <MobileNavbar />

        </header>
    )
};

export default Navbar
