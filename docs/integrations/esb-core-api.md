# ESB Core / ESB OMS API Reference

Working reference for integrating odoo-platform with **ESB** (esb.co.id), the Indonesian F&B
ERP / back-office used by the EFN (Erajaya F&B) vertical.

Source: <https://developers.esb.co.id/esb-core/> and <https://developers.esb.co.id/esb-oms/>,
captured 2026-07-21 (ESB Core API v2.0.0, apiDoc generated 2026-07-20).

> **Fetching the spec.** The documentation pages are empty apiDoc shells — a plain page fetch
> returns only `Loading...`. The actual specification is served as JavaScript:
> `https://developers.esb.co.id/esb-core/api_data.js` (a `define([...])`-wrapped JSON array) and
> `api_project.js` (overview + tutorial prose). Slice from the first `[` to the last `]` and
> `json.loads` it. Verbatim captures are committed here:
>
> - [`esb/esb-core.apidoc.json`](esb/esb-core.apidoc.json) — 363 endpoints, 41 groups
> - [`esb/esb-oms.apidoc.json`](esb/esb-oms.apidoc.json) — 38 endpoints
>
> Re-capture the same way when ESB revises the docs, and diff the JSON.

Sibling portals on the same developer site: `esb-core` (ERP/back-office), `esb-oms` (POS sales &
material usage), `eso-fs` (Order Full Service), `eso-qs` (Order Quick Service), `loop`.
Only Core and OMS are relevant to the stock-ops integration. The two ESO portals do not expose
`api_data.js` at the same path.

---

## 1. Base URLs

There is no single base URL. Endpoints fall into **three families**, each with its own host —
an integration needs three `custom.adapter.config` rows, not one.

| Family | Endpoints | Production | Staging | Staging INT |
|---|---|---|---|---|
| **Core** | `/auth/*`, `/inventory/*`, `/purchase/*`, `/product*`, `/branch`, `/location`, `/units`, `/report/*`, `/accounting/*`, `/budget*` | `https://services.esb.co.id/core` | `https://stg7.esb.co.id/core-stg` | `https://stg7.esb.co.id/core-int` |
| **corev1** | `/corev1/master/product`, `/corev1/goods-receipt/inquiry`, `/corev1/general-ledger`, `/corev1/sales/*`, `/extv1/*` | `https://core-api.esb.co.id` | `https://stg7.esb.co.id/api-fnb-backend/web` | `https://stg7.esb.co.id/api-fnb-backend-int/web` |
| **external/general** (OMS) | `/external/general/*`, `/external/push/*`, `/external/sales/*` | `https://esbcore.co.id` | `https://int-erp.esb.co.id` | — |

Note the trap: `/corev1/...` paths appear inside the *ESB Core* documentation but resolve against
the **corev1** host, not the Core host.

---

## 2. Authentication

Three schemes are supported; ESB decides which you get.

| Scheme | How | Notes |
|---|---|---|
| **Access token (JWT)** | `POST /auth/login` → `Authorization: Bearer {accessToken}` | Access token expires **1 hour**, refresh token **24 hours** |
| **Static token / API key** | `Authorization: Bearer {apiKey}` | Generated in ESB Core or issued by the project PIC. **Prefer this** — no session management |
| **Basic auth** | ESB Core username + password | Permissions follow that user's access rights |

### Login

```http
POST {core_base_url}/auth/login
Content-Type: application/json

{"username": "QA1Flx", "password": "abcde98765"}
```

```json
{"path":"…","timestamp":"2024-05-20 13:35:29","status":"ok","code":"EC03100000","message":"OK",
 "result":{"username":"QA1Flx","fullName":"Flx IE","companyID":1,"companyCode":"QA1",
   "companyName":"QA 1 Company","accessToken":"eyJ…","refreshToken":"eyJ…","flagActive":1,
   "logInfo":{"logID":2186,"username":"QA1Flx","loginTime":"…","logoutTime":null}},
 "errors":null}
```

Refresh: `GET {core_base_url}/auth/refresh` with `Authorization: Bearer {refreshToken}`.

> ### ⚠ Single-session eviction
>
> Quoting the docs verbatim: *"A successful API login will log you out of any existing ESB Core
> session using the same credentials, vice versa."*
>
> Concurrent Odoo workers each calling `/auth/login` will kick each other out, and a human
> logging into the ESB web UI with the same account kills the integration's token. Therefore:
>
> - use **one dedicated ESB user reserved for Odoo**, never a human's account;
> - cache **one** session record and serialise rotation behind a `SELECT … FOR UPDATE` row lock;
> - refresh at T-5min rather than waiting for a 401.

---

## 3. Response envelope

Every endpoint — success or failure — returns the same wrapper:

```json
{"path": "…", "timestamp": "YYYY-MM-DD HH:MM:SS", "status": "ok" | "fail",
 "code": "EC03100000", "message": "OK", "result": {…} | null,
 "errors": [{"attribute": "…", "code": "…", "message": "…"}] | null}
```

| Code | Meaning |
|---|---|
| `EC03100000` | OK |
| `EC03100001` | Unauthorized / Invalid Token |
| `EC03100032` | Invalid username or password |

> **`HTTP 200` with `"status": "fail"` is normal.** Any client that decides success from the HTTP
> status code alone will silently swallow errors. Check `status`/`code` as well.

### Pagination

Core and corev1: `page` + `limit` query params (default `limit=20`; the stock-movement report
caps at **100**), with `result.count`, `result.next`, `result.prev` in the body.
OMS `external/general/*` instead returns `X-Pagination-Total-Count`, `X-Pagination-Page-Count`,
`X-Pagination-Current-Page`, `X-Pagination-Per-Page` **headers**.

### Other conventions

- Path params are documented inconsistently as `:param` and `{param}` — both mean the same thing.
- Dates are `YYYY-MM-DD`; datetimes come back ISO-8601 with `+07:00`.
- Document status IDs are shared across most transactional documents:
  **1** New · **2** Rejected · **3** Authorized · **38** Waiting for Approval.
  Purchase Order adds **4** Receiving · **8** Finished · **11** Invoice.
- Most documents follow `create → (approval flow) → PATCH /{num}/authorize` or `/{num}/reject`.
- Endpoints titled **"(Piloting)"** are restricted to selected companies and may change without
  notice. Confirm availability with the PIC before depending on one.

---

## 4. Endpoints used by the stock-ops integration

### 4.1 Master data (pull)

| Endpoint | Returns |
|---|---|
| `GET /branch` | `branchID`, `branchCode`, `branchName` (active branches / outlets) |
| `GET /location?branchID=` | `locationID`, `locationName` |
| `GET /units` | `uomID`, `uomName` |
| `GET /product/list` | Paged list: `productID`, `productCode`, `productName`, `categoryID`, `subCategoryID`, `bomID`, `flagActive` |
| `GET /corev1/master/product` | **Richer.** Adds `productDetails[]` with `productDetailID`, `unit`, `conversionFactor`, `basePrice`, `sku`, `weight`, and `defaultUnit.{stockUnit,purchaseUnit,baseUnit,transferUnit,salesUnit}`. Filters: `productCode`, `productName`, `statusActive`, `createdDate`, `editedDate`, `page` |
| `GET /product/category`, `GET /product/sub-category` | Category tree |
| `GET /purpose` | `purposeID`, `purposeName`, `purposeAccount`, `purposeAppliedTo` — adjustment reasons, **each mapped to a COA**, so the purpose chosen on an item journal drives its GL routing |
| `GET /document-template` | `requestTemplateID`, `requestTemplateName`, `branchNames` |
| `GET /supplier`, `GET /cost-center` | Suppliers, cost centres |

> **`productDetailID`, not `productID`, is the key every transactional endpoint wants.** It is
> unit-specific (one product has one `productDetailID` per unit of measure). Store it per Odoo
> product variant; it is the join key for item journals, purchase requests, transfers and stock.

### 4.2 Stock levels (pull)

`GET /report/stock-movement`

| Param | |
|---|---|
| `startPeriod`, `endPeriod` | **required**, `YYYY-MM-DD` |
| `branchCode`, `location`, `productCode`, `productName` | optional filters |
| `unitToShow` | `Default Stock Sales` \| `Default Stock Unit` \| `Default Purchase Unit` \| `Base Unit` \| `Default Transfer Unit` |
| `page`, `limit` | default 20, **max 100** |

Each row: `branchID/branchCode/branchName`, `location`, `documentDate`, `createdDate`,
`productDetailID`, `productCode`, `productName`, `UOM`, `transactionType`, `referenceNumber`,
`documentCode`, `valuePerUnit`, `qtyIn`, `amountIn`, `qtyOut`, `amountOut`,
**`qtyBalance`**, **`amountBalance`**.

`GET /product/stock-location?productDetailID=&locationID=` → `qty`, `stockQty` for a **single**
product.

> ### ⚠ There is no bulk "stock on hand" endpoint
>
> Nothing returns current balances for all products at a location in one call. The practical
> substitute is to page through `/report/stock-movement` for a window and keep the **last
> `qtyBalance` per (branch, location, productDetailID)** as the closing balance;
> `/product/stock-location` is then useful only for spot-verifying a single SKU before a write.
> Worth asking the ESB PIC whether an undocumented bulk balance endpoint exists.

### 4.3 Stock opname → Item Journal (push)

```http
POST {core_base_url}/inventory/item-journal
Authorization: Bearer {accessToken}

{"itemJournalDate": "2025-12-10",
 "branchID": 373,
 "locationID": 964,
 "requestTemplateID": null,
 "additionalInfo": "…",
 "itemJournalDetails": [
   {"ID": -1, "productDetailID": 2112, "purposeID": 10, "qty": 22,  "hpp": 220},
   {"ID": -1, "productDetailID": 2058, "purposeID": 9,  "qty": -22, "hpp": 1}]}
```

→ `result.itemJournalNum`, e.g. `IU202512100023`. Then `PATCH /inventory/item-journal/{num}/authorize`.

- **`qty` is the signed adjustment delta (`counted − expected`), not the counted quantity.**
- `locationID` must belong to `branchID` and be of type **warehouse or kitchen**.
- `purposeID` is required if the user has the "purpose required" feature enabled.
- `requestTemplateID` non-null switches the journal to template mode, where every
  `productDetailID` must already exist in that template.
- `ID: -1` marks a new detail line (a real ID means update).

Read back: `GET /inventory/item-journal` (filters `page`, `limit`, `itemJournalNum`, `dateFrom`,
`dateTo`, `branchID`, `locationID`, `additionalInfo`, `statusID`, `sort`) and
`GET /inventory/item-journal/{itemJournalNum}` for header + lines + approval trail.
Also available: `PUT` update, `DELETE`, `PATCH /reject`, attachment upload/delete.

### 4.4 Replenishment (push)

**Purchase Request** — `POST /purchase/purchase-request`

```json
{"branchID": 1, "purchaseRequestDate": "2026-07-21", "requiredDate": "2026-07-25",
 "costCenterID": null, "requestTemplateID": null, "isTemplate": false, "additionalInfo": "…",
 "purchaseRequestDetails": [{"productDetailID": 2112, "requestProcessID": 2, "qty": 10, "notes": ""}]}
```
`requestProcessID`: **1** ALL · **2** Purchase · **3** Transfer. Returns `purchaseRequestNum`.

**Goods Transfer Request** — `POST /inventory/goods-transfer-request`

```json
{"originBranchID": 1, "destinationBranchID": 373, "transferDate": "2026-07-21",
 "categoryTypeID": 1, "originLocationID": 964, "purchaseRequestNum": null,
 "transferDetails": [{"productDetailID": 2112, "qty": 10, "requestQty": 10}]}
```
`categoryTypeID`: **1** Goods & Services · **3** Asset. `requestQty` is `0` when not linked to a
purchase request. Returns `transferNum`.

**Purchase Order** — `POST /purchase/purchase-order` (also `/draft`), then
`PATCH /{purchaseNum}/authorize`, `/close`, `/unclose`, `/unfinish`, `/print`.
Index filters include `statusID`, `branchID`, `supplierID`, `dateFrom/dateTo`,
`requiredDateFrom/To`, `purchaseRequestNums`.

**Goods Receipt** — `POST /inventory/goods-receipt/{refNum}` where `refNum` is a Goods Delivery
number, Purchase Order number or Purchase Sales Return number. Supports `autoClosePO`,
per-line `deviationVal` and `expiredDates[]`.

> ### ⚠ No idempotency key
>
> No POST accepts an idempotency header, so a retry after a timeout can create a duplicate
> document. Workable mitigation: generate a key, stamp it into the free-text **`additionalInfo`**
> field, and query the matching Index endpoint for that key before creating. Confirm with the PIC
> that `additionalInfo` is stored verbatim and is searchable on every Index endpoint you rely on.

### 4.5 Demand signal — ESB OMS (pull)

| Endpoint | Returns |
|---|---|
| `GET /corev1/sales/get-daily-sales-material-usage?salesDate=&flagUnit=&branchCode=` | **Primary forecasting input.** Per-outlet, per-day *material* consumption, already exploded through the BOM: `branchCode`, `branch`, `salesDate`, `productCode`, `productName`, `totalQty`, `unit`, `totalConversionQty`, `unitConversion`. `flagUnit` ∈ `stockUnit`, `purchaseUnit`, `baseUnit`, `transferUnit` |
| `GET /extv1/sales/sales-menu-summary/?salesDate=&branchCode=` | Menu-level daily summary: qty, amount, tax, discount |
| `POST /external/general/sales-menu` | Line-level menu transactions incl. packages and extras |
| `GET /corev1/sales/sales-information` | Full POS sales headers + payments synced from local POS |
| `POST /external/general/sales-branch-summary` | Per-branch daily totals (`paxTotal`, `billTotal`, `grandTotal`) |
| `GET /report/sales-payment-summary` | Payments by method incl. `mdr`, `netAfterMDR` |

---

## 5. Functional coverage of ESB Core (41 groups)

Sales (`Sales_Order`, `Simple_Sales`) · Purchasing (`Purchase_Request`, `Purchase_Order`,
`Purchase_Invoice`, `Purchase_Return`, `Simple_Purchase`, `Advance_Payment`) ·
Inventory (`Goods_Receipt`, `Goods_Delivery`, `Goods_Transfer_Request`, `Item_Journal`,
`Simple_Transfer`, `Receipt`) · Production (`Production_Order`, `Material_Delivery`,
`Production_Result`, `Simple_Manufacturing`) · Accounting (`Memorial_Journal`, `General_Ledger`,
`Employee_Advance_Payment`) · Budgeting (`Budget_Plan`, `Budget_Detail`, `Budget_Adjustment`,
`Budget_Allocate`) · Master data (`Master_Product`, `Master_Bill_of_Material`, `Master_Pricelist`,
`Master_Customer`, `Master_Supplier`, `Master_Company`, `Master_Unit`, `Master_Category`,
`Master_Sub_Category`, `Master_Cost_Center`, `Master_Accounting`, `Master_Document_Template`,
`Master_Customer_Pricelist`) · `Report` (stock movement only) · `Online_Voucher`.

The full per-endpoint index is in the appendix below.

---

## 6. Open questions for the ESB PIC

1. Static API key or username/password for the Odoo integration user?
2. Does a bulk stock-on-hand endpoint exist outside the public docs?
3. Is `additionalInfo` preserved verbatim and searchable on every Index endpoint (needed for the
   idempotency guard)?
4. Which "(Piloting)" endpoints are enabled for this company?
5. Rate limits — undocumented anywhere in the spec.

## Appendix — full ESB Core endpoint index (363 endpoints)


### Advance Payment

| Method | Path | Title |
|---|---|---|
| PATCH | `/purchase/advance-payment/:advancePaymentNum/authorize` | Authorize Advance Payment |
| GET | `/purchase/advance-payment/browse-purchase` | Browse Purchase Reference Advance Payment |
| GET | `/purchase/advance-payment/browse-reference` | Browse Reference Advance Payment |
| POST | `/purchase/advance-payment` | Create Advance Payment |
| DELETE | `/purchase/advance-payment/:advancePaymentNum` | Delete Advance Payment |
| DELETE | `/purchase/advance-payment/:advancePaymentNum/attachment` | Delete Attachment Advance Payment |
| GET | `/purchase/advance-payment/available-amount` | Get Available Advance Amount Advance Payment |
| GET | `/purchase/advance-payment/current-settlement-available-amount` | Get Available Advance Amount By Settlement Advance Payment |
| GET | `/purchase/advance-payment/purchase-advance-amount` | Get Purchase Advance Amount Advance Payment |
| GET | `/purchase/advance-payment/:advancePaymentNum/references` | Get References Advance Payment |
| GET | `/purchase/advance-payment` | Index Advance Payment |
| PATCH | `/purchase/advance-payment/:advancePaymentNum/reject` | Reject Advance Payment |
| PUT | `/purchase/advance-payment/:advancePaymentNum` | Update Advance Payment |
| PATCH | `/purchase/advance-payment/:advancePaymentNum/attachment` | Upload Attachment Advance Payment |
| GET | `/purchase/advance-payment/:advancePaymentNum` | View Advance Payment |

### Authorization

| Method | Path | Title |
|---|---|---|
| POST | `/auth/login` | Login |
| GET | `/auth/refresh` | Refresh Token |

### Budget Adjustment

| Method | Path | Title |
|---|---|---|
| PATCH | `/budget/budget-adjustment/:budgetAdjustmentNum/authorize` | Authorize Budget Adjustment |
| POST | `/budget/budget-adjustment` | Create Budget Adjustment |
| DELETE | `/budget/budget-adjustment/:budgetAdjustmentNum` | Delete Budget Adjustment |
| GET | `/budget/budget-adjustment` | Get All Data Budget Adjustment |
| GET | `/budget/budget-adjustment/:budgetAdjustmentNum` | Get Budget Adjustment |
| PATCH | `/budget/budget-adjustment/:budgetAdjustmentNum/reject` | Reject Budget Adjustment |
| PUT | `/budget/budget-adjustment/:budgetAdjustmentNum` | Update Budget Adjustment |

### Budget Allocate

| Method | Path | Title |
|---|---|---|
| PATCH | `/budget/budget-allocate/:budgetAdjustmentNum/authorize` | Authorize Budget Allocate |
| POST | `/budget/budget-allocate` | Create Budget Allocate |
| DELETE | `/budget/budget-allocate/:budgetAdjustmentNum` | Delete Budget Allocate |
| GET | `/budget/budget-allocate` | Get All Data Budget Allocate |
| GET | `/budget/budget-allocate/:budgetAdjustmentNum` | Get Budget Allocate |
| PATCH | `/budget/budget-allocate/:budgetAdjustmentNum/reject` | Reject Budget Allocate |
| PUT | `/budget/budget-allocate/:budgetAdjustmentNum` | Update Budget Allocate |

### Budget Detail

| Method | Path | Title |
|---|---|---|
| PATCH | `/budgets/:budgetNum/authorize` | Authorize Budget Detail |
| GET | `/budgets/browse` | Browse Budget Detail |
| GET | `/budgets/browse/detail` | Browse Budget Detail Data |
| POST | `/budgets` | Create Budget Detail |
| DELETE | `/budgets/:budgetNum` | Delete Budget Detail |
| POST | `/budgets/export-form` | Export Budget Detail Form |
| GET | `/budgets` | Get All Data Budget Detail |
| GET | `/budgets/:budgetNum` | Get Budget Detail |
| POST | `/budgets/amount` | Get Budget Detail Amount |
| GET | `/budgets/:budgetNum/dropdown` | Get Budget Dropdown |
| POST | `/budgets/import-form` | Import Budget Detail Form |
| PATCH | `/budgets/:budgetNum/reject` | Reject Budget Detail |
| PUT | `/budgets/:budgetNum` | Update Budget Detail |

### Budget Plan

| Method | Path | Title |
|---|---|---|
| PATCH | `/budget-plan/:budgetPlanNum/authorize` | Authorize Budget Plan |
| GET | `/budget-plan/browse` | Browse Budget Plan |
| POST | `/budget-plan` | Create Budget Plan |
| DELETE | `/budget-plan/:budgetPlanNum` | Delete Budget Plan |
| GET | `/budget-plan` | Get All Data Budget Plan |
| GET | `/budget-plan/:budgetPlanNum` | Get Budget Plan |
| GET | `/budget-plan/:budgetPlanNum/branches` | Get Budget Plan Branches |
| GET | `/budget-plan/:budgetPlanNum/chart-of-accounts` | Get Budget Plan Chart of Accounts |
| GET | `/budget-plan/:budgetPlanNum/branches/details` | Get Budget Plan Detail by Branch |
| GET | `/budget-plan/:budgetPlanNum/chart-of-accounts/details` | Get Budget Plan Detail by COA |
| PATCH | `/budget-plan/:budgetPlanNum/reject` | Reject Budget Plan |
| PUT | `/budget-plan/:budgetPlanNum` | Update Budget Plan |

### Employee Advance Payment

| Method | Path | Title |
|---|---|---|
| PATCH | `/employee/employee-advance-payment/:employeeAdvanceNum/authorize` | Authorize Employee Advance Payment |
| POST | `/employee/employee-advance-payment` | Create Employee Advance Payment |
| DELETE | `/employee/employee-advance-payment/:employeeAdvanceNum` | Delete Employee Advance Payment |
| GET | `/employee/employee-advance-payment` | Index Employee Advance Payment |
| PATCH | `/employee/employee-advance-payment/:employeeAdvanceNum/reject` | Reject Employee Advance Payment |
| PUT | `/employee/employee-advance-payment/:employeeAdvanceNum` | Update Employee Advance Payment |
| POST | `/employee/employee-advance-payment/:refNum/asset-images` | Upload Asset Images Employee Advance Payment |
| POST | `/employee/employee-advance-payment/upload` | Upload Employee Advance Payment |
| GET | `/employee/employee-advance-payment/:employeeAdvanceNum` | View Employee Advance Payment |

### General Ledger

| Method | Path | Title |
|---|---|---|
| GET | `/corev1/general-ledger` | General Ledger |
| POST | `/accounting/general-ledger/summary` | Get Summary General Ledger |

### Goods Delivery

| Method | Path | Title |
|---|---|---|
| PATCH | `/inventory/goods-delivery/{goodsDeliveryNum}/authorize` | Authorize Goods Delivery |
| POST | `/inventory/goods-delivery/{refNum}` | Create Goods Delivery |
| DELETE | `/inventory/goods-delivery/{goodsDeliveryNum}` | Delete Goods Delivery |
| — | `|` | Flow Goods Delivery |
| GET | `/inventory/goods-delivery` | Goods Delivery Index |
| GET | `/inventory/goods-delivery/create/{refNum}` | Initialize Goods Delivery Data |
| PATCH | `/inventory/goods-delivery/{goodsDeliveryNum}/reject` | Reject Goods Delivery |
| PUT | `/inventory/goods-delivery/{goodsDeliveryNum}` | Update Goods Delivery |
| POST | `/inventory/goods-delivery/{goodsDeliveryNum}/upload/attachment` | Upload Goods Delivery Attachment |
| GET | `/inventory/goods-delivery/{goodsDeliveryNum}` | View Goods Delivery |

### Goods Receipt

| Method | Path | Title |
|---|---|---|
| PATCH | `/inventory/goods-receipt/{goodsReceiptNum}/authorize` | Authorize Goods Receipt |
| GET | `/inventory/goods-receipt/browse-return` | Browse Return Goods Receipt |
| POST | `/inventory/goods-receipt/{refNum}` | Create Goods Receipt |
| DELETE | `/inventory/goods-receipt/{goodsReceiptNum}` | Delete Goods Receipt |
| — | `|` | Flow Goods Receipt |
| GET | `corev1/goods-receipt/inquiry` | Get Goods Receipt |
| GET | `/inventory/goods-receipt` | Goods Receipt Index |
| GET | `/inventory/goods-receipt/initialize` | Initialize Goods Receipt Data |
| PATCH | `/inventory/goods-receipt/{goodsReceiptNum}/reject` | Reject Goods Receipt |
| POST | `/inventory/goods-receipt/{goodsReceiptNum}/asset-imagesn` | Save Goods Receipt Attachments |
| PUT | `/inventory/goods-receipt/{goodsReceiptNum}` | Update Goods Receipt |
| GET | `/inventory/goods-receipt/{goodsReceiptNum}` | View Goods Receipt |

### Goods Transfer Request

| Method | Path | Title |
|---|---|---|
| PATCH | `/inventory/goods-transfer-request/{transferNum}/authorize` | Authorize Goods Transfer Request |
| POST | `/inventory/goods-transfer-request` | Create Goods Transfer Request |
| DELETE | `/inventory/goods-transfer-request/{transferNum}` | Delete Goods Transfer Request |
| PATCH | `/inventory/goods-transfer-request/{transferNum}/finish` | Finish Goods Transfer Request |
| — | `|` | Flow Goods Transfer Request |
| GET | `/inventory/goods-transfer-request` | Goods Transfer Request Index |
| PATCH | `/inventory/goods-transfer-request/{transferNum}/reject` | Reject Goods Transfer Request |
| PATCH | `/inventory/goods-transfer-request/{transferNum}/unfinished` | Unfinish Goods Transfer Request |
| PUT | `/inventory/goods-transfer-request/{transferNum}` | Update Goods Transfer Request |
| GET | `/inventory/goods-transfer-request/{transferNum}` | View Goods Transfer Request |

### Item Journal

| Method | Path | Title |
|---|---|---|
| PATCH | `/inventory/item-journal/:itemJournalNum/authorize` | Authorize Item Journal |
| POST | `/inventory/item-journal` | Create Item Journal |
| DELETE | `/inventory/item-journal/:itemJournalNum` | Delete Item Journal |
| DELETE | `/inventory/item-journal/:itemJournalNum/attachment` | Delete Item Journal Attachment |
| GET | `/inventory/item-journal` | Item Journal Index |
| PATCH | `/inventory/item-journal/:itemJournalNum/reject` | Reject Item Journal |
| PUT | `/inventory/item-journal/:itemJournalNum` | Update Item Journal |
| PATCH | `/inventory/item-journal/:itemJournalNum/attachment` | Upload Item Journal Attachment |
| GET | `/inventory/item-journal/{itemJournalNum}` | View Item Journal |

### Master Accounting

| Method | Path | Title |
|---|---|---|
| GET | `/purpose/[purposeID]` | Purpose Detail |
| GET | `/purpose` | Purpose List |

### Master Bill of Material

| Method | Path | Title |
|---|---|---|
| GET | `/product/bom/browse` | Bill of Material Browse |
| GET | `/product/bom/{bomID}` | Bill of Material Detail |
| GET | `/product/bom/export` | Bill of Material Export |
| GET | `/product/bom/export` | Bill of Material Export Template |
| GET | `/product/bom` | Bill of Material List |
| GET | `/product/stock-location` | Browse Stock Location |
| POST | `/product/bom` | Create Bill of Material Assembly |
| POST | `/product/bom` | Create Bill of Material Disassembly |
| POST | `/product/bom` | Create Bill of Material Menu |
| DELETE | `/product/bom/{bomID}` | Delete Bill of Material |
| PATCH | `/product/bom/{bomID}/restore` | Restore Bill of Material |
| PUT | `/product/bom/{bomID}` | Update Bill of Material |
| POST | `/product/bom/upload` | Upload Bill of Material |
| POST | `/product/bom/upload/template` | Upload Update Bill of Material |

### Master Category

| Method | Path | Title |
|---|---|---|
| GET | `/product/category/{categoryID}` | Category Detail |
| GET | `/product/category` | Category List |

### Master Company

| Method | Path | Title |
|---|---|---|
| GET | `/branch` | Branch List |
| GET | `/location/{locationID}` | Location Detail |
| GET | `/location` | Location List |
| GET | `/branch/user` | User Access List |
| GET | `/location/user` | User Access Location |

### Master Cost Center

| Method | Path | Title |
|---|---|---|
| GET | `/cost-center` | Cost Center Index |
| GET | `//cost-center/user` | User Cost Center |

### Master Customer

| Method | Path | Title |
|---|---|---|
| POST | `/customer` | Create Customer |
| GET | `/customer/list` | Customer Find All |
| GET | `/customer` | Customer Index |
| POST | `/customer/{customerID}/validation-before-delete` | Customer Validation Before Delete |
| DELETE | `/customer/{customerID}` | Delete Customer |
| GET | `/customer/export` | Export Customer |
| PATCH | `/customer/{customerID}/restore` | Restore Customer |
| PUT | `/customer/{customerID}` | Update Customer |
| POST | `/customer/upload` | Upload Customer |
| GET | `/customer/{customerID}` | View Customer |

### Master Customer Pricelist

| Method | Path | Title |
|---|---|---|
| POST | `/customer-pricelist` | Create Customer Pricelist |
| GET | `/customer-pricelist` | Customer Pricelist Index |
| DELETE | `/customer-pricelist/:customerPricelistID` | Delete Customer Pricelist |
| GET | `/customer-pricelist/export` | Export Customer Pricelist |
| PATCH | `/customer-pricelist/:customerPricelistID` | Update Customer Pricelist |
| POST | `/customer-pricelist/import` | Upload Customer Pricelist |
| GET | `/customer-pricelist/:customerPricelistID` | View Customer Pricelist |

### Master Document Template

| Method | Path | Title |
|---|---|---|
| GET | `/document-template/[requestTemplateID]` | Document Template Detail |
| GET | `/document-template` | Document Template List |

### Master Pricelist

| Method | Path | Title |
|---|---|---|
| PATCH | `/pricelist/temp/:pricelistNum/authorize` | Authorize Waiting For Approval Pricelist |
| POST | `/pricelist` | Create Pricelist |
| DELETE | `/pricelist/:pricelistID` | Delete Pricelist |
| DELETE | `/pricelist/temp/:pricelistNum` | Delete Waiting For Approval Pricelist |
| GET | `/pricelist/export` | Export Pricelist |
| GET | `/pricelist/temp/export` | Export Waiting For Approval Pricelist |
| GET | `/pricelist` | Pricelist Index |
| PATCH | `/pricelist/temp/:pricelistNum/reject` | Reject Waiting For Approval Pricelist |
| PUT | `/pricelist/:pricelistID` | Update Pricelist |
| PUT | `/pricelist/temp/:pricelistNum` | Update Waiting For Approval Pricelist |
| POST | `/pricelist/import` | Upload Pricelist |
| GET | `/pricelist/:pricelistID` | View Pricelist |
| GET | `/pricelist/temp/:pricelistNum` | View Waiting For Approval Pricelist |
| GET | `/pricelist/temp` | Waiting For Approval Pricelist Index |

### Master Product

| Method | Path | Title |
|---|---|---|
| PATCH | `/product/authorize` | Authorize Product |
| GET | `/product/browse-category` | Browse Category |
| GET | `/product/browse-sub-category` | Browse Sub Category |
| POST | `/product` | Create Product |
| DELETE | `/product/:productID/temp` | Delete Pending Product |
| DELETE | `/product/:productID` | Delete Product |
| POST | `/product/export/temp` | Export Pending Product |
| POST | `/product/export` | Export Product |
| POST | `/product/export-template` | Export Product Template |
| GET | `/corev1/master/product` | Get Product |
| GET | `/product/{productID}` | Product Detail |
| GET | `/product` | Product Index |
| GET | `/product/list` | Product List |
| GET | `/product/:productID/temp` | Product Pending Detail |
| GET | `/product/temp` | Product Pending Index |
| PUT | `/product/pull` | Pull Product |
| PUT | `/product/push` | Push Product |
| PATCH | `/product/reject` | Reject Product |
| PATCH | `/product/:productID/restore` | Restore Product |
| PUT | `/product/:productID` | Update Product |
| POST | `/product/import` | Upload Create Product |
| PUT | `/product/import` | Upload Update Product |
| GET | `/product/validate-barcode-number` | Validate Barcode Number |
| GET | `/product/:productID/validate-delete` | Validate Delete Product |
| GET | `/product/detail/validate-delete` | Validate Delete Product Detail |

### Master Sub Category

| Method | Path | Title |
|---|---|---|
| GET | `/product/sub-category/{subCategoryID}` | Sub Category Detail |
| GET | `/product/sub-category` | Sub Category List |

### Master Supplier

| Method | Path | Title |
|---|---|---|
| POST | `/supplier` | Create Supplier |
| DELETE | `/supplier/{supplierID}` | Delete Supplier |
| GET | `/supplier/export/BANK` | Export Supplier |
| PATCH | `/supplier/{supplierID}/restore` | Restore Supplier |
| GET | `/supplier/category/list` | Supplier Category List |
| GET | `/supplier/{supplierID}` | Supplier Detail |
| GET | `/supplier` | Supplier List |
| PATCH | `/supplier/{supplierID}` | Update Supplier |
| POST | `/supplier/upload` | Upload Supplier |
| PATCH | `/supplier/upload` | Upload Update Supplier |

### Master Unit

| Method | Path | Title |
|---|---|---|
| GET | `/units/{uomID}` | Unit Detail |
| GET | `/units` | Unit List |

### Material Delivery

| Method | Path | Title |
|---|---|---|
| PATCH | `/production/material-delivery/{materialDeliveryNum}/authorize` | Authorize Material Delivery |
| POST | `/production/material-delivery` | Create Material Delivery |
| DELETE | `/production/material-delivery/{materialDeliveryNum}` | Delete Material Delivery |
| GET | `/production/material-delivery` | Material Delivery Index |
| PATCH | `/production/material-delivery/{materialDeliveryNum}/reject` | Reject Material Delivery |
| PUT | `/production/material-delivery/{materialDeliveryNum}` | Update Material Delivery |
| GET | `/production/material-delivery/{materialDeliveryNum}` | View Material Delivery |

### Memorial Journal

| Method | Path | Title |
|---|---|---|
| PATCH | `/accounting/memorial-journal/:memorialJournalNum/authorize` | Authorize Memorial Journal |
| GET | `/accounting/memorial-journal/access` | Check Access Memorial Journal |
| POST | `/accounting/memorial-journal` | Create Memorial Journal |
| DELETE | `/accounting/memorial-journal/:memorialJournalNum` | Delete Memorial Journal |
| GET | `/accounting/memorial-journal/export` | Export Memorial Journal |
| POST | `/accounting/memorial-journal/form-upload` | Form Upload Memorial Journal |
| GET | `/accounting/memorial-journal` | Index Memorial Journal |
| PATCH | `/accounting/memorial-journal/:memorialJournalNum/reject` | Reject Memorial Journal |
| PUT | `/accounting/memorial-journal/:memorialJournalNum` | Update Memorial Journal |
| POST | `/accounting/memorial-journal/:memorialJournalNum/asset-images` | Upload Asset Images Memorial Journal |
| POST | `/accounting/memorial-journal/upload` | Upload Memorial Journal |
| GET | `/accounting/memorial-journal/:memorialJournalNum` | View Memorial Journal |

### Online Voucher

| Method | Path | Title |
|---|---|---|
| POST | `/v1/online-voucher/burn` | Burn Online Voucher |
| POST | `/v1/online-voucher/` | Create Online Voucher (Multi Company) |
| POST | `/v1/online-voucher/validate` | Validate Online Voucher |

### Production Order

| Method | Path | Title |
|---|---|---|
| PATCH | `/production/production-order/{productionOrderNum}/authorize` | Authorize Production Order |
| POST | `/production/production-order` | Create Production Order |
| DELETE | `/production/production-order/{productionOrderNum}` | Delete Production Order |
| GET | `/production/production-order` | Production Order Index |
| PATCH | `/production/production-order/{productionOrderNum}/reject` | Reject Production Order |
| PUT | `/production/production-order/{productionOrderNum}` | Update Production Order |
| GET | `/production/production-order/{productionOrderNum}` | View Production Order |

### Production Result

| Method | Path | Title |
|---|---|---|
| PATCH | `/production/production-result/{productionResultNum}/authorize` | Authorize Production Result |
| POST | `/production/production-result` | Create Production Result |
| DELETE | `/production/production-result/{productionResultNum}` | Delete Production Result |
| GET | `/production/production-result` | Production Result Index |
| PATCH | `/production/production-result/{productionResultNum}/reject` | Reject Production Result |
| PUT | `/production/production-result/{productionResultNum}` | Update Production Result |
| GET | `/production/production-result/{productionResultNum}` | View Production Result |

### Purchase Invoice

| Method | Path | Title |
|---|---|---|
| PATCH | `/purchase/purchase-invoices/:purchaseInvoiceNum/authorize` | Authorize Purchase Invoice |
| GET | `/purchase/purchase-invoices/browse-data-details` | Browse Data Details |
| GET | `/purchase/purchase-invoices/browse-data-heads` | Browse Data Heads |
| GET | `/purchase/purchase-invoices/browse-references` | Browse References |
| GET | `/purchase/purchase-invoices/browse-return` | Browse Return |
| GET | `/purchase/purchase-invoices/supplier-invoice/availability` | Check Supplier Invoice Number Availability |
| POST | `/purchase/purchase-invoices` | Create Purchase Invoice |
| DELETE | `/purchase/purchase-invoices/:purchaseInvoiceNum/attachment` | Delete Attachment Purchase Invoice |
| DELETE | `/purchase/purchase-invoices/:purchaseInvoiceNum` | Delete Purchase Invoice |
| POST | `/purchase/purchase-invoices/export-csv` | Export CSV Purchase Invoice |
| GET | `/purchase/purchase-invoices/:purchaseInvoiceNum/payable-settlements` | Fetch Payable Settlements |
| GET | `/purchase/purchase-invoices/:purchaseInvoiceNum/purchase-payments` | Fetch Purchase Payments |
| GET | `/purchase/purchase-invoices` | Get All Data Purchase Invoice |
| GET | `/purchase/purchase-invoices/:purchaseInvoiceNum` | Get Data Purchase Invoice |
| POST | `/purchase/purchase-invoices/return-details` | Get Purchase Invoice Return Details |
| GET | `/purchase/purchase-invoices/product-price` | Product Price |
| GET | `/purchase/purchase-invoices/product-price-history` | Product Price History |
| PATCH | `/purchase/purchase-invoices/:purchaseInvoiceNum/reject` | Reject Purchase Invoice |
| PUT | `/purchase/purchase-invoices/:purchaseInvoiceNum` | Update Purchase Invoice |
| PATCH | `/purchase/purchase-invoices/:purchaseInvoiceNum/attachment` | Upload Attachment Purchase Invoice |
| GET | `/purchase/purchase-invoices/:purchaseInvoiceNum/validate-adjustment` | Validate Purchase Invoice Adjustment |
| GET | `/purchase/purchase-invoices/:purchaseInvoiceNum/validate-payment` | Validate Purchase Payment |
| GET | `/purchase/purchase-invoices/:purchaseInvoiceNum/validate-return` | Validate Purchase Return |
| GET | `/purchase/purchase-invoices/validate-references-budget` | Validate References Budget |

### Purchase Order

| Method | Path | Title |
|---|---|---|
| PATCH | `/purchase/purchase-order/{purchaseNum}/authorize` | Authorize Purchase Order |
| PATCH | `/purchase/purchase-order/{purchaseNum}/close` | Close Purchase Order |
| POST | `/purchase/purchase-order/draft` | Create Draft Purchase Order |
| POST | `/purchase/purchase-order` | Create Purchase Order |
| DELETE | `/purchase/purchase-order/{purchaseNum}` | Delete Purchase Order |
| — | `|` | Flow Purchase Order |
| PATCH | `/purchase/purchase-order/{purchaseNum}/print` | Print Purchase Order |
| GET | `/purchase/purchase-order` | Purchase Order Index |
| PATCH | `/purchase/purchase-order/{{purchaseNum}}/reject` | Reject Purchase Order |
| PATCH | `/purchase/purchase-order/{purchaseNum}/unclose` | Unclose Purchase Order |
| PATCH | `/purchase/purchase-order/{purchaseNum}/unfinish` | Unfinish Purchase Order |
| PUT | `/purchase/purchase-order/{{purchaseNum}}/draft` | Update Draft Purchase Order |
| PUT | `/purchase/purchase-order/{{purchaseNum}}` | Update Purchase Order |
| POST | `/purchase/purchase-order/{purchaseNum}/asset-images` | Upload Asset Image Purchase Order |
| POST | `/purchase/purchase-order/upload` | Upload Purchase Order |
| GET | `/purchase/purchase-order/{purchaseNum}` | View Purchase Order |

### Purchase Request

| Method | Path | Title |
|---|---|---|
| PATCH | `/purchase/purchase-request/{purchaseRequestNum}/authorize` | Authorize Purchase Request |
| POST | `/purchase/purchase-request` | Create Purchase Request |
| DELETE | `/purchase/purchase-request/{purchaseRequestNum}` | Delete Purchase Request |
| GET | `/purchase/purchase-request` | Purchase Request Index |
| PATCH | `/purchase/purchase-request/{purchaseRequestNum}/reject` | Reject Purchase Request |
| PUT | `/purchase/purchase-request/{{purchaseRequestNum}}` | Update Purchase Request |
| GET | `/purchase/purchase-request/{purchaseRequestNum}` | View Purchase Request |

### Purchase Return

| Method | Path | Title |
|---|---|---|
| PATCH | `/purchases/purchase-return/:purchaseReturnNum/authorize` | Authorize Purchase Return |
| POST | `/purchases/purchase-return` | Create Purchase Return |
| DELETE | `/purchases/purchase-return/:purchaseReturnNum` | Delete Purchase Return |
| GET | `/purchases/purchase-return` | Get All Data Purchase Return |
| GET | `/purchases/purchase-return/:purchaseReturnNum` | Get Data Purchase Return |
| PATCH | `/purchases/purchase-return/:purchaseReturnNum/reject` | Reject Purchase Return |
| PUT | `/purchases/purchase-return/:purchaseReturnNum` | Update Purchase Return |

### Receipt

| Method | Path | Title |
|---|---|---|
| PATCH | `/receipt/{receiptNum}/authorize` | Authorize Receipt |
| POST | `/receipt` | Create Receipt |
| DELETE | `/receipt/{receiptNum}` | Delete Receipt |
| POST | `/receipt/import` | Import Receipt |
| GET | `/receipt` | Receipt Index |
| PATCH | `/inventory/receipt/{receiptNum}/reject` | Reject Receipt |
| PUT | `/receipt/{receiptNum}` | Update Receipt |
| POST | `/receipt/{receiptNum}/attachment` | Upload Receipt Attachment |
| GET | `/receipt/{receiptNum}` | View Receipt |

### Report

| Method | Path | Title |
|---|---|---|
| GET | `/report/stock-movement` | Stock Movement Report |

### Sales Order

| Method | Path | Title |
|---|---|---|
| PATCH | `/sales/product-sales/{productSalesNum}/authorize` | Authorize Sales Order |
| PATCH | `/sales/product-sales/{productSalesNum}/finish` | Close Sales Order |
| POST | `/sales/product-sales` | Create Sales Order |
| DELETE | `/sales/product-sales/{productSalesNum}` | Delete Sales Order |
| GET | `/sales/product-sales/{productSalesNum}/export` | Export Sales Order |
| PATCH | `/sales/product-sales/{{productSalesNum}}/reject` | Reject Sales Order |
| GET | `/sales/product-sales` | Sales Order Index |
| PATCH | `/sales/product-sales/{productSalesNum}/unfinished` | Unclose Sales Order |
| PUT | `/sales/product-sales/{productSalesNum}` | Update Sales Order |
| POST | `/sales/product-sales/upload` | Upload Sales Order |
| GET | `/sales/product-sales/{productSalesNum}` | View Sales Order |

### Simple Manufacturing

| Method | Path | Title |
|---|---|---|
| PATCH | `/production/simple-manufacturing/{simpleManufacturingNum}/authorize` | Authorize Simple Manufacturing |
| POST | `/production/simple-manufacturing/assembly-actual` | Create Simple Manufacturing Assembly Actual Costing |
| POST | `/production/simple-manufacturing/assembly` | Create Simple Manufacturing Assembly Standard Costing |
| POST | `/production/simple-manufacturing/disassembly-actual` | Create Simple Manufacturing Disassembly Actual Costing |
| POST | `/production/simple-manufacturing/disassembly` | Create Simple Manufacturing Disassembly Standard Costing |
| DELETE | `/production/simple-manufacturing/{simpleManufacturingNum}` | Delete Simple Manufacturing |
| PATCH | `/production/simple-manufacturing/{simpleManufacturingNum}/reject` | Reject Simple Manufacturing |
| GET | `/production/simple-manufacturing` | Simple Manufacturing Index |
| PUT | `/production/simple-manufacturing/assembly-actual/{simpleManufacturingNum}` | Update Simple Manufacturing Assembly Actual Costing |
| PUT | `/production/simple-manufacturing/assembly/{simpleManufacturingNum}` | Update Simple Manufacturing Assembly Standard Costing |
| PUT | `/production/simple-manufacturing/disassembly-actual/{simpleManufacturingNum}` | Update Simple Manufacturing Disassembly Actual Costing |
| PUT | `/production/simple-manufacturing/disassembly/{simpleManufacturingNum}` | Update Simple Manufacturing Disassembly Standard Costing |
| POST | `/production/simple-manufacturing/upload` | Upload Simple Manufacturing |
| GET | `/production/simple-manufacturing/{simpleManufacturingNum}` | View Simple Manufacturing |

### Simple Purchase

| Method | Path | Title |
|---|---|---|
| PATCH | `/purchase/simple-purchase/{cashPurchaseNum}/authorize` | Authorize Simple Purchase |
| POST | `/purchase/simple-purchase` | Create Simple Purchase |
| DELETE | `/purchase/simple-purchase/{cashPurchaseNum}` | Delete Simple Purchase |
| PATCH | `/purchase/simple-purchase/{cashPurchaseNum}/reject` | Reject Simple Purchase |
| GET | `/purchase/simple-purchase` | Simple Purchase Index |
| PUT | `/purchase/simple-purchase/{cashPurchaseNum}` | Update Simple Purchase |
| POST | `/purchase/simple-purchase/upload` | Upload Simple Purchase |
| GET | `/purchase/simple-purchase/{simplePurchaseNum}` | View Simple Purchase |

### Simple Sales

| Method | Path | Title |
|---|---|---|
| PATCH | `/sales/simple-product-sales/:simpleProductSalesNum/authorize` | Authorize Simple Sales |
| POST | `/sales/simple-product-sales` | Create Simple Sales |
| DELETE | `/sales/simple-product-sales/:simpleProductSalesNum` | Delete Simple Sales |
| GET | `/sales/simple-product-sales/export-csv-all` | Export CSV All |
| POST | `/sales/simple-product-sales/export-csv` | Export CSV by IDs |
| GET | `/sales/simple-product-sales/export-xlsx-all` | Export XLSX All |
| POST | `/sales/simple-product-sales/export-xlsx` | Export XLSX by IDs |
| GET | `/sales/simple-product-sales/export-xml-all` | Export XML All |
| POST | `/sales/simple-product-sales/export-xml` | Export XML by IDs |
| PATCH | `/sales/simple-product-sales/:simpleProductSalesNum/reject` | Reject Simple Sales |
| GET | `/sales/simple-product-sales` | Simple Sales Index |
| PUT | `/sales/simple-product-sales/:simpleProductSalesNum` | Update Simple Sales |
| POST | `/sales/simple-product-sales/upload` | Upload Asset Image Simple Sales |
| POST | `/sales/simple-product-sales/:simpleProductSalesNum/asset-images` | Upload Attachment Simple Sales |
| POST | `/sales/simple-product-sales/:simpleProductSalesNum/validate` | Validate Before Save |
| GET | `/sales/simple-product-sales/:simpleProductSalesNum` | View Simple Sales |

### Simple Transfer

| Method | Path | Title |
|---|---|---|
| PATCH | `/simple-transfer/simpleTransferNum/authorize` | Authorize Simple Transfer |
| POST | `/simple-transfer` | Create Simple Transfer |
| DELETE | `/simple-transfer/{simpleTransferNum}` | Delete Simple Transfer |
| POST | `/simple-transfer/import` | Import Simple Transfer |
| PATCH | `/simple-transfer/simpleTransferNum/reject` | Reject Simple Transfer |
| GET | `/simple-transfer` | Simple Transfer Index |
| PUT | `/simple-transfer/{simpleTransferNum}` | Update Simple Transfer |
| POST | `/simple-transfer/simpleTransferNum/attachment` | Upload Simple Transfer Attachment |
| GET | `/simple-transfer/{simpleTransferNum}` | View Simple Transfer |

## Appendix — full ESB OMS endpoint index (38 endpoints)


### Authorization

| Method | Path | Title |
|---|---|---|
| POST | `/auth/login` | Login |
| GET | `/auth/refresh` | Refresh Token |

### Master Member

| Method | Path | Title |
|---|---|---|
| GET | `/extv1/member` | Get Member |

### Master Menu

| Method | Path | Title |
|---|---|---|
| POST | `/corev1/master/create-menu` | Create Menu |
| GET | `/corev1/master/get-menu` | Get Menu |
| POST | `/web/corev1/master/update-menu` | Update Menu |

### Master Menu Category

| Method | Path | Title |
|---|---|---|
| POST | `/corev1/master/create-menu-category` | Create Menu Category |
| GET | `/corev1/master/get-menu-category` | Get Menu Category |
| POST | `/corev1/master/update-menu-category` | Update Menu Category |

### Master Menu Template

| Method | Path | Title |
|---|---|---|
| POST | `/corev1/master/create-menu-template` | Create Menu Template |
| GET | `/corev1/master/get-menu-template?page=1` | Get Menu Template |
| POST | `/corev1/master/update-menu-template` | Update Menu Template |

### Master POS

| Method | Path | Title |
|---|---|---|
| POST | `/external/general/get-branch` | Branch |
| POST | `/external/general/get-menu` | Menu |
| POST | `/external/general/get-payment-method` | Payment Method |
| POST | `/external/general/stock-branch` | Stock Branch |
| POST | `/external/general/get-visit-purpose` | Visit Purpose |

### Master Promotion

| Method | Path | Title |
|---|---|---|
| POST | `/corev1/promotion/` | Discount (%) |
| POST | `/corev1/promotion/` | Discount (%) ESO |
| POST | `/corev1/promotion/` | Discount (RP) ESO |
| POST | `/corev1/promotion/` | Discount Limit (%) |
| POST | `/corev1/promotion/` | Free Item |
| GET | `/extv1/promotion` | Promotion List |

### Other

| Method | Path | Title |
|---|---|---|
| POST | `/external/general/sales-branch-summary` | Branch Sales Summary |
| GET | `/corev1/sales/get-daily-sales-material-usage` | Daily Sales Material Usage |
| POST | `/external/general/get-sales` | Get Sales |

### Push Sales Data

| Method | Path | Title |
|---|---|---|
| — | `|` | Flow Push Sales And Shift Data |
| POST | `https://int-erp.esb.co.id/external/push/sales-data` | Push Sales Data |
| POST | `/extv1/push/sales-data` | Push Sales Data V2 |
| POST | `https://int-erp.esb.co.id/external/push/shift-data` | Shift Data |
| POST | `/corev1/shift-data/push` | Shift Data V2 |

### Report

| Method | Path | Title |
|---|---|---|
| POST | `/external/general/sales-head?page=x` | Sales Head |
| GET | `/corev1/sales/sales-information` | Sales Information |
| POST | `https://int-erp.esb.co.id/external/sales/get-sales-information?page={i}` | Sales Information |
| POST | `/external/general/sales-menu` | Sales Menu |
| POST | `/external/general/sales-menu-completion` | Sales Menu Completion |
| GET | `/extv1/sales/sales-menu-summary/` | Sales Menu Summary |
| GET | `/report/sales-payment-summary` | Sales Payment Summary |

