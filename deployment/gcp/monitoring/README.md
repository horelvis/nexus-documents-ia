# 📊 Monitoring Configuration - NouxCubeIA

## Overview

This directory contains monitoring configurations for NouxCubeIA environments. Each environment (PRE, PROD) has its own set of dashboards, alerts, and monitoring scripts.

## Structure

```
monitoring/
├── dashboard-pre.yaml        # PRE environment dashboard
├── alerts-pre.yaml          # PRE environment alerts
├── setup-monitoring-pre.sh  # PRE monitoring setup script
├── dashboard-prod.yaml      # PROD environment dashboard (future)
├── alerts-prod.yaml         # PROD environment alerts (future)
└── README.md               # This file
```

## PRE Environment Monitoring

### Dashboard Features

The PRE dashboard (`dashboard-pre.yaml`) includes:

1. **Service Health Overview**
   - Real-time status of all services
   - Error rate monitoring
   - P95 latency tracking

2. **Performance Metrics**
   - Request rate by service
   - Latency distribution (P50, P95, P99)
   - CPU and memory utilization

3. **Database Monitoring**
   - Connection pool usage
   - CPU utilization
   - Query performance

4. **AI Services**
   - Response times for LangChain/Langroid
   - Token usage rates
   - Model performance metrics

5. **Infrastructure**
   - Active Cloud Run instances
   - Cold start frequency
   - Cost estimates

### Alert Policies

The PRE alerts (`alerts-pre.yaml`) cover:

1. **Critical Alerts**
   - Service down (no requests for 5 minutes)
   - High error rate (>5% for 5 minutes)
   - Database backup failures
   - AI service failures (>10% errors)

2. **Warning Alerts**
   - High latency (P95 > 2 seconds)
   - High CPU usage (>80% for 10 minutes)
   - High memory usage (>85%)
   - Excessive cold starts

3. **Database Alerts**
   - Connection pool exhaustion (>80%)
   - High CPU usage (>70%)
   - Redis memory alerts (>80%)

### Setup Instructions

1. **Prerequisites**
   ```bash
   # Ensure you're authenticated
   gcloud auth login
   gcloud config set project nexusdocs360-pre
   ```

2. **Configure Secrets**
   ```bash
   # Add Slack webhook URLs
   echo "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" | \
     gcloud secrets create slack-webhook-pre --data-file=-
   
   # Add critical alerts webhook
   echo "https://hooks.slack.com/services/YOUR/CRITICAL/URL" | \
     gcloud secrets create slack-webhook-pre-critical --data-file=-
   ```

3. **Run Setup Script**
   ```bash
   cd monitoring
   ./setup-monitoring-pre.sh
   ```

4. **Verify Setup**
   - Dashboard: [Cloud Console](https://console.cloud.google.com/monitoring/dashboards)
   - Alerts: [Alert Policies](https://console.cloud.google.com/monitoring/alerting/policies)
   - Uptime Checks: [Uptime Monitoring](https://console.cloud.google.com/monitoring/uptime)

### Notification Channels

Configure these channels for alert notifications:

1. **Slack Integration**
   - `#nexus-pre-alerts` - General alerts
   - `#nexus-pre-critical` - Critical issues

2. **Email**
   - `pre-oncall@nexusdocs360.com` - On-call rotation

3. **PagerDuty** (Optional)
   - For critical production-like issues

### Custom Metrics

The setup creates these log-based metrics:

1. **ai_tokens_used** - Track AI token consumption
2. **endpoint_errors** - Errors by API endpoint
3. **document_processing_time** - Document processing performance

### SLOs (Service Level Objectives)

- **API Availability**: 99% over 30 days
- **Latency**: P95 < 2 seconds
- **Error Rate**: < 1%

## Best Practices

1. **Alert Fatigue Prevention**
   - Tune thresholds based on baseline metrics
   - Use appropriate severity levels
   - Implement alert suppression during maintenance

2. **Dashboard Usage**
   - Pin important dashboards
   - Create custom views for different roles
   - Use dashboard variables for flexibility

3. **Incident Response**
   - Follow runbooks in alert documentation
   - Update alerts based on post-mortems
   - Test alert channels regularly

4. **Cost Optimization**
   - Monitor metric ingestion rates
   - Use appropriate retention policies
   - Archive old data to Cloud Storage

## Maintenance

### Weekly Tasks
- Review alert noise and tune thresholds
- Check for new error patterns
- Validate notification channels

### Monthly Tasks
- Review SLO performance
- Update dashboards based on new features
- Audit metric usage and costs

### Quarterly Tasks
- Review and update alert documentation
- Conduct alert testing exercises
- Plan capacity based on trends

## Troubleshooting

### Common Issues

1. **Alerts not firing**
   ```bash
   # Check alert policy
   gcloud alpha monitoring policies list --filter="displayName:PRE"
   
   # Test notification channel
   gcloud alpha monitoring channels verify CHANNEL_ID
   ```

2. **Missing metrics**
   ```bash
   # Check metric descriptors
   gcloud monitoring metrics-descriptors list --filter="metric.type:custom"
   
   # Verify service logging
   gcloud logging read "resource.labels.service_name=nexus-api-pre" --limit=10
   ```

3. **Dashboard errors**
   ```bash
   # Validate dashboard config
   gcloud monitoring dashboards list
   
   # Re-import dashboard
   gcloud monitoring dashboards delete pre-overview
   gcloud monitoring dashboards create --config-from-file=dashboard-pre.yaml
   ```

## Future Enhancements

1. **Advanced Analytics**
   - ML-based anomaly detection
   - Predictive alerting
   - Capacity planning models

2. **Integration**
   - Grafana dashboards
   - Datadog integration
   - Custom webhook receivers

3. **Automation**
   - Auto-scaling based on metrics
   - Self-healing alerts
   - Automated incident creation

---

For questions or improvements, contact: devops@nexusdocs360.com