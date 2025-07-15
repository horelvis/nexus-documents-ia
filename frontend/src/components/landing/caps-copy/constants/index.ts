import { 
    BarChart3, 
    Bot, 
    Calendar, 
    CreditCard, 
    Facebook, 
    Instagram, 
    Linkedin, 
    LucideIcon, 
    PenTool, 
    ShieldCheck, 
    Smartphone, 
    Target, 
    TrendingUp, 
    Twitter, 
    Users, 
    Youtube,
    Zap,
    Lightbulb,
    Sparkles,
    MessageSquare,
    BarChart,
    Settings,
    Share2,
    Search,
    FileText,
    Globe
} from 'lucide-react';

export const badges = [
    {
        id: 1,
        title: "Analytics Insights",
        icon: BarChart3,
    },
    {
        id: 2,
        title: "Content Creation",
        icon: PenTool,
    },
    {
        id: 3,
        title: "Audience Engagement",
        icon: Users,
    },
    {
        id: 4,
        title: "Community Management",
        icon: MessageSquare,
    },
    {
        id: 5,
        title: "Brand Monitoring",
        icon: Search,
    },
    {
        id: 6,
        title: "Performance Reports",
        icon: BarChart,
    },
    {
        id: 7,
        title: "Content Scheduling",
        icon: Calendar,
    },
    {
        id: 8,
        title: "User Feedback",
        icon: Lightbulb,
    },
    {
        id: 9,
        title: "Custom Integrations",
        icon: Settings,
    },
    {
        id: 10,
        title: "Content Optimization",
        icon: Target,
    },
];

export const features = [
    {
        id: 1,
        title: "AI-Powered Caption Generation",
        description: "Generate engaging captions for your social media posts using advanced AI algorithms.",
        icon: Bot,
    },
    {
        id: 2,
        title: "Post Scheduling",
        description: "Schedule your posts across multiple platforms to reach your audience at the optimal time.",
        icon: Calendar,
    },
    {
        id: 3,
        title: "Analytics and Insights",
        description: "Track the performance of your posts and campaigns with detailed analytics and insights.",
        icon: BarChart3,
    },
    {
        id: 4,
        title: "Image Generation",
        description: "Create stunning images for your social media posts using AI-powered image generation.",
        icon: Sparkles,
    },
];

export const offerings = [
    {
        id: 1,
        title: "Trend Prediction",
        description: "Stay ahead of trends with our AI-powered trend prediction algorithms.",
        icon: TrendingUp,
    },
    {
        id: 2,
        title: "Emoji Analysis",
        description: "Understand the emotional impact of your content with emoji sentiment analysis.",
        icon: Lightbulb,
    },
    {
        id: 3,
        title: "Content Recycling",
        description: "Repurpose your best-performing content to maximize reach and engagement.",
        icon: Share2,
    },
    {
        id: 4,
        title: "Competitor Analysis",
        description: "Analyze your competitors' strategies and learn from their successes.",
        icon: Search,
    },
    {
        id: 5,
        title: "Brand Voice Consistency",
        description: "Maintain a consistent brand voice across all your social media platforms.",
        icon: FileText,
    },
    {
        id: 6,
        title: "Global Reach",
        description: "Expand your reach to global audiences with multi-language support.",
        icon: Globe,
    },
];

export const plans = [
    {
        id: 1,
        title: "Free",
        priceMonthly: "₹0",
        priceYearly: "₹0",
        buttonText: "Get Started",
        features: [
            "AI-Powered Caption Generation",
            "Multi-Platform Publishing",
            "Content Calendar",
            "Basic Analytics Insights",
        ],
    },
    {
        id: 2,
        title: "Standard",
        priceMonthly: "₹499",
        priceYearly: "₹2999",
        buttonText: "Get Started",
        features: [
            "AI-Powered Caption Generation",
            "Multi-Platform Publishing",
            "Content Calendar",
            "Advanced Analytics Insights",
            "Image Generation",
            "Post Scheduling",
        ],
    },
    {
        id: 3,
        title: "Premium",
        priceMonthly: "₹999",
        priceYearly: "₹7999",
        buttonText: "Get Started",
        features: [
            "AI-Powered Caption Generation",
            "Multi-Platform Publishing",
            "Content Calendar",
            "Tailored Analytics Insights",
            "Image Generation",
            "Post Scheduling",
            "Custom Integrations",
            "Priority Support",
        ],
    },
];

export const testimonials = [
    {
        name: "Emily Johnson",
        username: "@emilyjohnson",
        review: "CapsAI has transformed the way I create content for my social media. The AI-generated captions are spot-on and save me hours of brainstorming.",
    },
    {
        name: "Michael Chen",
        username: "@michaelchen",
        review: "As a small business owner, CapsAI helps me maintain a consistent social media presence without hiring a full-time social media manager.",
    },
    {
        name: "Sarah Martinez",
        username: "@sarahmartinez",
        review: "The scheduling feature is a game-changer. I can plan my entire week's content in advance and let CapsAI handle the rest.",
    },
    {
        name: "David Thompson",
        username: "@davidthompson",
        review: "The analytics insights have helped me understand my audience better and create more engaging content.",
    },
    {
        name: "Lisa Wang",
        username: "@lisawang",
        review: "CapsAI's image generation feature has elevated my visual content to a whole new level. Highly recommended!",
    },
    {
        name: "Alex Rodriguez",
        username: "@alexrodriguez",
        review: "The AI understands my brand voice perfectly. It's like having a personal content creator who knows my style.",
    },
    {
        name: "Jessica Brown",
        username: "@jessicabrown",
        review: "Customer support is exceptional. They helped me set up my account and optimize my content strategy.",
    },
    {
        name: "Ryan Kim",
        username: "@ryankim",
        review: "The multi-platform publishing saves me so much time. I can reach all my audiences with just one click.",
    },
    {
        name: "Amanda Davis",
        username: "@amandadavis",
        review: "The trend prediction feature keeps me ahead of the curve. My engagement rates have never been higher.",
    },
    {
        name: "Kevin Wilson",
        username: "@kevinwilson",
        review: "CapsAI has streamlined my entire content creation process. From ideation to publication, everything is seamless.",
    },
    {
        name: "Sophia Lee",
        username: "@sophialee",
        review: "The emoji analysis feature is genius! It helps me gauge the emotional response to my content before posting.",
    },
    {
        name: "James Taylor",
        username: "@jamestaylor",
        review: "As an influencer, maintaining authenticity is crucial. CapsAI helps me create genuine content that resonates with my audience.",
    },
];

export const tools = [
    {
        id: 1,
        name: "Instagram",
        info: "Publish and schedule your Instagram posts and stories directly from CapsAI.",
        icon: Instagram,
    },
    {
        id: 2,
        name: "Facebook",
        info: "Manage your Facebook pages and groups with automated posting and engagement tracking.",
        icon: Facebook,
    },
    {
        id: 3,
        name: "Twitter",
        info: "Schedule tweets, track mentions, and analyze your Twitter performance.",
        icon: Twitter,
    },
    {
        id: 4,
        name: "LinkedIn",
        info: "Professional networking made easy with LinkedIn integration for business content.",
        icon: Linkedin,
    },
    {
        id: 5,
        name: "Pinterest",
        info: "Create and schedule pins to drive traffic to your website and increase brand awareness.",
        icon: Target,
    },
    {
        id: 6,
        name: "YouTube",
        info: "Optimize your YouTube channel with automated descriptions and scheduling.",
        icon: Youtube,
    },
];