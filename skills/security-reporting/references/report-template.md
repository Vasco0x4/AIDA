# Copy-Paste Report Templates

Three templates: (A) full pentest/audit report, (B) single finding, (C) concise
bug-bounty submission. Fill the `{{placeholders}}`. Delete guidance in `«…»`.

---

## A. Full pentest / audit report

```markdown
# {{Client}} — {{Web App / Internal / Cloud}} Penetration Test Report
**Classification: CONFIDENTIAL**

| | |
|---|---|
| Client | {{Client legal name}} |
| Assessment type | {{Black/Grey/White-box}} {{External/Internal/Web/API/Cloud/AD}} |
| Scope (one line) | {{e.g. *.app.example.com + 10.0.0.0/24}} |
| Testing window | {{2026-08-01 → 2026-08-12}} |
| Prepared by | {{Tester / Firm}}, {{contact}} |
| Report version / date | v1.0 — {{2026-08-13}} |
| Distribution | {{named recipients only}} |

---

## 1. Executive summary
«1 page, non-technical. Written last, read first.»

{{Two–three sentences: what was assessed and the overall security posture.}}

**Overall risk: {{Critical / High / Medium / Low}}**

| Severity | Critical | High | Medium | Low | Info |
|----------|:--:|:--:|:--:|:--:|:--:|
| Count | {{1}} | {{3}} | {{5}} | {{4}} | {{2}} |

**Key findings & business impact**
- {{Finding 1 — one line + the business consequence, e.g. "Unauthenticated RCE on
  the customer portal could let an attacker take over the server and access all
  customer data — regulatory breach exposure under GDPR."}}
- {{Finding 2 …}}
- {{Finding 3 …}}

**Headline recommendations**
1. {{Fix X immediately (KEV/Critical).}}
2. {{Remediate the access-control gaps (systemic).}}
3. {{Adopt Y control / process improvement.}}

## 2. Methodology & standards
Approach: {{black/grey/white-box}}. Aligned to **NIST SP 800-115**, **PTES**, and
**OWASP WSTG/ASVS**. Findings scored with **CVSS v3.1 & v4.0**, prioritized using
**EPSS** and **CISA KEV**. Phases: planning → discovery → attack → reporting.
Tooling classes: {{recon, scanners, manual testing frameworks}}.

## 3. Scope
**In scope:** {{domains / IPs / apps / AD domain / accounts provided}}
**Out of scope / exclusions:** {{explicit exclusions}}
**Window:** {{dates + hours}}  **Access provided:** {{creds/roles or none}}
**Assumptions & limitations:** {{WAF present, time-boxed, prod vs staging, etc.
Absence of a finding does not guarantee absence of a vulnerability.}}

## 4. Findings summary

| ID | Finding | Severity | CVSS | CWE | Status |
|----|---------|----------|------|-----|--------|
| AIDA-2026-001 | {{Unauth SQLi in /api/search}} | Critical | 9.8 (v3.1) | CWE-89 | Open |
| AIDA-2026-002 | {{Stored XSS in profile bio}} | Medium | 5.4 | CWE-79 | Open |
| … | | | | | |

## 5. Detailed findings
«One per finding using Template B, ordered by severity.»

## 6. Remediation roadmap

| Priority | Finding(s) | Action | Suggested SLA |
|----------|-----------|--------|---------------|
| Immediate | 001 | {{Patch / block}} | {{24–72h — KEV/Critical}} |
| Short-term | 003, 005 | {{Fix access control}} | {{2 weeks}} |
| Strategic | headers, TLS | {{Baseline hardening}} | {{next cycle}} |

## 7. Appendices
- A. Detailed scope & asset inventory
- B. Tools used
- C. Evidence (request/response, screenshots — **PII/secrets redacted**)
- D. WSTG/ASVS coverage checklist
- E. Glossary & references

## 8. Cleanup list «mandatory — per safe-testing-doctrine»
| Artifact | Location | Created | Removed | Notes |
|----------|----------|---------|---------|-------|
| test file `poc.txt` | /uploads | 2026-08-05 | ✅ 2026-08-05 | benign marker |
| test account `pentest_a` | app | 2026-08-04 | ✅ 2026-08-12 | |
```

---

## B. Finding template (all fields)

```markdown
### {{AIDA-2026-001}} — {{Title: class + location + impact}}

| | |
|---|---|
| **Severity** | {{Critical}} |
| **CVSS v3.1** | {{9.8}} — `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` |
| **CVSS v4.0** | {{9.x}} — `CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N` |
| **CWE** | {{CWE-89: SQL Injection}} |
| **Classification** | {{OWASP A03:2021-Injection · WSTG-INPV-05}} |
| **EPSS / KEV** | {{N/A (novel) — or EPSS 0.94 / KEV: Listed}} |
| **Affected** | {{https://app.example.com/api/search?q= — `q` parameter}} |
| **Status** | Open |

**Description**
{{What the flaw is and its root cause, plainly. The `q` parameter is concatenated
into a SQL query without parameterization, allowing injection.}}

**Impact**
{{Concrete business consequence. An unauthenticated attacker can read/modify the
entire database, including {{~1.2M customer records}} — breach-notification and
regulatory exposure.}}

**Steps to reproduce**
1. {{Send: `GET /api/search?q=test' AND SLEEP(5)-- -`}}
2. {{Observe ~5s delayed response, confirming time-based blind SQLi.}}
3. {{Extract DB version (safe read-only PoC): `q=test' UNION SELECT @@version-- -`}}

```
{{paste minimal request + response evidence — redact PII/secrets}}
```

**Proof of concept**
{{Screenshot / log reference. Least-intrusive proof only; PII boxed/redacted.}}

**Remediation**
{{Use parameterized queries / prepared statements for all DB access; validate and
allowlist input; apply least-privilege DB account; add a WAF rule as defense-in-
depth. See web-vuln-hunting → injection remediation.}}

**References**
{{CWE-89 · OWASP SQL Injection Prevention Cheat Sheet · WSTG-INPV-05}}
```

---

## C. Bug-bounty submission (concise)

Programs want: clear title, real impact, exact repro, safe PoC, and a suggested
severity with a CVSS vector. Keep it tight; respect program scope & safe-harbor.

```markdown
**Title:** {{[BOLA] Any user can read other users' orders via /api/v2/orders/{id}}}

**Severity:** {{High}} — CVSS v3.1 {{8.1}}
`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N`
**Weakness:** {{CWE-639 / OWASP API1:2023 BOLA}}
**Asset / endpoint:** {{https://api.example.com/api/v2/orders/{id} (in scope)}}

**Summary**
{{One or two sentences: the object-level authorization check is missing, so an
authenticated user can access any order by incrementing the ID.}}

**Steps to reproduce**
1. {{Log in as User A (account I control); note my order id 10521.}}
2. {{Send `GET /api/v2/orders/10520` with User A's token.}}
3. {{Response returns User B's order (name, address, items) — not mine.}}

**Proof of concept**
```
{{minimal request + redacted response snippet}}
```
«Accessed one adjacent record only, as PoC. No bulk enumeration performed. PII redacted.»

**Impact**
{{Any authenticated user can enumerate and read all customers' order data (PII +
purchase history). Confidentiality breach across the whole order table.}}

**Remediation**
{{Enforce server-side authorization: verify the order belongs to the requesting
user (object owner check) before returning it.}}

**Remediation is not tested by me / no data was exfiltrated beyond this single PoC.**
```

Bug-bounty etiquette: one bug per report; don't test denial-of-service or pivot
out of scope; use your own test accounts; minimize data touched; follow the
program's disclosure timeline.
