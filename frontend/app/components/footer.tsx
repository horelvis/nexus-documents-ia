// frontend/app/components/footer.tsx
import { Link } from '@remix-run/react';

export function Footer() {
  return (
    <footer className="py-6 px-6 mt-auto bg-card border-t border-border">
      <div className="container mx-auto flex flex-col md:flex-row justify-between items-center text-sm text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} Remix SaaS. All rights reserved.</p>
        <nav className="flex gap-4 mt-2 md:mt-0">
          <Link to="/terms" className="hover:text-primary">Terms of Service</Link>
          <Link to="/privacy" className="hover:text-primary">Privacy Policy</Link>
        </nav>
      </div>
    </footer>
  );
}
