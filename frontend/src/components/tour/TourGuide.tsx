'use client';

import React, { useEffect, useRef, useState } from 'react';
import { driver, Driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { usePathname } from 'next/navigation';

export function TourGuide({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const driverRef = useRef<Driver | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    // Only run on dashboard
    if (pathname.includes('/dashboard')) {
      const tourSeen = localStorage.getItem('nexus_tour_v2');
      
      if (!tourSeen) {
        console.log('TourGuide: Initializing tour...');
        
        // Configure Driver
        const driverObj = driver({
          showProgress: true,
          animate: true,
          allowClose: true,
          doneBtnText: 'Entendido',
          nextBtnText: 'Siguiente',
          prevBtnText: 'Anterior',
          popoverClass: 'nexus-driver-popover', // Custom class for styling
          steps: [
            { 
              element: '.dashboard-welcome', 
              popover: { 
                title: 'Bienvenido a Nexus!', 
                description: 'Nexus Documents IA te ayuda a gestionar, analizar y firmar documentos con el poder de la IA.', 
                side: 'bottom', 
                align: 'start' 
              } 
            },
            { 
              element: '#main-sidebar', 
              popover: { 
                title: 'Navegación Principal', 
                description: 'Usa la barra lateral para acceder a tus Documentos, Agentes IA, Flujos de Trabajo y Configuración.', 
                side: 'right', 
                align: 'start' 
              } 
            },
            { 
              element: '.quick-actions-panel', 
              popover: { 
                title: 'Acciones Rápidas', 
                description: 'Sube documentos, inicia chats con Emma AI o crea flujos de trabajo con un solo clic.', 
                side: 'left', 
                align: 'start' 
              } 
            },
            { 
              element: '.user-nav-trigger', 
              popover: { 
                title: 'Tu Perfil', 
                description: 'Gestiona tu cuenta, facturación y preferencias desde aquí.', 
                side: 'right', 
                align: 'end' 
              } 
            }
          ],
          onDestroyed: () => {
             console.log('TourGuide: Destroyed');
             localStorage.setItem('nexus_tour_v2', 'true');
          },
          onCloseClick: () => {
             console.log('TourGuide: Closed');
            localStorage.setItem('nexus_tour_v2', 'true');
            driverObj.destroy();
          }
        });

        driverRef.current = driverObj;

        // Start tour with a delay to ensure elements are rendered
        const timer = setTimeout(() => {
            console.log('TourGuide: Starting drive...');
            
            // Check if elements exist
            const welcome = document.querySelector('.dashboard-welcome');
            const sidebar = document.querySelector('#main-sidebar');
            console.log('TourGuide: Elements check:', { 
                welcome: !!welcome, 
                sidebar: !!sidebar 
            });

            if (welcome) {
                driverObj.drive();
            } else {
                console.warn('TourGuide: .dashboard-welcome element not found, retrying in 1s...');
                setTimeout(() => {
                     if (document.querySelector('.dashboard-welcome')) {
                         driverObj.drive();
                     }
                }, 1000);
            }
        }, 1000);

        return () => {
            clearTimeout(timer);
            if (driverObj.isActive()) {
                driverObj.destroy();
            }
        };
      }
    }
  }, [pathname, mounted]);

  return <>{children}</>;
}
