import {
    BarChart3,
    Bot,
    Calendar,
    Cloud,
    LucideIcon,
    Mail,
    PenTool,
    ShieldCheck,
    Users,
    Sparkles,
    MessageSquare,
    Share2,
    Search,
    FileText,
    Globe
} from 'lucide-react';

export const badges = [
    {
        id: 1,
        title: "Reconocimiento Modelo 111",
        icon: FileText,
    },
    {
        id: 2,
        title: "Modelo 190 listo en segundos",
        icon: FileText,
    },
    {
        id: 3,
        title: "Control masivo de nóminas",
        icon: Users,
    },
    {
        id: 4,
        title: "Alertas antes de inspecciones",
        icon: ShieldCheck,
    },
    {
        id: 5,
        title: "Seguimiento de convenios",
        icon: Calendar,
    },
    {
        id: 6,
        title: "Costes salariales en tiempo real",
        icon: BarChart3,
    },
    {
        id: 7,
        title: "Firmas laborales con trazabilidad",
        icon: PenTool,
    },
    {
        id: 8,
        title: "Gestión documental multicliente",
        icon: Share2,
    },
    {
        id: 9,
        title: "Búsqueda semántica laboral",
        icon: Search,
    },
    {
        id: 10,
        title: "Integración con correo y Drive",
        icon: MessageSquare,
    },
];

export const features = [
    {
        id: 1,
        title: "Clasificación automática de nóminas y contratos",
        description: "La IA identifica documentos laborales, detecta anomalías y los archiva en el expediente correcto sin intervención manual.",
        icon: Bot,
    },
    {
        id: 2,
        title: "Panel de obligaciones y modelos",
        description: "Controla modelos 111/190/303, vacaciones y renovaciones en un calendario compartido con alertas proactivas.",
        icon: Calendar,
    },
    {
        id: 3,
        title: "Búsqueda semántica sobre expedientes",
        description: "Encuentra cláusulas, nóminas específicas o comunicaciones sensibles con consultas en lenguaje natural.",
        icon: Search,
    },
    {
        id: 4,
        title: "Workflows con firma y trazabilidad total",
        description: "Envía contratos y anexos a firma, sigue el estado en tiempo real y conserva el histórico con sello legal.",
        icon: Sparkles,
    },
];

export const offerings = [
    {
        id: 1,
        title: "Reconocimiento de modelos 111/190/303",
        description: "Detectamos automáticamente el tipo de documento y rellenamos los metadatos críticos para tu asesoría.",
        icon: FileText,
    },
    {
        id: 2,
        title: "Alertas de inspección y vencimientos",
        description: "Recibe avisos antes de que expire un contrato, caduque una nómina o llegue una inspección.",
        icon: ShieldCheck,
    },
    {
        id: 3,
        title: "Portal compartido con clientes",
        description: "Comparte expedientes con empresas, habilita subida segura de documentos y confirma firmas en minutos.",
        icon: Share2,
    },
    {
        id: 4,
        title: "Panel de convenios y nóminas",
        description: "Visualiza variaciones salariales, pluses y diferencias entre convenios desde un tablero único.",
        icon: BarChart3,
    },
    {
        id: 5,
        title: "Chat IA laboral especializado",
        description: "Resuelve dudas de tu equipo y clientes con un asistente entrenado en legislación laboral española.",
        icon: MessageSquare,
    },
    {
        id: 6,
        title: "Reporting exportable",
        description: "Descarga informes en PDF/Excel con el estado de cada cliente, obligaciones pendientes y actividad reciente.",
        icon: Globe,
    },
];

export const plans = [
    {
        id: 1,
        title: "Free",
        priceMonthly: "$0",
        priceYearly: "$0",
        buttonText: "Start Free",
        features: [
            "Up to 100 documents",
            "1 GB storage",
            "Basic search",
            "Standard support",
            "1 user",
        ],
    },
    {
        id: 2,
        title: "Pro",
        priceMonthly: "$29",
        priceYearly: "$290",
        buttonText: "Try Pro",
        features: [
            "Unlimited documents",
            "100 GB storage",
            "AI-powered advanced search",
            "Intelligent document analysis",
            "Digital signature integration",
            "Up to 10 users",
            "Priority support",
            "API access",
            "Advanced integrations",
        ],
    },
    {
        id: 3,
        title: "Enterprise",
        priceMonthly: "$99",
        priceYearly: "$990",
        buttonText: "Contact Sales",
        features: [
            "Everything in Pro, plus:",
            "1 TB storage",
            "Advanced AI agents",
            "Custom integrations",
            "White-label options",
            "Unlimited users",
            "24/7 dedicated support",
            "Guaranteed SLA",
            "Custom workflows",
            "Advanced analytics",
            "Full audit trails",
        ],
    },
];

export const testimonials = [
    {
        name: "Laura Gómez",
        username: "Socia · Asesoria LG",
        review: "Ahora localizamos cualquier nómina o contrato en segundos. El equipo deja de perder horas buscando en carpetas compartidas.",
    },
    {
        name: "Miguel Ruiz",
        username: "Director · HR Partners",
        review: "La clasificación automática de modelos 111/190 nos ahorra más de 12 horas por semana y reduce errores de filing.",
    },
    {
        name: "Nuria Pérez",
        username: "Responsable laboral · Gestoria Norte",
        review: "Los clientes valoran poder firmar contratos desde el portal y ver el estado sin llamarnos constantemente.",
    },
    {
        name: "Andrés Castillo",
        username: "CEO · Táctica Laboral",
        review: "Instalamos el piloto en dos días y ya tenemos alertas de inspecciones y renovaciones que antes se nos escapaban.",
    },
];

export const tools = [
    {
        id: 1,
        name: "Correo corporativo",
        info: "Procesa adjuntos desde Outlook, Gmail o buzones IMAP dedicados y clasifica automáticamente los documentos.",
        icon: Mail,
    },
    {
        id: 2,
        name: "Google Drive & OneDrive",
        info: "Sincroniza carpetas de clientes y respeta permisos existentes para que todo el despacho trabaje en el mismo sitio.",
        icon: Cloud,
    },
    {
        id: 3,
        name: "ERPs de nóminas",
        info: "Conecta Meta4, A3 o tu herramienta de nóminas para importar resúmenes y justificantes automáticamente.",
        icon: BarChart3,
    },
    {
        id: 4,
        name: "Firma electrónica",
        info: "Lanza workflows con firma avanzada y seguimiento en tiempo real para contratos, anexos y certificados.",
        icon: PenTool,
    },
    {
        id: 5,
        name: "Canales de mensajería",
        info: "Responde a clientes desde Teams o WhatsApp Business sin perder contexto del expediente.",
        icon: MessageSquare,
    },
    {
        id: 6,
        name: "APIs y conectores",
        info: "Sincroniza otros sistemas mediante webhooks y API abierta para personalizar tus flujos laborales.",
        icon: Share2,
    },
];
