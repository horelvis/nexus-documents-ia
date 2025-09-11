# VPC Connector Solution for NexusDocs360

## Problem Summary
The VPC connector `nexus-connector-pre` was failing in the PRE environment, preventing Cloud Run services from connecting to private resources like Cloud SQL and Redis.

## Root Causes Identified
1. **Deprecated machine type**: Initial configuration used `f1-micro` (deprecated)
2. **Missing Private Google Access**: The subnet didn't have Private Google Access enabled
3. **Resource dependencies**: VPC couldn't be deleted due to attached resources
4. **IP range conflicts**: VPC connector needed a dedicated IP range

## Solution Applied

### 1. Complete VPC Cleanup
Before recreating the VPC, all dependencies had to be removed:
- VPC connectors (stuck in DELETING state)
- Compute Engine instances (nginx-proxy-pre, weaviate-pre)
- Redis instance and its peering connection
- Firewall rules
- Cloud Router
- Subnets

### 2. Proper VPC Recreation
Created a new VPC with correct configuration:
```bash
# VPC Network
gcloud compute networks create nexus-vpc-pre \
    --subnet-mode=custom \
    --bgp-routing-mode=regional

# Subnet with Private Google Access ENABLED (critical)
gcloud compute networks subnets create nexus-subnet-pre \
    --network=nexus-vpc-pre \
    --region=europe-west1 \
    --range=10.1.0.0/24 \
    --enable-private-ip-google-access  # This was missing!

# VPC Connector with specific IP range
gcloud compute networks vpc-access connectors create nexus-connector-pre \
    --region=europe-west1 \
    --network=nexus-vpc-pre \
    --range=10.1.240.0/28  # High range to avoid conflicts
    --min-instances=2 \
    --max-instances=3 \
    --machine-type=e2-micro  # Updated from f1-micro
```

### 3. Key Configuration Details
- **VPC Network**: `nexus-vpc-pre` (custom mode)
- **Subnet**: `nexus-subnet-pre` (10.1.0.0/24)
- **Private Google Access**: ✅ ENABLED (critical for VPC connector)
- **VPC Connector**: `nexus-connector-pre`
  - IP Range: 10.1.240.0/28
  - Machine Type: e2-micro
  - Instances: 2-3
  - State: READY

## Scripts Created

### 1. `setup-vpc-complete-pre.sh`
Complete VPC setup script that:
- Enables required APIs
- Creates VPC and subnet with Private Google Access
- Sets up firewall rules
- Creates VPC connector with proper configuration
- Handles cleanup of existing resources

### 2. `cleanup-vpc-dependencies-pre.sh`
Comprehensive cleanup script that:
- Removes VPC connectors from Cloud Run services
- Deletes Compute Engine instances
- Removes Redis instances and peerings
- Deletes firewall rules and routers
- Attempts to delete VPC network

## Critical Success Factors

1. **Private Google Access must be enabled** on the subnet for VPC connector to work
2. **Use e2-micro machine type** (not f1-micro which is deprecated)
3. **Allocate dedicated IP range** for VPC connector (e.g., 10.1.240.0/28)
4. **Clean up all dependencies** before deleting VPC network
5. **Wait for async operations** to complete (VPC connector deletion can take 2-3 minutes)

## Deployment Configuration
When deploying Cloud Run services, use:
```yaml
- name: Deploy to Cloud Run
  run: |
    gcloud run deploy $SERVICE_NAME \
      --vpc-connector nexus-connector-pre \
      --vpc-egress private-ranges-only \
      ...
```

## Troubleshooting Commands

Check VPC connector status:
```bash
gcloud compute networks vpc-access connectors describe nexus-connector-pre \
    --region=europe-west1 --project=nexusdocs360-pre
```

List all resources using VPC:
```bash
# Compute instances
gcloud compute instances list --filter="networkInterfaces.network:nexus-vpc-pre"

# Network peerings
gcloud compute networks peerings list --network=nexus-vpc-pre

# Firewall rules
gcloud compute firewall-rules list --filter="network:nexus-vpc-pre"
```

## Lessons Learned
1. Always enable Private Google Access when creating subnets for VPC connectors
2. Plan IP ranges carefully to avoid conflicts
3. Document all resources attached to VPC for easier cleanup
4. Use the latest machine types (e2-micro instead of f1-micro)
5. Allow sufficient time for async operations to complete