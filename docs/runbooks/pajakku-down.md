# Runbook — Pajakku Adapter Down

## Symptoms

- `custom_coretax.transaction` rows accumulating in `error` state
- Circuit breaker open notification posted on `custom.coretax.config`
- User reports "Faktur Pengganti / submission failing with Pajakku error"

## Triage (5 min)

```bash
# 1. Recent transaction states
docker compose exec postgres psql -U "$POSTGRES_USER" -d <tenant_db> -c \
  "SELECT state, COUNT(*), MAX(create_date) AS last_seen
     FROM custom_coretax_transaction
    WHERE create_date > now() - interval '1 hour'
    GROUP BY state;"

# 2. Sample last 5 errors
docker compose exec postgres psql -U "$POSTGRES_USER" -d <tenant_db> -c \
  "SELECT id, state, retry_count, left(last_error, 200) AS err
     FROM custom_coretax_transaction
    WHERE state IN ('error', 'rejected')
    ORDER BY create_date DESC LIMIT 5;"

# 3. Test connection from inside the container
# (Via Odoo: Coretax Config → Pajakku tab → "Test Connection" button)
# Or via shell:
docker compose exec odoo python -c "
from odoo import api, SUPERUSER_ID
import odoo
db = odoo.modules.registry.Registry('<tenant_db>')
with db.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    config = env['custom.coretax.config'].search([('active','=',True)], limit=1)
    adapter = env['custom.coretax.adapter.pajakku']
    print(adapter.test_connection(config))
"
```

## Diagnosis Tree

| Test connection result | Diagnosis | Fix |
|------------------------|-----------|-----|
| `{ok: false, message: "OAuth2 transport error..."}` | Network — can't reach Pajakku | Check outbound HTTPS; if blocked, fall back to manual export below |
| `{ok: false, message: "OAuth2 failed: HTTP 401..."}` | Bad credentials | Rotate client secret on Pajakku dashboard; "Set / Rotate Secret..." in Coretax config |
| `{ok: false, message: "client_secret could not be decrypted..."}` | Master KMS key changed | Restore `MASTER_WRAPPING_KEY` from secrets vault; restart Odoo |
| `{ok: true, ...}` but circuit still open | Circuit breaker hasn't closed (1h window) | Wait, or force reset: `docker compose restart odoo` |
| `{ok: true, ...}` and submissions still fail | DJP-side issue at Pajakku | Check <https://status.pajakku.com>; fall back to manual |

## Fallback: Manual XML Export

When Pajakku is hard down and faktur deadline is approaching:

1. In Coretax Config → set `adapter_type = manual` (preserve Pajakku
   credentials; just switch the active adapter).
2. Run the standard Coretax export wizard — it produces the XML the
   operator uploads via the Coretax portal.
3. Operator records the issued NSFP manually on the `account.move`.
4. Once Pajakku recovers, switch back: `adapter_type = pajakku`.

## Resume After Recovery

```bash
# Reset circuit breaker (after Test Connection passes)
docker compose restart odoo

# Retry queued + errored transactions
docker compose exec postgres psql -U "$POSTGRES_USER" -d <tenant_db> -c \
  "UPDATE custom_coretax_transaction SET state='queued', last_error=NULL
    WHERE state='error' AND retry_count < 3;"

# Next cron tick (every 30 min) will pick them up.
# Or trigger manually:
docker compose exec odoo python -c "
import odoo
db = odoo.modules.registry.Registry('<tenant_db>')
with db.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    env['custom.coretax.adapter.pajakku']._cron_poll_pending()
    cr.commit()
"
```

## Escalation

- > 24 hours total Pajakku unavailability → notify finance team;
  switch all tenants with active Pajakku adapter to manual until
  recovery confirmed.
- If Pajakku ToS dispute or contract issue → escalate to commercial
  owner of the Pajakku subscription.
