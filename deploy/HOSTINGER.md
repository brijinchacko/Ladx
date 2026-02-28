# LADX Deployment Guide — Hostinger VPS

## Prerequisites

- A Hostinger VPS (Ubuntu 22.04 or 24.04 LTS)
- A domain name (e.g., `ladx.ai`) pointed to Hostinger nameservers
- SSH access to your VPS
- An OpenAI API key

---

## Step 1: SSH into Your VPS

From Hostinger hPanel:
1. Go to **VPS** → select your server
2. Find the **SSH Access** section — note the IP address and root password
3. Connect via terminal:

```
ssh root@YOUR_VPS_IP
```

---

## Step 2: Configure DNS

In Hostinger hPanel:
1. Go to **Domains** → select your domain → **DNS / Nameservers**
2. Add or edit these **A records**:

| Type | Name | Points to     | TTL  |
|------|------|---------------|------|
| A    | @    | YOUR_VPS_IP   | 3600 |
| A    | www  | YOUR_VPS_IP   | 3600 |

3. Wait 5–15 minutes for propagation (check with `ping yourdomain.com`)

---

## Step 3: Run the Setup Script

```bash
cd /tmp
git clone https://github.com/brijinchacko/Ladx.git
cd Ladx
sudo bash deploy/setup-vps.sh
```

The script will ask for:
- **Domain**: your domain (e.g., `ladx.ai`)
- **Email**: for SSL certificate notifications

The script installs all dependencies, creates the app user, sets up Nginx, and enables the systemd service.

---

## Step 4: Create the .env File

```bash
sudo -u ladx nano /opt/ladx/app/.env
```

Add these variables:

```
OPENAI_API_KEY=sk-your-openai-key
SECRET_KEY=your-random-secret-key-here
DATABASE_URL=sqlite:///./ladx.db
```

Generate a random secret key:
```bash
openssl rand -hex 32
```

---

## Step 5: Start the Service

```bash
sudo systemctl start ladx
sudo systemctl status ladx
```

Verify the app is responding:
```bash
curl http://localhost:8000/health
```

---

## Step 6: Get SSL Certificate

After DNS has propagated:

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com --email you@email.com --agree-tos --non-interactive
```

Certbot will automatically configure Nginx for HTTPS.

---

## Step 7: Verify

1. Open `https://yourdomain.com` in your browser — you should see the LADX landing page
2. Click **Get Started Free** — you should see the login/signup form
3. Create an account and start a project

---

## Useful Commands

| Action | Command |
|--------|---------|
| View logs | `sudo journalctl -u ladx -f` |
| Restart app | `sudo systemctl restart ladx` |
| Stop app | `sudo systemctl stop ladx` |
| Restart Nginx | `sudo systemctl restart nginx` |
| Update app | `cd /opt/ladx/app && sudo -u ladx git pull && sudo systemctl restart ladx` |
| Renew SSL | `sudo certbot renew` |
| Check SSL | `sudo certbot certificates` |

---

## Troubleshooting

**App won't start:**
```bash
sudo journalctl -u ladx --no-pager -n 50
```
Check for missing .env variables or Python import errors.

**502 Bad Gateway:**
The app isn't running. Check `systemctl status ladx` and app logs.

**SSL certificate error:**
Make sure DNS A records point to the correct VPS IP. Run `dig yourdomain.com` to verify.

**Permission denied errors:**
Make sure the ladx user owns the app directory:
```bash
sudo chown -R ladx:ladx /opt/ladx
```
