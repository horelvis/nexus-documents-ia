"use client";

import { Background } from '@/components';
import { Pricing } from '@/components';

export default function PricingPage() {
    return (
        <Background>
            <div className="relative flex flex-col items-center justify-center px-4 pt-20">
                <Pricing />
            </div>
        </Background>
    );
}