# Broken Access Control (IDOR / BOLA / BFLA / Mass Assignment)

The single largest category by report volume and payout across bug-bounty
platforms. Scanners barely find these — they require role/object modeling.

## Setup
- Create **two accounts per role** (attacker A, victim B) + one low-priv, one admin.
- Capture B's requests, then replay them **with A's session** and B's identifiers.
- Diff responses: 200 + victim data = IDOR; 403/404 = enforced.

## IDOR / BOLA (object-level) test matrix

| Identifier type | Attack |
|---|---|
| Sequential int (`/api/orders/1005`) | ± the number, iterate ranges with Burp Intruder |
| UUID / GUID | leaks in other responses, emails, JS, referer? Collect & reuse |
| Hashed/encoded (`base64`, `md5`) | decode, alter, re-encode |
| Filename (`/files/report_88.pdf`) | traverse index, predict siblings |
| Indirect (`?account=self`) | replace `self` with victim id/email/username |

Test on **every verb and location**: URL path, query, JSON body, headers
(`X-User-Id`, `X-Account`), cookies, and GraphQL variables.

### Common bypasses when a 403 appears
- Change method: `GET`→`POST`/`PUT`/`PATCH`/`DELETE`, or `POST`→`GET`.
- Add trailing `/`, `.json`, `;`, `%2e`, `//`, or case-swap the path.
- Wrap id in array/object: `{"id":123}` → `{"id":[123]}` or `{"id":{"id":123}}`.
- Duplicate param: `id=own&id=victim` (last/first wins depends on parser).
- Add `X-Original-URL`, `X-Rewrite-URL`, `X-Forwarded-For`, `X-Forwarded-Host`.
- Version pivot: `/api/v2/` enforces, `/api/v1/` or `/internal/` may not.

## BFLA — Broken Function-Level Authorization
Low-priv user reaching admin functions:
- Force-browse admin routes discovered in JS/`robots.txt`/sitemap:
  `/admin`, `/api/admin/users`, `/manage`, `/internal`, `/actuator`, `/debug`.
- Call the admin API directly with a normal-user token — many apps hide the UI
  but leave the endpoint unauthenticated at the function level.
- Toggle client-side flags (`isAdmin`, disabled buttons) and replay the request.

## Mass assignment / parameter pollution
Add fields the UI never sends to privilege-escalate or tamper state:
```json
{"email":"a@x.com","role":"admin","isAdmin":true,"verified":true,
 "account_balance":999999,"user_id":<victim>,"tenant_id":<other>}
```
Discover valid field names from GET responses, GraphQL schema, or mobile app
decompilation, then echo them back in the write request.

## Multi-tenant / horizontal
- Swap `tenant_id`/`org_id`/`workspace` to read another org's data.
- Invite/removal flows: remove another org's admin, or add yourself to their org.

## Real disclosed-report patterns
- Numeric invoice/order IDs readable across accounts (classic IDOR, still top-5).
- UUID leaked in a notification email → reused to fetch full PII object.
- `PUT /api/users/{id}` accepted `role` field → vertical privesc.
- GraphQL `node(id:)` global object fetch bypassing per-type authz.

## Severity guidance
- Read of other users' PII/financial data → High.
- Write/account-takeover/privesc → Critical.
- Read of non-sensitive metadata → Low/Medium.

## Remediation to recommend
Enforce **object ownership checks server-side on every request** (never trust
client-supplied ids for authorization); use unguessable, non-sequential ids as
defense-in-depth only; allow-list writable fields (no blanket model binding);
centralize authorization in middleware, not per-controller.
