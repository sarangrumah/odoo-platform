# MDM Product Master API — Integration Guide

**Audience:** Levi's Principal / MDM HUB team, SAP PO and Mulesoft integrators
**Version:** 19.0.1.0.0 · 27 July 2026
**Machine-readable spec:** [`mdm-product-api.openapi.yaml`](mdm-product-api.openapi.yaml) (OpenAPI 3.1 — importable into Mulesoft/Anypoint, Postman, Insomnia)

Erajaya exposes a REST endpoint that consumes the item-master JSON your MDM HUB
already produces, so the SSRS **X101** report no longer has to be run to keep Odoo's
product master current.

```
MDM HUB  →  SAP PO  →  IBM MQ  →  Mulesoft  →  POST <base>/products  →  Odoo
```

---

## 1. Connection

| | |
|---|---|
| Base URL — UAT | `https://103.130.240.24/api/mdm/uat` |
| Base URL — production | `https://103.130.240.24/api/mdm` — reserved, currently answers `404 NOT_DEPLOYED` |
| Auth | `Authorization: Bearer <key>` — or `X-API-Key: <key>` |
| API key | issued separately, not in this document |
| IP allow-list | your egress addresses must be registered with Erajaya first |
| TLS | internally-issued certificate (the host is addressed by IP, so no public CA can sign for it). For UAT, disable certificate verification; for production we will move to a named domain with a public certificate |

Check the connection before anything else — it has no side effects:

```bash
curl -k -H "Authorization: Bearer $KEY" https://103.130.240.24/api/mdm/uat/ping
# {"status":"ok","data":{"pong":true,"enabled":true,"dryRun":false,
#  "version":"19.0.1.0.0","environment":"uat","database":"tst_mdm_levis"},"error":null}
```

`enabled: false` means Erajaya has the service switched off — ingest will answer 503.
`dryRun: true` means messages are validated and mapped but **no product is written**;
that is the shadow phase, and it is expected at the start of the rollout.

---

## 1a. Telling UAT and production apart

They share this host, this port and this certificate. **The path prefix is the only
thing separating them**, and once your client is configured you cannot see it in a
response. So the endpoint states which system it is, and it does so on the write path
as well as on the health check:

```json
GET  /ping   → {"environment": "uat", "database": "tst_mdm_levis", ...}
POST /products → 202 {"environment": "uat", "database": "tst_mdm_levis", "requestId": "..."}
```

Please assert on `environment` before a run rather than trusting the URL your client
was configured with — that is the whole reason the field exists. An unconfigured
system answers `"unknown"`, which is deliberately not a reassuring value.

The production base URL is reserved rather than left unrouted: it answers
`404 NOT_DEPLOYED` today. Switching environments is therefore a change you make, not
one that happens to you when we deploy.

---

## 2. The two fields that decide everything

Getting these wrong is the one failure mode that is expensive to undo, so they are
worth stating before anything else.

### `udf2` is the SKU — not `skuCode`

X101 composes its PROD SKU as:

```
PROD SKU = PRODUCT_CODE without dashes + "0" + SIZE + INSEAM
```

We verified this against all **214,305 rows** of the material master: it holds without
a single exception. For the reference item:

```
udf1 = 002IJ-0027  →  002IJ0027 + "0" + "32" + "28"  =  002IJ002703228  =  udf2  ✓
skuCode = 002IJ-00273228   ← keeps the dash; this form appears nowhere in X101
```

So Odoo keys the product variant on **`udf2`**. `skuCode` is stored as an additional
lookup key — you can query by it — but it is never the internal reference. If we had
used `skuCode` instead, every sales transaction arriving from the stores would fail to
match its product.

**`udf2` is mandatory.** An item without it is rejected rather than guessed at.

### `udf1` is the template

All sizes of one article share `udf1`. Odoo creates one product template per `udf1`,
and one variant per `udf2` underneath it, with Size and Inseam as attributes.

---

## 3. Sending

One item, or an array of them — the near-realtime feed can send one message per SKU
while an initial load sends batches (up to 1,000 items, 5 MB per request).

```bash
curl -k -X POST https://103.130.240.24/api/mdm/uat/products \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: 4f0c1a2e-..." \
  -d @item.json
```

```json
HTTP 202
{"status":"ok","data":{"requestId":"6daaf1215aaa424abc4126b7840d61c1",
 "accepted":1,"duplicate":false,"skuCodes":["002IJ-00273228"],
 "environment":"uat","database":"tst_mdm_levis"},"error":null}
```

**202 means accepted, not applied.** The message is stored and the product write
happens immediately afterwards, asynchronously, so your call never waits on Odoo
generating a size matrix. Poll for the outcome:

```bash
curl -k -H "Authorization: Bearer $KEY" \
  https://103.130.240.24/api/mdm/uat/requests/6daaf1215aaa424abc4126b7840d61c1
```

### Retries are safe — please send `X-Request-Id`

Repeat the same id and the message is recognised: HTTP **200** with
`duplicate: true`, and nothing happens a second time. That makes a retry after a
timeout the correct thing to do.

It is deliberately not a 409: a retry is not an error.

Without the header we fall back to a hash of the body, which also works but cannot
distinguish "you re-sent the same message" from "you genuinely re-sent unchanged
content".

Re-sending the same SKU with **changed** content is not a duplicate. It is an update,
and it is applied.

---

## 4. Reading the result

`state` on the request is `done` when every item settled cleanly, `partial` when at
least one needs attention. Each item then carries its own `state`:

| Item state | Meaning | Action |
|---|---|---|
| `done` | Created or updated | — |
| `duplicate` | Byte-identical to what we already hold; nothing written | — |
| `skipped` | Deliberately not applied. Usually a **stale message**: a newer update for this SKU had already been applied, so this one is ignored rather than allowed to revert it | none, unless you believe it was newest |
| `needs_review` | Applied, but a human should look. Most often the category pair is not in the agreed crosswalk yet | see §5 |
| `conflict` | **Refused, nothing written.** The GTIN belongs to a different product, or the article code collides | fix at source and re-send |
| `error` | Could not be processed; `error` says why | fix and re-send |

`conflict` is the one that needs your attention most. We never move a barcode from one
product to another: a GTIN that already belongs to a different SKU is refused, because
silently reassigning it would redirect every point-of-sale scan of that code in every
store.

---

## 5. Category mapping — the open item

Your feed sends a two-level taxonomy:

```json
"category1": "BOTTOMS", "category2": "LONG BOTTOMS", "udf8": "MEN"
```

X101 uses a three-level, gender-prefixed one — 7 top-level categories and 118
`CATEGORY / CLASS / SUBCLASS` combinations, e.g. `MENS BOTTOMS / JEANS / SLIM`.

Level 1 reconstructs cleanly (`MEN` + `BOTTOMS` → `MENS BOTTOMS`). But `LONG BOTTOMS`
is not a CLASS value in X101, and **there is no SUBCLASS in the payload at all**.

This matters beyond naming: in Odoo the product category drives the revenue and cost-
of-goods accounts, so guessing would misstate the financial reporting. We therefore
keep an explicit mapping table on our side. Until a pair is in it, the product is
**still created** — so sales can post — but flagged `needs_review`.

**What we need from you:** either send the X101 `CATEGORY / CLASS / SUBCLASS` triple
directly, or agree a mapping covering every `category1`/`category2` pair you will
emit. See §8.

---

## 6. Fields we record but do not apply

Two incoming values move money, so they are stored against the product and applied
only when Erajaya's finance team switches them on:

- **`baseCost`** → product cost. On goods that already have stock, writing cost posts
  an inventory revaluation journal entry.
- **`isActive: "No"`** → archiving. It cascades to all variants and can break open
  orders and stock records.

`isSaleable` **is** applied — it stops new sales without touching history.

`serialTrackingRequired` is applied **when the product is created**. Changing it later
on a product that already holds stock is refused by Odoo, so such a change comes back
as `needs_review` rather than being forced.

Fields we do not yet map — `budf3`, `udf3`, `udf5`, `udf6`, `udf7` — are stored
verbatim, so nothing is lost and we can map them later without asking you to re-send.

---

## 7. Barcodes

One `upc_ean` per message, but a SKU has several GTINs. They **accumulate**: send them
in successive messages and every one will resolve at the till. The first GTIN stays
the primary barcode; later ones are added alongside it and never replace it.

We cannot currently detect a **withdrawn** GTIN — see §8.

---

## 8. Open questions for the MDM HUB team

Answers to the first three are needed before we write to live master data.

1. **Category taxonomy.** Can the feed send X101's `CATEGORY / CLASS / SUBCLASS`
   triple? If not, we need a signed-off mapping for every `category1`/`category2`
   pair — and confirmation from finance that a two-level tree is acceptable, given
   118 three-level categories exist today with account mappings attached.
2. **Confirm `udf2` is the stable SKU** and `skuCode` is a display/composite form. If
   the HUB considers `skuCode` primary, migrating 159,658 existing variants is a
   separate project and must be planned as one.
3. **`salePrice` and `baseCost` are both `"999"`** in the reference payload, while
   X101 retail prices are of the order of `749900` IDR. What currency and scale is
   this? Is `baseCost` a real landed cost, or a placeholder?
4. **GTIN withdrawal.** Is there a delete/deactivate event for a barcode, or only
   additions?
5. **`isActive: "No"`** — discontinued, or temporarily unavailable?
6. **Ordering.** Does MQ/Mulesoft guarantee per-SKU ordering? We currently treat the
   arrival time as the version. A source-side `lastModified` timestamp in the payload
   would be materially better, and we would use it in preference.
7. **Delta or full refresh?** A periodic full push of ~160k SKUs needs a scheduled
   window; deltas do not.
8. **Volume and SLA.** Messages per day, peak items per message, and the response time
   you expect on the 202.
9. **Unknown fields.** What are `budf3`, `udf3`, `udf5`, `udf6`, `udf7`, `udf10`? Do
   any of them affect accounting or reporting? (X101 also carries `PRICE LEVEL` /
   `LEVEL VALUE`, which the payload has no counterpart for.)
10. **`vendorCode: "LS"`** — should this create a supplier record and a purchase link?
11. **Price effective date.** X101 carries `PRICE EFFECTIVE FROM` and we use it to pick
    the newest row per SKU. The payload has no equivalent — is a message always
    "effective now"?
12. **Error feedback.** Would you prefer a callback for items ending `error` /
    `conflict` / `needs_review`, or is polling the status endpoint acceptable? Polling
    is what exists today.

---

## 9. The other half: SKUs sold before they were mastered

Store sales sometimes quote a SKU the product master does not have yet. Those
transactions are held rather than posted against a guessed product.

Two endpoints make that visible, and the loop closes by itself:

```bash
# Is this SKU registered?
curl -k -H "Authorization: Bearer $KEY" \
  "https://103.130.240.24/api/mdm/uat/products/lookup?skuCode=002IJ-00273228"

# Everything sold but not yet mastered, busiest first
curl -k -H "Authorization: Bearer $KEY" \
  "https://103.130.240.24/api/mdm/uat/pending?limit=50"
```

When `lookup` reports `found: false`, it still tells you whether we have *seen* that
SKU in sales and how many transactions it is holding up. **The moment its master
arrives through this API, those transactions post automatically** — no manual step, no
re-import. So the `pending` list is both a data-quality report on the feed and the
backlog that the feed itself will clear.

---

## 10. Error reference

| HTTP | `error.code` | Meaning |
|---|---|---|
| 400 | `INVALID_PAYLOAD` | Not an object or array of objects |
| 400 | `EMPTY_PAYLOAD` | No items |
| 400 | `TOO_MANY_ITEMS` | Over the batch limit (1,000) |
| 400 | `MISSING_SKU_CODE` | An item has neither `skuCode` nor `udf2` — **the whole batch is rejected and nothing is stored** |
| 400 | `DUPLICATE_SKU_IN_BATCH` | The same `skuCode` twice in one message |
| 401 | `MISSING_API_KEY` / `BAD_API_KEY` | Credential problem |
| 403 | `IP_NOT_ALLOWED` | Caller's address is not on the allow-list |
| 413 | `PAYLOAD_TOO_LARGE` | Body over 5 MB |
| 500 | `INTERNAL_ERROR` | Our side. Retryable — reuse the same `X-Request-Id` |
| 503 | `SERVICE_DISABLED` | Switched off on this database. Retryable |

Two shapes to be aware of:

- Authentication failures answer `{"ok": false, "error_code": "..."}` — not the
  `{status, data, error}` envelope.
- A body that is not valid JSON at all is rejected by the web framework before our
  code runs, and comes back as HTTP 400 in a different shape again. Do not assume the
  envelope is present on a 400.

---

## 11. Rollout

1. **Shadow** — `dryRun: true`. Real traffic is validated, mapped and reported, but no
   master data is written. This is where the category mapping and the price-scale
   question get settled against actual messages rather than samples.
2. **Dual-write** — the API and the X101 file both write. They cannot conflict: both
   address the same records by the same keys.
3. **API primary** — X101 drops back to a periodic reconciliation.

Rollback at any point is a switch on our side; nothing is lost, because every message
is stored and can be replayed.
