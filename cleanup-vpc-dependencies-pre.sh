#!/bin/bash
# Clean up all VPC dependencies before deleting the VPC network
# This script removes all resources that reference the VPC

set -e

PROJECT_ID="nexusdocs360-pre"
REGION="europe-west1"
VPC_NAME="nexus-vpc-pre"

echo "🧹 Cleaning up all VPC dependencies for $VPC_NAME..."
echo ""

# Set project
gcloud config set project $PROJECT_ID

# 1. List all resources using the VPC
echo "📋 Identifying resources using VPC $VPC_NAME..."
echo ""

# 2. Remove VPC connectors
echo "🔌 Removing VPC connectors..."
VPC_CONNECTORS=$(gcloud compute networks vpc-access connectors list --region=$REGION --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
if [ -n "$VPC_CONNECTORS" ]; then
    for CONNECTOR in $VPC_CONNECTORS; do
        echo "  - Deleting connector: $CONNECTOR"
        
        # First remove from Cloud Run services
        echo "    Detaching from Cloud Run services..."
        SERVICES=$(gcloud run services list --region=$REGION --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
        for SERVICE in $SERVICES; do
            gcloud run services update $SERVICE \
                --clear-vpc-connector \
                --region=$REGION \
                --project=$PROJECT_ID 2>/dev/null || true
        done
        
        # Delete connector
        gcloud compute networks vpc-access connectors delete $CONNECTOR \
            --region=$REGION \
            --project=$PROJECT_ID \
            --quiet 2>/dev/null || true
    done
    echo "  ✅ VPC connectors removed"
else
    echo "  ℹ️  No VPC connectors found"
fi
echo ""

# 3. Remove Cloud SQL instances from VPC
echo "🗄️  Checking Cloud SQL instances..."
SQL_INSTANCES=$(gcloud sql instances list --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
if [ -n "$SQL_INSTANCES" ]; then
    for INSTANCE in $SQL_INSTANCES; do
        # Check if instance uses private IP
        PRIVATE_IP=$(gcloud sql instances describe $INSTANCE --project=$PROJECT_ID --format="value(ipAddresses[0].ipAddress)" 2>/dev/null || true)
        if [ -n "$PRIVATE_IP" ]; then
            echo "  - Instance $INSTANCE uses VPC (private IP: $PRIVATE_IP)"
            echo "    ⚠️  Cloud SQL instances cannot be detached from VPC after creation"
            echo "    ⚠️  You must delete and recreate the instance without VPC"
            read -p "    Delete Cloud SQL instance $INSTANCE? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                echo "    Deleting Cloud SQL instance..."
                gcloud sql instances delete $INSTANCE --project=$PROJECT_ID --quiet
                echo "    ✅ Instance deleted"
            fi
        fi
    done
else
    echo "  ℹ️  No Cloud SQL instances found"
fi
echo ""

# 4. Remove Redis peering connections
echo "🔗 Removing Redis/service peering connections..."
PEERINGS=$(gcloud compute networks peerings list --network=$VPC_NAME --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
if [ -n "$PEERINGS" ]; then
    for PEERING in $PEERINGS; do
        echo "  - Removing peering: $PEERING"
        
        # Check if it's a Redis peering
        if [[ $PEERING == *"redis-peer"* ]]; then
            # Find and delete associated Redis instance
            REDIS_INSTANCES=$(gcloud redis instances list --region=$REGION --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
            for REDIS in $REDIS_INSTANCES; do
                echo "    Deleting Redis instance: $REDIS"
                gcloud redis instances delete $REDIS --region=$REGION --project=$PROJECT_ID --quiet 2>/dev/null || true
            done
        fi
        
        # Remove the peering
        gcloud compute networks peerings delete $PEERING \
            --network=$VPC_NAME \
            --project=$PROJECT_ID \
            --quiet 2>/dev/null || true
    done
    echo "  ✅ Peering connections removed"
else
    echo "  ℹ️  No peering connections found"
fi
echo ""

# 5. Remove Compute Engine instances
echo "💻 Checking Compute Engine instances..."
INSTANCES=$(gcloud compute instances list --project=$PROJECT_ID --format="value(name,zone)" 2>/dev/null || true)
if [ -n "$INSTANCES" ]; then
    while IFS=' ' read -r INSTANCE ZONE; do
        # Check if instance is in our VPC
        INSTANCE_NETWORK=$(gcloud compute instances describe $INSTANCE --zone=$ZONE --project=$PROJECT_ID --format="value(networkInterfaces[0].network)" 2>/dev/null || true)
        if [[ $INSTANCE_NETWORK == *"$VPC_NAME"* ]]; then
            echo "  - Instance $INSTANCE in zone $ZONE uses VPC"
            read -p "    Delete instance $INSTANCE? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                gcloud compute instances delete $INSTANCE --zone=$ZONE --project=$PROJECT_ID --quiet
                echo "    ✅ Instance deleted"
            fi
        fi
    done <<< "$INSTANCES"
else
    echo "  ℹ️  No Compute Engine instances found"
fi
echo ""

# 6. Remove firewall rules
echo "🔥 Removing firewall rules..."
FIREWALL_RULES=$(gcloud compute firewall-rules list --filter="network:$VPC_NAME" --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
if [ -n "$FIREWALL_RULES" ]; then
    for RULE in $FIREWALL_RULES; do
        echo "  - Deleting firewall rule: $RULE"
        gcloud compute firewall-rules delete $RULE --project=$PROJECT_ID --quiet
    done
    echo "  ✅ Firewall rules removed"
else
    echo "  ℹ️  No firewall rules found"
fi
echo ""

# 7. Remove routes (custom routes only)
echo "🛣️  Removing custom routes..."
ROUTES=$(gcloud compute routes list --filter="network:$VPC_NAME AND NOT name:default-route*" --project=$PROJECT_ID --format="value(name)" 2>/dev/null || true)
if [ -n "$ROUTES" ]; then
    for ROUTE in $ROUTES; do
        echo "  - Deleting route: $ROUTE"
        gcloud compute routes delete $ROUTE --project=$PROJECT_ID --quiet
    done
    echo "  ✅ Custom routes removed"
else
    echo "  ℹ️  No custom routes found"
fi
echo ""

# 8. Remove forwarding rules
echo "🔀 Checking forwarding rules..."
FORWARDING_RULES=$(gcloud compute forwarding-rules list --project=$PROJECT_ID --format="value(name,region)" 2>/dev/null || true)
if [ -n "$FORWARDING_RULES" ]; then
    while IFS=' ' read -r RULE RULE_REGION; do
        if [ -n "$RULE_REGION" ]; then
            gcloud compute forwarding-rules delete $RULE --region=$RULE_REGION --project=$PROJECT_ID --quiet 2>/dev/null || true
        else
            gcloud compute forwarding-rules delete $RULE --global --project=$PROJECT_ID --quiet 2>/dev/null || true
        fi
    done <<< "$FORWARDING_RULES"
    echo "  ✅ Forwarding rules checked"
else
    echo "  ℹ️  No forwarding rules found"
fi
echo ""

# 9. Final check for remaining dependencies
echo "🔍 Final check for VPC dependencies..."
echo ""

# Try to delete subnets first
echo "🔀 Attempting to delete subnets..."
SUBNETS=$(gcloud compute networks subnets list --network=$VPC_NAME --project=$PROJECT_ID --format="value(name,region)" 2>/dev/null || true)
if [ -n "$SUBNETS" ]; then
    while IFS=' ' read -r SUBNET SUBNET_REGION; do
        echo "  - Deleting subnet: $SUBNET in region $SUBNET_REGION"
        gcloud compute networks subnets delete $SUBNET --region=$SUBNET_REGION --project=$PROJECT_ID --quiet 2>/dev/null || {
            echo "    ⚠️  Failed to delete subnet $SUBNET - may have active resources"
        }
    done <<< "$SUBNETS"
fi
echo ""

# 10. Attempt to delete the VPC network
echo "🌐 Attempting to delete VPC network..."
gcloud compute networks delete $VPC_NAME --project=$PROJECT_ID --quiet 2>&1 || {
    echo "❌ Failed to delete VPC network. Checking for remaining dependencies..."
    echo ""
    echo "📊 Remaining resources that may be using the VPC:"
    echo ""
    
    # List any remaining instances
    echo "Compute instances:"
    gcloud compute instances list --filter="networkInterfaces.network:$VPC_NAME" --project=$PROJECT_ID 2>/dev/null || echo "  None found"
    echo ""
    
    # List any remaining SQL instances
    echo "Cloud SQL instances:"
    gcloud sql instances list --project=$PROJECT_ID 2>/dev/null || echo "  None found"
    echo ""
    
    # List any remaining Redis instances
    echo "Redis instances:"
    gcloud redis instances list --region=$REGION --project=$PROJECT_ID 2>/dev/null || echo "  None found"
    echo ""
    
    # List any remaining peerings
    echo "Network peerings:"
    gcloud compute networks peerings list --network=$VPC_NAME --project=$PROJECT_ID 2>/dev/null || echo "  None found"
    echo ""
    
    exit 1
}

echo "✅ VPC network and all dependencies successfully removed!"