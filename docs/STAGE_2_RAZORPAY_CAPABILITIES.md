# STAGE 2 — Razorpay API Capability Matrix

> **Source:** Official Razorpay documentation (verified 2026-08-30)
> **Scope:** Payment Failure Incident MVP only

---

## Capability Matrix

| Capability | Verified? | Endpoint | Method | Read/Write/Event | MVP Required? | Notes |
|------------|-----------|----------|--------|------------------|---------------|-------|
| **READ OPERATIONS** | | | | | | |
| List Payments | ✅ | `/v1/payments` | GET | Read | ✅ | Pagination via `count`, `skip`; filters `from`, `to`, `expand[]` |
| Get Payment | ✅ | `/v1/payments/:id` | GET | Read | ✅ | Supports `expand[]=card\|emi\|offers` |
| List Orders | ✅ | `/v1/orders` | GET | Read | ✅ | Pagination; `expand[]=payments` |
| Get Order | ✅ | `/v1/orders/:id` | GET | Read | ✅ | |
| Get Order Payments | ✅ | `/v1/orders/:id/payments` | GET | Read | ✅ | |
| List Customers | ✅ | `/v1/customers` | GET | Read | ✅ | |
| Get Customer | ✅ | `/v1/customers/:id` | GET | Read | ✅ | |
| List Payment Links | ✅ | `/v1/payment_links/` | GET | Read | ✅ | Separate endpoints for Standard vs UPI |
| Get Payment Link | ✅ | `/v1/payment_links/:id` | GET | Read | ✅ | |
| List Refunds | ✅ | `/v1/refunds/` | GET | Read | ✅ | |
| Get Refund | ✅ | `/v1/refunds/:id` | GET | Read | ✅ | |
| Get Refunds for Payment | ✅ | `/v1/payments/:id/refunds` | GET | Read | ✅ | |
| List Settlements | ✅ | `/v1/settlements/` | GET | Read | ✅ | |
| Get Settlement | ✅ | `/v1/settlements/:id` | GET | Read | ✅ | |
| **WRITE OPERATIONS** | | | | | | |
| Create Order | ✅ | `/v1/orders` | POST | Write | ⚠️ | Not used for MVP recovery (Payment Link preferred) |
| **Create Payment Link** | ✅ | `/v1/payment_links/` | POST | **Write** | ✅ | **MVP Recovery Action**; `amount` in minor units, `expire_by` ≤ 6 months, test limit 30 |
| Create Refund | ✅ | `/v1/payments/:id/refund` | POST | Write | ⚠️ | Only for `captured` payments; normal & instant; idempotency supported |
| Update Payment Link | ✅ | `/v1/payment_links/:id` | PATCH | Write | ❌ | Not needed for MVP |
| Cancel Payment Link | ✅ | `/v1/payment_links/:id/cancel` | POST | Write | ❌ | Not needed for MVP |
| **EVENTS (WEBHOOKS)** | | | | | | |
| `payment.authorized` | ✅ | — | Event | Event | ⚠️ | Pre-capture; not used for failed payment recovery |
| `payment.captured` | ✅ | — | Event | Event | ✅ | Indicates successful capture |
| `payment.failed` | ✅ | — | Event | Event | ✅ | Core incident detection signal |
| `order.paid` | ✅ | — | Event | Event | ✅ | Alternative to payment.captured |
| `refund.processed` | ✅ | — | Event | Event | ⚠️ | If refund path used |
| `payment_link.paid` | ✅ | — | Event | Event | ✅ | Recovery completion signal |
| `invoice.paid` | ✅ | — | Event | Event | ⚠️ | Alternative recovery path |
| `settlement.processed` | ✅ | — | Event | Event | ⚠️ | Post-settlement confirmation |
| **NOT VERIFIED / DO NOT EXIST** | | | | | | |
| Retry Payment | ❌ | — | — | — | — | **No such API exists** |
| Direct Payment Retry | ❌ | — | — | — | — | Cannot retry a failed payment via API |
| Capture Payment | ✅ | `/v1/payments/:id/capture` | POST | Write | ⚠️ | Only for `authorized` payments; not for `failed` |

---

## Key Findings for MVP Design

### 1. Payment Retry Does Not Exist
The Razorpay API **does not expose a "retry payment" operation**. A failed payment cannot be retried via API. The only programmatic recovery paths are:
- **Payment Link re-collection** (create a new link for the customer to pay again) ✅ **SELECTED FOR MVP**
- Refund (if overcharge/capture error) — not applicable for simple failure
- Invoice (similar to Payment Link but for formal billing)

### 2. Payment Link is the Verified MVP Recovery Action
**Endpoint:** `POST /v1/payment_links/`
- Creates a Standard or UPI Payment Link
- Amount in **minor units** (paise for INR)
- `expire_by` timestamp (max 6 months from creation)
- Returns `short_url` (`https://rzp.io/i/...`) and `id` (`plink_...`)
- Test mode limit: **30 links per business** (contact support for more)
- Idempotency: Not explicitly documented for creation; use `reference_id` for deduplication
- Webhook event: `payment_link.paid` when customer completes payment

### 3. Refund Requires `captured` Payment
Refunds can only be created on payments in `captured` state. Not applicable for simple payment failures where no money was captured.

### 4. Pagination is Standard
All list endpoints support `count` (max 100) and `skip` for pagination. Use cursor-like iteration.

### 4. Authentication
- **Basic Auth**: `key_id` as username, `key_secret` as password
- **Test vs Live**: Separate key pairs; base URL same (`https://api.razorpay.com/v1`)
- **Webhook Secret**: Separate secret per webhook endpoint; HMAC SHA256 validation

### 5. Webhook Signature Validation
- Header: `X-Razorpay-Signature`
- Algorithm: HMAC SHA256 with webhook secret
- Payload: Raw request body
- Must validate in live mode; optional but recommended in test

### 6. Test Mode Limitations
- Payment Links: 30 per business in test mode
- Webhook URLs: Cannot use localhost without tunneling (ngrok, etc.)
- Webhook IPs must be whitelisted

---

## Selected MVP Recovery Operation

| Property | Value |
|----------|-------|
| **Operation** | `CREATE_PAYMENT_LINK` |
| **Endpoint** | `POST /v1/payment_links/` |
| **Purpose** | Re-collection for failed payment |
| **Verification** | ✅ Documented, testable, idempotent via `reference_id` |
| **Approval Required** | Human approval (policy engine) |
| **Post-Action Verification** | Webhook `payment_link.paid` + API fetch |

---

## Unverified / Excluded Capabilities

| Capability | Reason for Exclusion |
|------------|---------------------|
| `payment.retry` | Does not exist |
| `payment.capture` on failed | Only works on `authorized` state |
| Instant Refund | Requires `captured` payment; not applicable |
| Invoice creation | Overkill for simple re-collection; Payment Link is lighter |
| UPI Payment Link | Subtype of Payment Link; use standard unless UPI-only required |
| Subscriptions | Out of scope |
| Smart Collect | Different use case (virtual accounts) |

---

## Conclusion

**Only `CREATE_PAYMENT_LINK` is verified and suitable as the MVP recovery action.** All other write operations are either not applicable to the Payment Failure Incident or not verified for this use case.

The adapter will implement:
- Read operations for ingestion (payments, orders, customers, refunds, settlements, payment links)
- One verified write: `create_payment_link`
- Webhook ingestion with signature validation

No other write operations will be implemented until verified against the official documentation.