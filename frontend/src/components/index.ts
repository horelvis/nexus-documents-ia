// Header components
import Navbar from "./header/navbar";
import Menu from "./header/menu";
import MobileNavbar from "./header/mobile-navbar";

// UI components
import { Button } from "./ui/button";
import Icons from "./ui/icons";
import { Badge } from "./ui/badge";

// Page sections
import HomeSection from "./sections/home-section";
import LoginSection from "./sections/login-section";
import RegisterSection from "./sections/register-section";

// Utils
import AnimationContainer from "./utils/animation-container";
import Background from "./utils/background";
import SectionContainer from "./utils/section-container";

// Site/Landing page components
import {
    Hero,
    Banner,
    Companies,
    Features,
    Newsletter,
    Offerings,
    Pricing,
    Services,
    Testimonial,
    Tools,
    HeroImage,
    Footer
} from "./site";

// Providers
import { ApiAuthProvider } from "./providers/api-auth-provider";

export {
    // Header components
    Navbar,
    Menu,
    MobileNavbar,

    // UI components
    Button,
    Icons,
    Badge,

    // Page sections (auth, etc.)
    HomeSection,
    LoginSection,
    RegisterSection,

    // Utils
    AnimationContainer,
    Background,
    SectionContainer,

    // Site/Landing page components
    HeroImage,
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

    // Providers
    ApiAuthProvider
}