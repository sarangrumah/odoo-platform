# AI Features Activation Guide

This guide turns on `custom_ai_features` for a production tenant. The
module surfaces the platform `ai-gateway` capabilities (Ask AI, Anomaly
Inbox, NLQ Chat, Doc Auto-Classify) throughout the Odoo UI.

Prerequisite: `ai-gateway` container is running and reachable from the
Odoo worker network. Default service URL is `http://ai-gateway:8080`
(compose service name).

---

## 1. Environment variables (gateway side)

Set these in the `ai-gateway` container's `.env` (`.env.ai-gateway` if
you use the layered compose files):

| Variable                | Purpose                                                   | Example / default                                  |
| ----------------------- | --------------------------------------------------------- | -------------------------------------------------- |
| `AI_GATEWAY_URL`        | Odoo-side URL of the gateway. Set in Odoo container env. | `http://ai-gateway:8080`                            |
| `GATEWAY_SHARED_SECRET` | HMAC secret between Odoo and gateway. Mandatory.          | `openssl rand -hex 32`                              |
| `ANTHROPIC_API_KEY`     | Anthropic Console API key (Claude).                       | `sk-ant-...`                                       |
| `OPENAI_API_KEY`        | Optional fallback provider.                               | `sk-...`                                           |
| `OLLAMA_URL`            | Optional self-hosted fallback (Llama, Mistral).           | `http://ollama:11434`                              |

Generate `GATEWAY_SHARED_SECRET` once per environment:

```bash
openssl rand -hex 32
```

Mirror the same value on the Odoo side under
`ir.config_parameter` key `custom_ai_bridge.gateway_secret` (Settings →
Technical → Parameters → System Parameters).

---

## 2. Per-tenant override (Odoo side)

Navigate: **Settings → Custom Platform → AI Intelligence**.

Each tenant can override:

- `custom_ai_bridge.gateway_url` — override the gateway endpoint
  (useful for staging-only tenants).
- `custom_ai_features.default_provider` — `anthropic` | `openai` | `ollama`.
- `custom_ai_features.default_model` — see provider selection below.
- `custom_ai_features.anomaly_scan_cron_utc` — cron schedule
  (default `30 2 * * *` = 02:30 UTC daily).
- `custom_ai_features.max_tokens_per_request` — hard cap, default `4096`.

---

## 3. Provider / model selection

| Use case                                  | Default model          | Why                                                                                       |
| ----------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------------- |
| **Ask AI** (record-level "explain / suggest") | Claude Sonnet 4.6       | Balanced accuracy + cost; user-facing latency target < 3 s.                                |
| **Anomaly Inbox**                         | Claude Haiku 4.5        | Nightly batch over thousands of rows. Throughput + low cost win over marginal accuracy gain. |
| **Doc Auto-Classify**                     | Claude Haiku 4.5        | High volume on document upload. Classification ⇒ Haiku is plenty.                          |
| **NLQ Chat** (`/ai/chat`)                 | Claude Opus 4.7         | Translates ambiguous natural language to SQL/domain — accuracy matters most.               |
| **Self-hosted / air-gapped fallback**     | `ollama:llama3.1:8b`    | When tenant policy disallows external APIs.                                               |

Override per use case via `ir.config_parameter`:

```
custom_ai_features.model.ask_ai        = claude-sonnet-4-6
custom_ai_features.model.anomaly_scan  = claude-haiku-4-5
custom_ai_features.model.doc_classify  = claude-haiku-4-5
custom_ai_features.model.nlq_chat      = claude-opus-4-7
```

---

## 4. Prompt caching (Anthropic)

Anthropic prompt caching reduces cost ~90% and latency on cache hits.
TTL is 5 minutes. The `ai-gateway` *must* set
`cache_control: {type: "ephemeral"}` on the system prompt block (and on
any large stable context, e.g. company schema).

### Verify activation

```bash
docker compose exec ai-gateway env | grep CACHING
# expect: ANTHROPIC_PROMPT_CACHING_ENABLED=1
```

### Example outbound payload (gateway → Anthropic)

```json
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 1024,
  "system": [
    {
      "type": "text",
      "text": "You are an Odoo accounting assistant. Schema...",
      "cache_control": {"type": "ephemeral"}
    }
  ],
  "messages": [
    {"role": "user", "content": "Why is this invoice overdue?"}
  ]
}
```

The response includes `usage.cache_creation_input_tokens` (first call)
or `usage.cache_read_input_tokens` (subsequent hits within 5 min).
Monitor cache hit rate via the gateway's `/metrics` endpoint
(`ai_gateway_cache_hit_total`).

---

## 5. Cron schedules

Default schedules (override in **Settings → Technical → Scheduled
Actions**):

| Cron                         | Default schedule | What                                              |
| ---------------------------- | ---------------- | ------------------------------------------------- |
| AI Anomaly Scan              | `30 2 * * *` UTC | Scan `account.move`, `hr.payslip`, etc.            |
| AI Cost Aggregation          | `0 * * * *`      | Roll up `custom.ai.usage.daily`.                   |
| Doc Auto-Classify (reactive) | on create        | Hook on `document.document` create — not a cron.   |

To change the anomaly cron timing:

```python
cron = env.ref('custom_ai_features.ir_cron_anomaly_scan')
cron.write({'interval_type': 'days', 'interval_number': 1,
            'nextcall': '2026-05-20 02:30:00'})
```

---

## 6. Cost tracking

`custom.ai.usage.daily` aggregates per-tenant, per-model token counts
and dollar cost. Anthropic usage is pulled via the [Usage and Cost
API](https://docs.anthropic.com/en/api/admin-api/usage-cost/get-cost-report)
hourly:

```
GET https://api.anthropic.com/v1/organizations/{org_id}/usage_report/messages
Authorization: Bearer $ANTHROPIC_API_KEY
```

Output is reconciled with the gateway's own per-request `ai_call_log`
to attribute costs to the originating tenant + use case.

---

## 7. Troubleshooting

| Symptom                                       | Likely cause                                              | Fix                                                                          |
| --------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `GATEWAY_UNREACHABLE` on Ask AI               | Gateway container down or wrong URL.                       | `docker compose ps ai-gateway`; curl `$AI_GATEWAY_URL/healthz`.               |
| `SIGNATURE_MISMATCH` 401                      | Odoo and gateway have different `GATEWAY_SHARED_SECRET`.   | Re-sync the secret; restart both containers.                                  |
| `RATE_LIMITED` 429 from Anthropic             | Burst > org tier.                                         | Gateway has a token-bucket retry with backoff; if persistent, raise tier or shift volume to Haiku. |
| Slow responses, no cache hits                 | `cache_control` not set on system prompt.                  | Check gateway logs; ensure system prompt > 1024 tokens (caching minimum).      |
| Anomaly scan produces nothing                 | Cron disabled, or window has no source rows.               | Check `Settings → Scheduled Actions`; check `ai.anomaly.scan` log.            |
| Fallback provider not used                    | `custom_ai_features.fallback_provider` not set.            | Set to `openai` or `ollama` to enable second-chance on 5xx from primary.       |

---

## 8. Verification steps (post-deploy)

1. Open any posted `sale.order`. Click the cog → **Ask AI**. A wizard
   appears with a streaming answer within 3 s on cache hit (warm), or
   < 6 s on cold start.
2. Settings → Technical → Scheduled Actions → **AI Anomaly Scan** →
   **Run Manually**. Within 60 s, check **AI → Anomaly Inbox**;
   findings appear if any outliers existed.
3. Open `/ai/chat` as a portal user; ask "show invoices over 100M
   posted this month". Expect a structured table of results.
4. Check **AI → Cost Tracking** the next day: yesterday's tokens and
   USD cost should be populated.
