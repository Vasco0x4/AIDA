# CVSS Scoring + EPSS + CISA KEV Prioritization

Score with **CVSS** for magnitude, then layer **EPSS** (likelihood of exploitation)
and **CISA KEV** (confirmed in-the-wild exploitation) plus business context for
*prioritization*. Always publish the **full vector string** so anyone can re-derive
the score. Use an official calculator to compute — don't hand-wave the number:
- CVSS v3.1: https://www.first.org/cvss/calculator/3.1
- CVSS v4.0: https://www.first.org/cvss/calculator/4.0

Report both v3.1 and v4.0 during the transition period if the client's tooling
still ingests v3.1; v4.0 is the current standard (published Nov 2023).

## Qualitative severity ranges (identical for v3.1 and v4.0)

| Rating | Score |
|--------|-------|
| None | 0.0 |
| Low | 0.1 – 3.9 |
| Medium | 4.0 – 6.9 |
| High | 7.0 – 8.9 |
| Critical | 9.0 – 10.0 |

---

## CVSS v3.1 base metrics

Vector prefix `CVSS:3.1/`. Base = Exploitability + Scope + Impact.

**Exploitability**
- **AV** Attack Vector: `N` Network / `A` Adjacent / `L` Local / `P` Physical
- **AC** Attack Complexity: `L` Low / `H` High
- **PR** Privileges Required: `N` None / `L` Low / `H` High
- **UI** User Interaction: `N` None / `R` Required

**Scope** — does the vuln let you affect resources beyond its security authority?
- **S** Scope: `U` Unchanged / `C` Changed  (Changed generally raises the score)

**Impact** (to the impacted component)
- **C** Confidentiality: `H` High / `L` Low / `N` None
- **I** Integrity: `H` / `L` / `N`
- **A** Availability: `H` / `L` / `N`

Optional Temporal (E/RL/RC) and Environmental (CR/IR/AR + modified base) groups
refine the base. Example base vector:
`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` → 9.8 Critical.

---

## CVSS v4.0 base metrics

Vector prefix `CVSS:4.0/`. v4.0 replaces the single Scope metric with **two impact
sets** (Vulnerable System + Subsequent System), adds **Attack Requirements (AT)**,
splits User Interaction into Passive/Active, and adds Threat + Supplemental groups.
All base metrics are **mandatory** in the vector string.

**Exploitability (base)**
- **AV** Attack Vector: `N` Network / `A` Adjacent / `L` Local / `P` Physical
- **AC** Attack Complexity: `L` Low / `H` High
- **AT** Attack Requirements: `N` None / `P` Present (needs a specific condition/race/config)
- **PR** Privileges Required: `N` None / `L` Low / `H` High
- **UI** User Interaction: `N` None / `P` Passive / `A` Active

**Vulnerable System impact** — `VC` / `VI` / `VA`: each `H` High / `L` Low / `N` None
**Subsequent System impact** — `SC` / `SI` / `SA`: each `H` / `L` / `N`
(Subsequent = impact to *other* systems/components beyond the vulnerable one —
the v4.0 successor to Scope:Changed.)

**Threat group (optional, `BT`)**
- **E** Exploit Maturity: `X` Not Defined / `A` Attacked / `P` Proof-of-Concept / `U` Unreported

**Environmental group (optional, `BE`)**
- **CR / IR / AR** Requirements: `X` / `H` / `M` / `L`
- Modified base metrics: `MAV MAC MAT MPR MUI MVC MVI MVA MSC MSI MSA`

**Supplemental group (optional — describes, does not change score)**
- **S** Safety: `X` / `N` Negligible / `P` Present
- **AU** Automatable: `X` / `N` No / `Y` Yes
- **R** Recovery: `X` / `A` Automatic / `U` User / `I` Irrecoverable
- **V** Value Density: `X` / `D` Diffuse / `C` Concentrated
- **RE** Vulnerability Response Effort: `X` / `L` / `M` / `H`
- **U** Provider Urgency: `X` / `Clear` / `Green` / `Amber` / `Red`

**Nomenclature** (name the score by which groups you used):
- **CVSS-B** Base only · **CVSS-BT** Base+Threat · **CVSS-BE** Base+Environmental ·
  **CVSS-BTE** Base+Threat+Environmental.

Example v4.0 vector:
`CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N` → Critical.

---

## Example vectors for common findings

Baselines — adjust to the actual case (auth required? data exposed? pivot?).

| Finding | CVSS v3.1 | v3.1 score | CVSS v4.0 (Base) |
|---------|-----------|-----------|------------------|
| **Unauth RCE** (internet-facing) | `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` | 9.8 Critical | `AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H` |
| **Unauth SQLi** (full DB read/write) | `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` | 9.8 Critical | `AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:L/SC:N/SI:N/SA:N` |
| **Stored XSS** (in authed app, hits other users) | `AV:N/AC:L/PR:L/UI:R/S:C/C:L/I:L/A:N` | 5.4 Medium | `AV:N/AC:L/AT:N/PR:L/UI:A/VC:L/VI:L/VA:N/SC:L/SI:L/SA:N` |
| **Reflected XSS** | `AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N` | 6.1 Medium | `AV:N/AC:L/AT:N/PR:N/UI:A/VC:L/VI:L/VA:N/SC:L/SI:N/SA:N` |
| **IDOR / BOLA** (read another user's PII) | `AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N` | 6.5 Medium | `AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N` |
| **IDOR** (modify another user's data) | `AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N` | 8.1 High | `AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` |
| **SSRF** (to cloud metadata → creds) | `AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:L/A:N` | 8.5 High | `AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:L/VA:N/SC:H/SI:L/SA:N` |
| **CSRF** (state-changing, authed) | `AV:N/AC:L/PR:N/UI:R/S:U/C:N/I:H/A:N` | 6.5 Medium | `AV:N/AC:L/AT:N/PR:N/UI:A/VC:N/VI:H/VA:N/SC:N/SI:N/SA:N` |
| **Missing security headers** (HSTS/CSP) | `AV:N/AC:H/PR:N/UI:R/S:U/C:L/I:N/A:N` | 3.1 Low | `AV:N/AC:H/AT:P/PR:N/UI:P/VC:L/VI:N/VA:N/SC:N/SI:N/SA:N` |

Notes:
- **Missing headers** is often Low/Info — score the *realistic* impact, not the
  worst theoretical one. Many programs treat lone missing headers as informational.
- **XSS/CSRF** need `UI` and usually `Scope:Changed` (v3.1) / subsequent impact
  (v4.0) because the victim's browser is a different security authority.
- **SSRF to metadata** is where subsequent-system impact (v4.0) / Scope:Changed
  (v3.1) matters — it pivots beyond the vulnerable app.

---

## EPSS — Exploit Prediction Scoring System

- ML model from FIRST that estimates the **probability (0–1) a CVE will be exploited
  in the wild within the next 30 days**, plus a **percentile** ranking it against
  all CVEs. **Updated daily.** Free via CSV/API/GitHub.
- **CVSS = severity; EPSS = likelihood-now.** They answer different questions; use
  together. A 9.8 CVSS with EPSS 0.02 (2%) may be less urgent *right now* than a
  6.5 CVSS with EPSS 0.90.
- Lookup: `https://api.first.org/data/v1/epss?cve=CVE-2021-44228`
- Common thresholds (calibrate to the org's capacity): **EPSS ≥ 0.10 (or ≥ 0.5)**
  as an escalation trigger; combine with percentile (e.g. ≥ 90th) to catch high-
  relative-risk CVEs. Only applies to **published CVEs** — not to novel app-specific
  findings from a pentest.

## CISA KEV — Known Exploited Vulnerabilities catalog

- Authoritative list of CVEs with **reliable evidence of active exploitation in the
  wild.** Inclusion criteria: (1) assigned CVE ID, (2) reliable evidence of active
  exploitation, (3) a clear remediation action available.
- Under **BOD 22-01**, US federal agencies must remediate KEV entries by the
  catalog's **due date** (often ~2 weeks / vendor-set). Everyone else should treat
  it as a **top-priority fix list** regardless of CVSS.
- **KEV membership overrides EPSS**: if it's in KEV, exploitation is not a
  prediction — it's happening. Prioritize immediately.
- Lookup: https://www.cisa.gov/known-exploited-vulnerabilities-catalog (JSON feed
  available).

## Prioritization decision order

For a known-CVE finding, prioritize by:
1. **In CISA KEV?** → highest priority, patch now (treat as Critical priority
   regardless of base CVSS).
2. **High EPSS** (e.g. ≥ 0.5 or ≥ 90th percentile) → near-term, expect exploitation.
3. **CVSS-BTE / Environmental-adjusted score** on a business-critical, exposed
   asset → schedule per SLA.
4. **Base CVSS alone** → baseline severity when no threat/exposure signal.

For **novel pentest findings** (no CVE), EPSS/KEV don't apply — prioritize by
CVSS + real exploitability observed + asset criticality (Environmental metrics /
OWASP Risk Rating).

---

## Worked example 1 — Log4Shell (CVE-2021-44228) on an internet-facing app

- **CVSS v3.1**: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H` = **10.0 Critical**
  (network, no auth, no interaction, RCE, and Scope:Changed — it breaks out of the
  JVM/app into the host).
- **CVSS v4.0**: `CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H`
  = Critical; add threat `E:A` (attacked) → CVSS-BT.
- **EPSS**: ~0.94+ (very high). **KEV**: **listed.**
- **Verdict**: KEV + max CVSS + max EPSS → **emergency remediation**, top of the
  roadmap, SLA "immediate/24–72h", independent of any other Critical.

## Worked example 2 — Authenticated IDOR exposing other users' invoices

- Attacker with a normal account changes `invoice_id` and reads other tenants'
  invoices (PII + financial). Single request, no special tooling.
- **CVSS v3.1**: `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N` = **6.5 Medium**
  (confidentiality-only, low privilege required).
- **CVSS v4.0**: `CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N`.
- No CVE → EPSS/KEV N/A. **Environmental adjust**: if invoices are crown-jewel PII
  under PCI/GDPR, raise Confidentiality Requirement `CR:H` → modified score climbs
  toward High. Automatable across IDs (enumeration) also argues for prioritizing
  above its base band.
- **Verdict**: base Medium, but **prioritize as High** due to data sensitivity,
  trivial exploitability, and enumerability. Document the reasoning in the finding.
