import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Nexus Document Management',
  description: 'Transform your document management with AI-powered insights and automation.',
};

export default function SiteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background">
      {children}
    </div>
  );
}