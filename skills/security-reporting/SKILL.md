---
name: security-reporting
description: "Professional vulnerability reporting, scoring, and remediation writing for authorized pentest/audit deliverables and bug-bounty submissions. Covers the reporting workflow and report structure (title page, executive summary, methodology/scope, findings, severity, remediation, appendices, cleanup list); how to write a clear finding; how to score with CVSS v3.1 and v4.0 (metrics, vectors, qualitative ranges) and prioritize with EPSS + CISA KEV; OWASP Risk Rating; CWE mapping; translating technical risk into business risk; SLA/prioritization guidance; the retest/verification process; and copy-paste report + bug-bounty templates aligned to NIST SP 800-115, PTES, OWASP, and Bugcrowd VRT / HackerOne norms. Use to write a pentest report, score a finding, choose a CVSS vector, write remediation, build an executive summary, or draft a bug-bounty submission."
version: 1.0.0
triggers:
  - write pentest report
  - vulnerability report
  - cvss score
  - cvss v4
  - cvss vector
  - epss
  - cisa kev
  - risk rating
  - remediation
  - executive summary
  - bug bounty report
  - severity
  - retest
  - cwe mapping
  - report template
  - finding writeup
---

# Security Reporting, Scoring & Remediation

The deliverable is the product. Testing finds risk; the report is what the client
pays for, acts on, and keeps. A finding nobody can reproduce, understand, or fix
is worthless no matter how clever the exploit. This skill turns raw findings into
a professional, standards-aligned report or bug-bounty submission.

> Load `safe-testing-doctrine` before any active testing and `pentest-methodology`
> to structure the engagement. This skill covers the **reporting phase**
> (NIST SP 800-115 §5.4; PTES "Reporting"). For per-vuln-class remediation detail,
> cross-reference the attack skills' remediation notes (`web-vuln-hunting`,
> `active-directory-attack-paths`, `api-security-testing`, `cloud-security-testing`,
> `network-service-exploitation`, `*-cve-exploitation`).

## ⚠️ Safety / ethics (inherits `safe-testing-doctrine`)

A report concentrates the most sensitive product of the engagement: working
exploits, credentials, internal architecture, and proof data. Handle accordingly.

- **Treat the report and evidence as sensitive.** Encrypt at rest and in transit
  (PGP / password-protected archive / client secure portal). Limit distribution
  to named recipients on the RoE. Delete raw evidence and the report copy after
  the client accepts it and the retention window expires.
- **No real-user PII in the report.** Redact usernames, emails, tokens, card/SSN
  data, health/financial records. Prove access with the *minimum* — a row count,
  a masked value (`4111 **** **** 1111`), a screenshot with PII boxed out — never
  a full dump. If you had to touch real data to prove impact, say so and redact.
- **Redact your own secrets too.** Mask captured hashes, session tokens, API keys
  and private keys in the body; put anything a fixer truly needs in a separately
  encrypted appendix.
- **Responsible disclosure.** For findings outside a paid engagement (or affecting
  third parties / upstream vendors), follow coordinated disclosure: report
  privately, give a reasonable remediation window, don't publicize until fixed or
  agreed. Respect each program's bug-bounty policy and safe-harbor terms.
- **Accuracy over drama.** Don't inflate severity to look impressive or deflate it
  to close faster. Score honestly with a published vector so anyone can re-derive it.
- **Cleanup is part of the report.** Every artifact you created (files, accounts,
  ACLs, tickets, tasks) is listed in a cleanup section with its removal status.

## Reporting workflow

1. **Collect while you test, not after.** For every finding capture: exact target
   (URL/host/parameter), timestamped request/response, reproduction steps, tool +
   command, screenshots, and the proof artifact. Reproducibility is decided here.
2. **Deduplicate & cluster.** Merge the same root cause across many endpoints into
   one finding with an affected-locations list. Split genuinely different bugs.
3. **Classify.** Assign a CWE (root cause) and, where relevant, OWASP Top 10 / API
   Top 10 / WSTG / MITRE ATT&CK IDs. See `references/severity-and-remediation.md`.
4. **Score.** Compute CVSS (v3.1 and/or v4.0) with a full vector. Layer EPSS +
   CISA KEV + business context for *prioritization*. See `references/cvss.md`.
5. **Write each finding** to the finding template (below and in
   `references/report-template.md`).
6. **Write remediation** — specific, actionable, verifiable. Cross-reference the
   relevant attack skill's remediation note for the class.
7. **Roll up** into an executive summary and a findings-severity table.
8. **Assemble** the full report; add methodology, scope, appendices, cleanup list.
9. **QA pass**: every finding reproducible, every score has a vector, no unredacted
   PII/secrets, severities consistent with the rubric, remediation testable.
10. **Deliver securely**, then schedule the **retest** (below).

## Report structure (pentest / audit deliverable)

Full copy-paste template in `references/report-template.md`. Standard sections:

1. **Title page** — client, assessment type, scope one-liner, testing window,
   author/firm, report version/date, **classification (Confidential)**.
2. **Executive summary** — 1 page, non-technical. What was tested, overall risk
   posture, count by severity, the 3-5 things that matter, business impact, and
   the headline recommendations. A busy executive should be able to stop here.
3. **Methodology & standards** — approach (black/grey/white-box), frameworks
   followed (NIST SP 800-115, PTES, OWASP WSTG/ASVS), tooling classes, scoring
   system used (CVSS v3.1/v4.0 + EPSS/KEV).
4. **Scope** — in-scope targets (domains/IPs/apps/AD/accounts), explicit
   exclusions, testing window, assumptions, and limitations (e.g. WAF, time-boxing,
   creds not provided). State what was NOT covered so absence of findings ≠ safety.
5. **Findings summary** — table: ID, title, severity, CVSS, CWE, status. Optional
   heat map / severity bar. Trend vs. previous test if applicable.
6. **Detailed findings** — one per finding, full template. Ordered by severity.
7. **Remediation roadmap** — prioritized fix plan with SLAs (KEV/EPSS-informed),
   grouped quick-wins vs. strategic fixes; owners if known.
8. **Appendices** — scope detail, tool list, full request/response evidence (PII
   redacted), raw scan output, methodology checklists (WSTG/ASVS coverage),
   glossary, references.
9. **Cleanup list** — every test artifact created and its removal status
   (mandatory per `safe-testing-doctrine`).

## How to write a good finding

A finding must let a stranger (a) understand the risk, (b) reproduce it, and
(c) fix and verify it. Use the finding template for every one:

| Field | Guidance |
|-------|----------|
| **ID** | Stable ref, e.g. `AIDA-2026-001`. |
| **Title** | Vuln class + location + impact. "Unauthenticated SQL injection in `/api/search` allows full DB read." Not "SQLi found." |
| **Severity** | Qualitative rating (Critical…Info) consistent with the rubric. |
| **CVSS** | Version, base score, **full vector string**, and any threat/env adjustment. |
| **CWE / classification** | CWE-ID + OWASP/WSTG/ATT&CK IDs. |
| **EPSS / KEV** | For known CVEs: EPSS probability+percentile; KEV listed? (raises priority). |
| **Affected assets** | Exact URLs/hosts/params/accounts. Cluster same root cause. |
| **Description** | What the flaw is and why it exists (root cause), plainly. |
| **Impact** | Concrete, business-relevant consequence — see risk translation below. |
| **Steps to reproduce** | Numbered, exact. Include request/response, tool+command. A reviewer follows them verbatim. |
| **Proof of concept** | Screenshot/log/benign marker. Redact PII/secrets. Least-intrusive proof only. |
| **Remediation** | Specific, actionable, verifiable fix + hardening. Cross-ref the class's remediation note. |
| **References** | CWE, OWASP, vendor advisory, CVE. |

**Writing rules:** lead with impact; one root cause per finding; be specific
(name the parameter, not "a field"); make steps copy-paste runnable; separate fact
(what you observed) from inference (what it implies); never overstate what you
proved. Include a negative control where useful (works as attacker, blocked as
victim) to prove access control findings.

## Translating technical risk to business risk

Executives fund fixes for *business* consequences, not CWE numbers. For each
significant finding, answer "so what?" in their terms:

- **Data**: what data is exposed, whose, how much, and the regulatory hook
  (GDPR/CCPA/HIPAA/PCI-DSS). "Read access to the full customer table (~1.2M
  records incl. emails and hashed passwords)" → breach-notification + fines.
- **Money**: fraud, theft, chargebacks, downtime cost, fix/IR cost.
- **Operations**: could it halt a business process? (Note: don't *test* the halt —
  reason about it. No DoS.)
- **Trust / reputation**: customer-facing breach, public disclosure exposure.
- **Compliance**: which control/standard fails (PCI-DSS req, SOC 2, ISO 27001,
  ASVS level). Ties the finding to an obligation the client already has.
- **Likelihood in plain terms**: "unauthenticated, single request, no special
  tooling, and this CVE is in CISA KEV / high EPSS" → treat as imminent.

Rule of thumb: **Risk = Likelihood × Impact.** CVSS gives a technical baseline;
EPSS/KEV inform likelihood; the *business* impact and asset value adjust it up or
down via the CVSS Environmental metrics or OWASP Risk Rating. Use the client's own
crown-jewel/asset-criticality ratings when provided.

## Severity & prioritization (summary)

- Assign qualitative severity from the CVSS score band, then sanity-check against
  the rubric and Bugcrowd VRT / real-world exploitability. See
  `references/severity-and-remediation.md`.
- **Prioritize** (order of fixing) ≠ **severity** (magnitude). A Medium CVSS that
  is in **CISA KEV** or has **high EPSS** and sits on an internet-facing crown-jewel
  can outrank a theoretical High. Remediation SLAs and the KEV/EPSS decision matrix
  are in `references/severity-and-remediation.md`.

## Retest / verification process

1. **Agree scope**: which findings, the fix window, the retest date (in the SOW).
2. **Re-run the exact original reproduction steps** per finding — same request,
   same account, same conditions.
3. **Classify each**: `Remediated` (fix verified, cannot reproduce), `Partially
   remediated` (mitigated/reduced but residual risk — re-score), `Not remediated`
   (still reproducible), `Risk accepted` (client sign-off, documented),
   `Cannot verify` (env/access changed — state why).
4. **Check for regressions & bypasses** — confirm the fix isn't defeatable with a
   trivial variant (e.g. filter added but encoding bypass works), and that it
   didn't open a new issue.
5. **Issue a retest report / addendum**: original vs. current status table, updated
   residual-risk posture, evidence of closure. Update severities where the fix
   changed real risk. Re-confirm cleanup completed.

## References

- `references/cvss.md` — CVSS v3.1 & v4.0 base metrics, example vectors per common
  finding, qualitative ranges, EPSS + CISA KEV prioritization, worked examples.
- `references/report-template.md` — full pentest report template, concise
  bug-bounty submission template, finding template with all fields.
- `references/severity-and-remediation.md` — severity rubric with examples, CWE
  mapping, per-class remediation guidance, SLA/prioritization via KEV/EPSS.
- `references/sources.md` — public standards and URLs consulted.
