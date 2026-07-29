# Workflows & Diagrams
## EFN (Erajaya F&B) — Odoo ↔ ESB Core Integration

**Audience:** everyone — this is the visual index to the specification set
**Version:** 1.0 · 22 July 2026
**Companion documents:** [BRD Management](01-BRD-management.md) · [BRD Technical](02-BRD-technical.md) · [FSD](03-FSD.md) · [TSD](04-TSD.md)

Every diagram below also appears in context in the document it belongs to. This page
collects them so the integration can be understood end to end in one sitting.

---

## 1. The relationship between the two systems

The single most important thing to understand: **ESB stays in charge of stock.**
Odoo reads from it, thinks, and writes back only what a person has approved.

```mermaid
flowchart LR
    subgraph ESB["ESB — stays the system of record"]
        core["ESB Core<br/>stock · purchasing · finance"]
        oms["ESB OMS<br/>POS sales · material usage"]
    end

    subgraph ODOO["Odoo — new intelligence layer"]
        mirror["Read-only mirror<br/>of ESB master data and stock"]
        brain["Opname · Forecasting · Replenishment"]
    end

    core -->|"master data, stock movements"| mirror
    oms -->|"daily material usage"| mirror
    mirror --> brain
    brain --> gate{"Human<br/>approval"}
    gate -->|"approved"| back["Stock adjustment<br/>Purchase request / transfer / order"]
    back --> core
    gate -.->|"not approved — nothing happens"| stop([" "])

    classDef esb fill:#E2EFED,stroke:#0B5D5D,color:#0B3F3F
    classDef odoo fill:#F6EBD8,stroke:#8A5A12,color:#5C3D0C
    classDef gateS fill:#E1EFE3,stroke:#3B6B45,color:#24421F
    class core,oms esb
    class mirror,brain,back odoo
    class gate gateS
    style stop fill:none,stroke:none
```

---

## 2. What moves, in which direction, and how often

Inbound is scheduled and read-only. Outbound is event-driven and always passes a
person. **There is no path from a schedule directly to a write in ESB.**

```mermaid
flowchart LR
    subgraph inb["Inbound — ESB to Odoo, scheduled"]
        direction TB
        i1["Master data<br/>daily"]
        i2["Stock balances<br/>every 4 h"]
        i3["Material usage<br/>daily, previous day"]
        i4["Document status<br/>every 30 min"]
    end

    subgraph odoo["Odoo"]
        direction TB
        store["Mirror + snapshot + history"]
        think["Forecast · count · plan"]
        gate{"Human approval"}
    end

    subgraph outb["Outbound — Odoo to ESB, event-driven"]
        direction TB
        o1["Item Journal<br/>on session close"]
        o2["Purchase request<br/>Transfer request<br/>Purchase order<br/>on proposal approval"]
    end

    i1 --> store
    i2 --> store
    i3 --> store
    store --> think
    think --> gate
    gate --> o1
    gate --> o2
    i4 -.->|"reconciles"| o1
    i4 -.->|"reconciles"| o2

    classDef in fill:#E2EFED,stroke:#0B5D5D,color:#0B3F3F
    classDef out fill:#F6EBD8,stroke:#8A5A12,color:#5C3D0C
    classDef g fill:#E1EFE3,stroke:#3B6B45,color:#24421F
    class i1,i2,i3,i4 in
    class o1,o2 out
    class gate g
```

---

## 3. Stock opname, end to end

```mermaid
sequenceDiagram
    autonumber
    actor S as Supervisor
    actor C as Counter
    participant O as Odoo
    participant E as ESB Core

    S->>O: Create session for branch + location
    S->>O: Load Lines from ESB
    O->>E: Read stock movement report
    E-->>O: Closing balance per material
    O-->>S: Lines with expected quantities

    C->>O: Record counted quantities
    O->>O: variance = counted − expected

    opt Expected quantity is stale
        S->>O: Refresh Expected from ESB
        O->>E: Read authoritative balance per material
        E-->>O: Current balance
    end

    S->>O: Approve or reject each variance
    S->>O: Close session

    Note over O: Only approved, non-zero variances are included

    O->>E: Search for an existing journal with our key
    E-->>O: None found
    O->>E: Create Item Journal — signed variance per line
    E-->>O: Item Journal number
    O-->>S: Session shows the ESB document number
```

> **The quantity sent is the difference, not the count.** Counting 7 against an
> expected 10 sends **−3**. Sending 7 would post the outlet's whole stock balance as
> an adjustment.

---

## 4. Demand to replenishment, with the approval gate

```mermaid
flowchart TD
    start(["Overnight scheduled run"]) --> pull["Pull yesterday's material usage<br/>from ESB OMS"]
    pull --> fc["Recompute forecasts"]
    fc --> rule["For each replenishment rule"]

    rule --> q1{"Forecast<br/>available?"}
    q1 -->|no| skipA["Skip — no demand history"]
    q1 -->|yes| q2{"On-hand known<br/>in ESB?"}

    q2 -->|"no row reported"| skipB["Skip — on-hand unknown<br/>never assumed to be zero"]
    q2 -->|yes| calc["need = demand over cover<br/>+ safety stock<br/>− on hand − on order"]

    calc --> q3{"need > 0<br/>after rounding?"}
    q3 -->|no| skipC["Skip — stock sufficient"]
    q3 -->|yes| draft["Draft proposal in Odoo"]

    draft --> review["Planner reviews<br/>derivation shown per line"]
    review --> q4{"Approve?"}
    q4 -->|"cancel or edit"| draft
    q4 -->|approve| push["Create document in ESB<br/>Purchase request · transfer · order"]
    push --> done(["ESB authorises → proposal closed"])

    classDef skip fill:#F1F4F4,stroke:#8A9499,color:#4A5A5E
    classDef gate fill:#E1EFE3,stroke:#3B6B45,color:#24421F
    classDef esbw fill:#F6EBD8,stroke:#8A5A12,color:#5C3D0C
    class skipA,skipB,skipC skip
    class q4 gate
    class push,done esbw
```

Note the two deliberate refusals: no forecast means no proposal, and an **unknown**
on-hand quantity means the system declines rather than guesses.

---

## 5. How duplicate documents are prevented

ESB accepts no idempotency key, so a create that times out *after* ESB committed it
would be duplicated on retry — duplicated stock adjustments and duplicated ledger
entries. This is the guard.

```mermaid
flowchart TD
    q(["Outbox row queued"]) --> sw{"Outbound writes<br/>enabled?"}
    sw -->|off| hold["Stay queued<br/>kill switch — nothing lost"]
    sw -->|on| look["Search ESB for a document<br/>carrying our key"]

    look --> res{"Lookup<br/>result"}
    res -->|"lookup FAILED"| abort["Abort the push<br/>we cannot tell whether it exists —<br/>posting blind is how duplicates happen"]
    res -->|"key found"| adopt["Adopt the existing document<br/>no second one is created"]
    res -->|"not found"| post["Create the document"]

    post --> pr{"Accepted?"}
    pr -->|no| fail["Record ESB's exact error"]
    fail --> att{"attempts < 5?"}
    att -->|yes| q
    att -->|no| dead["Failed — waits for a human"]
    pr -->|yes| sent["Sent — store the ESB number"]

    adopt --> sent
    sent --> done(["ESB's approval flow continues"])

    classDef stop fill:#F6EBD8,stroke:#8A5A12,color:#5C3D0C
    classDef good fill:#E1EFE3,stroke:#3B6B45,color:#24421F
    class abort,dead,hold stop
    class adopt,done good
```

---

## 6. Staying authenticated to ESB

ESB permits **one active session per account** — logging in anywhere evicts the
previous session. This is why the integration needs an account of its own, and why
token rotation is serialised.

```mermaid
flowchart TD
    call(["Any ESB call needs a token"]) --> mode{"Authentication<br/>mode"}
    mode -->|"static API key"| key["Use the key<br/>no rotation, no eviction risk"]
    mode -->|"login + refresh"| lock["Lock the session row<br/>only one worker may rotate"]

    lock --> reread["Re-read — another worker<br/>may have just refreshed it"]
    reread --> q1{"Access token still<br/>valid in 5 min?"}
    q1 -->|yes| use["Use it"]
    q1 -->|no| q2{"Refresh token still<br/>valid in 5 min?"}

    q2 -->|yes| refresh["Refresh"]
    refresh --> q3{"Accepted?"}
    q3 -->|yes| use
    q3 -->|no| login

    q2 -->|no| login["Log in"]
    login --> store["Store both tokens<br/>this evicts any other ESB session"]
    store --> use

    use --> rej{"ESB rejects<br/>the token?"}
    rej -->|no| ok(["Response returned"])
    rej -->|"yes — evicted by someone else"| inval["Clear both tokens"]
    inval --> retry["Re-authenticate, retry once"]
    retry --> ok

    classDef danger fill:#F6EBD8,stroke:#8A5A12,color:#5C3D0C
    classDef safe fill:#E1EFE3,stroke:#3B6B45,color:#24421F
    class login,store,inval danger
    class key,use safe
```

> A steadily climbing login count is the signature of someone using the
> integration's ESB account. It is the first thing to check if the integration
> starts failing intermittently.

---

## 7. Software architecture

```mermaid
flowchart TB
    subgraph esb["ESB — three API hosts"]
        h1["core<br/>/auth /inventory /purchase /report"]
        h2["corev1<br/>/corev1/master/product · sales"]
        h3["oms<br/>/external/general"]
    end

    subgraph conn["custom_esb_connector · ee_gap"]
        ad["EsbCoreAdapter<br/>envelope · pagination · retry"]
        se["custom.esb.session<br/>token rotation under row lock"]
        mi["Mirror models<br/>branch · location · purpose<br/>supplier · product.detail"]
        sn["custom.esb.stock.snapshot"]
        ob["custom.esb.outbox<br/>idempotent push · queue_job"]
    end

    subgraph ops["custom_fnb_stock_ops · verticals"]
        cc["cycle.count.session<br/>inherits custom_wms_cycle_count"]
        dh["demand.history → demand.forecast"]
        rp["replenishment.rule → proposal"]
    end

    h1 <--> ad
    h2 <--> ad
    h3 <--> ad
    se -.->|"bearer token"| ad
    ad --> mi
    ad --> sn
    ob --> ad

    sn --> cc
    sn --> rp
    mi --> cc
    mi --> rp
    dh --> rp
    cc -->|"Item Journal"| ob
    rp -->|"PR / GTR / PO"| ob

    classDef esbn fill:#E2EFED,stroke:#0B5D5D,color:#0B3F3F
    classDef connn fill:#EEF3F3,stroke:#4A5A5E,color:#101A1D
    classDef opsn fill:#F6EBD8,stroke:#8A5A12,color:#5C3D0C
    class h1,h2,h3 esbn
    class ad,se,mi,sn,ob connn
    class cc,dh,rp opsn
```

The connector knows nothing about food. The vertical module knows nothing about
HTTP. That separation is what makes the connector reusable for the next F&B customer
running on ESB.

---

## 8. Go-live sequence

```mermaid
flowchart LR
    A["1 · Connect<br/>read only"] --> B["2 · Master data<br/>verify against ESB"]
    B --> C["3 · Stock visibility<br/>one outlet, reconcile"]
    C --> D["4 · Opname<br/>one material, variance of 1"]
    D --> E["5 · Replenishment<br/>purchase requests only"]
    E --> F["6 · Rollout<br/>outlet by outlet"]

    C -.->|"first write to ESB happens here"| D

    classDef read fill:#E2EFED,stroke:#0B5D5D,color:#0B3F3F
    classDef write fill:#F6EBD8,stroke:#8A5A12,color:#5C3D0C
    class A,B,C read
    class D,E,F write
```

Steps 1–3 cannot change anything in ESB. Each step is independently useful and
independently reversible; a single switch stops all writing without a code change.

---

## 9. State of a replenishment proposal

```mermaid
stateDiagram-v2
    [*] --> Draft: generated by the scheduled run
    Draft --> ToApprove: submitted
    Draft --> Cancelled: discarded
    ToApprove --> Draft: sent back
    ToApprove --> Cancelled: rejected
    Draft --> Pushed: approved
    ToApprove --> Pushed: approved
    Pushed --> Done: ESB authorises the document
    Cancelled --> [*]
    Done --> [*]

    note right of Draft
        Nothing exists in ESB
        while the proposal is here
    end note

    note right of Pushed
        The ESB document now exists
        and cannot be withdrawn from Odoo
    end note
```

---

*For the reasoning behind each of these flows, see the
[BRD Technical](02-BRD-technical.md) and [TSD](04-TSD.md).*
