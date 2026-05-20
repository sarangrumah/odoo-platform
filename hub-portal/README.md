# Hub Portal

Internal control plane for the Erajaya Odoo multi-tenant platform.

Stack: Vite 5 + React 18 + TypeScript + Express (proxy/HMAC signer).

## Dev

```
npm install
npm run server   # express proxy on :18001 (orchestrator + Odoo bridge)
npm run dev      # vite on :18000
```

Env vars (server):

```
ORCHESTRATOR_BASE_URL=http://orchestrator:8000
ORCHESTRATOR_SHARED_SECRET=<>=32 chars>
ODOO_BASE_URL=http://odoo:8069
ODOO_DB=hub_admin
ODOO_LOGIN=admin
ODOO_PASSWORD=admin
```
