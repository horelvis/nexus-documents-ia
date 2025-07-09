#!/bin/bash
# Script to manage Nginx proxy VM

set -e

PROJECT_ID=${PROJECT_ID:-nexus-document-prod}
ZONE=${ZONE:-europe-west1-b}
INSTANCE_NAME="nginx-proxy"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

function show_help {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status    - Show Nginx VM status"
    echo "  logs      - Show Nginx logs"
    echo "  reload    - Reload Nginx configuration"
    echo "  renew     - Force SSL certificate renewal"
    echo "  ssh       - SSH into Nginx VM"
    echo "  restart   - Restart Nginx service"
    echo ""
}

function check_vm_exists {
    if ! gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --project=$PROJECT_ID &>/dev/null; then
        echo -e "${RED}Error: Nginx VM '$INSTANCE_NAME' not found${NC}"
        exit 1
    fi
}

case "$1" in
    status)
        echo -e "${YELLOW}Checking Nginx VM status...${NC}"
        gcloud compute instances describe $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --format="table(name,status,networkInterfaces[0].accessConfigs[0].natIP)"
        
        echo -e "\n${YELLOW}Checking Nginx service status...${NC}"
        gcloud compute ssh $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --command="sudo docker ps | grep nginx"
        ;;
    
    logs)
        echo -e "${YELLOW}Fetching Nginx logs...${NC}"
        gcloud compute ssh $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --command="sudo docker logs nexus-nginx --tail=50"
        ;;
    
    reload)
        echo -e "${YELLOW}Reloading Nginx configuration...${NC}"
        gcloud compute ssh $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --command="sudo docker exec nexus-nginx nginx -s reload"
        echo -e "${GREEN}✓ Nginx reloaded successfully${NC}"
        ;;
    
    renew)
        echo -e "${YELLOW}Forcing SSL certificate renewal...${NC}"
        gcloud compute ssh $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --command="cd /opt/nexus && sudo docker-compose run --rm certbot renew --force-renewal"
        
        echo -e "${YELLOW}Reloading Nginx...${NC}"
        gcloud compute ssh $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --command="sudo docker exec nexus-nginx nginx -s reload"
        echo -e "${GREEN}✓ SSL certificates renewed${NC}"
        ;;
    
    ssh)
        echo -e "${YELLOW}Connecting to Nginx VM...${NC}"
        gcloud compute ssh $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID
        ;;
    
    restart)
        echo -e "${YELLOW}Restarting Nginx service...${NC}"
        gcloud compute ssh $INSTANCE_NAME \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --command="cd /opt/nexus && sudo docker-compose restart nginx"
        echo -e "${GREEN}✓ Nginx restarted successfully${NC}"
        ;;
    
    *)
        show_help
        ;;
esac