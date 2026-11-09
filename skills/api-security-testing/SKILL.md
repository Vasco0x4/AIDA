---
name: api-security-testing
description: "Operational playbook for authorized API penetration testing structured around the OWASP API Security Top 10 (2023) across REST, GraphQL, gRPC, SOAP, and webhooks. Covers all ten risks — API1 BOLA, API2 Broken Authentication, API3 BOPLA (excessive data exposure + mass assignment / property-level authz), API4 Unrestricted Resource Consumption, API5 BFLA, API6 Unrestricted Access to Sensitive Business Flows, API7 SSRF, API8 Security Misconfiguration, API9 Improper Inventory Management (shadow/zombie APIs), API10 Unsafe Consumption of APIs — with how each is FOUND, how it is tested/exploited via SAFE proof-of-concept, the real disclosed bug-bounty report pattern, detection, and remediation. Grounded in public HackerOne/PortSwigger disclosures and OWASP guidance. Authorized, in-scope engagements only. Rate-limiting (API4) is tested by safely probing whether a control EXISTS — never by flooding or exhausting resources."
version: 1.0.0
triggers:
  - api security
  - api security testing
  - owasp api top 10
  - owasp api security top 10
  - bola
  - broken object level authorization
  - bfla
  - broken function level authorization
  - bopla
  - broken object property level authorization
  - mass assignment
  - excessive data exposure
  - unrestricted resource consumption
  - api rate limiting test
  - graphql security
  - graphql introspection
  - api key
  - jwt api
  - oauth api
  - rest api testing
  - grpc security
  - soap api testing
  - webhook security
  - swagger openapi
  - shadow api
  - api ssrf
  - api inventory
---

# API Security Testing (Authorized — OWASP API Top 10 2023)

Operational playbook for finding, safely proving, and reporting the API bugs that
dominate HackerOne/PortSwigger disclosures and the **OWASP API Security Top 10
(2023)**. Framed API-first: object/function/property authorization, token flows,
resource-consumption *controls*, business-flow abuse, SSRF, misconfig, API
inventory, and third-party trust — across REST, GraphQL, gRPC, SOAP, and webhooks.

This skill assumes the web fundamentals in the base skill `web-vuln-hunting` and
its `references/graphql-and-api.md`. It does **not** re-teach payload mechanics;
it adds the **API-Top-10 framing** and API-specific discovery/exploitation depth.
Use them together.

## ⚠️ Safety — inherits `safe-testing-doctrine` (read first)

This skill operates **only** under the base `safe-testing-doctrine`. Load it
before any active test. API-specific hard limits:

- **API4 (Unrestricted Resource Consumption) — NO DoS, ever.** You do **not**
  flood, stress, or exhaust anything. You test *whether a rate-limit / quota
  control EXISTS* with a **small controlled burst (~10–20 requests)**, observe
  whether `429`/throttling/`Retry-After` appears, then **STOP and report the
  gap**. Never send a flood, never chain large fan-out, never run overnight
  loops, never trigger auto-scaling/billing. Reporting "no rate limit was
  observed in 20 requests" is the finding — proving DoS is forbidden.
- **No destructive mutations.** Use your **own test accounts** and **benign
  markers** (e.g. `pentest-<date>`). Never delete/overwrite/encrypt real data.
- **BOLA/BFLA proof is minimal.** Read **1–2 objects** to prove cross-tenant
  access, capture redacted evidence, then stop. Do not enumerate or exfiltrate
  user datasets. Redact PII in the report.
- **Scope-only.** Test only in-scope hosts/paths. Third-party APIs consumed by
  the target (API10) are tested by inspecting the target's *handling* of their
  responses, not by attacking the third party.
- **Least-intrusive PoC + cleanup.** Prefer read-only proof. Remove any test
  objects you create; log every request with timestamps for auditability.

If scope or authorization is unclear → **STOP and ask the operator.**

## How to use this skill

1. **Inventory the API first** (API9 is a prerequisite, not an afterthought):
   pull Swagger/OpenAPI, scrape endpoints from JS and mobile apps, discover
   shadow/zombie versions. You cannot test what you have not enumerated.
2. **Model roles & objects.** Two accounts per role (attacker + victim) + one
   low-priv + one admin makes API1/API3/API5 testing mechanical.
3. **Pick the risk** from the index, open the matching reference, work the
   HOW-TO-FIND → HOW-TO-TEST (safe PoC) → detection → remediation flow.
4. **Validate & report** with the severity/remediation guidance in each file and
   the base `web-vuln-hunting/references/reporting.md`.

## OWASP API Security Top 10 (2023) → reference index

| # | Risk | Reference file |
|---|---|---|
| API1:2023 | Broken Object Level Authorization (BOLA) | `references/access-control.md` |
| API3:2023 | Broken Object Property Level Authorization (BOPLA — excessive data exposure + mass assignment) | `references/access-control.md` |
| API5:2023 | Broken Function Level Authorization (BFLA) | `references/access-control.md` |
| API6:2023 | Unrestricted Access to Sensitive Business Flows | `references/access-control.md` |
| API2:2023 | Broken Authentication (API keys, JWT, OAuth for APIs) | `references/auth-and-config.md` |
| API4:2023 | Unrestricted Resource Consumption (safe rate-limit testing) | `references/auth-and-config.md` |
| API8:2023 | Security Misconfiguration | `references/auth-and-config.md` |
| API9:2023 | Improper Inventory Management (shadow/zombie APIs) | `references/auth-and-config.md` |
| API10:2023 | Unsafe Consumption of APIs (third-party trust) | `references/auth-and-config.md` |
| API7:2023 | Server-Side Request Forgery (SSRF) | `references/graphql-and-protocols.md` |
| — | GraphQL, gRPC, SOAP, webhooks (protocol-specific depth) | `references/graphql-and-protocols.md` |

Public URLs consulted: `references/sources.md`.

## The three-pass API test loop (quick reference)

1. **Discover** — OpenAPI/Swagger, JS, mobile, `kiterunner`, `arjun`, robots,
   git history, versioned paths. Build the full operation list (method + path +
   params) per role. (API9)
2. **Authorize** — replay every operation as *unauth*, *low-priv*, and
   *other-tenant*. Object id swaps (API1), property injection/leakage (API3),
   admin functions (API5), business-flow automation gates (API6). (Access
   control is where most API findings live.)
3. **Abuse the plumbing** — token/JWT/OAuth flaws (API2), missing consumption
   controls (API4, tested safely), misconfig & verbose errors (API8), SSRF via
   URL-taking params (API7), trust of upstream API data (API10).

## Severity anchors (API context)

- Cross-tenant read of PII/financial objects (BOLA) → **High**; write / account
  takeover / privesc (BFLA, mass assignment) → **Critical**.
- SSRF reaching cloud metadata / internal services → **Critical**.
- Missing rate-limit on auth/OTP/expensive/paid ops (proven safely) →
  **Medium–High** depending on abusability; business-flow automation (API6)
  scales the impact.
- Verbose errors / introspection / shadow endpoints alone → **Low/Info** unless
  they chain into the above.
