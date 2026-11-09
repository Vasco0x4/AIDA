---
name: compliance-mapping
description: "Map authorized pentest/audit findings to compliance and regulatory frameworks so reports speak to auditors, GRC, and management. Covers PCI DSS v4.0/4.0.1, HIPAA Security Rule (45 CFR 164.308-312), SOC 2 Trust Services Criteria (CC1-CC9 + Availability/Confidentiality/Processing Integrity/Privacy), ISO/IEC 27001:2022 Annex A (93 controls, 4 themes), NIST CSF 2.0 (Govern/Identify/Protect/Detect/Respond/Recover) and SP 800-53 Rev.5 control families, GDPR (Arts. 32/33/34), and CIS Controls v8.1 (18 controls, IG1-IG3). Provides per-framework overview + pentest relevance, a mapping methodology (finding -> violated control in each framework), a practical common-finding -> control crosswalk (weak crypto, missing MFA, IDOR/PII exposure, unpatched CVE, missing logging, etc.), framework-specific pentest requirements (PCI DSS Req 11.4 scope/segmentation testing), and how to phrase findings + what evidence auditors expect. A reporting/mapping aid, not a compliance attestation. Use to add a Compliance Mapping column to findings, translate a finding into control language, answer 'which PCI/ISO/SOC 2 control does this break', or scope compliance-driven pentests."
version: 1.0.0
triggers:
  - compliance mapping
  - control mapping
  - map finding to control
  - pci dss
  - pci 11.4
  - hipaa
  - hipaa security rule
  - soc 2
  - trust services criteria
  - iso 27001
  - iso 27001 annex a
  - nist csf
  - nist csf 2.0
  - nist 800-53
  - gdpr
  - gdpr article 32
  - breach notification
  - cis controls
  - audit report
  - regulatory
  - control crosswalk
  - compliance pentest
---

# Compliance & Regulatory Mapping

Auditors, GRC teams, and executives do not act on CWE numbers or CVSS vectors —
they act on **control failures** against a framework they are already obligated
to. This skill turns a technical finding ("stored XSS in the support portal",
"TLS 1.0 accepted", "no MFA on the VPN") into the language of the standard:
*which requirement it violates, why an auditor cares, and what evidence closes
the gap.* The mapping is the bridge between the pentest report and the compliance
program.

> This skill covers the **mapping layer**. Produce the actual report with
> `security-reporting` (structure, severity, CVSS, remediation) and structure the
> engagement with `pentest-methodology`. A compliance mapping is a *column added
> to a finding*, not a replacement for the finding itself.

## ⚠️ Safety / ethics (inherits `safe-testing-doctrine`)

- This is a **reporting and mapping aid**, not active testing — all `safe-testing-doctrine`
  limits still apply to any testing that produced the findings.
- **Do not overstate compliance status.** A pentest samples; it does not certify.
  A clean finding on one control is *not* "PCI compliant" — only a QSA/RoC,
  ISO certification body, or CPA firm (SOC 2) can attest. Write "this finding
  maps to / would be assessed against PCI DSS Req X.Y", never "you are/aren't
  compliant". Only a licensed assessor issues an attestation.
- Mapping supports the deliverable produced via `security-reporting`; it does not
  produce an audit opinion, a Report on Compliance (RoC), or a SOC 2 report.
- Frameworks and requirement numbers change (PCI DSS 4.0 -> 4.0.1; ISO 2013 ->
  2022; CSF 1.1 -> 2.0). Confirm the version in scope with the client and cite it.
  See `references/sources.md`.

## How to use this skill

1. **Confirm which framework(s) the client answers to** — from the SOW/scope.
   A payments company: PCI DSS. US healthcare/PHI: HIPAA. SaaS selling to
   enterprise: SOC 2 and/or ISO 27001. EU personal data: GDPR. US federal /
   general baseline: NIST CSF + 800-53. Broad hygiene baseline: CIS Controls.
   Most clients answer to **several at once** — map to each in scope.
2. **For each finding, identify the control category it breaks** (access control,
   crypto, logging, patching, config, etc.) — see the crosswalk.
3. **Look up the specific control ID** in each in-scope framework from
   `references/finding-to-control-crosswalk.md`.
4. **Add a "Compliance Mapping" row/column** to the finding in the report (format
   below), and reference it in the executive summary for management.
5. **For compliance-driven scoping** (e.g. a PCI 11.4 pentest), use
   `references/pentest-requirements-by-framework.md` to make sure the test itself
   satisfies the standard's requirements (scope, frequency, segmentation, tester
   independence, retest).

## The frameworks at a glance (index)

| Framework | What it is / who needs it | Pentest hook | File |
|---|---|---|---|
| **PCI DSS v4.0.1** | Card-brand contractual standard; anyone storing/processing/transmitting cardholder data | Req **11.4** (internal+external pentest, segmentation test), 6.2.4 app vulns, 11.3 vuln scans | `references/frameworks-overview.md` |
| **HIPAA Security Rule** | US federal law; covered entities & business associates handling ePHI (45 CFR 164.308-312) | §164.308(a)(1)(ii)(A) risk analysis, §164.308(a)(8) evaluation | `references/frameworks-overview.md` |
| **SOC 2 (TSC)** | AICPA attestation for service orgs; SaaS/cloud selling to enterprise | CC4.1 monitoring, CC7.1 vuln detection, CC7.x incident response | `references/frameworks-overview.md` |
| **ISO/IEC 27001:2022** | International ISMS certification; global enterprise/B2B | Annex A **8.8** technical vuln mgmt, A.8.29 security testing in dev | `references/frameworks-overview.md` |
| **NIST CSF 2.0** | Voluntary US framework; org-wide risk posture (6 functions) | ID.RA (risk assessment), PR.PS, DE.CM continuous monitoring | `references/frameworks-overview.md` |
| **NIST SP 800-53 Rev.5** | US federal control catalog (FISMA/FedRAMP); 20 families | **CA-8** penetration testing, RA-5 vuln scanning | `references/frameworks-overview.md` |
| **GDPR** | EU regulation; anyone processing EU personal data | Art. **32** security of processing; Arts. 33/34 breach notification | `references/frameworks-overview.md` |
| **CIS Controls v8.1** | Prioritized control set / hygiene baseline; maps to the rest | Control **18** penetration testing; Control 7 vuln mgmt | `references/frameworks-overview.md` |

## Mapping methodology (the core idea)

A finding violates a **control**, and most frameworks have an equivalent control
for the same weakness — that is why one finding maps to many frameworks at once.
Work from the *class* of weakness, not the exact exploit:

1. Classify the finding into a control domain: **Access control / AuthN & MFA /
   Cryptography / Vulnerability & patch mgmt / Logging & monitoring / Secure
   config / Data protection & privacy / Network segmentation / Change mgmt /
   Secure development**.
2. Each domain has a near-1:1 control in every framework. Example — *missing MFA
   on remote access*:
   - PCI DSS **8.4 / 8.5** (MFA required) and 8.3 (strong auth)
   - HIPAA **§164.312(d)** person/entity authentication
   - SOC 2 **CC6.1 / CC6.6** logical access, boundary protection
   - ISO 27001 Annex A **8.5** secure authentication
   - NIST CSF **PR.AA-03** (authenticate); 800-53 **IA-2(1)/(2)** MFA
   - GDPR **Art. 32(1)** appropriate technical measures
   - CIS Control **6.3 / 6.5** MFA for external & admin access
3. Record the specific IDs per in-scope framework in the finding.

See `references/finding-to-control-crosswalk.md` for the full lookup tables across
weak crypto, IDOR/PII exposure, unpatched CVE, missing logging, SQLi/injection,
default creds, missing encryption in transit/at rest, excessive privilege, and
more.

## Finding write-up format (compliance-aware)

Add this block to each finding produced via `security-reporting`:

```
Finding: <title>   Severity: <High>   CVSS: <vector/score>   CWE: <CWE-id>

Compliance Mapping:
  PCI DSS v4.0.1 : Req 8.4.2, 8.5.1 (MFA not enforced on CDE remote access)
  HIPAA          : 45 CFR 164.312(d) (person/entity authentication)
  SOC 2 (TSC)    : CC6.1, CC6.6 (logical access / boundary)
  ISO 27001:2022 : A.8.5 (secure authentication)
  NIST CSF 2.0   : PR.AA-03 ; 800-53 IA-2(1)
  GDPR           : Art. 32(1)(b) (ongoing confidentiality)
  CIS v8.1       : 6.3, 6.5

Auditor evidence to close: MFA enforcement config/screenshot for all remote &
admin access; policy; sample of enrolled accounts; retest confirming enforcement.
```

## Phrasing for compliance & management audiences

- **Lead with the obligation, not the exploit.** "Remote access to the cardholder
  data environment is reachable with a password alone — PCI DSS Req 8.4/8.5
  requires MFA, so this is a control gap a QSA would flag" beats "we bypassed the
  login".
- **Map severity to the standard's own language** where it exists (PCI's pass/fail
  per requirement; ISO's nonconformity major/minor; SOC 2 exception/deviation).
- **Give the auditor the evidence they will ask for** (config export, policy,
  ticket, log sample, retest) — see the "evidence" column in the crosswalk and
  `references/pentest-requirements-by-framework.md`.
- **For the executive summary**, aggregate: "5 findings map to PCI DSS Req 6
  (secure development) and would be assessment failures; 3 map to GDPR Art. 32
  and raise breach-notification exposure under Arts. 33/34." Ties technical risk
  to money, contracts, and regulators.
- **Never write "compliant/non-compliant" as a verdict** — write "maps to /
  would be assessed against / represents a gap relative to" the control.

## References

- `references/frameworks-overview.md` — each framework: what it is, who needs it,
  structure, version, and specific pentest relevance/hooks.
- `references/finding-to-control-crosswalk.md` — the practical common-finding ->
  control lookup tables across PCI / HIPAA / SOC 2 / ISO / NIST CSF+800-53 /
  GDPR / CIS, plus the evidence auditors expect.
- `references/pentest-requirements-by-framework.md` — framework-specific pentest
  mandates: PCI DSS 11.4 scope/segmentation/frequency, ISO A.8.8/A.8.29,
  SOC 2 CC7.1, 800-53 CA-8, GDPR Art. 32, CIS Control 18.
- `references/sources.md` — public standards and URLs consulted (with versions).

Cross-references: `security-reporting` (build the report, score, remediate),
`pentest-methodology` (engagement phases and standards map).
