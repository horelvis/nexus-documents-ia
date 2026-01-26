#!/bin/bash

# ================================================================
# setup-github-actions.sh - Configuración de GitHub Actions
# ================================================================
# Uso: ./setup-github-actions.sh [pre|prod|all]
# 
# Este script configura los service accounts necesarios para
# GitHub Actions en GCP.
# ================================================================

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Función para imprimir mensajes
print_message() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}[ADVERTENCIA]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Verificar parámetro
ENVIRONMENT=${1:-all}

if [[ ! "$ENVIRONMENT" =~ ^(pre|prod|all)$ ]]; then
    print_error "Uso: $0 [pre|prod|all]"
    exit 1
fi

# Función para crear service account
create_service_account() {
    local PROJECT_ID=$1
    local ENV_NAME=$2
    
    print_message "Configurando Service Account para $ENV_NAME..."
    
    # Configurar proyecto
    gcloud config set project ${PROJECT_ID}
    
    # Nombre del service account
    SA_NAME="github-actions-sa"
    SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
    
    # Verificar si ya existe
    if gcloud iam service-accounts describe ${SA_EMAIL} &>/dev/null; then
        print_warning "Service Account ${SA_EMAIL} ya existe"
    else
        # Crear service account
        print_info "Creando Service Account..."
        gcloud iam service-accounts create ${SA_NAME} \
            --display-name="GitHub Actions Service Account" \
            --description="Service account for GitHub Actions CI/CD deployments"
    fi
    
    # Asignar roles necesarios
    print_info "Asignando roles IAM..."
    
    ROLES=(
        "roles/run.admin"                    # Cloud Run Admin
        "roles/storage.admin"                # Storage Admin  
        "roles/artifactregistry.writer"      # Artifact Registry Writer
        "roles/secretmanager.secretAccessor" # Secret Manager Accessor
        "roles/cloudsql.client"              # Cloud SQL Client
        "roles/compute.networkUser"          # Compute Network User
        "roles/logging.logWriter"            # Logs Writer
        "roles/monitoring.metricWriter"      # Monitoring Metrics Writer
        "roles/cloudtrace.agent"             # Cloud Trace Agent
        "roles/serviceusage.serviceUsageConsumer" # Service Usage Consumer
    )
    
    for ROLE in "${ROLES[@]}"; do
        print_info "  Asignando ${ROLE}..."
        gcloud projects add-iam-policy-binding ${PROJECT_ID} \
            --member="serviceAccount:${SA_EMAIL}" \
            --role="${ROLE}" \
            --quiet || print_warning "No se pudo asignar ${ROLE}"
    done
    
    # Crear directorio para keys si no existe
    mkdir -p ./credentials
    
    # Nombre del archivo de key
    KEY_FILE="./credentials/github-actions-key-${ENV_NAME}.json"
    
    # Verificar si ya existe una key
    if [[ -f "$KEY_FILE" ]]; then
        print_warning "El archivo de key ${KEY_FILE} ya existe"
        read -p "¿Deseas crear una nueva key? (s/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            print_info "Manteniendo key existente"
            return
        fi
    fi
    
    # Crear key
    print_info "Creando service account key..."
    gcloud iam service-accounts keys create ${KEY_FILE} \
        --iam-account=${SA_EMAIL} \
        --key-file-type=json
    
    print_message "Service Account configurado para ${ENV_NAME}"
    print_info "Key guardada en: ${KEY_FILE}"
    
    # Mostrar siguiente paso
    echo
    print_warning "IMPORTANTE - Siguiente paso:"
    echo "1. Ve a: https://github.com/TU_USUARIO/nexusdocs360/settings/secrets/actions"
    echo "2. Crea un nuevo secret llamado: GCP_SA_KEY_${ENV_NAME^^}"
    echo "3. Copia el contenido de ${KEY_FILE} como valor del secret"
    echo
}

# Función para verificar prerrequisitos
check_prerequisites() {
    print_message "Verificando prerrequisitos..."
    
    # Verificar gcloud
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI no está instalado"
        exit 1
    fi
    
    # Verificar autenticación
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
        print_error "No hay autenticación activa en gcloud"
        print_info "Ejecuta: gcloud auth login"
        exit 1
    fi
    
    print_message "Prerrequisitos verificados ✓"
}

# Función para mostrar resumen
show_summary() {
    echo
    print_message "==================== RESUMEN ===================="
    echo
    echo "Service Accounts creados:"
    
    if [[ "$ENVIRONMENT" == "pre" || "$ENVIRONMENT" == "all" ]]; then
        echo "  - PRE: github-actions-sa@nexusdocs360-pre.iam.gserviceaccount.com"
        if [[ -f "./credentials/github-actions-key-pre.json" ]]; then
            echo "    Key: ./credentials/github-actions-key-pre.json ✓"
        fi
    fi
    
    if [[ "$ENVIRONMENT" == "prod" || "$ENVIRONMENT" == "all" ]]; then
        echo "  - PROD: github-actions-sa@nexusdocs360-prod.iam.gserviceaccount.com"
        if [[ -f "./credentials/github-actions-key-prod.json" ]]; then
            echo "    Key: ./credentials/github-actions-key-prod.json ✓"
        fi
    fi
    
    echo
    print_message "==================== PRÓXIMOS PASOS ===================="
    echo
    echo "1. Agregar secrets en GitHub:"
    echo "   - Ve a: https://github.com/TU_USUARIO/nexusdocs360/settings/secrets/actions"
    
    if [[ "$ENVIRONMENT" == "pre" || "$ENVIRONMENT" == "all" ]]; then
        echo "   - Crea secret GCP_SA_KEY_PRE con el contenido de ./credentials/github-actions-key-pre.json"
    fi
    
    if [[ "$ENVIRONMENT" == "prod" || "$ENVIRONMENT" == "all" ]]; then
        echo "   - Crea secret GCP_SA_KEY_PROD con el contenido de ./credentials/github-actions-key-prod.json"
    fi
    
    echo
    echo "2. Crear environments en GitHub:"
    echo "   - Ve a: Settings > Environments"
    echo "   - Crea 'pre-production' (branch: develop)"
    echo "   - Crea 'production' (branch: main, tags: v*)"
    echo
    echo "3. Hacer commit de los workflows:"
    echo "   git add .github/workflows/"
    echo "   git commit -m 'feat: add GitHub Actions workflows'"
    echo "   git push origin develop"
    echo
    echo "4. Verificar:"
    echo "   - Push a develop para activar deploy a PRE"
    echo "   - Crear tag vX.X.X para activar deploy a PROD"
    echo
    
    print_warning "SEGURIDAD: No commitees los archivos .json de credentials/"
    print_info "Asegúrate de que credentials/ esté en .gitignore"
    echo
}

# Main
main() {
    print_message "=== Setup GitHub Actions para NouxCubeIA ==="
    echo
    
    # Verificar prerrequisitos
    check_prerequisites
    
    # Configurar PRE
    if [[ "$ENVIRONMENT" == "pre" || "$ENVIRONMENT" == "all" ]]; then
        create_service_account "nexusdocs360-pre" "pre"
    fi
    
    # Configurar PROD
    if [[ "$ENVIRONMENT" == "prod" || "$ENVIRONMENT" == "all" ]]; then
        create_service_account "nexusdocs360-prod" "prod"
    fi
    
    # Mostrar resumen
    show_summary
    
    print_message "Setup completado! 🎉"
}

# Ejecutar
main