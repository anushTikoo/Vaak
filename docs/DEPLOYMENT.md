# Vaak (वाक्) — Cloudflare & Deployment Guide

This guide documents the setup process for Cloudflare Python Workers, Neon PostgreSQL, and Cloudflare Hyperdrive.

> [!NOTE]
> Cloudflare hosting and public deployment are deferred until local MVP verification is finalized. This guide outlines the setup for future staging and production rollouts.

---

## 1. Cloudflare Python Worker Setup

The backend uses Cloudflare's official Python Workers runtime with FastAPI ASGI integration (`workers.asgi.entrypoint(app)`).

### Steps to Deploy:
1. **Authenticate Wrangler**:
   ```bash
   npx wrangler login
   ```
2. **Review `services/backend/wrangler.jsonc`**:
   Ensures `compatibility_flags: ["python_workers"]` is enabled.
3. **Local Worker Simulation**:
   ```bash
   cd services/backend
   npx wrangler dev
   ```
4. **Deploy to Cloudflare Workers**:
   ```bash
   cd services/backend
   npx wrangler deploy
   ```

---

## 2. Neon PostgreSQL & Hyperdrive Configuration

1. Create a serverless PostgreSQL database on [Neon](https://neon.tech).
2. Copy the connection string:
   `postgres://[user]:[password]@[neon-host]/[dbname]?sslmode=require`
3. Configure Cloudflare Hyperdrive:
   ```bash
   npx wrangler hyperdrive create vaak-db-hyperdrive \
     --connection-string="postgres://[user]:[password]@[neon-host]/[dbname]?sslmode=require"
   ```
4. Bind the Hyperdrive ID into `wrangler.jsonc`:
   ```jsonc
   "hyperdrive": [
     {
       "binding": "HYPERDRIVE",
       "id": "<YOUR_HYPERDRIVE_ID>"
     }
   ]
   ```

---

## 3. Cloudflare Secrets Management

Never commit secrets to Git or include them in client builds. Set secrets via Wrangler CLI:

```bash
cd services/backend
npx wrangler secret put SARVAM_API_KEY
npx wrangler secret put ZEPTO_CLIENT_SECRET
```
