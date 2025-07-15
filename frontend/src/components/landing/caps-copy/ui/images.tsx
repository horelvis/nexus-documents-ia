import { LucideProps } from "lucide-react";

const Images = {
    dashboard: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-xl border border-gray-200 dark:border-gray-700 flex items-center justify-center`}>
            <div className="text-gray-500 dark:text-gray-400 text-lg font-medium">Dashboard Preview</div>
        </div>
    ),
    leftboard: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-green-50 to-emerald-100 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center justify-center`}>
            <div className="text-gray-500 dark:text-gray-400 text-sm">Analytics</div>
        </div>
    ),
    rightboard: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-purple-50 to-pink-100 dark:from-purple-900/20 dark:to-pink-900/20 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center justify-center`}>
            <div className="text-gray-500 dark:text-gray-400 text-sm">Reports</div>
        </div>
    ),
    lines: (props: LucideProps) => (
        <svg {...props} viewBox="0 0 400 200" fill="none">
            <path d="M0 100 Q200 50 400 100" stroke="currentColor" strokeWidth="2" opacity="0.3" />
            <path d="M0 120 Q200 70 400 120" stroke="currentColor" strokeWidth="2" opacity="0.2" />
            <path d="M0 80 Q200 30 400 80" stroke="currentColor" strokeWidth="2" opacity="0.2" />
        </svg>
    ),
    cone: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center`}>
            <span className="text-gray-600 dark:text-gray-400 font-bold">COMPANY</span>
        </div>
    ),
    ctwo: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center`}>
            <span className="text-gray-600 dark:text-gray-400 font-bold">BRAND</span>
        </div>
    ),
    cthree: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center`}>
            <span className="text-gray-600 dark:text-gray-400 font-bold">PARTNER</span>
        </div>
    ),
    service: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-lg flex items-center justify-center`}>
            <div className="text-blue-600 dark:text-blue-400 text-lg font-medium">Service</div>
        </div>
    ),
    service2: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 rounded-lg flex items-center justify-center`}>
            <div className="text-green-600 dark:text-green-400 text-lg font-medium">Business</div>
        </div>
    ),
    service3: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 rounded-lg flex items-center justify-center`}>
            <div className="text-purple-600 dark:text-purple-400 text-lg font-medium">Speed</div>
        </div>
    ),
    service4: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20 rounded-lg flex items-center justify-center`}>
            <div className="text-orange-600 dark:text-orange-400 text-lg font-medium">Safe</div>
        </div>
    ),
    service5: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-indigo-50 to-indigo-100 dark:from-indigo-900/20 dark:to-indigo-800/20 rounded-lg flex items-center justify-center`}>
            <div className="text-indigo-600 dark:text-indigo-400 text-lg font-medium">Control</div>
        </div>
    ),
    grad: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-b from-transparent via-blue-500/20 to-transparent rounded-lg`}>
        </div>
    ),
    offer: (props: LucideProps) => (
        <div {...props} className={`${props.className} bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900/20 dark:to-gray-800/20 rounded-lg flex items-center justify-center`}>
            <div className="text-gray-600 dark:text-gray-400 text-lg font-medium">Offerings</div>
        </div>
    ),
};

export default Images;