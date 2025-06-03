import { Metadata } from "next";

export const SITE_CONFIG: Metadata = {
    title: {
        default: "Nexus Document Backend - AI-Powered Document Management",
        template: `%s | Nexus`
    },
    description: "Transform your document management with AI. Upload, search, chat with your documents, and unlock insights with our intelligent document processing platform.",
    icons: {
        icon: [
            {
                url: "/icons/favicon.svg",
                href: "/icons/favicon.svg",
            }
        ]
    },
    openGraph: {
        title: "Nexus Document Backend - AI-Powered Document Management",
        description: "Transform your document management with AI. Upload, search, chat with your documents, and unlock insights with our intelligent document processing platform.",
        images: [
            {
                url: "/assets/og-image.png",
            }
        ]
    },
    twitter: {
        card: "summary_large_image",
        creator: "@nexus",
        title: "Nexus Document Backend - AI-Powered Document Management",
        description: "Transform your document management with AI. Upload, search, chat with your documents, and unlock insights with our intelligent document processing platform.",
        images: [
            {
                url: "/assets/og-image.png",
            }
        ]
    },
    metadataBase: new URL("http://localhost:3000"),
};