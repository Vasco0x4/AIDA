# Access Control — API1 BOLA · API3 BOPLA · API5 BFLA · API6 Business Flows

Access-control failures are where the overwhelming majority of API findings live
(BOLA has been OWASP API #1 since 2019). This file adds the **API-Top-10
framing** on top of the mechanics in
`web-vuln-hunting/references/access-control.md` — do not re-teach id-swapping
there; here we map each authorization *layer* to its Top-10 risk and the
API-specific proof.

**Setup (once):** two accounts per role — attacker **A**, victim **B** — plus a
low-priv and an admin. Capture B's traffic, replay with A's token and B's
identifiers. Diff responses: `200 + victim data` = broken; `403/404` = enforced.

---

## API1:2023 — Broken Object Level Authorization (BOLA)

The endpoint checks *authentication* but not *ownership of the object id*.

### How to find
- Every operation that takes an object id: `/api/orders/{id}`, `/users/{id}`,
  `?account=`, `X-Account-Id` header, JSON `"id"`, GraphQL `node(id:)`.
- Harvest ids from your own responses, notification emails, JS, referers.
- Note the id shape: sequential int (trivial), UUID (needs a leak source),
  base64/hash (decode → alter → re-encode).

### How to test (safe PoC)
```bash
# A's token, B's object id. Read ONE object to prove it, then stop.
curl -s https://api.target.com/api/v1/orders/1005 \
  -H "Authorization: Bearer $A_TOKEN" -i
# 200 + B's order = BOLA. Capture redacted evidence for 1-2 ids max.
```
Bypasses when a `403` appears (from base access-control.md): method swap, trailing
`/`/`.json`, wrap id `{"id":[123]}`, duplicate param `id=own&id=victim`, version
pivot `/v2/`→`/v1/`. **Do not** iterate ranges to scrape data — proving 1–2
cross-tenant reads is sufficient and required by the safety doctrine.

### Real disclosed pattern
Numeric invoice/order IDs readable across accounts; UUID leaked in a notification
email then reused to pull a full PII object; GraphQL `node(id:)` returning any
user's private object (global BOLA bypassing per-type authz).

### Detection / Remediation
Detection: authz decisions keyed only on the id in the request, no owner check in
logs. Remediation: enforce **object-ownership check server-side on every
request**; never trust client-supplied ids for authorization; random ids are
defense-in-depth only, not a control.

---

## API3:2023 — Broken Object Property Level Authorization (BOPLA)

Authorization is right at the *object* level but wrong at the *property* level —
two directions: **read** side = *Excessive Data Exposure*; **write** side =
*Mass Assignment*.

### Excessive Data Exposure (read)
The API returns the full object and expects the client to filter. Read the raw
response, not the rendered UI.
```bash
curl -s https://api.target.com/api/v1/users/me \
  -H "Authorization: Bearer $A_TOKEN" | jq 'keys'
# Look for password_hash, ssn, internal_flags, isAdmin, mfa_secret, tokens.
```
### Mass Assignment (write)
Send properties the UI never exposes to escalate or tamper state. Discover valid
field names from GET responses, the GraphQL schema, or mobile decompilation, then
echo them into the write request.
```bash
# Use YOUR OWN test account; benign markers only.
curl -s -X PATCH https://api.target.com/api/v1/users/me \
  -H "Authorization: Bearer $A_TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"pentest-2026@example.com","role":"admin","isAdmin":true,"verified":true,"account_balance":1}'
# Re-GET to see which unauthorized properties actually persisted.
```

### Real disclosed pattern
`PUT /api/users/{id}` accepted a `role` field → vertical privesc; user object
returned password hash / internal entitlement flags; registration accepted
`"credit":` field.

### Detection / Remediation
Remediation: **explicit response schemas** (return only needed fields, never
`return user`); **allow-list writable properties** (no blanket model/ORM
binding); validate `readOnly`/`writeOnly` in the OpenAPI schema and generate
serializers from it.

---

## API5:2023 — Broken Function Level Authorization (BFLA)

Low-priv (or unauth) principal reaching a *function*/route reserved for a higher
role. Object-level may be fine; the whole operation should have been denied.

### How to find
- Force-browse admin/management routes found in JS bundles, `robots.txt`,
  sitemaps, OpenAPI: `/api/admin/users`, `/manage`, `/internal`, `/actuator`,
  `/debug`, `/api/v1/admin/*`.
- Note verbs the UI hides: the app disables the button but the `DELETE`/`POST`
  endpoint stays live.

### How to test (safe PoC)
```bash
# Normal-user token hitting an admin function. Read-only first (list, not delete).
curl -s https://api.target.com/api/v1/admin/users \
  -H "Authorization: Bearer $LOWPRIV_TOKEN" -i
# 200 = BFLA. To prove a write, use your own test object + benign marker, never a real one.
```
Also try **HTTP method tampering** (`GET`→`POST/PUT/DELETE`), and role-swap
headers (`X-Role: admin`, `isAdmin=true`) replayed onto the admin route.

### Real disclosed pattern
Admin API left function-level-unauthenticated while only the UI hid it; normal
token could call `/admin/users` and change roles; `POST /api/v1/admin/promote`
callable by any authenticated user.

### Detection / Remediation
Remediation: **deny by default**; centralize function-level authz in middleware
keyed on role, not per-controller; admin controllers inherit an admin guard;
regularly reconcile the route map against the role matrix.

---

## API6:2023 — Unrestricted Access to Sensitive Business Flows

The individual request is authorized, but the *business flow* has no protection
against automated/excessive use — scalping, gift-card/credit farming, mass
account creation, referral/coupon abuse, review flooding, bulk data harvesting.

### How to find
Model the money/trust-sensitive flows: purchase/checkout, ticket reservation,
signup, invite, coupon redeem, points transfer, "add to cart" limited stock,
password-reset-email trigger. Ask: *what stops a script from doing this 10,000
times?* (no CAPTCHA, no per-account cap, no device/velocity check, no
step-up.)

### How to test (safe PoC)
This overlaps API4 but the concern is **flow abuse**, not resource exhaustion.
Prove the *control gap* with a tiny controlled sample — e.g. redeem the same
coupon, or trigger the flow, **~5–10 times** with your own account and benign
data, and observe whether any velocity/uniqueness/anti-automation control fires.
**Stop at the sample; do not actually farm value or place real orders at scale.**
Report: "flow X enforced no anti-automation across N controlled attempts."

### Real disclosed pattern
Coupon/referral codes redeemable unlimited times for stacked credit; unlimited
account creation feeding a signup-bonus; ticket/stock reservation with no
per-user cap enabling inventory hoarding.

### Detection / Remediation
Remediation: layer anti-automation on the *flow* — device fingerprinting, CAPTCHA
/ proof-of-work on abuse-prone steps, per-account and per-flow rate/velocity
limits, uniqueness constraints (one redemption per user), and human-review
thresholds. This is a business decision, not just a WAF rule.

---

## Cross-reference
Multi-tenant `tenant_id`/`org_id` swaps, encoding/parser bypass tricks, and the
full id-shape matrix live in `web-vuln-hunting/references/access-control.md`.
GraphQL-specific BOLA (`node(id:)`, per-type authz) is in
`references/graphql-and-protocols.md`.
