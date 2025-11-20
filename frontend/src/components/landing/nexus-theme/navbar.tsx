"use client"

import { ArrowRight, Menu, X } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { Button } from '../../ui/button';
import Icons from './ui/icons';

const navigation = [
  { name: 'Solución', href: '#features' },
  { name: 'Casos de uso', href: '#services' },
  { name: 'Planes', href: '#pricing' },
  { name: 'Recursos', href: '#about' },
];

const NexusNavbar = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const scrollToSection = (href: string) => {
    if (href.startsWith('#')) {
      const element = document.getElementById(href.substring(1));
      element?.scrollIntoView({ behavior: 'smooth' });
      setMobileMenuOpen(false);
    }
  };

  return (
    <header className="fixed inset-x-0 top-0 z-[999] w-full h-16 backdrop-blur-md bg-background/50 bg-[rgba(4,1,2,0.2)] flex">
      {/* Desktop */}
      <div className="hidden lg:flex items-center justify-between w-full px-4 mx-auto lg:px-8 max-w-7xl">
        <div className="flex items-center justify-between w-full flex-nowrap">
          <div className="flex items-center flex-1 lg:flex-none">
            <Link href="/" className="text-lg font-semibold text-primary">
              <Icons.logo className="w-auto h-6" />
            </Link>
            <div className="items-center hidden ml-8 lg:flex gap-x-6">
              {navigation.map((item) => (
                <button
                  key={item.name}
                  onClick={() => scrollToSection(item.href)}
                  className="text-sm font-medium leading-6 text-foreground hover:text-primary transition-colors"
                >
                  {item.name}
                </button>
              ))}
            </div>
          </div>
          <div className="items-center hidden lg:flex gap-x-4">
            <Button size="sm" variant="secondary" asChild>
              <Link href="/auth/sign-in">
                Iniciar sesión
              </Link>
            </Button>
            <Button size="sm" asChild>
              <Link href="/pricing">
                Solicitar demo
                <ArrowRight className="w-4 h-4 ml-2" />
              </Link>
            </Button>
          </div>
        </div>
      </div>

      {/* Mobile */}
      <div className="flex items-center justify-between w-full px-4 mx-auto lg:hidden max-w-7xl">
        <div className="flex items-center">
          <Link href="/" className="text-lg font-semibold text-primary">
            <Icons.logo className="w-auto h-6" />
          </Link>
        </div>
        <div className="flex items-center">
          <button
            type="button"
            className="inline-flex items-center justify-center p-2 rounded-md text-foreground hover:text-primary hover:bg-accent transition-colors"
            onClick={() => setMobileMenuOpen(true)}
          >
            <span className="sr-only">Open main menu</span>
            <Menu className="w-6 h-6" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileMenuOpen && (
        <div className="lg:hidden">
          <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm" />
          <div className="fixed inset-y-0 right-0 z-50 w-full overflow-y-auto bg-background px-6 py-6 sm:max-w-sm border-l border-border">
            <div className="flex items-center justify-between">
              <Link href="/" className="text-lg font-semibold text-primary">
                <Icons.logo className="w-auto h-6" />
              </Link>
              <button
                type="button"
                className="rounded-md p-2 text-foreground hover:text-primary hover:bg-accent transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                <span className="sr-only">Close menu</span>
                <X className="w-6 h-6" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-6 flow-root">
              <div className="-my-6 divide-y divide-border">
                <div className="space-y-2 py-6">
                  {navigation.map((item) => (
                    <button
                      key={item.name}
                      onClick={() => scrollToSection(item.href)}
                      className="block w-full text-left px-3 py-2 text-base font-semibold leading-7 text-foreground hover:text-primary hover:bg-accent transition-colors rounded-md"
                    >
                      {item.name}
                    </button>
                  ))}
                </div>
                <div className="py-6 space-y-2">
                  <Button variant="secondary" asChild className="w-full">
                    <Link href="/auth/sign-in">
                      Iniciar sesión
                    </Link>
                  </Button>
                  <Button asChild className="w-full">
                    <Link href="/pricing">
                      Solicitar demo
                      <ArrowRight className="w-4 h-4 ml-2" />
                    </Link>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};

export default NexusNavbar;
