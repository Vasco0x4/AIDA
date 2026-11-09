---
name: secure-code-review-sast
description: "Practical white-box audit playbook for manual secure code review + SAST, plus lightweight threat modeling. Covers scoping a review, data-flow/taint thinking (sources -> sanitizers -> sinks), trust boundaries, and prioritizing hot spots (authn/authz, input handling, crypto, secrets, deserialization, SSRF, path traversal, template/XXE); a per-language catalog of dangerous sinks and patterns for JS/TS/Node, Python, Java/Kotlin, PHP, Go, C#/.NET and Ruby (injection, insecure deserialization, weak crypto/randomness, hardcoded secrets, authz gaps, SSTI, XXE); tooling for running and WRITING rules in Semgrep (mode: taint, pattern-sources/pattern-sinks/pattern-sanitizers, --config auto) and CodeQL (isSource/isSink/isAdditionalFlowStep dataflow & taint tracking), plus secret scanning (gitleaks, trufflehog verified findings), dependency SCA and IaC scan cross-referencing; diff/PR review technique; STRIDE threat modeling with data-flow diagrams, trust boundaries and abuse cases mapped to OWASP ASVS controls; and triage of true vs false positive with dev-friendly finding write-ups. Grounded in the OWASP Code Review Guide, OWASP ASVS, OWASP Cheat Sheets, the 2024 CWE Top 25, and Semgrep/CodeQL docs. Use when auditing application source code (white-box), reviewing a PR/diff for security bugs, writing or tuning SAST rules, performing taint/source-to-sink analysis, threat modeling a design, or scanning a repo for secrets."
version: 1.0.0
triggers:
  - secure code review
  - sast
  - static analysis
  - semgrep
  - codeql
  - code audit
  - white-box review
  - taint analysis
  - source to sink
  - dangerous sinks
  - dataflow analysis
  - threat modeling
  - stride
  - data flow diagram
  - abuse cases
  - cwe top 25
  - secret scanning
  - gitleaks
  - trufflehog
  - source code security
  - insecure deserialization
  - hardcoded secrets
  - pr security review
  - diff review
  - dependency SCA
  - false positive triage
---

# Secure Code Review + SAST (Authorized White-Box Audit)

A practical playbook for auditing application **source code you are authorized to
review**: manual review technique, taint/data-flow reasoning, SAST tooling
(Semgrep + CodeQL), secret & dependency scanning, lightweight STRIDE threat
modeling, and dev-friendly triage. Optimized for security audits, secure-SDLC
reviews, and in-scope PR/diff reviews.

## ⚠️ Safety / ethics — read first

This skill inherits **`safe-testing-doctrine`**. Secure code review is
**analysis, not exploitation** — it is inherently low-risk (you read code, run
read-only scanners, and write findings). But the material is sensitive, so:

- **Authorized code only.** Review source you own or have written authorization
  to audit (engagement scope, employment, or an in-scope program). Respect the
  **NDA and scope** — do not pull in adjacent repos or private submodules that
  the authorization does not cover.
- **Treat source and secrets as confidential.** Source code, credentials, keys,
  and internal architecture you discover are the client's. **No exfiltration** —
  do not paste proprietary code or discovered secrets into third-party services,
  public gists, or SAST SaaS that the client has not approved. Prefer local /
  self-hosted tooling (`semgrep` CLI, CodeQL CLI, `gitleaks`, `trufflehog`) when
  the client has not sanctioned a cloud backend.
- **A discovered secret is a live credential.** If you find a hardcoded key/token,
  do **not** use it to access systems — report it, and recommend rotation. Using
  it would cross from review into unauthorized access.
- **Do not run untrusted code.** SAST is static — you are reading, not executing
  the target. If you must run a tool that *builds* the target (CodeQL DB build),
  do it in an isolated environment.
- Findings and evidence handling follow `safe-testing-doctrine` (minimal proof,
  redact secrets in reports, secure storage, cleanup).

If scope or authorization is unclear, STOP and confirm before reading the code.

## The review loop (at a glance)

```
Scope & context  ->  Threat model (STRIDE + DFD)  ->  Automated pass (SAST/secrets/SCA)
       ->  Manual pass (taint: sources -> sanitizers -> sinks at trust boundaries)
       ->  Triage (TP vs FP, exploitability)  ->  Dev-friendly findings (CWE + ASVS + fix)
```

- **Combine, don't choose.** SAST finds breadth fast and cheaply but is noisy and
  misses logic/authz bugs; manual review finds the deep and business-logic bugs
  but is slow. Run SAST first to map hot spots, then spend human time where it
  pays: **authn/authz, business logic, crypto, and trust boundaries**.
- **Think in data flow.** A bug exists when **untrusted input (source)** reaches a
  **dangerous operation (sink)** without an adequate **sanitizer** in between.
  Everything below is a way to find those three things faster.

## Prioritize hot spots (where bugs cluster)

Spend your manual budget here first (2024 CWE Top 25 leaders in parentheses):

1. **Input handling & injection** — SQL/NoSQL, OS command, LDAP, SSTI, XXE
   (CWE-79 XSS #1, CWE-89 SQLi #3, CWE-77/78 command injection, CWE-94 code inj).
2. **AuthN / AuthZ** — missing/incorrect access checks, IDOR/BOLA, privilege
   management (CWE-862 Missing Authorization, CWE-863 Incorrect Authorization,
   CWE-269 Improper Privilege Management). SAST is weak here — read it by hand.
3. **Secrets & config** — hardcoded credentials/keys, secrets in history, weak
   default config (CWE-798 Use of Hard-coded Credentials).
4. **Crypto & randomness** — weak/obsolete algorithms, ECB, static IV/salt,
   `Math.random()` for tokens, disabled TLS verification (CWE-327, CWE-338).
5. **Deserialization & parsers** — untrusted deserialization, XXE-prone XML
   parsers, unsafe YAML (CWE-502). See sibling `deserialization-attacks`.
6. **SSRF / path traversal / file handling** — user-controlled URLs, path
   concatenation, unrestricted upload (CWE-918 SSRF, CWE-22 path traversal,
   CWE-434 unrestricted upload).
7. **Resource / info exposure** — verbose errors, sensitive data in logs
   (CWE-200), uncontrolled resource consumption (CWE-400).

## Index

| # | Reference | Read it when you need... |
|---|-----------|--------------------------|
| 1 | `references/methodology-and-threat-modeling.md` | How to scope a review, do source->sink taint reasoning, map trust boundaries, review a PR/diff, combine SAST+manual, run STRIDE + data-flow diagrams + abuse cases, and map to ASVS controls. |
| 2 | `references/dangerous-sinks-by-language.md` | Per-language sink tables and grep patterns (JS/TS/Node, Python, Java/Kotlin, PHP, Go, C#/.NET, Ruby): injection, deserialization, SSRF, path traversal, weak crypto/randomness, hardcoded secrets, SSTI, XXE — with the safe alternative for each. |
| 3 | `references/tooling-semgrep-codeql.md` | Running & writing SAST rules: Semgrep (`--config auto`, `mode: taint`, pattern-sources/sinks/sanitizers, custom rules), CodeQL (dataflow/taint tracking, isSource/isSink), secret scanning (gitleaks/trufflehog), dependency SCA, IaC scan cross-ref, and CI wiring. |
| 4 | `references/sources.md` | Public provenance — OWASP Code Review Guide, ASVS, Cheat Sheets, CWE Top 25, Semgrep/CodeQL docs, threat modeling, gitleaks/trufflehog. |

## Triage in one paragraph

For every candidate finding ask: **(1) Is the source actually attacker-controlled?**
(trace it back — config/const/internal is not a source). **(2) Is there a real
sanitizer on the path?** (parameterized query, allow-list, encoder, framework
auto-escaping). **(3) Is the sink reachable and exploitable?** (dead code, feature
flags, auth in front). If all three hold, it is a true positive — write it up with
a concrete data-flow path, CWE, ASVS requirement, severity, and a **copy-pasteable
fix**, not just "sanitize input." If any fails, it's a false positive or lower
severity — say why, and suppress the rule inline (`// nosemgrep: rule-id`) with a
comment so the next reviewer isn't re-triaging it.

## Cross-references

- **`web-vuln-hunting`** — the black-box/exploit view of the same bug classes
  (SQLi/XSS/SSRF/IDOR/SSTI). Use it to confirm exploitability of a code finding.
- **`deserialization-attacks`** — deep dive on insecure deserialization gadget
  chains across languages; pairs with the deserialization sinks here.
- **`vulnerability-research-zeroday`** — variant analysis, patch diffing (n-day ->
  variant), and using CodeQL/Semgrep to find siblings of a known bug.
- **`security-reporting`** — CVSS/EPSS scoring, CWE mapping, and the finding /
  report templates to deliver these results.
