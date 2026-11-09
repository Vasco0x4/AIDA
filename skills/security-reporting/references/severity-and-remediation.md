# Severity Rubric, CWE Mapping, Remediation & SLA Guidance

## Severity rubric (CVSS band → qualitative → what it means)

Assign from the CVSS score, then sanity-check against real exploitability and the
Bugcrowd VRT priority (P1–P5) and OWASP Risk Rating. Severity = *magnitude*;
prioritization (below) = *fix order*.

| Severity | CVSS | VRT | Meaning | Typical examples |
|----------|------|-----|---------|------------------|
| **Critical** | 9.0–10.0 | P1 | Immediate, severe compromise; often unauth. | Unauth RCE, unauth SQLi with full DB, auth bypass to admin, SSRF→full cloud takeover, hardcoded prod admin creds. |
| **High** | 7.0–8.9 | P2 | Serious compromise, may need low privilege/one condition. | Authed RCE, stored XSS hitting admins, IDOR modifying others' data, SSRF to metadata creds, privilege escalation, insecure deserialization. |
| **Medium** | 4.0–6.9 | P3 | Real flaw, needs conditions or limited impact. | Reflected XSS, CSRF on sensitive action, IDOR read-only PII, verbose errors leaking data, weak TLS config, missing rate-limit control. |
| **Low** | 0.1–3.9 | P4 | Minor issue, hard to exploit or low impact. | Missing security headers, autocomplete on/off, low-risk info disclosure, clickjacking on non-sensitive page. |
| **Info** | 0.0 | P5 | No direct security impact; hygiene/best-practice. | Version banners, missing best-practice headers with no impact, stack traces without sensitive data. |

VRT: Bugcrowd's Vulnerability Rating Taxonomy — baseline technical priority
P1 Critical → P5 Informational. Many programs mark lone missing-header/best-practice
items P5 (non-rewardable). Use VRT to align expectations, CVSS to score.

### OWASP Risk Rating (when a CVSS number isn't the right lens)
`Risk = Likelihood × Impact`. Rate **Likelihood** from threat-agent factors (skill,
motive, opportunity, population) + vulnerability factors (ease of discovery, ease of
exploit, awareness, intrusion detection), and **Impact** from technical (loss of
confidentiality/integrity/availability/accountability) + business (financial,
reputation, non-compliance, privacy) factors, each 0–9. Combine via the
Likelihood×Impact matrix (LOW/MEDIUM/HIGH each) → overall severity. Useful for
business-context findings and logic flaws where CVSS fits poorly.

---

## CWE mapping (common pentest findings → root-cause CWE)

Always cite the **root cause** CWE, not just the symptom.

| Finding class | CWE |
|---------------|-----|
| SQL injection | CWE-89 |
| Command injection | CWE-78 |
| Cross-site scripting (XSS) | CWE-79 |
| Server-side template injection | CWE-1336 (or CWE-94 code injection) |
| XXE | CWE-611 |
| Insecure deserialization | CWE-502 |
| SSRF | CWE-918 |
| Path traversal / LFI | CWE-22 |
| Unrestricted file upload | CWE-434 |
| IDOR / BOLA (object-level authz) | CWE-639 / CWE-284 |
| Missing function-level authz (BFLA) | CWE-862 |
| Broken authentication | CWE-287 |
| Session fixation | CWE-384 |
| CSRF | CWE-352 |
| Open redirect | CWE-601 |
| CORS misconfiguration | CWE-942 |
| Hardcoded / exposed credentials | CWE-798 / CWE-522 |
| Sensitive data exposure / cleartext | CWE-200 / CWE-319 |
| Improper certificate/TLS validation | CWE-295 |
| Mass assignment | CWE-915 |
| Race condition | CWE-362 |
| Security misconfiguration | CWE-16 |
| Missing security headers (e.g. HSTS) | CWE-693 (protection mechanism failure) |
| Info disclosure via error/stack trace | CWE-209 |
| Improper access control (general) | CWE-284 |
| Use of vulnerable/outdated component | CWE-1104 |

Cross-reference: OWASP Top 10 2021 (A01 Broken Access Control … A06 Vulnerable
Components), OWASP API Top 10 2023, MITRE ATT&CK where relevant.

---

## Remediation writing — rules

Good remediation is **specific, actionable, and verifiable**. State the fix, then
hardening/defense-in-depth, then a reference. Avoid "sanitize input" hand-waving —
say *how*. Prefer platform/framework-native controls. For each class below, and for
deeper detail, cross-reference the owning attack skill's remediation notes.

### Per-class remediation guidance

- **SQLi (CWE-89)** — Parameterized queries / prepared statements everywhere; ORM
  with bound params; least-privilege DB account; input allowlisting; WAF as
  defense-in-depth. *See `web-vuln-hunting` → injection.*
- **Command injection (CWE-78)** — Avoid shelling out; use language APIs; if
  unavoidable, pass args as an array (no shell string), allowlist values. *`web-vuln-hunting`, `network-service-exploitation`.*
- **XSS (CWE-79)** — Context-aware output encoding; framework auto-escaping; strict
  CSP; `HttpOnly`/`Secure`/`SameSite` cookies; sanitize rich HTML with a vetted
  library (DOMPurify). *`web-vuln-hunting` → XSS.*
- **SSTI / deserialization (CWE-1336/502)** — Don't feed user input to template
  engines/serializers; use data-only formats (JSON w/ schema); allowlist types;
  sandbox. *`web-vuln-hunting`, `web-cve-exploitation`.*
- **SSRF (CWE-918)** — Allowlist outbound hosts; block link-local/metadata
  (169.254.169.254) & internal ranges; enforce IMDSv2; resolve-then-validate to
  stop DNS rebinding; drop redirects. *`web-vuln-hunting`, `cloud-security-testing`.*
- **IDOR/BOLA & BFLA (CWE-639/862)** — Server-side authorization on *every* object
  and function; check ownership/tenant on each request; use unguessable IDs as
  defense-in-depth (not the control); deny-by-default. *`api-security-testing`, `web-vuln-hunting`.*
- **Broken auth / session (CWE-287/384)** — Strong password policy + breach-list
  check; MFA; rotate session IDs on login; short-lived tokens; secure cookie flags;
  lockout/backoff that resists both brute-force and lockout-DoS. *`web-vuln-hunting`.*
- **CSRF (CWE-352)** — Anti-CSRF tokens (synchronizer/double-submit); `SameSite`
  cookies; re-auth on sensitive actions. *`web-vuln-hunting` → CSRF.*
- **File upload / traversal (CWE-434/22)** — Allowlist extension+MIME+magic bytes;
  store outside webroot; randomize names; canonicalize & confine paths; no
  user-controlled path segments. *`web-vuln-hunting`.*
- **CORS (CWE-942)** — Don't reflect arbitrary Origin; allowlist origins; never
  combine `Access-Control-Allow-Origin: *` with credentials. *`web-vuln-hunting`.*
- **Exposed secrets (CWE-798/522)** — Rotate the leaked secret now; move to a secret
  manager/env; remove from VCS history; scan CI; scope keys least-privilege.
  *`offensive-osint`, `cloud-security-testing`.*
- **TLS / crypto (CWE-295/319/326)** — TLS 1.2+ only, strong ciphers, HSTS; validate
  certs; no cleartext transport; modern hashing (Argon2/bcrypt) for passwords.
- **Missing security headers (CWE-693)** — Add HSTS, CSP, `X-Content-Type-Options:
  nosniff`, `X-Frame-Options`/frame-ancestors, Referrer-Policy. Note realistic (often
  Low/Info) impact.
- **Known CVE / outdated component (CWE-1104)** — Patch/upgrade to fixed version;
  if unpatchable, apply vendor mitigation/virtual patch; inventory dependencies (SCA).
  *`web-cve-exploitation`, `windows-ad-cve-exploitation`, `network-service-exploitation`.*
- **AD-specific findings** — Kerberoasting, delegation, ADCS ESC*, DCSync, coercion:
  remediation (managed service accounts, gMSA, disable RC4, template hardening,
  RBCD/ACL cleanup, LDAP signing/channel binding). *See `active-directory-attack-paths`
  remediation notes.*

---

## SLA / prioritization (KEV/EPSS-informed)

Severity sets the *bar*; threat intelligence sets the *urgency*. Suggested default
SLAs (tune to the client's risk appetite and change process):

| Priority tier | Trigger | Suggested fix SLA |
|---------------|---------|-------------------|
| **Emergency** | In **CISA KEV**, OR Critical+internet-facing+active exploitation | **24–72 hours** (BOD 22-01: by KEV due date for fed) |
| **Urgent** | Critical (9.0+), OR High with **EPSS ≥ 0.5 / ≥90th pct** | **7 days** |
| **High** | High (7.0–8.9) | **14–30 days** |
| **Medium** | Medium (4.0–6.9) | **30–90 days** |
| **Low / Info** | Low / Info | **Next release cycle / risk-accept** |

Escalation rules:
- **KEV membership overrides CVSS** — a Medium base CVSS in KEV is patched now.
- **High EPSS raises urgency** even when CVSS is moderate (exploitation likely soon).
- **Exposure & asset value** move priority via CVSS Environmental metrics — an
  internet-facing crown-jewel outranks an internal low-value host at the same base.
- **Automatable / enumerable** findings (whole-table IDOR, credential stuffing
  surface) deserve priority above their base band.
- **Novel pentest findings** have no CVE → no EPSS/KEV; prioritize by CVSS +
  observed exploitability + asset criticality (OWASP Risk Rating).

Present the roadmap as *quick-wins* (low-effort, high-impact) vs *strategic*
(systemic fixes) so the client can act immediately and plan the rest.
