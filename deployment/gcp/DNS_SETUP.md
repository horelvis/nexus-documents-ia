# DNS Configuration for NexusDocs360 PRE Environment

## Required DNS Records

You need to add the following DNS A records at your DNS provider (Cloudflare, GoDaddy, etc.):

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | pre | 34.78.30.77 | 300 |
| A | pre-api | 34.78.30.77 | 300 |

## Step-by-Step Instructions

### For Cloudflare:
1. Log in to Cloudflare dashboard
2. Select your domain (nexusdocs360.com)
3. Go to DNS settings
4. Click "Add record"
5. Add each record:
   - Type: A
   - Name: pre (this creates pre.nexusdocs360.com)
   - IPv4 address: 34.78.30.77
   - Proxy status: DNS only (gray cloud)
   - TTL: Auto
6. Repeat for pre-api

### For Google Domains:
1. Go to domains.google.com
2. Click on your domain
3. Select "DNS" from the left menu
4. Under "Custom records", add:
   - Host name: pre
   - Type: A
   - TTL: 300
   - Data: 34.78.30.77
5. Click "Add"
6. Repeat for pre-api

### For GoDaddy:
1. Log in to GoDaddy
2. Go to "My Products" > Domains
3. Click "DNS" next to your domain
4. Click "Add" in the Records section
5. Select Type: A
6. Enter:
   - Host: pre
   - Points to: 34.78.30.77
   - TTL: 600 seconds
7. Save
8. Repeat for pre-api

## Verify DNS Configuration

After adding the records, wait 5-10 minutes, then verify:

```bash
# Check from your local machine
dig pre.nexusdocs360.com
dig pre-api.nexusdocs360.com

# Or use nslookup
nslookup pre.nexusdocs360.com
nslookup pre-api.nexusdocs360.com

# Expected result: 34.78.30.77
```

## Current Status

Based on the error, these DNS records are missing:
- ❌ pre.nexusdocs360.com → 34.78.30.77
- ❌ pre-api.nexusdocs360.com → 34.78.30.77

## Alternative: Path-Based Routing

If you cannot add DNS records immediately, you can use path-based routing:
- Frontend: https://nexusdocs360.com/pre/
- API: https://nexusdocs360.com/api/pre/

Run this to configure path-based routing:
```bash
sudo ./configure-nginx-single-domain.sh
# Choose option 1
```

## After DNS is Configured

Once DNS records are added and propagated:

```bash
# Run the configuration script
sudo ./configure-nginx-pre-v3.sh

# Or if nginx is already running with HTTP, just generate certificates:
sudo certbot certonly --webroot -w /var/www/certbot \
  -d pre.nexusdocs360.com \
  -d pre-api.nexusdocs360.com \
  --email admin@nexusdocs360.com \
  --agree-tos
```

## Troubleshooting

1. **DNS not propagating**: 
   - DNS changes can take up to 48 hours, but usually 5-30 minutes
   - Try flushing DNS cache: `sudo dscacheutil -flushcache` (Mac) or `ipconfig /flushdns` (Windows)

2. **Certificate generation fails**:
   - Ensure nginx is running: `sudo systemctl status nginx`
   - Check nginx can serve files: `curl http://pre.nexusdocs360.com/.well-known/acme-challenge/test`
   - Check firewall allows port 80: `sudo ufw status`

3. **Wrong IP in DNS**:
   - Verify the nginx server IP: `curl ifconfig.me` (run on the nginx server)
   - Update DNS records if IP has changed