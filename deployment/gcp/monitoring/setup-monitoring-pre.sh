#!/bin/bash
# Setup monitoring for NouxCubeIA PRE environment

set -e

# Load environment variables
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/../load-env.sh"

PROJECT_ID=${GCP_PROJECT_ID:-nexusdocs360-pre}
REGION=${GCP_REGION:-europe-west1}

echo "📊 Setting up monitoring for PRE environment: $PROJECT_ID"

# Enable required APIs
echo "📡 Enabling monitoring APIs..."
gcloud services enable monitoring.googleapis.com --project=$PROJECT_ID
gcloud services enable logging.googleapis.com --project=$PROJECT_ID
gcloud services enable cloudtrace.googleapis.com --project=$PROJECT_ID
gcloud services enable clouderrorreporting.googleapis.com --project=$PROJECT_ID

# Create notification channels
echo "🔔 Setting up notification channels..."

# Slack channels
create_slack_channel() {
    local CHANNEL_NAME=$1
    local SLACK_CHANNEL=$2
    local WEBHOOK_SECRET=$3
    
    # Get webhook URL from secret
    WEBHOOK_URL=$(gcloud secrets versions access latest --secret=$WEBHOOK_SECRET --project=$PROJECT_ID 2>/dev/null || echo "")
    
    if [ -z "$WEBHOOK_URL" ]; then
        echo "⚠️  Warning: $WEBHOOK_SECRET not found. Please update it with your Slack webhook URL"
        return
    fi
    
    # Create notification channel
    cat <<EOF | gcloud alpha monitoring channels create --project=$PROJECT_ID
{
  "type": "webhook_tokenauth",
  "displayName": "$CHANNEL_NAME",
  "description": "Slack notifications for PRE environment",
  "labels": {
    "url": "$WEBHOOK_URL"
  },
  "userLabels": {
    "channel": "$SLACK_CHANNEL"
  }
}
EOF
}

# Create Slack channels
create_slack_channel "PRE Alerts - Slack" "#nexus-pre-alerts" "slack-webhook-pre"
create_slack_channel "PRE Critical - Slack" "#nexus-pre-critical" "slack-webhook-pre-critical"

# Email channel
echo "📧 Creating email notification channel..."
gcloud alpha monitoring channels create --project=$PROJECT_ID <<EOF
{
  "type": "email",
  "displayName": "PRE On-Call Email",
  "description": "Email notifications for PRE critical alerts",
  "labels": {
    "email_address": "pre-oncall@nexusdocs360.com"
  }
}
EOF

# Create uptime checks
echo "🏃 Creating uptime checks..."

create_uptime_check() {
    local NAME=$1
    local URL=$2
    local PATH=$3
    
    gcloud monitoring uptime create $NAME \
        --project=$PROJECT_ID \
        --display-name="PRE - $NAME Uptime Check" \
        --resource-type="uptime-url" \
        --monitored-url="$URL$PATH" \
        --check-interval=60s \
        --timeout=10s \
        --max-retries=3 || true
}

# Create uptime checks for each service
create_uptime_check "frontend" "https://pre-app.nexusdocs360.com" "/"
create_uptime_check "api-health" "https://pre-api.nexusdocs360.com" "/health"
create_uptime_check "api-docs" "https://pre-api.nexusdocs360.com" "/docs"

# Import dashboard
echo "📊 Creating monitoring dashboard..."
gcloud monitoring dashboards create \
    --config-from-file="$SCRIPT_DIR/dashboard-pre.yaml" \
    --project=$PROJECT_ID || \
gcloud monitoring dashboards update pre-overview \
    --config-from-file="$SCRIPT_DIR/dashboard-pre.yaml" \
    --project=$PROJECT_ID

# Create alert policies
echo "🚨 Setting up alert policies..."

# Function to create alert policy
create_alert_policy() {
    local CONFIG_FILE=$1
    local POLICY_NAME=$2
    
    # Extract policy configuration
    yq eval ".[] | select(.displayName == \"$POLICY_NAME\")" "$CONFIG_FILE" > /tmp/policy.yaml
    
    # Create the policy
    gcloud alpha monitoring policies create \
        --policy-from-file=/tmp/policy.yaml \
        --project=$PROJECT_ID || \
    echo "Policy $POLICY_NAME already exists or failed to create"
}

# Create each alert policy
ALERT_POLICIES=(
    "PRE - High Error Rate Alert"
    "PRE - High Latency Alert"
    "PRE - Service Down Alert"
    "PRE - Database Connection Pool Alert"
    "PRE - High Memory Usage Alert"
    "PRE - High CPU Usage Alert"
    "PRE - Database High CPU Alert"
    "PRE - Redis Memory Alert"
    "PRE - Excessive Cold Starts"
    "PRE - AI Service Failure"
    "PRE - Storage Service Alert"
    "PRE - Database Backup Failure"
)

for policy in "${ALERT_POLICIES[@]}"; do
    echo "Creating alert: $policy"
    create_alert_policy "$SCRIPT_DIR/alerts-pre.yaml" "$policy"
done

# Create log-based metrics
echo "📈 Creating log-based metrics..."

# AI Token Usage Metric
gcloud logging metrics create ai_tokens_used \
    --description="AI tokens consumed by service" \
    --log-filter='
    resource.type="cloud_run_revision"
    resource.labels.service_name=~"nexus-(langchain|langroid)-pre"
    jsonPayload.tokens_used>0
    ' \
    --value-extractor='EXTRACT(jsonPayload.tokens_used)' \
    --project=$PROJECT_ID || true

# Error Rate by Endpoint
gcloud logging metrics create endpoint_errors \
    --description="Errors by API endpoint" \
    --log-filter='
    resource.type="cloud_run_revision"
    resource.labels.service_name="nexus-api-pre"
    httpRequest.status>=400
    ' \
    --project=$PROJECT_ID || true

# Document Processing Time
gcloud logging metrics create document_processing_time \
    --description="Time to process documents" \
    --log-filter='
    resource.type="cloud_run_revision"
    jsonPayload.event="document_processed"
    jsonPayload.processing_time>0
    ' \
    --value-extractor='EXTRACT(jsonPayload.processing_time)' \
    --project=$PROJECT_ID || true

# Create SLO definitions
echo "🎯 Creating SLO definitions..."

cat > /tmp/slo-pre.yaml <<EOF
displayName: "PRE - API Availability SLO"
serviceLevelIndicator:
  requestBased:
    goodTotalRatio:
      goodServiceFilter: |
        resource.type="cloud_run_revision"
        resource.labels.service_name="nexus-api-pre"
        metric.type="run.googleapis.com/request_count"
        metric.labels.response_code_class="2xx"
      totalServiceFilter: |
        resource.type="cloud_run_revision"
        resource.labels.service_name="nexus-api-pre"
        metric.type="run.googleapis.com/request_count"
goal: 0.99
rollingPeriod: 2592000s  # 30 days
displayName: "99% Availability over 30 days"
EOF

# Create custom dashboard for AI metrics
echo "🤖 Creating AI metrics dashboard..."

cat > /tmp/ai-dashboard-pre.yaml <<EOF
displayName: "NouxCubeIA PRE - AI Services Dashboard"
mosaicLayout:
  columns: 12
  tiles:
    - width: 12
      height: 2
      widget:
        title: "AI Services Overview - PRE Environment"
        text:
          content: |
            Monitoring AI-specific metrics for LangChain and Langroid services
            
    - width: 6
      height: 4
      yPos: 2
      widget:
        title: "Token Usage by Model"
        pieChart:
          dataSets:
            - timeSeriesQuery:
                timeSeriesFilter:
                  filter: |
                    metric.type="logging.googleapis.com/user/ai_tokens_used"
                    resource.type="cloud_run_revision"
                  aggregation:
                    alignmentPeriod: 3600s
                    perSeriesAligner: ALIGN_SUM
                    crossSeriesReducer: REDUCE_SUM
                    groupByFields:
                      - metric.label.model_name
                      
    - width: 6
      height: 4
      xPos: 6
      yPos: 2
      widget:
        title: "AI Response Time Distribution"
        xyChart:
          dataSets:
            - timeSeriesQuery:
                timeSeriesFilter:
                  filter: |
                    resource.type="cloud_run_revision"
                    resource.labels.service_name=~"nexus-(langchain|langroid)-pre"
                    metric.type="run.googleapis.com/request_latencies"
                  aggregation:
                    alignmentPeriod: 300s
                    perSeriesAligner: ALIGN_DELTA
                    crossSeriesReducer: REDUCE_PERCENTILE_95
                    groupByFields:
                      - resource.label.service_name
EOF

gcloud monitoring dashboards create \
    --config-from-file=/tmp/ai-dashboard-pre.yaml \
    --project=$PROJECT_ID || true

# Create error reporting configuration
echo "❌ Configuring error reporting..."

# Enable error reporting for services
for service in api frontend langchain langroid storage; do
    gcloud run services update nexus-${service}-pre \
        --region=$REGION \
        --update-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,ENABLE_ERROR_REPORTING=true" \
        --project=$PROJECT_ID || true
done

# Create trace configuration
echo "🔍 Configuring distributed tracing..."

# Update services to enable tracing
for service in api frontend langchain langroid storage; do
    gcloud run services update nexus-${service}-pre \
        --region=$REGION \
        --update-env-vars="ENABLE_TRACING=true,TRACE_SAMPLING_RATIO=0.1" \
        --project=$PROJECT_ID || true
done

# Create budget alerts
echo "💰 Setting up budget alerts..."

gcloud billing budgets create \
    --billing-account=$(gcloud beta billing projects describe $PROJECT_ID --format="value(billingAccountName)") \
    --display-name="PRE Environment Budget" \
    --budget-amount=300 \
    --threshold-rule=percent=50 \
    --threshold-rule=percent=90 \
    --threshold-rule=percent=100,basis=forecasted \
    --project=$PROJECT_ID || true

# Create monitoring workspace
echo "🏢 Setting up monitoring workspace..."

# Link project to workspace
gcloud alpha monitoring workspaces create \
    --display-name="NouxCubeIA PRE Monitoring" \
    --project=$PROJECT_ID || true

# Summary
echo "
✅ Monitoring setup complete for PRE environment!

📊 Dashboards:
- Main Dashboard: https://console.cloud.google.com/monitoring/dashboards/custom/pre-overview?project=$PROJECT_ID
- AI Dashboard: https://console.cloud.google.com/monitoring/dashboards/custom/ai-services-pre?project=$PROJECT_ID

🚨 Alert Policies Created:
- High Error Rate (>5%)
- High Latency (P95 > 2s)
- Service Down
- Database Issues
- Memory/CPU Alerts
- AI Service Failures

🔔 Notification Channels:
- Slack: #nexus-pre-alerts, #nexus-pre-critical
- Email: pre-oncall@nexusdocs360.com

⚠️  Next Steps:
1. Update Slack webhook secrets with actual webhook URLs
2. Configure PagerDuty integration if needed
3. Test alerts with synthetic failures
4. Fine-tune thresholds based on baseline metrics

📝 To view all alerts:
gcloud alpha monitoring policies list --project=$PROJECT_ID

📈 To view custom metrics:
gcloud logging metrics list --project=$PROJECT_ID
"