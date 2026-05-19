# Zebra DataWedge Profile for Platform HHTs

This guide configures a Zebra industrial handheld terminal (TC21, TC52,
TC72, etc.) to scan barcodes directly into the platform's HHT bridge
endpoint. The result: warehouse workers scan stock without typing,
and the platform receives a signed JSON POST per scan.

The Odoo-side receiver is built in `custom_hht_bridge` (Phase 2). This
document covers only the device-side DataWedge configuration.

---

## Use case

- Industrial handhelds (Zebra Android, DataWedge ≥ 11.0).
- Receiving, putaway, picking, stock-count operations.
- Symbologies in scope: **Code 128**, **EAN-13**, **QR Code**, **GS1-128**
  (also called UCC/EAN-128, mandatory for FEFO/lot scanning).

---

## DataWedge profile — step-by-step

### 1. Create / clone profile

DataWedge → **Profiles → +** → name it `PlatformScan`. Associate the
profile with the apps that should use it (browser, PWA wrapper, or
"All apps" for kiosk-style devices).

### 2. Enable barcode input

**Barcode input → Enabled = ON**.

In **Decoders**:

| Decoder         | Enabled |
| --------------- | ------- |
| Code 128        | YES     |
| EAN-13          | YES     |
| QR Code         | YES     |
| GS1-128         | YES     |
| (everything else) | OFF (reduces false reads) |

**Decoder Params → Code 128 → Length1 = 4, Length2 = 50** to reject
spurious very-short reads.

### 3. Output mode — Keystroke vs HTTP Post

DataWedge supports two output modes; configure both for redundancy.

**A. Keystroke Output (fallback):**

- Enabled = ON
- Action key character = `Carriage Return`
- This lets a worker fall back to a focused text field if the HTTP
  Post plugin is misconfigured.

**B. HTTP Post Output Plugin (primary):**

- Enabled = ON
- URL: `https://<tenant>.platform.example/api/hht/scan`
  (substitute the tenant subdomain; one profile per environment).
- Method: `POST`
- Headers:
  - `Content-Type: application/json`
  - `X-HHT-Device-ID: <device_id>`
  - `X-HHT-Signature: <pre-computed HMAC>` (see provisioning below).
- Data Format: **JSON**
- JSON body template:

  ```json
  {
    "barcode": "%BARCODE%",
    "action": "scan",
    "scanned_at": "%DATE%T%TIME%Z"
  }
  ```

  DataWedge expands `%BARCODE%`, `%DATE%`, `%TIME%` at scan time.

- Authentication = `None` (we authenticate via HMAC header, not Basic
  auth — the secret never leaves the device).
- Retry = ON, Retry interval = 30 s, Max retries = 50 (≈ 25 min offline
  tolerance; the device queues scans on Wi-Fi loss and replays them).
- Archive = ON (keep last 1000 successful scans on-device for audit).

---

## Device-ID and API secret provisioning

Each device receives a unique `device_id` and `api_secret` (HMAC key)
via the super-admin's **HHT Devices** page (`custom_hht_bridge`, Phase 2).

Provisioning flow:

1. Super-admin navigates to **Operations → HHT Devices → New**.
2. Fills serial number, tenant assignment, intended user group.
3. Clicks **Generate Credentials** → screen shows:
   - `device_id` (UUID v4)
   - `api_secret` (32-byte hex, shown once)
4. Operator imports the values into DataWedge:
   - `X-HHT-Device-ID` header → `device_id`.
   - `X-HHT-Signature` header → pre-computed HMAC over a rolling
     timestamp; in practice this is set by a tiny on-device companion
     app that signs each scan body with `api_secret` and rewrites the
     `X-HHT-Signature` header before DataWedge fires the POST. (Pure
     DataWedge cannot HMAC the body — the companion app is mandatory
     for production.)

If you don't run the companion app, fall back to a long-lived bearer
token instead: set `X-HHT-Device-ID` to the device UUID and put the
secret in `Authorization: Bearer <api_secret>`. Trade-off: a stolen
device replays all scans until you revoke. The HMAC path mitigates
replay via a `X-Timestamp` header.

---

## Test procedure

1. Open the DataWedge **Test** view in the profile.
2. Trigger a hardware scan on a known barcode (e.g. EAN-13 from a
   product).
3. Verify:
   - The scan body matches the JSON template above.
   - The HTTP POST returns `200 OK` with body `{"ok": true, ...}`.
   - In Odoo, **Operations → HHT Inbox** shows a new row within 5 s.
   - The platform audit log (`pdp.audit_log`) has an entry for
     `hht.scan.received` with the device ID.
4. Repeat with each enabled symbology to confirm the decoder list is
   correct.

---

## Failure modes & remediation

| Failure                              | Cause                                                          | Remediation                                                                                                              |
| ------------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Offline (Wi-Fi loss)**             | Plant Wi-Fi blip.                                              | DataWedge queues scans on-device; auto-replays when connectivity returns. Worker sees a small "queued" icon in the status bar. |
| **Bad / self-signed TLS cert**       | Custom internal CA; device doesn't trust it by default.        | Settings → Security → Encryption & credentials → **Install a certificate** → CA certificate. Push via MDM (StageNow / Workspace ONE). |
| **HTTP 401 `BAD_SIGNATURE`**         | Clock drift > 5 min or wrong `api_secret`.                     | Force device time sync (NTP); re-provision credentials in HHT Devices.                                                    |
| **HTTP 401 `DEVICE_UNKNOWN`**        | Device was deleted / archived super-admin side.                | Re-issue credentials; reassign in HHT Devices.                                                                            |
| **HTTP 429 rate-limit**              | Burst scan during stocktake exceeds tenant quota.              | Raise `custom_hht_bridge.rate_limit_per_min` for the tenant; or stagger workers.                                          |
| **Repeated 5xx**                     | Odoo backend down or DB locked.                                | DataWedge keeps retrying. Investigate platform; no data lost.                                                            |
| **Scans not appearing in Odoo**      | Wrong tenant URL (caller hitting a sibling tenant).            | Check `X-HHT-Device-ID` resolution; verify `tenant_id` on the device record matches the URL host.                         |
| **Wrong symbology being decoded**    | Decoder list too permissive; ambiguous barcodes (Code 39 vs 128). | Disable all decoders except the four in scope.                                                                            |

---

## MDM (mass rollout)

For ≥ 10 devices, do not configure by hand. Export the profile as a
`*.db` file (DataWedge → Profiles → Export) and push via your MDM
(StageNow XML, MobileIron, Workspace ONE). The exported profile
includes everything except the `api_secret`, which must be injected
per-device via the companion app at provisioning time.

Recommended fleet hygiene:

- Rotate `api_secret` every 90 days; do not reuse across devices.
- Disable the test profile on devices in production.
- Lock down device admin via Zebra StageNow PowerPrecision policy.
