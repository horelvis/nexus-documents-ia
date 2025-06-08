# 🎯 Configuración de Stripe para Nexus

Esta guía te ayudará a configurar Stripe para el sistema de suscripciones de Nexus.

## 📋 Pasos de Configuración

### 1. **Configurar Variables de Entorno**

Agrega estas variables a tu archivo `.env`:

```bash
# Stripe Configuration
STRIPE_SECRET_KEY=sk_test_... # o sk_live_... para producción
STRIPE_PUBLIC_KEY=pk_test_... # o pk_live_... para producción
STRIPE_WEBHOOK_SECRET=whsec_... # Webhook endpoint secret

# Frontend URLs
FRONTEND_URL=http://localhost:3000
NEXT_PUBLIC_STRIPE_PRO_PRICE_ID=price_... # Se obtendrá del script
NEXT_PUBLIC_STRIPE_ENTERPRISE_PRICE_ID=price_... # Se obtendrá del script
NEXT_PUBLIC_STRIPE_PRO_YEARLY_PRICE_ID=price_... # Se obtendrá del script
NEXT_PUBLIC_STRIPE_ENTERPRISE_YEARLY_PRICE_ID=price_... # Se obtendrá del script
```

### 2. **Crear Productos y Precios en Stripe**

Ejecuta el script de configuración:

```bash
cd backend
python scripts/create_stripe_products.py
```

Este script creará:

#### **📦 Productos:**
- **Nexus Free**: Plan gratuito
- **Nexus Pro**: Plan profesional ($29/mes o $290/año)
- **Nexus Enterprise**: Plan empresarial ($99/mes o $990/año)

#### **💰 Precios:**
- Pro Monthly: $29.00/mes
- Pro Yearly: $290.00/año (17% descuento)
- Enterprise Monthly: $99.00/mes  
- Enterprise Yearly: $990.00/año (17% descuento)

### 3. **Configurar Variables con Price IDs**

Después de ejecutar el script, copia los Price IDs generados a tus variables de entorno:

```bash
# Backend (.env)
STRIPE_PRO_PRICE_ID=price_1234567890abcdef
STRIPE_ENTERPRISE_PRICE_ID=price_0987654321fedcba

# Frontend (.env.local)
NEXT_PUBLIC_STRIPE_PRO_PRICE_ID=price_1234567890abcdef
NEXT_PUBLIC_STRIPE_ENTERPRISE_PRICE_ID=price_0987654321fedcba
NEXT_PUBLIC_STRIPE_PRO_YEARLY_PRICE_ID=price_yearly123456
NEXT_PUBLIC_STRIPE_ENTERPRISE_YEARLY_PRICE_ID=price_yearly654321
```

### 4. **Configurar Webhooks en Stripe Dashboard**

1. Ve a [Stripe Dashboard > Webhooks](https://dashboard.stripe.com/webhooks)
2. Clic en "Add endpoint"
3. Agrega la URL: `https://tu-dominio.com/api/v1/webhooks/stripe`
4. Selecciona estos eventos:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`

5. Copia el **Webhook Signing Secret** a `STRIPE_WEBHOOK_SECRET`

### 5. **Ejecutar Migraciones de Base de Datos**

```bash
cd backend
python -m alembic upgrade head
```

### 6. **Configurar Customer Portal (Opcional)**

Para permitir que los usuarios gestionen sus suscripciones:

```bash
cd backend
python scripts/configure_stripe_portal.py
```

## 🔧 Estructura del Flujo

### **Flujo de Usuario:**

```
Landing → Pricing → Stripe Checkout → Pago → 
Signup → Express Onboarding → Dashboard Premium
```

### **Componentes Principales:**

1. **`/pricing`** - Página de selección de planes
2. **`/checkout/success`** - Confirmación post-pago
3. **`/auth/sign-up`** - Registro con datos de Stripe
4. **`/welcome`** - Onboarding express para usuarios pagos

## 🧪 Testing

### **Tarjetas de Prueba Stripe:**

```bash
# Pago exitoso
4242 4242 4242 4242

# Pago fallido
4000 0000 0000 0002

# Requiere autenticación 3D Secure
4000 0027 6000 3184
```

### **Webhooks Locales:**

Para testing local de webhooks:

```bash
# Instalar Stripe CLI
brew install stripe/stripe-cli/stripe

# Login y forward webhooks
stripe login
stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
```

## 📊 Monitoreo

### **Logs de Stripe:**

- Dashboard > Logs para ver todas las transacciones
- Webhooks > tu endpoint para ver eventos recibidos

### **Métricas Importantes:**

- Conversion rate (pricing → checkout)
- Checkout abandonment
- Failed payments
- Subscription churn

## 🚨 Troubleshooting

### **Errores Comunes:**

1. **"Invalid price ID"**
   - Verificar que los Price IDs estén correctos en las variables de entorno
   - Asegurar que los precios estén activos en Stripe

2. **"Webhook signature verification failed"**
   - Verificar `STRIPE_WEBHOOK_SECRET`
   - Comprobar que la URL del webhook sea correcta

3. **"Customer not found"**
   - El usuario debe tener `stripe_customer_id` en la base de datos
   - Verificar que el sync con Stripe funcione correctamente

### **Debug Mode:**

```bash
# Backend logs
export DEBUG=true

# Stripe CLI events
stripe logs tail
```

## 🔐 Seguridad

### **Variables Sensibles:**
- Nunca commits las Secret Keys a Git
- Usar diferentes keys para test/producción
- Rotar webhooks secrets periódicamente

### **Validación:**
- Siempre verificar webhook signatures
- Validar amounts en el backend
- Verificar ownership antes de modificar suscripciones

## 📚 Recursos

- [Stripe Documentation](https://stripe.com/docs)
- [Stripe Checkout](https://stripe.com/docs/checkout)
- [Stripe Customer Portal](https://stripe.com/docs/billing/customer-portal)
- [Webhooks Best Practices](https://stripe.com/docs/webhooks/best-practices)

## ✅ Checklist Final

- [ ] Variables de entorno configuradas
- [ ] Productos y precios creados en Stripe
- [ ] Price IDs agregados a variables de entorno  
- [ ] Webhooks configurados y funcionando
- [ ] Migraciones de BD ejecutadas
- [ ] Testing con tarjetas de prueba exitoso
- [ ] Customer Portal configurado (opcional)
- [ ] Flujo completo end-to-end probado