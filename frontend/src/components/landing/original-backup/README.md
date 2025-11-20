# Original Landing Page Backup

Este directorio contiene una copia de respaldo de la landing page original de NexusDocs360 antes de la migración a nexus-theme.

La estructura original de la landing page (landing-header, landing-footer, hero-section, etc.) se ha movido aquí para mantener el código seguro mientras se implementa la nueva versión.

## Contenido
- `landing-header.tsx`: Header original
- `landing-footer.tsx`: Footer original
- `hero-section.tsx`: Hero section original
- `features-section.tsx`: Features section original
- `stats-section.tsx`: Stats section original
- `pricing-section.tsx`: Pricing section original
- `cta-section.tsx`: CTA section original
- `original-page.tsx`: Copia del page.tsx original que usaba estos componentes

## Uso
Estos componentes no deberían usarse en la versión activa de la aplicación a menos que se decida revertir los cambios.
Respaldo creado antes de migrar a nexus-theme como landing page principal.

## Restauración:
Para restaurar la landing original, copiar estos archivos de vuelta a sus ubicaciones originales:
- `original-page.tsx` → `app/page.tsx`
- Los demás archivos ya están en `/components/landing/`