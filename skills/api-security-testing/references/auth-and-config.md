# Auth, Consumption & Config — API2 · API4 · API8 · API9 · API10

Covers the non-authorization half of the API Top 10: authentication mechanics,
resource-consumption *controls* (tested safely), misconfiguration, API inventory,
and trust of third-party APIs. Token cryptanalysis (JWT `alg:none`, OAuth flows,
SAML) is covered deeply in `web-vuln-hunting/references/auth-and-session.md` —
this file adds the API-specific framing and discovery.

---

## API9:2023 — Improper Inventory Management (discover FIRST)

You cannot test what you have not enumerated, and the most vulnerable endpoints
are usually the *undocumented, deprecated, or shadow* ones. Do inventory before
everything else.

### How to find
```bash
# 1. Pull machine-readable specs if exposed
for p in openapi.json swagger.json swagger/v1/swagger.json api-docs v2/api-docs \
         openapi.yaml swagger.yaml graphql .well-known/openapi; do
  curl -s -o /dev/null -w "%{http_code} $p\n" "https://api.target.com/$p"; done

# 2. Contextual API brute-force with kiterunner (assetnote wordlists)
wget -q https://wordlists-cdn.assetnote.io/data/kiterunner/routes-large.kite
kr scan https://api.target.com -w routes-large.kite -x 10 -j 50 \
   --fail-status-codes 400,401,403,404,429,501,502

# 3. Scrape endpoints & params from JS bundles
#    (LinkFinder / getjs / grep for fetch(), axios, "/api/")
# 4. Decompile the mobile app (apktool / jadx) for hidden hosts & v-numbers.
```
Then hunt **version drift**: `/api/v1/` often stays live and *unpatched* after
`/api/v2/` is fixed. Look for `staging.`, `dev.`, `internal.`, `-old`,
`beta`, and hostnames in JS/CORS/CSP headers → **shadow & zombie APIs**.

### Real disclosed pattern
`/api/v1/` left unauthenticated after `/v2/` was fixed; a forgotten `staging`
API host served production data without auth; a deprecated mobile endpoint kept
returning full PII.

### Detection / Remediation
Remediation: maintain a live API inventory (spec-driven); retire deprecated
versions; gate non-prod hosts; a gateway that only exposes documented,
governed routes.

---

## API2:2023 — Broken Authentication

### How to find & test (safe)
- **API keys**: static, in the URL/JS/mobile, no expiry, shared across tenants.
  Test key from account A against account B's data; test a revoked/old key.
  ```bash
  curl -s "https://api.target.com/v1/me?api_key=$FOUND_KEY" -i   # key in URL = logged everywhere
  ```
- **JWT**: inspect with `jwt_tool $TOKEN`. Check `alg:none`, `HS256`/`RS256`
  confusion, weak HMAC secret (`hashcat -m 16500`), missing `exp`, unverified
  `kid`/`jku`. Full method: `web-vuln-hunting/references/auth-and-session.md`.
- **OAuth/OIDC for APIs**: over-scoped tokens, missing audience (`aud`) check so a
  token minted for service X is accepted by service Y, refresh tokens that never
  rotate, `redirect_uri` laxness on the token endpoint.
- **Login/OTP without protection**: see API4 for the *safe* rate-limit probe;
  also test credential-stuffing surfaces, password reset token entropy, and
  whether OTP is verified server-side.

### Real disclosed pattern
JWT accepted with `alg:none`; API key valid across all tenants; access token
issued for one microservice accepted by another (missing `aud`); OTP endpoint
with no attempt limit.

### Remediation
Short-lived tokens with rotation; verify `alg`/`aud`/`exp`/`iss` server-side;
per-tenant keys with expiry and scopes; never place secrets in URLs; standard
auth libraries, not hand-rolled.

---

## API4:2023 — Unrestricted Resource Consumption  ⚠️ SAFE test only

**The goal is to prove a rate-limit / quota control is MISSING — never to cause
DoS.** You send a *small controlled burst* and observe whether any throttling
appears. If it does not, that observation *is* the finding.

### How to find
Target expensive or abusable operations: login/OTP, password-reset email/SMS
triggers (cost per call), search/export/report generation, file processing,
GraphQL/`?limit=` fan-out, anything that hits email/SMS/3rd-party billing.

### How to test (SAFE controlled probe)
```bash
# ~15 sequential requests, NOT parallel, NOT a flood. Watch for 429 / Retry-After.
for i in $(seq 1 15); do
  code=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST https://api.target.com/api/v1/login \
    -H 'Content-Type: application/json' \
    -d '{"user":"pentest-2026@example.com","pass":"wrong"}')
  echo "req $i -> $code"; sleep 0.3
done
# All 200/401 and NO 429/throttle across the sample => rate-limit control absent.
# STOP here. Report the gap. Do NOT escalate to a flood to "prove" DoS.
```
Also **safely** check resource-size controls with a *single* request: does the
API cap `?limit=`/`page_size=` (request `limit=100000` once and see if it's
clamped), pagination, upload size, or array length? One probe each — do not loop.

**Hard stops:** no parallelism, no sustained loops, no triggering auto-scaling or
per-message billing at volume, no OTP/email flooding to real inboxes. If ~10–20
controlled requests do not reveal a limit, that is enough.

### Real disclosed pattern
Login/OTP with no attempt throttling enabling credential brute force; unbounded
`limit` param dumping the whole table in one call; password-reset endpoint that
sent unlimited emails/SMS (cost + spam) — reported as *missing control*, proven
with a small sample, not a flood.

### Remediation
Per-user and per-IP rate limits with `429`+`Retry-After`; quotas on expensive
ops; server-enforced max page size / payload size / query depth; spending caps &
alerts on pay-per-use downstreams; timeouts and container resource limits.

---

## API8:2023 — Security Misconfiguration

### How to find & test
```bash
# Verbose errors / stack traces
curl -s "https://api.target.com/api/v1/orders/notanint" -i     # 500 + stack = leak

# CORS: does it reflect an arbitrary origin with credentials?
curl -s -I https://api.target.com/api/v1/me \
  -H "Origin: https://evil.example" | grep -i 'access-control-allow'
#   ACAO: https://evil.example + ACA-Credentials: true = exploitable CORS

# Missing security headers, permissive methods
curl -s -X OPTIONS https://api.target.com/api/v1/users -i       # Allow: shows verbs (TRACE/PUT?)
```
Also: default creds on admin panels, debug/actuator endpoints
(`/actuator/env`, `/debug`, `/metrics`, `/graphiql`), directory listing,
unauthenticated Swagger UI that also *executes* calls, missing TLS / HSTS,
`Server`/framework version banners.

### Real disclosed pattern
Reflective CORS with credentials → cross-origin data theft; Spring `/actuator/env`
leaking secrets; verbose 500s exposing SQL/internal paths; exposed GraphiQL in
prod.

### Remediation
Hardened, repeatable config baseline; strict CORS allow-list (no wildcard +
credentials); disable debug/introspection/verbose errors in prod; generic error
bodies; enforce TLS; drop version banners; automated config scanning in CI.

---

## API10:2023 — Unsafe Consumption of APIs

The target *consumes* third-party/upstream APIs and trusts their data more than
user input. Test the target's **handling** of upstream responses — do **not**
attack the third party (out of scope).

### How to find & test (safe)
- Map where the target ingests external data: webhooks, OAuth userinfo, payment
  callbacks, partner APIs, URL-fetch features (also API7/SSRF).
- If you control an endpoint the target calls back to (e.g. a webhook URL or an
  OAuth `redirect`/resource you host), return **malformed / oversized / injected**
  data and observe whether the target validates it: does an oversized field cause
  a 500? Does unescaped upstream data reach SQL/HTML (stored injection via the
  integration)? Does the target follow upstream redirects blindly?
- Check TLS validation and whether upstream calls go over plain HTTP.

### Real disclosed pattern
App trusted an upstream API's redirect and followed it into internal space; data
from a partner API stored unsanitized → stored XSS/SQLi; blind trust of a
webhook payload's `amount`/`status` field enabling payment tampering.

### Remediation
Validate & sanitize all data from third parties like user input; allow-list
upstream hosts; enforce TLS + cert validation; timeouts and size caps on
integrations; don't blindly follow upstream redirects; segregate integration
processing.

---

## Cross-reference
JWT/OAuth/SAML deep mechanics: `web-vuln-hunting/references/auth-and-session.md`.
SSRF (API7) and webhook attack surface: `references/graphql-and-protocols.md`.
