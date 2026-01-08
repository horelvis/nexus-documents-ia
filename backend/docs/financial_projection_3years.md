# NexusDocs360 - Proyección Financiera a 3 Años

## Resumen Ejecutivo

Este documento presenta la proyección financiera de NexusDocs360 para los próximos 3 años, basada en el modelo de suscripción SaaS con planes Basic y Pro, considerando los costes de infraestructura en Google Cloud Platform.

| Métrica | Valor |
|---------|-------|
| **Break-even** | Mes 11 (~100 usuarios) |
| **Margen bruto estable** | 80%+ después del Año 1 |
| **ROI a 3 años** | +90% sobre inversión total |
| **ARR Año 3** | $630,000 |
| **Valoración potencial** (5x ARR) | ~$3.15M |

---

## 1. Supuestos Base

### 1.1 Modelo de Precios

| Plan | Precio Mensual | Precio Anual (-20%) | Target |
|------|----------------|---------------------|--------|
| **Basic** | €19/usuario | €182/usuario | Freelancers, PYMES |
| **Pro** | €49/usuario | €470/usuario | Equipos medianos |
| **Enterprise** | €99+/usuario | Custom | Corporaciones |

### 1.2 Parámetros del Modelo

| Parámetro | Valor | Notas |
|-----------|-------|-------|
| Mix de planes | 70% Basic / 30% Pro | Conservador |
| Precio medio ponderado | €28/usuario/mes (~$30) | |
| Churn mensual | 5% | Estándar SaaS B2B |
| Crecimiento mensual (Año 1-1.5) | 15% | Fase de tracción |
| Crecimiento mensual (Año 1.5-3) | 8% | Fase de escala |

### 1.3 Infraestructura Base (Escenario 2)

| Componente | Configuración | Coste Mensual |
|------------|---------------|---------------|
| Frontend | e2-standard-2 | $49 |
| Backend | n2-standard-8 | $280 |
| PostgreSQL | Cloud SQL db-standard-2 | $90 |
| Redis | Memorystore 2GB | $70 |
| GPU vLLM | g2-standard-8 (1x L4) | $550 |
| Storage GCS | 500GB Standard | $10 |
| Network + LB | | $30 |
| **TOTAL BASE** | | **$1,080/mes** |

---

## 2. Proyección por Trimestres

### 2.1 Año 1 - Fase de Lanzamiento

| Trimestre | Usuarios Activos | Ingresos | Coste Infra | Margen Bruto | Margen % |
|-----------|------------------|----------|-------------|--------------|----------|
| Q1 | 25 | $2,250 | $3,240 | **-$990** | -44% |
| Q2 | 45 | $4,050 | $3,240 | **$810** | 20% |
| Q3 | 80 | $7,200 | $3,780 | **$3,420** | 47% |
| Q4 | 140 | $12,600 | $4,320 | **$8,280** | 66% |
| **Total Año 1** | | **$26,100** | **$14,580** | **$11,520** | **44%** |

**Hitos Año 1:**
- Q1: Lanzamiento beta, primeros clientes early adopters
- Q2: Product-market fit, inicio de crecimiento orgánico
- Q3: Primeras referencias y casos de éxito
- Q4: Equipo de ventas inicial, expansión marketing

### 2.2 Año 2 - Fase de Crecimiento

| Trimestre | Usuarios Activos | Ingresos | Coste Infra | Margen Bruto | Margen % |
|-----------|------------------|----------|-------------|--------------|----------|
| Q5 | 220 | $19,800 | $5,400 | $14,400 | 73% |
| Q6 | 340 | $30,600 | $6,480 | $24,120 | 79% |
| Q7 | 480 | $43,200 | $8,100 | $35,100 | 81% |
| Q8 | 650 | $58,500 | $10,800 | $47,700 | 82% |
| **Total Año 2** | | **$152,100** | **$30,780** | **$121,320** | **80%** |

**Hitos Año 2:**
- Q5: Infraestructura HA (alta disponibilidad)
- Q6: Expansión a nuevos mercados verticales
- Q7: Programa de partners/integradores
- Q8: Preparación para ronda de financiación

### 2.3 Año 3 - Fase de Escala

| Trimestre | Usuarios Activos | Ingresos | Coste Infra | Margen Bruto | Margen % |
|-----------|------------------|----------|-------------|--------------|----------|
| Q9 | 850 | $76,500 | $14,040 | $62,460 | 82% |
| Q10 | 1,100 | $99,000 | $18,360 | $80,640 | 81% |
| Q11 | 1,400 | $126,000 | $23,760 | $102,240 | 81% |
| Q12 | 1,750 | $157,500 | $29,700 | $127,800 | 81% |
| **Total Año 3** | | **$459,000** | **$85,860** | **$373,140** | **81%** |

**Hitos Año 3:**
- Q9: Multi-región (EU + US)
- Q10: Enterprise features completas
- Q11: Certificaciones (SOC2, ISO 27001)
- Q12: Preparación para expansión internacional

---

## 3. Resumen Acumulado 3 Años

```
                    AÑO 1        AÑO 2        AÑO 3        TOTAL 3 AÑOS
                    ────────────────────────────────────────────────────
Usuarios (fin año)  140          650          1,750

Ingresos           $26,100      $152,100     $459,000     $637,200
Coste Infra        $14,580      $30,780      $85,860      $131,220
────────────────────────────────────────────────────────────────────────
MARGEN BRUTO       $11,520      $121,320     $373,140     $505,980
Margen %           44%          80%          81%          79%
```

---

## 4. Escala de Infraestructura

### 4.1 Crecimiento de Costes por Usuarios

| Rango Usuarios | Configuración Requerida | Coste/mes |
|----------------|-------------------------|-----------|
| 0-50 | Escenario 2 base | $1,080 |
| 50-150 | + Redis 5GB, SQL upgrade | $1,260 |
| 150-300 | + 2ª GPU (HA), SQL HA | $1,800 |
| 300-500 | + n2-standard-16, CDN | $2,700 |
| 500-1,000 | Multi-region, LB global | $4,500 |
| 1,000-2,000 | Kubernetes cluster, 3 GPUs | $9,000 |
| 2,000+ | Enterprise infra dedicada | $15,000+ |

### 4.2 Detalle de Escalado por Componente

| Componente | 50 usuarios | 300 usuarios | 1,000 usuarios | 2,000 usuarios |
|------------|-------------|--------------|----------------|----------------|
| Compute (Backend) | $280 | $560 | $1,200 | $2,400 |
| GPU/vLLM | $550 | $1,100 | $1,650 | $2,750 |
| PostgreSQL | $90 | $180 | $400 | $800 |
| Redis | $70 | $170 | $300 | $500 |
| Storage | $10 | $40 | $150 | $400 |
| Network/CDN | $30 | $100 | $300 | $650 |
| **TOTAL** | **$1,030** | **$2,150** | **$4,000** | **$7,500** |

---

## 5. Análisis de Sensibilidad

### 5.1 Escenario Conservador (10% crecimiento mensual)

| Año | Usuarios (fin) | Ingresos Anuales | Margen Bruto |
|-----|----------------|------------------|--------------|
| 1 | 85 | $18,900 | $6,120 |
| 2 | 320 | $86,400 | $64,800 |
| 3 | 950 | $256,500 | $199,800 |
| **Total** | | **$361,800** | **$270,720** |

### 5.2 Escenario Base (15%/8% crecimiento)

| Año | Usuarios (fin) | Ingresos Anuales | Margen Bruto |
|-----|----------------|------------------|--------------|
| 1 | 140 | $26,100 | $11,520 |
| 2 | 650 | $152,100 | $121,320 |
| 3 | 1,750 | $459,000 | $373,140 |
| **Total** | | **$637,200** | **$505,980** |

### 5.3 Escenario Optimista (20% crecimiento mensual)

| Año | Usuarios (fin) | Ingresos Anuales | Margen Bruto |
|-----|----------------|------------------|--------------|
| 1 | 220 | $39,600 | $24,300 |
| 2 | 1,100 | $297,000 | $243,000 |
| 3 | 3,500 | $945,000 | $756,000 |
| **Total** | | **$1,281,600** | **$1,023,300** |

---

## 6. Flujo de Caja Mensual

### 6.1 Evolución del Cash Flow

```
Mes      Usuarios    Ingresos    Costes      Mensual     Acumulado
─────────────────────────────────────────────────────────────────────
1        10          $300        $1,080      -$780       -$780
3        18          $540        $1,080      -$540       -$2,160
6        35          $1,050      $1,080      -$30        -$4,200
9        70          $2,100      $1,260      $840        -$2,700
11       100         $3,000      $1,260      $1,740      -$990     ← Break-even
12       140         $4,200      $1,440      $2,760      $1,770
18       340         $10,200     $1,800      $8,400      $42,000
24       650         $19,500     $2,700      $16,800     $163,000
30       1,100       $33,000     $4,500      $28,500     $340,000
36       1,750       $52,500     $9,000      $43,500     $506,000
```

### 6.2 Gráfico de Evolución (ASCII)

```
Cash Flow Acumulado ($K)
    │
500 │                                                          ●
    │                                                      ●
400 │                                                  ●
    │                                              ●
300 │                                          ●
    │                                      ●
200 │                                  ●
    │                              ●
100 │                          ●
    │                      ●
  0 │──────────●──────●───────────────────────────────────────────
    │      ●
-10 │  ●
    └─────────────────────────────────────────────────────────────
         3    6    9   12   15   18   21   24   27   30   33   36  Mes
                       ↑
                  Break-even
                  (Mes 11)
```

---

## 7. Métricas SaaS Clave

### 7.1 Métricas al Final del Año 3

| Métrica | Valor | Benchmark SaaS | Estado |
|---------|-------|----------------|--------|
| **ARR** (Annual Recurring Revenue) | $630,000 | - | - |
| **MRR** (Monthly Recurring Revenue) | $52,500 | - | - |
| **ARPU** (Avg Revenue Per User) | $30/mes | $25-50 | ✅ Óptimo |
| **Gross Margin** | 81% | >70% | ✅ Excelente |
| **Net Revenue Retention** | 95% | >100% | ⚠️ Mejorable |
| **LTV** (Lifetime Value) | $600 | - | - |
| **CAC** máximo recomendado | $200 | LTV/3 | - |
| **LTV:CAC Ratio** | 3:1 | >3:1 | ✅ Saludable |
| **Payback Period** | <7 meses | <12 meses | ✅ Bueno |

### 7.2 Evolución de Métricas por Año

| Métrica | Año 1 | Año 2 | Año 3 |
|---------|-------|-------|-------|
| ARR | $50,400 | $234,000 | $630,000 |
| MRR (fin año) | $4,200 | $19,500 | $52,500 |
| Usuarios | 140 | 650 | 1,750 |
| ARPU | $30 | $30 | $30 |
| Gross Margin | 44% | 80% | 81% |
| Churn Anual | 46% | 46% | 46% |

---

## 8. Inversión vs Retorno (ROI)

### 8.1 Estructura de Inversión

| Concepto | Año 1 | Año 2 | Año 3 | Total |
|----------|-------|-------|-------|-------|
| **Infraestructura GCP** | $14,580 | $30,780 | $85,860 | $131,220 |
| **Desarrollo (equipo)** | $50,000 | $30,000 | $40,000 | $120,000 |
| **Marketing/Sales** | $10,000 | $25,000 | $50,000 | $85,000 |
| **Operaciones/Legal** | $5,000 | $10,000 | $20,000 | $35,000 |
| **Total Inversión** | **$79,580** | **$95,780** | **$195,860** | **$371,220** |

### 8.2 Retorno sobre Inversión

| Año | Inversión | Ingresos | ROI Anual | ROI Acumulado |
|-----|-----------|----------|-----------|---------------|
| 1 | $79,580 | $26,100 | -67% | -67% |
| 2 | $95,780 | $152,100 | +59% | +2% |
| 3 | $195,860 | $459,000 | +134% | **+72%** |

### 8.3 Punto de Equilibrio (Break-even)

- **Break-even operativo**: Mes 11 (~100 usuarios)
- **Break-even total** (incluyendo desarrollo): Mes 18 (~340 usuarios)
- **ROI positivo acumulado**: Mes 24

---

## 9. Límites por Plan y Unit Economics

### 9.1 Estructura de Límites

| Recurso | Basic (€19) | Pro (€49) | Coste Real/Unidad |
|---------|-------------|-----------|-------------------|
| Almacenamiento GCS | 5 GB | 50 GB | $0.02/GB/mes |
| Documentos | 500/mes | Ilimitados | ~$0.01/doc |
| Consultas Emma AI | 100/mes | 1,000/mes | $0.02-0.05/consulta |
| Búsquedas semánticas | 500/mes | Ilimitadas | ~$0.001/búsqueda |
| Firmas digitales | 10/mes | 100/mes | $1-2/firma |
| Extracción entidades | 50 docs/mes | Ilimitado | ~$0.03/doc |
| Usuarios por tenant | 3 | 10 | - |
| Retención historial | 30 días | 1 año | ~$0.01/MB/mes |
| API Access | No | Sí | - |

### 9.2 Unit Economics por Plan

| Métrica | Basic (€19) | Pro (€49) |
|---------|-------------|-----------|
| Coste infra estimado/usuario | $8 | $15 |
| Margen bruto | 58% | 69% |
| Contribución mensual | $11 | $34 |
| LTV (20 meses avg) | $220 | $680 |

### 9.3 Pricing de Overages

| Recurso | Precio Overage |
|---------|----------------|
| Consultas AI extra | €0.05/consulta |
| Storage extra | €0.50/GB/mes |
| Firmas extra | €1.50/firma |
| Usuarios extra | €10/usuario/mes |

---

## 10. Comparativa de Mercado

### 10.1 Posicionamiento de Precios

| Competidor | Plan Básico | Plan Pro | Notas |
|------------|-------------|----------|-------|
| DocuSign | $15/mes | $40/mes | Solo firma digital |
| PandaDoc | $19/mes | $49/mes | Documentos + firma |
| Notion AI | $20/mes | $20/mes | Solo IA, sin firma |
| ChatPDF | $20/mes | - | Solo chat PDF |
| **NexusDocs360** | **€19/mes** | **€49/mes** | **IA + Docs + Firma** |

### 10.2 Diferenciadores de Valor

| Feature | NexusDocs360 | Competencia |
|---------|--------------|-------------|
| Emma AI (RAG 7 capas) | ✅ | Parcial |
| Búsqueda semántica | ✅ | Parcial |
| Extracción entidades | ✅ | ❌ |
| Firma digital integrada | ✅ | Separado |
| Multi-tenant nativo | ✅ | Variable |
| Chain of Thought | ✅ | ❌ |
| On-premise option | ✅ Enterprise | ❌ |

---

## 11. Riesgos y Mitigaciones

### 11.1 Riesgos Identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Crecimiento menor al esperado | Media | Alto | Escenario conservador viable |
| Aumento costes GPU | Media | Medio | Contratos CUD, alternativas (RunPod) |
| Competencia agresiva | Alta | Medio | Diferenciación por IA avanzada |
| Churn elevado | Media | Alto | Mejora onboarding, success team |
| Problemas técnicos escala | Baja | Alto | Arquitectura probada, monitoreo |

### 11.2 Plan de Contingencia

**Si crecimiento < 10% mensual:**
1. Reducir a Spot VMs para GPU (-60% coste)
2. Consolidar servicios en menos instancias
3. Pivotar a modelo usage-based puro
4. Coste mínimo viable: ~$500/mes

**Si churn > 8% mensual:**
1. Implementar programa de customer success
2. Añadir features de retención (gamification, reporting)
3. Ofrecer contratos anuales con descuento mayor

---

## 12. Conclusiones y Recomendaciones

### 12.1 Viabilidad del Modelo

| Aspecto | Evaluación | Comentario |
|---------|------------|------------|
| Pricing | ✅ Competitivo | Alineado con mercado, margen saludable |
| Infraestructura | ✅ Escalable | GCP permite crecer on-demand |
| Unit Economics | ✅ Sostenible | LTV:CAC > 3:1 |
| Break-even | ✅ Alcanzable | ~11 meses con 100 usuarios |
| ROI 3 años | ✅ Positivo | +72% sobre inversión total |

### 12.2 Recomendaciones

1. **Iniciar con Spot VMs** para GPU hasta alcanzar 50+ usuarios
2. **Ofrecer descuento anual 20%** para mejorar cash flow y reducir churn
3. **Implementar overages** desde el inicio para proteger márgenes
4. **Firmar CUD 1-year** al alcanzar break-even para reducir costes 20%
5. **Monitorear ARPU** y ajustar mix de planes según demanda real

### 12.3 Próximos Pasos

- [ ] Definir estructura legal y fiscal
- [ ] Configurar Stripe para suscripciones
- [ ] Implementar sistema de límites en backend
- [ ] Preparar landing page con pricing
- [ ] Establecer métricas de tracking (MRR, Churn, LTV)

---

## Anexo: Glosario de Términos

| Término | Definición |
|---------|------------|
| **ARR** | Annual Recurring Revenue - Ingresos recurrentes anualizados |
| **MRR** | Monthly Recurring Revenue - Ingresos recurrentes mensuales |
| **ARPU** | Average Revenue Per User - Ingreso promedio por usuario |
| **LTV** | Lifetime Value - Valor total del cliente durante su vida |
| **CAC** | Customer Acquisition Cost - Coste de adquisición de cliente |
| **Churn** | Tasa de cancelación de suscripciones |
| **CUD** | Committed Use Discount - Descuento por compromiso de uso en GCP |
| **Gross Margin** | Margen bruto = (Ingresos - Coste Infra) / Ingresos |

---

*Documento generado: Enero 2026*
*Versión: 1.0*
*Próxima revisión: Abril 2026*
