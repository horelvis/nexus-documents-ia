#!/bin/bash
# cleanup-packages.sh - Script seguro para limpiar paquetes obsoletos

set -e  # Exit on any error

echo "🧹 Iniciando limpieza de paquetes obsoletos para migración a backend API..."

# Función para verificar si un paquete está instalado
check_package() {
    npm list "$1" --depth=0 >/dev/null 2>&1
}

# Función para remover paquete de forma segura
safe_remove() {
    local package=$1
    if check_package "$package"; then
        echo "  🗑️  Removiendo $package..."
        npm uninstall "$package"
    else
        echo "  ✅ $package no está instalado"
    fi
}

echo ""
echo "📦 1. Removiendo dependencias de Stripe (ahora manejado por backend)..."
safe_remove "stripe"

echo ""
echo "📦 2. Removiendo dependencias de Prisma (reemplazado por API calls)..."
safe_remove "prisma"
safe_remove "@prisma/client"

echo ""
echo "📦 3. Removiendo dependencias de autenticación custom (reemplazado por Clerk)..."
safe_remove "remix-auth"
safe_remove "remix-auth-form"
safe_remove "remix-auth-github"
safe_remove "remix-auth-google"
safe_remove "remix-auth-oauth2"

echo ""
echo "📦 4. Removiendo dependencias de email (backend maneja emails)..."
safe_remove "resend"
safe_remove "@react-email/components"
safe_remove "@react-email/render"

echo ""
echo "📦 5. Removiendo dependencias de crypto/hashing (backend maneja seguridad)..."
safe_remove "bcryptjs"
safe_remove "@types/bcryptjs"
safe_remove "argon2"

echo ""
echo "📦 6. Removiendo dependencias de validación obsoletas..."
safe_remove "remix-validated-form"
safe_remove "yup"
safe_remove "joi"


echo ""
echo "📦 8. Removiendo dependencias de testing obsoletas..."
safe_remove "@testing-library/jest-dom"
safe_remove "jest"
safe_remove "ts-jest"

echo ""
echo "📦 9. Removiendo dependencias de desarrollo no necesarias..."
safe_remove "dotenv"
safe_remove "cross-env"
safe_remove "concurrently"
safe_remove "nodemon"

echo ""
echo "🔍 Verificando dependencias restantes..."
echo "Dependencias principales que deben permanecer:"
echo "  - @remix-run/* (framework)"
echo "  - @clerk/remix (autenticación)"
echo "  - react, react-dom (UI)"
echo "  - tailwindcss (estilos)"
echo "  - zod (validación)"
echo "  - lucide-react (iconos)"

echo ""
echo "📋 Dependencias actuales después de la limpieza:"
npm list --depth=0 | head -20

echo ""
echo "🧪 Verificando que no hay dependencias rotas..."
npm audit --audit-level=moderate

echo ""
echo "🔨 Verificando que el proyecto compile..."
if npm run typecheck; then
    echo "  ✅ TypeScript compilado correctamente"
else
    echo "  ❌ Error en compilación TypeScript"
    exit 1
fi

echo ""
echo "✨ Limpieza completada exitosamente!"
echo ""
echo "📝 Próximos pasos:"
echo "  1. Implementar los nuevos archivos de servicio API"
echo "  2. Actualizar las variables de entorno"
echo "  3. Probar los flujos de Stripe con el backend"
echo ""
echo "🚀 Para verificar que todo funciona:"
echo "  npm run dev"
echo "  npm run build"
