# Common Finding → Control Crosswalk

Practical lookup: for each common pentest finding class, the control(s) it maps
to in each framework, plus the **evidence an auditor expects** to close it. IDs
are indicative and abbreviated — always confirm the requirement wording against
the current standard version (`sources.md`) and adjust for the client's scope.
Cross-reference `security-reporting` for the finding write-up and severity.

**Abbreviations:** PCI = PCI DSS v4.0.1 requirement; HIPAA = 45 CFR 164 section;
SOC 2 = TSC Common Criteria; ISO = ISO/IEC 27001:2022 Annex A; CSF = NIST CSF 2.0
Subcategory; 800-53 = SP 800-53 Rev.5 control; GDPR = Article; CIS = CIS v8.1
Control/Safeguard.

---

## Quick master crosswalk (one row per finding class)

| Finding class | PCI DSS | HIPAA | SOC 2 | ISO 27001:2022 | NIST CSF / 800-53 | GDPR | CIS v8.1 |
|---|---|---|---|---|---|---|---|
| **Missing/weak MFA** on remote/admin | 8.4, 8.5 | 164.312(d) | CC6.1, CC6.6 | A.8.5 | PR.AA-03 / IA-2(1)(2) | Art.32(1) | 6.3, 6.5 |
| **Weak/deprecated crypto** (TLS1.0/1.1, RC4, weak cipher) | 4.2.1, 2.2.7 | 164.312(e)(1) | CC6.7 | A.8.24 | PR.DS-02 / SC-8, SC-13 | Art.32(1)(a) | 3.10 |
| **No encryption at rest** (PAN/PHI/PII stored plaintext) | 3.5.1 | 164.312(a)(2)(iv) | CC6.1, C1.1 | A.8.24, A.8.12 | PR.DS-01 / SC-28 | Art.32(1)(a) | 3.11 |
| **IDOR / BOLA / broken access control** exposing data | 7.2, 6.2.4 | 164.312(a)(1) | CC6.1, CC6.3 | A.8.3, A.5.15 | PR.AA-05 / AC-3, AC-6 | Art.32, Art.5(1)(f) | 6.8, 16.x |
| **PII/PHI/PAN exposure or over-collection** | 3.2, 3.3 | 164.502, 164.312(a) | C1.1, P-series | A.5.34, A.8.12 | PR.DS / SC-28 | Art.5, 25, 32 | 3.1, 3.3 |
| **Unpatched CVE / missing patch** | 6.3.1, 6.3.3 | 164.308(a)(1) | CC7.1 | A.8.8 | ID.RA-01 / RA-5, SI-2 | Art.32(1)(d) | 7.3, 7.4 |
| **Injection** (SQLi/cmd/SSTI) | 6.2.4 | 164.312(c)(1) | CC7.1, CC8.1 | A.8.28 | PR.PS / SI-10, SA-11 | Art.32 | 16.11 |
| **XSS / output handling** | 6.2.4 | 164.312(c)(1) | CC7.1 | A.8.28 | PR.PS / SI-10 | Art.32 | 16.11 |
| **Missing/insufficient logging & monitoring** | 10.2, 10.3 | 164.312(b), 164.308(a)(1)(ii)(D) | CC7.2, CC7.3 | A.8.15, A.8.16 | DE.CM / AU-2, AU-6, SI-4 | Art.32, 33 | 8.2, 8.5, 13.x |
| **Default / weak credentials** | 2.2.2, 8.3.1 | 164.312(a)(2)(i), 164.312(d) | CC6.1 | A.8.5, A.5.17 | PR.AA / IA-5 | Art.32 | 4.7, 5.2 |
| **Insecure/default configuration** (hardening gap) | 2.2 | 164.308(a)(1) | CC6.8, CC7.1 | A.8.9 | PR.PS-01 / CM-6, CM-7 | Art.32 | 4.1, 4.2 |
| **Excessive privilege / no least-privilege** | 7.2, 7.3 | 164.308(a)(4), 164.312(a)(1) | CC6.1, CC6.3 | A.8.2, A.5.15 | PR.AA-05 / AC-6 | Art.32, 25 | 5.4, 6.8 |
| **Cleartext transmission** (HTTP, FTP, telnet) | 4.2.1 | 164.312(e)(1) | CC6.7 | A.8.24, A.8.20 | PR.DS-02 / SC-8 | Art.32(1)(a) | 3.10 |
| **Insecure deserialization / RCE** | 6.2.4 | 164.312(c)(1) | CC7.1 | A.8.28 | PR.PS / SI-10, SA-11 | Art.32 | 16.11 |
| **Exposed sensitive service / segmentation gap** | 1.3, 1.4, 11.4.5 | 164.312(a)(1), 164.310 | CC6.6 | A.8.20, A.8.22 | PR.IR-01 / SC-7 | Art.32 | 12.2, 4.4 |
| **Secrets in code / config / repo** | 6.3, 8.3 | 164.312(a)(2)(i) | CC6.1 | A.8.24, A.5.17 | PR.AA / IA-5 | Art.32 | 3.11, 16.11 |
| **No/weak account lockout & session mgmt** | 8.3.4, 8.2.8 | 164.312(a)(2)(iii) | CC6.1 | A.8.5 | PR.AA / AC-7, AC-12 | Art.32 | 6.x |
| **Missing WAF / public app protection** | 6.4.1, 6.4.2 | 164.312(c) | CC6.6, CC7.1 | A.8.23, A.8.26 | PR.PS / SC-7 | Art.32 | 13.10 |
| **No secure SDLC / untested code** | 6.2.1-6.2.3 | 164.308(a)(1) | CC8.1 | A.8.25, A.8.29 | PR.PS / SA-11, SA-15 | Art.25, 32 | 16.1 |
| **Vuln/pentest program absent** | 11.3, 11.4 | 164.308(a)(1)(ii)(A), (a)(8) | CC4.1, CC7.1 | A.8.8, A.8.29 | ID.RA / CA-8, RA-5 | Art.32(1)(d) | 7.x, 18.x |
| **No incident response capability** | 12.10 | 164.308(a)(6) | CC7.3, CC7.4 | A.5.24-5.28 | RS.MA / IR-4 | Art.33, 34 | 17.x |

---

## Detailed mapping notes by finding class

### Weak/missing MFA
Most frameworks now treat MFA as baseline for remote and privileged access. PCI
4.0 broadened MFA to **all access into the CDE** (8.4.2) not just remote/admin.
Phrase: "MFA is not enforced for [context]; PCI DSS 8.4/8.5 and CIS 6.3/6.5
require it, and an assessor would record this as a control gap."
- **Evidence to close:** MFA enforcement config/screenshots for every in-scope
  access path, IdP policy export, sample of enrolled users, retest confirming a
  password-only login is rejected.

### Weak cryptography (transit & at rest)
Covers deprecated TLS (1.0/1.1), weak ciphers/RC4/3DES, self-signed/expired certs,
weak hashing, and unencrypted storage of sensitive data. PCI 4.2.1 requires strong
cryptography for transmission over open/public networks; 3.5.1 for stored PAN.
- **Evidence:** cipher-suite/TLS scan output showing only strong protocols, key
  management/rotation policy, encryption config for data stores, cert inventory.

### IDOR / BOLA / broken access control (often exposing PII/PHI/PAN)
The highest-signal compliance finding — it usually triggers **three** obligations
at once: access control (PCI 7 / ISO A.8.3 / AC-3), data protection, and (if EU
personal data) **GDPR Art. 32 + breach exposure Arts. 33/34**. For US health data,
add **HIPAA breach notification (§164.400-414)**; for PAN, PCI account-data
requirements. Always name the data type and volume exposed.
- **Evidence:** authz matrix / access-control policy, code or config fix, negative
  test (attacker blocked, legitimate user allowed) at retest, and — if data was
  reachable — the data-classification and breach-assessment records.

### Unpatched CVE / missing patch
Maps to vulnerability & patch management everywhere. PCI 6.3.3 requires critical
patches within one month. Reference EPSS/CISA KEV from `security-reporting` /
`cve-knowledge-base` to justify urgency to the auditor.
- **Evidence:** patch/vuln-management policy with SLAs, scan showing remediation,
  change ticket, and the risk-ranking process (PCI 6.3.1).

### Missing / insufficient logging & monitoring
Often understated but a direct control failure and a **GDPR/breach-detection**
concern (you cannot meet Art. 33's 72-hour clock if you cannot detect the breach).
PCI 10 is prescriptive about what to log and daily review. HIPAA §164.312(b) audit
controls + §164.308(a)(1)(ii)(D) information-system-activity review.
- **Evidence:** log sources & retention config, SIEM/alerting rules, sample of
  reviewed logs / alert tickets, log-review procedure.

### Default / weak credentials & insecure configuration
PCI 2.2 (secure config standards, no vendor defaults) and CIS 4/5 are the direct
hits. Tie to a hardening baseline (CIS Benchmarks) the client can adopt.
- **Evidence:** configuration/hardening standard, config export vs. baseline,
  credential-management policy, retest.

### Data exposure / privacy (PII/PHI over-collection, retention)
Beyond security controls this touches **privacy principles**: GDPR Arts. 5
(minimization, storage limitation), 25 (privacy by design), SOC 2 Privacy (P) and
Confidentiality (C) categories, HIPAA minimum-necessary. Note when data collected
or retained exceeds need.
- **Evidence:** data inventory / RoPA (GDPR Art. 30), retention & minimization
  policy, DPIA where applicable, data-flow diagram.

---

## Framework mapping direction (Rosetta Stone)

Because these frameworks overlap, you can pivot between them:
- **CIS Controls publishes official mappings** to NIST CSF, 800-53, PCI DSS, ISO
  27001, and others — a fast way to translate one control ID to another.
- **NIST CSF 2.0 Informative References** map each Subcategory to 800-53 controls
  and CIS Safeguards.
- **PCI SSC and the Secure Controls Framework (SCF)** publish cross-framework
  mappings.
- When a client answers to several frameworks, map the finding **once to a control
  domain**, then emit the ID for each framework from the master table above —
  don't re-derive per framework.

> Reminder: a mapping shows *which control the finding would be assessed against*.
> It is not an assertion that the client is compliant or non-compliant overall —
> only the relevant assessor (QSA, certification body, CPA firm, OCR) determines
> that. See the safety note in `SKILL.md`.
