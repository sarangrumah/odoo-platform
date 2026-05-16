# CI/CD activation guide

The repo includes 3 ready-to-fire GitHub Actions workflows but has not been pushed to a remote yet. This guide walks an operator through the activation sequence.

## Prerequisites
- A GitHub (or GitLab — workflows would need rewriting) account.
- `gh` CLI authenticated: `gh auth login`.
- Local repo at `E:\Projects\Odoo\platform` already `git init`-ed (done in phase 3D).

## Step 1 — Create the remote
```bash
# Private by default — flip to --public only if intentional
gh repo create odoo19-platform --private --source=. --remote=origin
```

## Step 2 — First push (triggers CI on GitHub)
```bash
git push -u origin main
```
This kicks off all 3 workflows on the first push:
- `ci.yml`: lint (pre-commit) → SAST (Semgrep+CodeQL) → SCA (pip-audit) → secret-scan (gitleaks) → container-scan (Trivy) → fs-scan → sign-images
- `codeql.yml`: weekly CodeQL Python scan + per-PR
- `dependency-review.yml`: PR-only dependency review

## Step 3 — Install pre-commit hooks locally
```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
pre-commit run --all-files   # fix existing issues before pushing
```

## Step 4 — Branch protection (recommended)
```bash
gh api repos/$(gh repo view --json owner,name -q '.owner.login + "/" + .name')/branches/main/protection \
  --method PUT \
  --field required_status_checks[strict]=true \
  --field required_status_checks[contexts][]=lint \
  --field required_status_checks[contexts][]=sast-python \
  --field required_status_checks[contexts][]=sca-python \
  --field required_status_checks[contexts][]=secret-scan \
  --field required_status_checks[contexts][]=container-scan \
  --field required_status_checks[contexts][]=fs-scan \
  --field enforce_admins=false \
  --field required_pull_request_reviews[required_approving_review_count]=1 \
  --field restrictions=null
```

## Step 5 — Container registry + cosign keyless OIDC
The `sign-images` job in `ci.yml` is a placeholder. To enable real signing:
1. Create a GHCR (GitHub Container Registry) repository (auto-created on first push from CI with `packages: write` permission already set).
2. Replace the placeholder step in `ci.yml`:
   ```yaml
   - name: Login to GHCR
     uses: docker/login-action@v3
     with:
       registry: ghcr.io
       username: ${{ github.actor }}
       password: ${{ secrets.GITHUB_TOKEN }}
   - name: Push + sign
     run: |
       docker tag local-odoo:ci ghcr.io/${{ github.repository }}/odoo:${{ github.sha }}
       docker push ghcr.io/${{ github.repository }}/odoo:${{ github.sha }}
       cosign sign --yes ghcr.io/${{ github.repository }}/odoo:${{ github.sha }}
   ```
3. `id-token: write` permission is already declared in `ci.yml`.

## Step 6 — Local SBOM (optional, mirrors what CI does)
```bash
pip install cyclonedx-bom
cyclonedx-py environment -o sbom-odoo.json --of JSON
cyclonedx-py requirements -i odoo/requirements.txt -o sbom-odoo-reqs.json --of JSON
cyclonedx-py pipenv -i ai-gateway/pyproject.toml -o sbom-ai-gateway.json --of JSON
```
SBOMs are gitignored as `sbom-*.json` per `.gitignore`. Upload them as workflow artifacts (CI already does this).

## Step 7 — Run workflows locally with `act` (optional)
```bash
# Install act once:
go install github.com/nektos/act@latest
act -j lint --container-architecture linux/amd64
act -j sast-python
```
`act` runs GitHub Actions inside Docker on your host — useful for debugging before pushing.

## Known gaps to fix before first prod merge

| Gap | Workaround | Priority |
|---|---|---|
| `mail_tracking` not vendored from OCA (no 19.0 or 18.0 branch yet) | Watch [`OCA/social`](https://github.com/OCA/social). Re-run `bash addons/_vendor/fetch_oca.sh`. | Low |
| `base_rest_auth_jwt` not vendored | Same. | Low |
| `auth_jwt` vendored from OCA 18.0 — needs Odoo 19 port | Smoke-test install; fix any Odoo 19 API breaks (`res.groups.privilege_id` etc.). | Medium |
| Coretax XSDs are placeholders | Manual download via Coretax portal then drop into `addons/compliance/custom_coretax/data/xsd/`. | High (compliance blocker) |
| `ANTHROPIC_API_KEY` in `.env` is a stub | Replace with real key + re-encrypt `.secrets.enc.yaml` via SOPS. | High (AI features won't work) |
| node-exporter doesn't run on Docker Desktop/WSL2 | Accept on dev; works fine on Linux prod hosts. | Low |
| Self-signed nginx cert | For prod: use `make up-tls` with `DOMAIN` + `ACME_EMAIL` set, Caddy auto-issues LE cert. | High (only blocks public TLS) |
| S3 backup not yet tested | Configure `S3_*` env vars then `make backup-now` and verify object in bucket. | Medium |

## Verifying CI after first push
- `gh run list --limit 5` — list recent runs.
- `gh run view <run-id> --log` — fetch logs.
- `gh run watch` — live tail.
- Workflow files reference `secrets.GITHUB_TOKEN` (auto-provided). No additional secrets need to be configured in repo Settings → Secrets unless you wire in external services (S3 backup creds, Anthropic API key for integration tests, etc.).
