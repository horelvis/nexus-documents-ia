# VPC Connector Analysis for NexusDocs360

## Issue Summary
The VPC connector `nexus-connector-pre` is failing during Cloud Run deployment in the PRE environment. This analysis examines the configuration and potential causes.

## VPC Connector Configuration

### PRE Environment (nexus-connector-pre)
**Location**: `/deployment/gcp/scripts/deploy-infrastructure-pre.sh` (lines 249-257)
```bash
gcloud compute networks vpc-access connectors create nexus-connector-pre \
    --region=$REGION \
    --subnet=nexus-subnet-pre \
    --subnet-project=$PROJECT_ID \
    --min-instances=2 \
    --max-instances=3 \
    --machine-type=f1-micro \
    --project=$PROJECT_ID
```

**Configuration Details**:
- Region: europe-west1
- Subnet: nexus-subnet-pre (10.1.0.0/24)
- Project: nexusdocs360-pre
- Machine Type: f1-micro
- Instances: 2-3

### PROD Environment (nexus-connector-prod)
**Location**: `/deployment/gcp/scripts/deploy-infrastructure-prod.sh` (lines 325-333)
```bash
gcloud compute networks vpc-access connectors create nexus-connector-prod \
    --region=$REGION \
    --subnet=nexus-subnet-prod-primary \
    --subnet-project=$PROJECT_ID \
    --min-instances=4 \
    --max-instances=10 \
    --machine-type=e2-micro \
    --project=$PROJECT_ID
```

**Configuration Details**:
- Region: europe-west1
- Subnet: nexus-subnet-prod-primary (10.0.0.0/23)
- Project: nexusdocs360-prod
- Machine Type: e2-micro
- Instances: 4-10

## Usage in GitHub Actions

### Deploy PRE Workflow
**File**: `.github/workflows/deploy-pre.yml`

The VPC connector is used in multiple service deployments:
1. **Backend Service** (line 82): `--vpc-connector nexus-connector-pre`
2. **Storage Service** (line 123): `--vpc-connector nexus-connector-pre`

Note: Frontend service does NOT use the VPC connector.

### Deploy PROD Workflow
**File**: `.github/workflows/deploy-prod.yml`

The VPC connector is used in:
1. **Backend Service** (line 201): `--vpc-connector nexus-connector-prod`
2. **Microservices** (line 307): `--vpc-connector nexus-connector-prod`
3. **Migration Jobs** (line 322): `--vpc-connector nexus-connector-prod`

## Potential Issues and Solutions

### 1. VPC Connector Not Created
**Issue**: The VPC connector might not have been created during infrastructure setup.

**Verification**:
```bash
gcloud compute networks vpc-access connectors describe nexus-connector-pre \
    --region=europe-west1 \
    --project=nexusdocs360-pre
```

**Solution**: Run the infrastructure deployment script:
```bash
cd deployment/gcp/scripts
./deploy-infrastructure-pre.sh
```

### 2. Insufficient Permissions
**Issue**: The service account used by GitHub Actions might lack permissions to use the VPC connector.

**Required Roles**:
- `roles/vpcaccess.user` - To use VPC connectors
- `roles/compute.networkUser` - To access VPC network

**Solution**: Grant permissions to the service account:
```bash
PROJECT_ID=nexusdocs360-pre
SA_EMAIL=nexus-cloud-run-pre@${PROJECT_ID}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/vpcaccess.user"
```

### 3. Machine Type Issue
**Issue**: `f1-micro` machine type might be deprecated or unavailable in the region.

**Solution**: Update to `e2-micro` (like production):
```bash
gcloud compute networks vpc-access connectors update nexus-connector-pre \
    --region=europe-west1 \
    --machine-type=e2-micro
```

### 4. Subnet Configuration
**Issue**: The subnet might not exist or have incorrect configuration.

**Verification**:
```bash
gcloud compute networks subnets describe nexus-subnet-pre \
    --region=europe-west1 \
    --project=nexusdocs360-pre
```

### 5. Quota Limits
**Issue**: VPC connector quota might be exceeded.

**Check Quota**:
```bash
gcloud compute project-info describe --project=nexusdocs360-pre
```

## Recommended Actions

### Immediate Fix
1. **Verify VPC Connector Exists**:
   ```bash
   gcloud compute networks vpc-access connectors list \
       --region=europe-west1 \
       --project=nexusdocs360-pre
   ```

2. **If Missing, Create It**:
   ```bash
   gcloud compute networks vpc-access connectors create nexus-connector-pre \
       --region=europe-west1 \
       --subnet=nexus-subnet-pre \
       --subnet-project=nexusdocs360-pre \
       --min-instances=2 \
       --max-instances=3 \
       --machine-type=e2-micro \
       --project=nexusdocs360-pre
   ```

3. **Validate Configuration**:
   ```bash
   cd deployment/gcp/scripts
   ./validate-pre.sh
   ```

### Long-term Improvements
1. **Update Machine Type**: Change from `f1-micro` to `e2-micro` in the infrastructure script
2. **Add Health Checks**: Include VPC connector validation in the deployment workflow
3. **Error Handling**: Add fallback deployment without VPC connector for non-critical services
4. **Documentation**: Update deployment guides with VPC connector troubleshooting

## Alternative Deployment (Temporary)
If VPC connector continues to fail, you can temporarily deploy without it:

```bash
# Deploy without VPC connector (loses access to private resources)
gcloud run deploy nexus-backend-pre \
    --image ${IMAGE_URL} \
    --region europe-west1 \
    # Remove: --vpc-connector nexus-connector-pre
    # Other flags remain the same
```

**Note**: This will prevent access to:
- Private Cloud SQL database
- Private Redis instance
- Private Qdrant vector database

## Monitoring Commands
```bash
# Check recent errors
gcloud logging read "resource.type=vpc_access_connector AND severity>=ERROR" \
    --project=nexusdocs360-pre \
    --limit=10

# Check connector status
gcloud compute networks vpc-access connectors describe nexus-connector-pre \
    --region=europe-west1 \
    --project=nexusdocs360-pre \
    --format="value(state)"
```

## Related Files
- Infrastructure Setup: `/deployment/gcp/scripts/deploy-infrastructure-pre.sh`
- GitHub Actions: `/.github/workflows/deploy-pre.yml`
- Validation Script: `/deployment/gcp/scripts/validate-pre.sh`
- Deployment Guide: `/deployment/gcp/PRE_DEPLOYMENT_GUIDE.md`