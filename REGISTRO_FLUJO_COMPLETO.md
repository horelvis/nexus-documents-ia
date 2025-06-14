# Flujo Completo de Registro de Usuario con Suscripción

## 1. Flujo General Paso a Paso

### Flujo para Usuario con Plan Gratuito
1. **Usuario accede a la página de registro** → `/auth/sign-up`
2. **Completa registro con Clerk** → Datos básicos (email, password)
3. **Redirección a página de bienvenida** → `/welcome`
4. **Sincronización con backend** → Se crea usuario y tenant en BD
5. **Onboarding multi-paso** → Recopilación de datos adicionales
6. **Selección de plan** → Puede elegir plan premium si desea
7. **Activación** → Usuario activo con plan Free

### Flujo para Usuario con Plan de Pago
1. **Usuario visita página de precios** → `/pricing`
2. **Selecciona plan Pro/Enterprise** → Click en "Get Started"
3. **Redirección a registro** → `/auth/sign-up?plan=pro`
4. **Registro con Clerk** → Completa datos básicos
5. **Sincronización con backend** → Se crea usuario y tenant
6. **Redirección a checkout** → Se genera sesión de Stripe para el usuario registrado
7. **Pago en Stripe** → Usuario completa el pago
8. **Webhook actualiza suscripción** → Se asocia la suscripción al usuario
9. **Activación** → Usuario activo con plan de pago

### Diagrama de Flujo
```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Pricing   │────▶│ Select Plan  │────▶│    Clerk     │
│    Page     │     │  (Pro/Ent)   │     │   Sign Up    │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                    ┌──────────────┐             ▼
                    │  Direct      │     ┌──────────────┐
                    │  Sign Up     │────▶│   Backend    │
                    │  (Free)      │     │  Sync User   │
                    └──────────────┘     └──────┬───────┘
                                                 │
                                         ┌───────▼───────┐
                                         │ Plan de Pago? │
                                         └───────┬───────┘
                                               Yes│ No
                                    ┌─────────────┴─────────────┐
                                    ▼                           ▼
                            ┌──────────────┐            ┌──────────────┐
                            │   Stripe     │            │  Onboarding  │
                            │  Checkout    │            │   Wizard     │
                            └──────┬───────┘            └──────┬───────┘
                                   │                           │
                                   ▼                           ▼
                            ┌──────────────┐            ┌──────────────┐
                            │   Webhook    │            │  Dashboard   │
                            │  Update Sub  │            │   (Free)     │
                            └──────┬───────┘            └──────────────┘
                                   │
                                   ▼
                            ┌──────────────┐
                            │  Dashboard   │
                            │   (Pro)      │
                            └──────────────┘
```

## 2. Código de Ejemplo

### Frontend (Next.js)

#### A. Página de Precios con Selección de Plan
```typescript
// app/(main)/pricing/page.tsx
'use client'

import { useState } from 'react'
import { useUser } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { toast } from 'sonner'

const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: 0,
    features: ['5 documentos', 'Chat básico', '1 usuario'],
    cta: 'Comenzar Gratis'
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 10,
    priceId: 'price_1234567890', // ID de Stripe Price
    features: ['Documentos ilimitados', 'IA avanzada', '5 usuarios'],
    cta: 'Comenzar Prueba'
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Personalizado',
    features: ['Todo en Pro', 'Soporte prioritario', 'Usuarios ilimitados'],
    cta: 'Contactar Ventas'
  }
]

export default function PricingPage() {
  const { isSignedIn, user } = useUser()
  const router = useRouter()
  const [loading, setLoading] = useState<string | null>(null)

  const handlePlanSelection = async (plan: typeof PLANS[0]) => {
    setLoading(plan.id)

    try {
      // Plan gratuito: ir directo a registro/dashboard
      if (plan.id === 'free') {
        if (isSignedIn) {
          router.push('/dashboard')
        } else {
          router.push('/auth/sign-up')
        }
        return
      }

      // Plan enterprise: ir a contacto
      if (plan.id === 'enterprise') {
        router.push('/contact?plan=enterprise')
        return
      }

      // Plan de pago: redirigir a registro con plan seleccionado
      if (isSignedIn) {
        // Usuario ya registrado, crear checkout directamente
        const response = await fetch('/api/stripe/create-checkout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            priceId: plan.priceId,
            planId: plan.id,
            successUrl: `${window.location.origin}/dashboard?welcome=true`,
            cancelUrl: `${window.location.origin}/pricing`
          })
        })

        const data = await response.json()
        if (!response.ok) {
          throw new Error(data.detail || 'Error al crear sesión de pago')
        }
        
        // Redirigir a Stripe Checkout
        window.location.href = data.url
      } else {
        // Usuario nuevo, primero registro con plan seleccionado
        router.push(`/auth/sign-up?plan=${plan.id}`)
      }
    } catch (error) {
      console.error('Error:', error)
      toast.error('Error al procesar la solicitud')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="container mx-auto py-12">
      <h1 className="text-4xl font-bold text-center mb-12">
        Elige tu Plan
      </h1>

      <div className="grid md:grid-cols-3 gap-8">
        {PLANS.map((plan) => (
          <Card key={plan.id} className="p-6">
            <h2 className="text-2xl font-bold mb-4">{plan.name}</h2>
            <div className="text-3xl font-bold mb-6">
              {typeof plan.price === 'number' 
                ? `$${plan.price}/mes` 
                : plan.price}
            </div>
            <ul className="space-y-2 mb-8">
              {plan.features.map((feature, i) => (
                <li key={i} className="flex items-center">
                  <span className="mr-2">✓</span> {feature}
                </li>
              ))}
            </ul>
            <Button
              onClick={() => handlePlanSelection(plan)}
              disabled={loading === plan.id}
              className="w-full"
              variant={plan.id === 'pro' ? 'default' : 'outline'}
            >
              {loading === plan.id ? 'Procesando...' : plan.cta}
            </Button>
          </Card>
        ))}
      </div>
    </div>
  )
}
```

#### B. Componente de Registro con Checkout
```typescript
// app/auth/sign-up/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { SignUp } from '@clerk/nextjs'
import { useSearchParams } from 'next/navigation'
import { Card } from '@/components/ui/card'
import { CheckCircle } from 'lucide-react'

export default function SignUpPage() {
  const searchParams = useSearchParams()
  const planId = searchParams.get('plan')
  const [selectedPlan, setSelectedPlan] = useState(planId || 'free')

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-4">
        {/* Mostrar plan seleccionado si viene de pricing */}
        {planId && planId !== 'free' && (
          <Card className="p-6 bg-blue-50 border-blue-200">
            <div className="flex items-center space-x-3">
              <div>
                <h3 className="font-semibold">Plan {planId} seleccionado</h3>
                <p className="text-sm text-gray-600">
                  Completa tu registro para continuar con el pago
                </p>
              </div>
            </div>
          </Card>
        )}

        {/* Componente de Clerk SignUp */}
        <SignUp 
          afterSignUpUrl={`/welcome?plan=${selectedPlan}`}
          appearance={{
            elements: {
              rootBox: 'mx-auto',
              card: 'shadow-none'
            }
          }}
        />
      </div>
    </div>
  )
}
```

#### C. Página de Bienvenida y Sincronización
```typescript
// app/(main)/welcome/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { useUser } from '@clerk/nextjs'
import { useRouter, useSearchParams } from 'next/navigation'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'

interface OnboardingData {
  firstName: string
  lastName: string
  companyName: string
  taxId: string
  selectedPlan?: string
}

export default function WelcomePage() {
  const { user } = useUser()
  const router = useRouter()
  const searchParams = useSearchParams()
  const planId = searchParams.get('plan') || 'free'
  
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [syncCompleted, setSyncCompleted] = useState(false)
  const [data, setData] = useState<OnboardingData>({
    firstName: user?.firstName || '',
    lastName: user?.lastName || '',
    companyName: '',
    taxId: '',
    selectedPlan: planId
  })

  useEffect(() => {
    if (user) {
      syncUser()
    }
  }, [user])

  const syncUser = async () => {
    try {
      const response = await fetch('/api/auth/sync-user', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clerkUserId: user!.id,
          email: user!.emailAddresses[0].emailAddress,
          firstName: user!.firstName,
          lastName: user!.lastName
        })
      })

      if (!response.ok) {
        throw new Error('Error al sincronizar usuario')
      }

      const userData = await response.json()
      setSyncCompleted(true)
      
      // Si el usuario ya completó el onboarding
      if (userData.onboardingCompleted) {
        router.push('/dashboard')
        return
      }

      // Si seleccionó un plan de pago, ir directo al checkout después del sync
      if (planId !== 'free' && syncCompleted) {
        await createCheckoutSession()
      }
    } catch (error) {
      console.error('Error:', error)
      toast.error('Error al sincronizar usuario')
    }
  }

  const createCheckoutSession = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/stripe/create-checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          planId: data.selectedPlan,
          successUrl: `${window.location.origin}/dashboard?welcome=true&plan=${data.selectedPlan}`,
          cancelUrl: `${window.location.origin}/welcome`
        })
      })

      const checkoutData = await response.json()
      if (!response.ok) {
        throw new Error(checkoutData.detail || 'Error al crear sesión de pago')
      }

      // Redirigir a Stripe Checkout
      window.location.href = checkoutData.url
    } catch (error) {
      console.error('Error:', error)
      toast.error('Error al procesar el pago')
      setLoading(false)
    }
  }

  const handleSubmit = async () => {
    setLoading(true)
    
    try {
      // Actualizar perfil del usuario
      const response = await fetch('/api/users/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          firstName: data.firstName,
          lastName: data.lastName,
          companyName: data.companyName,
          taxId: data.taxId,
          onboardingCompleted: true
        })
      })

      if (!response.ok) {
        throw new Error('Error al actualizar perfil')
      }

      // Completar onboarding
      toast.success('¡Bienvenido!')
      router.push('/dashboard')
    } catch (error) {
      console.error('Error:', error)
      toast.error('Error al completar el registro')
    } finally {
      setLoading(false)
    }
  }

  const renderStep = () => {
    // Si es plan de pago y ya se sincronizó, mostrar loading mientras redirige a Stripe
    if (planId !== 'free' && syncCompleted && step === 1) {
      return (
        <Card className="p-6">
          <h2 className="text-2xl font-bold mb-4">Procesando...</h2>
          <p className="text-gray-600 mb-6">
            Redirigiendo a Stripe para completar el pago del plan {planId}...
          </p>
          <div className="flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
          </div>
        </Card>
      )
    }

    switch (step) {
      case 1:
        // Para plan free, mostrar bienvenida
        if (planId === 'free') {
          return (
            <Card className="p-6">
              <h2 className="text-2xl font-bold mb-4">¡Bienvenido!</h2>
              <p className="text-gray-600 mb-6">
                Vamos a configurar tu cuenta en unos simples pasos.
              </p>
              <Button onClick={() => setStep(2)} className="w-full">
                Comenzar
              </Button>
            </Card>
          )
        }
        
        // Para plan de pago, esperar sincronización
        return (
          <Card className="p-6">
            <h2 className="text-2xl font-bold mb-4">Preparando tu cuenta...</h2>
            <p className="text-gray-600 mb-6">
              Estamos configurando tu cuenta para el plan {planId}.
            </p>
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
            </div>
          </Card>
        )

      case 2:

      case 3:
        return (
          <Card className="p-6">
            <h2 className="text-2xl font-bold mb-4">Información de la Empresa</h2>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="firstName">Nombre</Label>
                  <Input
                    id="firstName"
                    value={data.firstName}
                    onChange={(e) => setData({ ...data, firstName: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="lastName">Apellido</Label>
                  <Input
                    id="lastName"
                    value={data.lastName}
                    onChange={(e) => setData({ ...data, lastName: e.target.value })}
                    required
                  />
                </div>
              </div>
              
              <div>
                <Label htmlFor="companyName">Nombre de la Empresa</Label>
                <Input
                  id="companyName"
                  value={data.companyName}
                  onChange={(e) => setData({ ...data, companyName: e.target.value })}
                  required
                />
              </div>
              
              <div>
                <Label htmlFor="taxId">CIF/NIF</Label>
                <Input
                  id="taxId"
                  value={data.taxId}
                  onChange={(e) => setData({ ...data, taxId: e.target.value })}
                  required
                />
              </div>

              <Button 
                type="submit" 
                className="w-full"
                disabled={loading}
              >
                {loading ? 'Procesando...' : 'Completar Registro'}
              </Button>
            </form>
          </Card>
        )
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {renderStep()}
      </div>
    </div>
  )
}
```

### Backend (FastAPI)

#### A. Modelos de Base de Datos
```python
# backend/app/db/models.py
from sqlalchemy import Column, String, Boolean, Float, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    company_name = Column(String)
    tax_id = Column(String)
    stripe_customer_id = Column(String, unique=True, index=True)
    onboarding_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    tenant = relationship("Tenant", back_populates="users")
    subscriptions = relationship("Subscription", back_populates="user")

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    bucket_name = Column(String, unique=True, nullable=False)
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    users = relationship("User", back_populates="tenant")
    subscriptions = relationship("Subscription", back_populates="tenant")

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_subscription_id = Column(String, unique=True, index=True)
    stripe_customer_id = Column(String, index=True)
    plan = Column(String, nullable=False)  # free, pro, enterprise
    status = Column(String, nullable=False)  # active, canceled, past_due
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    user = relationship("User", back_populates="subscriptions")
    tenant = relationship("Tenant", back_populates="subscriptions")
```

#### B. Endpoints de Stripe
```python
# backend/app/api/v1/stripe.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
from typing import Optional
import os

router = APIRouter(prefix="/stripe", tags=["stripe"])
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Configuración de planes
PLANS = {
    "free": {
        "name": "Free Plan",
        "price": 0,
        "features": ["5 documents", "Basic chat", "1 user"]
    },
    "pro": {
        "name": "Pro Plan", 
        "price_id": os.getenv("STRIPE_PRO_PRICE_ID"),
        "price": 10,
        "features": ["Unlimited documents", "Advanced AI", "5 users"],
        "trial_days": 14
    },
    "enterprise": {
        "name": "Enterprise Plan",
        "custom": True,
        "features": ["Everything in Pro", "Priority support", "Unlimited users"]
    }
}

@router.post("/create-checkout")
async def create_checkout_session(
    request: dict,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Crear sesión de checkout en Stripe para suscripción
    """
    try:
        # Validar plan
        plan_id = request.get("planId")
        if plan_id not in PLANS or plan_id == "free":
            raise HTTPException(400, "Invalid plan selected")
        
        plan = PLANS[plan_id]
        
        # Metadatos para el checkout
        metadata = {
            "plan_id": plan_id,
            "user_id": request.get("userId") or "pending",
            "environment": os.getenv("ENVIRONMENT", "development")
        }
        
        # Crear o recuperar cliente de Stripe
        customer = None
        if current_user:
            user = await db.get(User, current_user["id"])
            if user and user.stripe_customer_id:
                customer = user.stripe_customer_id
            else:
                # Crear nuevo cliente en Stripe
                stripe_customer = stripe.Customer.create(
                    email=current_user["email"],
                    name=f"{current_user.get('firstName', '')} {current_user.get('lastName', '')}",
                    metadata={"clerk_user_id": current_user["clerk_id"]}
                )
                customer = stripe_customer.id
                
                # Guardar en BD
                if user:
                    user.stripe_customer_id = customer
                    await db.commit()
        
        # Configurar línea de checkout
        line_items = [{
            "price": plan["price_id"],
            "quantity": 1
        }]
        
        # Configurar trial si aplica
        subscription_data = {}
        if plan.get("trial_days"):
            subscription_data["trial_period_days"] = plan["trial_days"]
            subscription_data["trial_settings"] = {
                "end_behavior": {
                    "missing_payment_method": "cancel"
                }
            }
        
        # Crear sesión de checkout
        session = stripe.checkout.Session.create(
            customer=customer,
            payment_method_types=["card"],
            line_items=line_items,
            mode="subscription",
            success_url=request["successUrl"],
            cancel_url=request["cancelUrl"],
            metadata=metadata,
            subscription_data=subscription_data if subscription_data else None,
            allow_promotion_codes=True,
            billing_address_collection="required",
            customer_creation="always" if not customer else None,
            payment_method_collection="if_required" if plan.get("trial_days") else "always"
        )
        
        return {"url": session.url, "sessionId": session.id}
        
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Error creating checkout session: {str(e)}")

@router.get("/verify-checkout/{session_id}")
async def verify_checkout_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Verificar estado de una sesión de checkout
    """
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["customer", "subscription"]
        )
        
        if session.payment_status != "paid" and not session.subscription:
            raise HTTPException(400, "Payment not completed")
        
        return {
            "status": session.payment_status,
            "customerEmail": session.customer_details.email,
            "plan": session.metadata.get("plan_id"),
            "subscriptionId": session.subscription.id if session.subscription else None,
            "customerId": session.customer
        }
        
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Invalid session: {str(e)}")

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Webhook para procesar eventos de Stripe
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    
    # Procesar eventos
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_checkout_completed(session, db)
    
    elif event["type"] == "customer.subscription.created":
        subscription = event["data"]["object"]
        await handle_subscription_created(subscription, db)
    
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        await handle_subscription_updated(subscription, db)
    
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await handle_subscription_deleted(subscription, db)
    
    return {"status": "success"}

async def handle_checkout_completed(session: dict, db: AsyncSession):
    """
    Manejar checkout completado
    """
    customer_id = session["customer"]
    subscription_id = session["subscription"]
    plan_id = session["metadata"].get("plan_id")
    
    # Buscar usuario por email o customer_id
    customer = stripe.Customer.retrieve(customer_id)
    user = await db.query(User).filter(
        (User.email == customer.email) | 
        (User.stripe_customer_id == customer_id)
    ).first()
    
    if user:
        # Actualizar customer_id si no existe
        if not user.stripe_customer_id:
            user.stripe_customer_id = customer_id
        
        # Crear suscripción en BD
        if subscription_id and plan_id:
            subscription = await db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if not subscription:
                subscription = Subscription(
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=customer_id,
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    plan=plan_id,
                    status="active"
                )
                db.add(subscription)
        
        await db.commit()

@router.post("/create-customer-portal")
async def create_customer_portal(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Crear sesión del portal de cliente de Stripe
    """
    user = await db.get(User, current_user["id"])
    
    if not user or not user.stripe_customer_id:
        raise HTTPException(400, "No customer found")
    
    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{os.getenv('FRONTEND_URL')}/dashboard/billing"
        )
        
        return {"url": session.url}
        
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Error creating portal session: {str(e)}")
```

#### C. Endpoints de Autenticación y Usuario
```python
# backend/app/api/v1/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import hashlib
from typing import Optional

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/sync-user")
async def sync_user(
    request: dict,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Sincronizar usuario de Clerk con base de datos local
    """
    clerk_user_id = request["clerkUserId"]
    email = request["email"]
    
    # Buscar usuario existente
    user = await db.query(User).filter(
        User.clerk_user_id == clerk_user_id
    ).first()
    
    if not user:
        # Crear nuevo tenant para el usuario
        org_name = email.split("@")[0].lower().replace(".", "-")
        bucket_hash = hashlib.md5(f"{org_name}-{clerk_user_id}".encode()).hexdigest()[:8]
        bucket_name = f"org-{org_name}-{bucket_hash}"
        
        tenant = Tenant(
            name=f"{request.get('firstName', '')} {request.get('lastName', '')} Organization",
            bucket_name=bucket_name,
            settings={
                "max_storage_gb": 5,  # Free plan default
                "max_users": 1,
                "features": ["basic_chat", "document_upload"]
            }
        )
        db.add(tenant)
        await db.flush()
        
        # Crear usuario
        user = User(
            clerk_user_id=clerk_user_id,
            email=email,
            first_name=request.get("firstName"),
            last_name=request.get("lastName"),
            tenant_id=tenant.id,
            onboarding_completed=False
        )
        db.add(user)
        
        # Crear bucket en GCS
        try:
            from app.services.storage_service import create_tenant_bucket
            await create_tenant_bucket(bucket_name)
        except Exception as e:
            print(f"Error creating bucket: {e}")
    
    else:
        # Actualizar usuario existente
        user.first_name = request.get("firstName", user.first_name)
        user.last_name = request.get("lastName", user.last_name)
        user.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(user)
    
    # Obtener suscripción activa
    subscription = await db.query(Subscription).filter(
        Subscription.user_id == user.id,
        Subscription.status == "active"
    ).first()
    
    return {
        "id": str(user.id),
        "email": user.email,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "tenantId": str(user.tenant_id),
        "onboardingCompleted": user.onboarding_completed,
        "subscription": {
            "plan": subscription.plan,
            "status": subscription.status
        } if subscription else None
    }

@router.put("/users/profile")
async def update_user_profile(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Actualizar perfil del usuario
    """
    user = await db.get(User, current_user["id"])
    
    if not user:
        raise HTTPException(404, "User not found")
    
    # Actualizar campos
    user.first_name = request.get("firstName", user.first_name)
    user.last_name = request.get("lastName", user.last_name)
    user.company_name = request.get("companyName", user.company_name)
    user.tax_id = request.get("taxId", user.tax_id)
    user.onboarding_completed = request.get("onboardingCompleted", user.onboarding_completed)
    user.updated_at = datetime.utcnow()
    
    # Actualizar nombre del tenant si es necesario
    if request.get("companyName") and user.tenant:
        user.tenant.name = request["companyName"]
    
    await db.commit()
    
    return {"status": "success", "user": user}

@router.post("/reset-onboarding")
async def reset_onboarding(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Reiniciar onboarding (útil para testing)
    """
    user = await db.get(User, current_user["id"])
    
    if user:
        user.onboarding_completed = False
        await db.commit()
    
    return {"status": "success"}
```

## 3. Extras y Buenas Prácticas

### A. Almacenamiento de IDs de Stripe
```python
# Recomendación: Guardar en BD, no en Clerk metadata

# ✅ BIEN - En base de datos
class User(Base):
    stripe_customer_id = Column(String, unique=True, index=True)
    # Fácil de consultar, migrar y gestionar

# ❌ EVITAR - En Clerk metadata
# user.publicMetadata.stripeCustomerId
# Más difícil de consultar y puede perderse
```

### B. Middleware de Protección de Rutas
```typescript
// middleware.ts
import { authMiddleware } from '@clerk/nextjs'
import { NextResponse } from 'next/server'

export default authMiddleware({
  publicRoutes: ['/pricing', '/auth/sign-up', '/auth/sign-in'],
  
  afterAuth(auth, req) {
    // Si no está autenticado y trata de acceder ruta protegida
    if (!auth.userId && !auth.isPublicRoute) {
      return NextResponse.redirect(new URL('/auth/sign-in', req.url))
    }
    
    // Verificar suscripción para rutas premium
    if (auth.userId && req.nextUrl.pathname.startsWith('/premium')) {
      // Aquí podrías verificar el plan del usuario
      // Por ahora, redirigir a pricing si no tiene metadata
      if (!auth.sessionClaims?.subscription?.plan || 
          auth.sessionClaims.subscription.plan === 'free') {
        return NextResponse.redirect(new URL('/pricing', req.url))
      }
    }
  }
})

export const config = {
  matcher: ['/((?!.*\\..*|_next).*)', '/', '/(api|trpc)(.*)']
}
```

### C. Hook para Gestión de Suscripción
```typescript
// hooks/useSubscription.ts
import { useUser } from '@clerk/nextjs'
import { useEffect, useState } from 'react'

interface Subscription {
  plan: string
  status: string
  features: string[]
}

export function useSubscription() {
  const { user } = useUser()
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (user) {
      fetchSubscription()
    }
  }, [user])

  const fetchSubscription = async () => {
    try {
      const response = await fetch('/api/users/subscription')
      const data = await response.json()
      setSubscription(data)
    } catch (error) {
      console.error('Error fetching subscription:', error)
    } finally {
      setLoading(false)
    }
  }

  const canAccess = (feature: string) => {
    return subscription?.features.includes(feature) || false
  }

  const upgradeToPlan = async (planId: string) => {
    const response = await fetch('/api/stripe/create-checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ planId })
    })
    
    const data = await response.json()
    window.location.href = data.url
  }

  const manageSubscription = async () => {
    const response = await fetch('/api/stripe/create-customer-portal', {
      method: 'POST'
    })
    
    const data = await response.json()
    window.location.href = data.url
  }

  return {
    subscription,
    loading,
    canAccess,
    upgradeToPlan,
    manageSubscription,
    isPro: subscription?.plan === 'pro',
    isEnterprise: subscription?.plan === 'enterprise'
  }
}
```

### D. Manejo de Errores y Estados Edge
```python
# backend/app/api/v1/stripe.py

@router.post("/handle-failed-payment")
async def handle_failed_payment(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Manejar pagos fallidos
    """
    user = await db.get(User, current_user["id"])
    
    if not user or not user.stripe_customer_id:
        raise HTTPException(400, "No customer found")
    
    # Obtener suscripciones con problemas
    subscriptions = stripe.Subscription.list(
        customer=user.stripe_customer_id,
        status="past_due"
    )
    
    if subscriptions.data:
        # Enviar email de notificación
        await send_payment_failed_email(user.email)
        
        # Actualizar estado en BD
        for sub in subscriptions.data:
            db_sub = await db.query(Subscription).filter(
                Subscription.stripe_subscription_id == sub.id
            ).first()
            
            if db_sub:
                db_sub.status = "past_due"
                await db.commit()
        
        # Crear sesión para actualizar método de pago
        session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            mode="setup",
            success_url=f"{os.getenv('FRONTEND_URL')}/dashboard?payment=updated",
            cancel_url=f"{os.getenv('FRONTEND_URL')}/dashboard/billing"
        )
        
        return {"url": session.url}
    
    return {"status": "no_failed_payments"}
```

### E. Testing del Flujo
```typescript
// cypress/e2e/registration-flow.cy.ts
describe('Registration Flow', () => {
  it('should complete free plan registration', () => {
    cy.visit('/auth/sign-up')
    
    // Completar registro con Clerk
    cy.fillClerkSignUp({
      email: 'test@example.com',
      password: 'TestPassword123!'
    })
    
    // Verificar redirección a welcome
    cy.url().should('include', '/welcome')
    
    // Completar onboarding
    cy.get('[data-cy=start-onboarding]').click()
    cy.get('[data-cy=plan-free]').click()
    cy.get('[data-cy=continue]').click()
    
    // Llenar información de empresa
    cy.get('#companyName').type('Test Company')
    cy.get('#taxId').type('B12345678')
    cy.get('[data-cy=complete]').click()
    
    // Verificar dashboard
    cy.url().should('include', '/dashboard')
    cy.contains('Welcome to your dashboard')
  })
  
  it('should complete paid plan registration', () => {
    cy.visit('/pricing')
    
    // Seleccionar plan Pro
    cy.get('[data-cy=plan-pro]').click()
    
    // Verificar redirección a Stripe
    cy.origin('https://checkout.stripe.com', () => {
      // Completar pago de prueba
      cy.fillStripeCheckout()
    })
    
    // Verificar retorno con session_id
    cy.url().should('include', '/auth/sign-up?session_id=')
    
    // Completar registro
    cy.fillClerkSignUp({
      email: 'pro@example.com',
      password: 'TestPassword123!'
    })
    
    // Verificar onboarding simplificado
    cy.url().should('include', '/welcome')
    cy.get('[data-cy=payment-confirmed]').should('be.visible')
  })
})
```

Este flujo completo asegura una experiencia fluida desde el registro hasta la activación con suscripción.