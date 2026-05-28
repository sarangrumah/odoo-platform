# Ollama Local LLM — Deployment Steps

Self-hosted LLM via the `ollama` service. Optional overlay that lets the
`ai-gateway` route requests to local models instead of Anthropic / OpenAI.
Use it for offline demos, cost-sensitive workloads, or data-residency
constraints.

> Compose overlay: `docker-compose.local-llm.yml` (service `ollama`,
> bind-mount `./data/ollama:/root/.ollama`, mem cap 8 GB).
> Makefile shortcuts: `make up-llm` (dev) — see `Makefile:50`.

---

## 1. Prerequisites (VPS)

- Docker Engine ≥ 24 + Docker Compose v2.
- RAM: **≥ 12 GB** total on the host (Ollama alone gets 8 GB; leave
  headroom for Postgres + Odoo workers). For 7B-class models bump to 16
  GB.
- CPU: 6 vCPU minimum (env `OLLAMA_NUM_THREAD=6`). GPU is optional and
  not configured by default — add an `nvidia` runtime block if needed.
- Disk: **≥ 20 GB** free under `./data/ollama` (models are 2–8 GB each).
- Network: outbound to `https://ollama.com` for initial model pull.

---

## 2. First-time bring-up (fresh VPS after `git pull`)

```bash
# 1. Make sure base stack is up
make up                        # or:  docker compose up -d

# 2. Bring up the Ollama overlay alongside it
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.local-llm.yml \
  up -d ollama

# 3. Pull a model into the bind-mounted volume (one-time per model)
docker compose exec ollama ollama pull llama3.2:3b
# Optional larger model for better quality:
# docker compose exec ollama ollama pull llama3.1:8b

# 4. Verify
docker compose exec ollama ollama list
curl -s http://localhost:11434/api/tags | jq .
```

For **dev** on a workstation, the equivalent is just:

```bash
make up-llm
docker compose exec ollama ollama pull llama3.2:3b
```

---

## 3. Persist the overlay so you don't retype `-f` flags

Pick one:

**Option A — env var (recommended for VPS):**

```bash
# /etc/profile.d/odoo-compose.sh   (or append to ~/.bashrc of the deploy user)
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml:docker-compose.local-llm.yml
```

After this, plain `docker compose up -d` includes Ollama automatically.

**Option B — `.env` file at repo root:**

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml:docker-compose.local-llm.yml
```

---

## 4. Route `ai-gateway` to Ollama

In the repo-root `.env` (read by `docker-compose.yml:174`):

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
# Optional: pin default model used by the gateway
OLLAMA_DEFAULT_MODEL=llama3.2:3b
```

Recreate the gateway so it picks up the new env:

```bash
docker compose up -d --force-recreate ai-gateway
docker compose logs -f ai-gateway | grep -i provider
```

Per-tenant override is also available in Odoo:
**Settings → Custom Platform → AI Intelligence → Provider Override =
Local Ollama**.

---

## 5. Smoke test end-to-end

```bash
# Direct to Ollama
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3.2:3b","prompt":"ping","stream":false}' | jq -r .response

# Via gateway (replace SECRET with GATEWAY_SHARED_SECRET)
curl -s -X POST http://localhost:8080/v1/complete \
  -H "X-Gateway-Secret: $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"ping","quality":"fast"}'
```

In Odoo, open any record with the **Ask AI** action — the response
header should show `provider=ollama`.

---

## 6. Operational notes

- **Model storage** lives in `./data/ollama/` — back it up or
  `rsync` it to skip re-downloading on a rebuilt VPS.
- **Memory pressure**: `OLLAMA_KEEP_ALIVE=10m` unloads idle models;
  drop to `2m` on tight VPS.
- **Health**: `docker compose ps ollama` should show `healthy`
  (probe = `ollama list`).
- **Switching back to Anthropic**: set `AI_PROVIDER=anthropic` and
  recreate `ai-gateway`; the `ollama` container can stay running idle
  or be stopped with `docker compose stop ollama`.

---

## 7. When to choose Ollama vs Anthropic

See the presentation slide **"AI Provider Tradeoffs"**
(`docs/presentation-erajaya-vas.md`, Slide 10b) and the in-app banner
under **Settings → AI Intelligence**. Short version:

| Aspect              | Anthropic Claude         | Local Ollama              |
| ------------------- | ------------------------ | ------------------------- |
| Quality (reasoning) | High (Sonnet/Opus class) | Moderate (3B–8B class)    |
| Latency             | 1–4 s / request          | 3–15 s on CPU-only VPS    |
| Cost                | Per-token billing        | Flat (VPS RAM/CPU only)   |
| Data residency      | Sent to Anthropic API    | Stays on-prem             |
| Throughput          | Scales horizontally      | Bound by single VPS       |
| Offline support     | No                       | Yes                       |
| Best for            | Production reasoning,    | Demos, PoC, sensitive     |
|                     | NLQ, anomaly explain     | docs, air-gapped tenants  |
