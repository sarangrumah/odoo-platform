# SOC 2 Control Matrix

Mapping of the Trust Service Criteria (TSC) to platform components that
implement, evidence, or monitor each control. This is a **self-attestation
matrix** — not a formal SOC 2 Type II audit report. Use as the starting
point when an external audit is commissioned.

> Coverage applies to the Phase 2 multi-tenant deployment. Items marked
> 🟡 are partially covered (manual workflow or partial automation);
> ⚪ items are out of scope for this iteration.

## Trust Service Criteria

### CC1 — Control Environment

| Control | Status | Evidence |
|---------|--------|----------|
| CC1.1 — Demonstrates commitment to integrity and ethical values | 🟡 | Repository code-of-conduct (TODO), separation of duties via `group_*` |
| CC1.2 — Board independence + oversight | ⚪ | Out of platform scope — organisational |
| CC1.3 — Establishes structures, reporting lines, authorities | ✓ | `custom_super_admin` group hierarchy, `custom_approval_engine` matrices |
| CC1.4 — Demonstrates commitment to competence | ⚪ | Hiring practice — out of scope |
| CC1.5 — Holds individuals accountable | ✓ | Every state change written to `pdp.audit_log` w/ `actor_user_id` |

### CC2 — Communication and Information

| Control | Status | Evidence |
|---------|--------|----------|
| CC2.1 — Internal communications | ✓ | `mail.thread` on `tenant.registry`, `approval.request`, `custom.coretax.transaction` |
| CC2.2 — Communications with external parties | 🟡 | Portal endpoint `/my/approvals`, customer-facing email templates; status page TBD |
| CC2.3 — Whistleblower channel | ⚪ | Out of platform scope |

### CC3 — Risk Assessment

| Control | Status | Evidence |
|---------|--------|----------|
| CC3.1 — Specifies objectives | ✓ | This document, Phase 2 plan file |
| CC3.2 — Identifies + analyses risks | ✓ | `docs/runbooks/disaster-recovery.md` § Severity Classification |
| CC3.3 — Considers fraud | 🟡 | Append-only `pdp.audit_log` + `tenant_registry.action_log` with hash chains; no UEBA |
| CC3.4 — Identifies + assesses change risks | 🟡 | CI runs SAST + dependency scan; staging environment for changes pending |

### CC4 — Monitoring Activities

| Control | Status | Evidence |
|---------|--------|----------|
| CC4.1 — Selects, develops, performs monitoring | ✓ | `observability/` stack — Prometheus + Grafana + Loki + Alertmanager |
| CC4.2 — Evaluates and communicates deficiencies | ✓ | era-predictor → ai-gateway capacity recommendations; post-mortems |

### CC5 — Control Activities

| Control | Status | Evidence |
|---------|--------|----------|
| CC5.1 — Selects + develops control activities | ✓ | `custom_approval_engine` (multi-tier + delegation + escalation) |
| CC5.2 — Selects + develops technology controls | ✓ | HMAC-signed inter-service auth (ai-gateway + tenant-orchestrator); read-only containers; seccomp profile |
| CC5.3 — Deploys via policies + procedures | ✓ | `docs/sops/` — tenant onboarding/offboarding |

### CC6 — Logical and Physical Access

| Control | Status | Evidence |
|---------|--------|----------|
| CC6.1 — Implements logical access controls | ✓ | Odoo `res.groups` + record rules + per-model ACLs; postgres roles (`tenant_orchestrator`, `tenant_registry_reader`, `odoo_pdp_writer`) |
| CC6.2 — Provisions logical access | ✓ | `custom_super_admin` provisioning flow; CSM-driven (no self-service) |
| CC6.3 — Revokes logical access | ✓ | `make tenant-suspend` + Odoo user archive; orphan-cleanup cron in scheduler |
| CC6.4 — Restricts physical access | ⚪ | Datacenter — VPS provider responsibility |
| CC6.5 — Encrypts data at rest | ✓ | Sertel encrypted via `custom.ir.config` (Fernet); per-tenant DEK envelope-encrypted with master KMS key; MinIO `ServerSideEncryption: AES256` on backups |
| CC6.6 — Encrypts data in transit | ✓ | Caddy TLS termination (internal CA → ACME in prod); HTTPS to Pajakku |
| CC6.7 — Disposes of confidential information | ✓ | `custom_pdp_retention` cron + DSAR anonymisation in `custom_pdp_dsar` |
| CC6.8 — Restricts privileged user access | ✓ | Super-admin database isolated; `group_super_admin` distinct from `group_csm` |

### CC7 — System Operations

| Control | Status | Evidence |
|---------|--------|----------|
| CC7.1 — Detects + monitors anomalies | ✓ | `era-predictor` + Alertmanager rules in `observability/prometheus/alerts/` |
| CC7.2 — Monitors components + configures | ✓ | Healthchecks on every service in `docker-compose.yml`; Prometheus `up{}` metric |
| CC7.3 — Identifies + corrects security events | ✓ | Circuit breaker on Pajakku adapter; HMAC rejection logging in ai-gateway + orchestrator |
| CC7.4 — Identifies + addresses security incidents | ✓ | `docs/runbooks/disaster-recovery.md` |
| CC7.5 — Restores from incidents | ✓ | `make tenant-restore` + DR runbook + monthly drill schedule |

### CC8 — Change Management

| Control | Status | Evidence |
|---------|--------|----------|
| CC8.1 — Authorises + manages + implements changes | 🟡 | GitHub Actions CI; no formal change-advisory board (small team) |

### CC9 — Risk Mitigation

| Control | Status | Evidence |
|---------|--------|----------|
| CC9.1 — Identifies + selects risk mitigations | ✓ | Circuit breaker + retry policy + backup retention + DR drill |
| CC9.2 — Assesses + manages vendor + business partner risks | 🟡 | Pajakku SLA tracked via `custom.coretax.pajakku.usage` + Test Connection button |

### A1 — Availability

| Control | Status | Evidence |
|---------|--------|----------|
| A1.1 — Maintains current processing capacity | ✓ | `era-predictor` + `tests/load/k6/` |
| A1.2 — Authorises + designs + develops disaster recovery | ✓ | DR runbook + monthly drills |
| A1.3 — Tests disaster recovery | ✓ | `scripts/chaos/` drill scripts |

### C1 — Confidentiality

| Control | Status | Evidence |
|---------|--------|----------|
| C1.1 — Identifies + maintains confidential information | ✓ | `pdp.classification` taxonomy + `_pdp_audit_classification()` mixin |
| C1.2 — Disposes of confidential information | ✓ | `custom_pdp_retention` daily cron |

### P (Privacy)

UU 27/2022 mapping documented separately in `docs/pdp-compliance.md`. SOC 2
Privacy criteria largely align with what we built for PDP — see that file
for one-to-one mapping.

---

## Automated Verification

Run `make compliance-verify` to execute every automatable check in this
matrix. The script:

1. Verifies `pdp.audit_log` hash chain integrity per tenant.
2. Verifies `tenant_registry.action_log` master-DB chain.
3. Counts coverage: every `account.move._post` for the last 30 days
   must have a corresponding `pdp.audit_log` row; same for approval
   state changes + Pajakku transactions.
4. Verifies encryption at rest: master wrapping key present, sertel
   ciphertext present (not plaintext), per-tenant DEK wrapped.
5. Verifies access boundary: a non-`group_super_admin` user cannot
   read `tenant.registry` via the ORM.
6. Verifies retention: at least one `pdp.retention.policy` exists
   per tenant.

A failed run emits a structured JSON report
(`docs/compliance/_last_verify.json`) suitable for attaching to a
quarterly review.

## Manual Evidence Collection

For an external audit, also collect:

- Last 12 months of incident post-mortems
  (`docs/runbooks/postmortems/`)
- Monthly DR drill log (DR runbook § Appendix)
- Backup verification logs (`make verify-backup TENANT=...`)
- CI run artefacts (SAST + dependency scan reports)
- SOPS-encrypted secret rotation log (operator should keep a
  manual log of rotation dates + actor)
