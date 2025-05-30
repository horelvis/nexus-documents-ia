// frontend/app/components/sidebar.tsx
import { Link, useLocation } from '@remix-run/react';
import { cn } from '#app/utils/misc';
import { Button, buttonVariants } from '#app/components/ui/button'; // Assuming you have these
import { ScrollArea } from '#app/components/ui/scroll-area'; // For potentially many links
import {
  LayoutDashboard, // Icon for Dashboard
  Settings,       // Icon for Settings
  CreditCard,     // Icon for Billing
  Shield,         // Icon for Admin
  PanelLeftOpen,  // Icon for collapse/expand
  PanelRightOpen,
} from 'lucide-react';
import { useState } from 'react';

// Route path imports (ensure these are correct based on your project structure)
import { ROUTE_PATH as ADMIN_PATH } from '#app/routes/admin+/_layout';
import { ROUTE_PATH as DASHBOARD_PATH } from '#app/routes/dashboard+/_layout';
import { ROUTE_PATH as DASHBOARD_SETTINGS_PATH } from '#app/routes/dashboard+/settings';
import { ROUTE_PATH as DASHBOARD_SETTINGS_BILLING_PATH } from '#app/routes/dashboard+/settings.billing';

interface SidebarProps {
  isAdmin: boolean; // To conditionally show Admin link
  className?: string;
}

export function Sidebar({ isAdmin, className }: SidebarProps) {
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const navItems = [
    {
      to: DASHBOARD_PATH,
      icon: <LayoutDashboard className="h-5 w-5" />,
      text: 'Dashboard',
      adminOnly: false,
    },
    {
      to: DASHBOARD_SETTINGS_PATH,
      icon: <Settings className="h-5 w-5" />,
      text: 'Configuración',
      adminOnly: false,
    },
    {
      to: DASHBOARD_SETTINGS_BILLING_PATH,
      icon: <CreditCard className="h-5 w-5" />,
      text: 'Facturación',
      adminOnly: false,
    },
    {
      to: ADMIN_PATH,
      icon: <Shield className="h-5 w-5" />,
      text: 'Admin',
      adminOnly: true,
    },
  ];

  return (
    <div
      className={cn(
        'h-full bg-card border-r flex flex-col transition-all duration-300 ease-in-out',
        isCollapsed ? 'w-16' : 'w-64',
        className,
      )}
    >
      <div
        className={cn(
          'h-[60px] border-b flex items-center px-4',
          isCollapsed ? 'justify-center' : 'justify-between',
        )}
      >
        {!isCollapsed && (
          <span className="text-lg font-semibold">Menú</span>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setIsCollapsed(!isCollapsed)}
          className={cn(isCollapsed ? 'mx-auto' : '')}
        >
          {isCollapsed ? <PanelRightOpen className="h-5 w-5" /> : <PanelLeftOpen className="h-5 w-5" />}
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <nav className="py-4 px-2 space-y-1">
          {navItems.map((item) => {
            if (item.adminOnly && !isAdmin) {
              return null;
            }
            const isActive = location.pathname.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                prefetch="intent"
                className={cn(
                  buttonVariants({
                    variant: isActive ? 'secondary' : 'ghost',
                    size: 'default', // or 'lg'
                  }),
                  'w-full flex items-center',
                  isCollapsed ? 'justify-center px-0' : 'justify-start gap-3 px-3',
                )}
                title={item.text}
              >
                {item.icon}
                {!isCollapsed && <span>{item.text}</span>}
              </Link>
            );
          })}
        </nav>
      </ScrollArea>
    </div>
  );
}
