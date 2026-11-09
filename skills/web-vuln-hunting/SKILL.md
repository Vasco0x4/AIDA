---
name: web-vuln-hunting
description: "Operational playbook for authorized web application penetration testing and bug-bounty auditing, distilled from high-signal HackerOne / Bugcrowd / Intigriti disclosed reports and OWASP. Covers the highest-frequency, highest-payout web vulnerability classes with concrete test methodology, copy-paste payloads, curl probes, real disclosed-report patterns, and triage/severity guidance: broken access control (IDOR/BOLA/BFLA), SSRF (incl. cloud metadata & DNS rebinding), injection (SQLi/NoSQLi/command/SSTI/XXE/LDAP), XSS (reflected/stored/DOM/mutation), authentication & session flaws (JWT, OAuth/OIDC, SAML, password reset, MFA bypass), business-logic & race conditions, file upload / path traversal / LFI, CSRF, CORS misconfiguration, open redirect, GraphQL abuse, API security, subdomain takeover, HTTP request smuggling, web cache poisoning/deception, and secrets exposure. Use when planning or executing an authorized web app pentest/audit, reproducing a bug-bounty finding, choosing payloads for a specific vuln class, or writing up a report with severity and remediation."
version: 1.0.0
triggers:
  - web pentest
  - web application testing
  - bug bounty web
  - IDOR
  - BOLA
  - broken access control
  - SSRF
  - SQL injection
  - XSS
  - SSTI
  - XXE
  - JWT attack
  - OAuth testing
  - CSRF
  - CORS misconfiguration
  - open redirect
  - GraphQL security
  - API security testing
  - subdomain takeover
  - request smuggling
  - web cache poisoning
  - file upload bypass
  - path traversal
  - LFI
  - business logic
  - race condition
  - OWASP Top 10
---

# Web Vulnerability Hunting (Authorized Testing)

Operational playbook for finding, validating, and reporting the web bugs that
actually appear in HackerOne/Bugcrowd/Intigriti disclosures and OWASP Top 10
engagements. Optimized for **authorized** penetration tests, security audits,
and in-scope bug-bounty programs.

## ⚠️ Authorization gate — read first

This skill inherits **`safe-testing-doctrine`** (hard limits: no DoS/DDoS, no
destruction, no impact on real users, scope-only, least-intrusive PoC, cleanup).
Load it before testing. Before running ANY active test:
1. Confirm a written scope / rules of engagement or an in-scope bug-bounty
   program brief. Note the exact in-scope domains, IP ranges, and excluded paths.
2. Respect out-of-scope rules: no destructive payloads, no DoS/rate-flooding,
   no testing of third-party/shared infra, no pivoting outside scope, no
   accessing other users' real data beyond the minimum needed to prove impact.
3. Prefer read-only proof-of-concept. When a write/state-changing action is the
   only way to prove impact, use your own test accounts and benign markers.
4. Log everything (timestamps, requests) so findings are reproducible and the
   client can audit your activity.

If scope is unclear or absent, STOP and ask the operator before probing.

## How to use this skill

1. **Map first.** Enumerate endpoints, parameters, roles, auth flows, and object
   identifiers before firing payloads. Two accounts per role (attacker + victim)
   makes access-control testing trivial.
2. **Pick the class** from the table below, open the matching reference file for
   deep payloads/methodology, and work the checklist.
3. **Validate** every finding with a clean, minimal PoC. Rule out WAF echo,
   self-XSS, and non-exploitable reflections before reporting.
4. **Report** with the severity rubric and remediation notes at the bottom.

## Vulnerability class index

| Class | Why it matters | Deep reference |
|---|---|---|
| Broken Access Control (IDOR/BOLA/BFLA) | #1 by volume & payout on HackerOne | `references/access-control.md` |
| SSRF | Cloud metadata → full compromise | `references/ssrf.md` |
| Injection (SQL/NoSQL/cmd/SSTI/XXE/LDAP) | Highest impact when present | `references/injection.md` |
| XSS (reflected/stored/DOM/mXSS) | Ubiquitous, account takeover chains | `references/xss.md` |
| Auth & Session (JWT/OAuth/SAML/reset/MFA) | Account takeover class | `references/auth-and-session.md` |
| Business logic & race conditions | Undetectable by scanners | `references/business-logic-and-race.md` |
| File upload / path traversal / LFI | RCE and file disclosure | `references/injection.md` |
| CSRF / CORS / open redirect / clickjacking | Common misconfig chains | `references/client-side-and-misconfig.md` |
| GraphQL & API abuse | Modern high-yield surface | `references/graphql-and-api.md` |
| Subdomain takeover | Easy, high-severity infra bug | `references/infra-and-transport.md` |
| HTTP request smuggling | Front/back desync, cache poison | `references/infra-and-transport.md` |
| Web cache poisoning / deception | Mass impact from one request | `references/infra-and-transport.md` |

## Fast recon before testing (in-scope only)

```bash
# Content & endpoint discovery
ffuf -w wordlist.txt -u https://TARGET/FUZZ -mc all -fc 404 -t 40
katana -u https://TARGET -jc -d 3 -o endpoints.txt   # crawl incl. JS
gau TARGET | sort -u > urls.txt                       # historical URLs
# Parameters
arjun -u https://TARGET/api/endpoint                  # hidden param discovery
# JS secrets & endpoints
subjs -i urls.txt | httpx -mc 200 > js.txt
# Then: pull every path/param out of JS; those are your test surface.
```

Build an **object/parameter inventory**: every numeric ID, UUID, filename,
account reference, `redirect`/`url`/`next` param, `role`/`is_admin` field, and
state transition. That inventory drives the class-specific checklists.

## The 12 highest-yield checks (quick triage sweep)

Run these first on any new target — they catch the bulk of real reports:

1. Swap an object ID to another user's resource (IDOR) — numeric, UUID, hashed.
2. Change HTTP method / content-type on a protected endpoint (PUT/PATCH/DELETE, JSON↔form).
3. Add `?url=`, `?next=`, `?redirect=`, `?callback=`, `?dest=` and point at
   internal/collab host (SSRF / open redirect).
4. Inject `'"><svg onload=confirm(1)>` and `{{7*7}}`/`${7*7}` into every reflected field (XSS/SSTI).
5. `alter` JWT: `alg:none`, weak-secret crack, `kid` path traversal.
6. Test password-reset token: reuse, no-expiry, host-header poisoning, victim email leakage.
7. Force-browse admin/API paths as a low-priv user (BFLA).
8. Mass-assign `role`, `isAdmin`, `verified`, `price`, `userId` in JSON bodies.
9. `Origin:` reflection + `Access-Control-Allow-Credentials: true` (CORS ATO).
10. Upload `.php`/`.svg`/`.html`/polyglot and check retrieval path.
11. Race the coupon/withdraw/vote endpoint with parallel requests.
12. GraphQL introspection + `aliases` batching for BOLA/rate-limit bypass.

## Reporting output

For each confirmed finding produce: title, affected endpoint(s), severity
(CVSS + business impact), reproduction steps with exact requests, PoC, and
remediation. Use `references/reporting.md` for the severity rubric, CVSS
shortcuts, and a report template.

## Toolbox

Burp Suite (Repeater/Intruder/Turbo Intruder), ffuf/feroxbuster, nuclei,
sqlmap, tplmap/SSTImap, jwt_tool, arjun, katana/gau, interactsh (OOB/SSRF
callbacks), Param Miner + Collaborator (cache poisoning/smuggling), graphql-cop
/ clairvoyance, subzy/nuclei-takeover-templates. Always prefer the least
intrusive tool that proves impact.
