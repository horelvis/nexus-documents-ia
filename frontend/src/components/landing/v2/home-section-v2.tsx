"use client"

import { SectionContainer } from "./section-container"
import { HeroV2 } from "./hero-v2"
import { HeroImageV2 } from "./hero-image-v2"
import { CompaniesV2 } from "./companies-v2"
import { ServicesV2 } from "./services-v2"
import { FeaturesV2 } from "./features-v2"
import { OfferingsV2 } from "./offerings-v2"
import { PricingV2 } from "./pricing-v2"
import { TestimonialV2 } from "./testimonial-v2"
import { ToolsV2 } from "./tools-v2"
import { BannerV2 } from "./banner-v2"

export function HomeSectionV2() {
  return (
    <SectionContainer>
      <div className="relative flex flex-col items-start justify-center w-full mx-auto">
        <div className="mx-auto relative flex flex-col items-center justify-center w-full">
          <HeroV2 />
          <HeroImageV2 />
          <CompaniesV2 />
          <ServicesV2 />
          <FeaturesV2 />
          <OfferingsV2 />
          <PricingV2 />
          <TestimonialV2 />
          <ToolsV2 />
          <BannerV2 />
        </div>
      </div>
    </SectionContainer>
  )
}