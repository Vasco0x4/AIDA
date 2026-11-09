---
name: social-engineering-phishing
description: "Planning and executing authorized social-engineering / phishing SIMULATIONS as part of a CONTRACTED engagement with a SEPARATE, explicit written authorization (its own SOW / SE-specific rider) — NOT covered by a generic pentest RoE and NOT for real-world malicious phishing. Covers pre-engagement authorization and scoping (which employees, exclusions, no-personal-harm rules, safe-word/abort, legal/HR/works-council, data handling of any captured proof), campaign planning (pretext development, target lists from OSINT, infrastructure — domains/mail/TLS/GoPhish/King Phisher/SET, landing pages, tracking), the AiTM/MFA-phishing concept (evilginx) at an AWARENESS level, controlled delivery and click/submit metrics without harming users, immediate awareness redirect, brief vishing/smishing/physical pretext, and constructive awareness-focused reporting. Grounded in GoPhish docs, SET, King Phisher, OWASP, NIST SP 800-115, and MITRE ATT&CK T1566. Use for phishing simulation, social-engineering assessment, awareness testing, pretext design, GoPhish setup, vishing/smishing planning, or the AiTM concept — on the client's OWN employees, in scope, only."
version: 1.0.0
triggers:
  - phishing simulation
  - social engineering
  - social engineering assessment
  - gophish
  - king phisher
  - social engineer toolkit
  - SET toolkit
  - pretext
  - pretext development
  - awareness testing
  - security awareness campaign
  - simulated phishing
  - spear phishing simulation
  - vishing
  - smishing
  - aitm phishing
  - adversary in the middle
  - evilginx concept
  - MFA phishing awareness
  - credential harvesting test
  - phishing landing page
  - phishing metrics
  - click rate
  - T1566
---

# Social-Engineering & Phishing Simulation (Authorized, Contracted)

Social engineering measures the **human** attack surface. On an authorized
engagement it answers one question constructively: *if a real adversary sent this,
how would our people and our controls respond — and how do we help them do better?*
The product is **measurement and training**, never exploitation, never blame.

Phishing is the most common initial-access vector in real breaches (MITRE ATT&CK
**T1566**, sub-techniques `.001` attachment / `.002` link / `.003` via-service).
Simulating it responsibly lets a client find and close the gap before an attacker
does. Doing it *ir*responsibly harms employees, breaks trust, and can break the law.
This skill is entirely about doing it the first way.

> **Load `safe-testing-doctrine` FIRST.** That doctrine forbids social engineering
> against real users **by default** — it is permitted only when *explicitly and
> separately contracted*. This skill is the controlled procedure for that
> explicitly-contracted case, and it never overrides the doctrine's hard limits.
> Cross-reference `offensive-osint` (target lists / pretext OSINT),
> `pentest-methodology` (engagement phases), and `security-reporting` (deliverable).

---

## ⚠️ Safety, Ethics & Legality — READ BEFORE ANYTHING ELSE

**This section is mandatory and inherits `safe-testing-doctrine`. If any item below
is not satisfied, STOP — do not plan, build infrastructure, or send anything.**

Social engineering is the one activity `safe-testing-doctrine` **forbids by
default**. A generic pentest RoE, a bug-bounty brief, or a verbal "sure, go ahead"
is **NOT** sufficient. Proceed only with a *separate, specific, written*
authorization for social engineering.

### The non-negotiables

1. **Separate explicit written authorization.** SE must be named specifically in
   its own SOW / signed rider / RoE addendum — who authorized it (a signatory with
   authority to consent on the org's behalf), the exact SE techniques permitted
   (email / vishing / smishing / physical), the window, and the sign-off. If SE is
   not *explicitly* in writing, it is **out of scope** — full stop.

2. **Only the client's OWN employees, only in scope.** Simulate solely against the
   contracting organization's own personnel who are named in scope. **NEVER** target
   third parties, customers, partners, suppliers, family members, personal accounts,
   or the general public. Honor every exclusion (individuals, teams, VIPs opted out,
   protected roles).

3. **No real financial loss, no reusable real credentials.** Never move money,
   trigger real payments, alter real accounts, or induce any real financial or legal
   harm. If demonstrating credential exposure is in scope, capture the **minimal
   proof** that a credential *would* have been submitted (e.g., that a submission
   occurred, or a truncated/redacted/hashed token) — **do not store, reuse, test,
   or transmit real passwords or session cookies**. Redact and delete promptly per
   the agreed retention. Prefer capturing *the fact of submission* over the secret
   itself.

4. **No harmful, cruel, or exploitative content.** Forbidden pretext themes:
   layoffs/terminations, bonuses/pay/benefits cuts, disciplinary action, bereavement,
   medical/health scares, personal emergencies, immigration/legal threats, or
   anything exploiting trauma, protected characteristics, or genuine fear. Pretexts
   must be plausible and workplace-relevant without weaponizing an employee's
   personal life.

5. **Immediate awareness moment.** Anyone who clicks/submits is redirected at once
   to a supportive, educational landing page ("this was an authorized simulation,
   here's what to look for, here's how to report real ones") — never a page that
   shames, scores publicly, or dwells on the mistake.

6. **Privacy, HR, legal, works-council alignment.** Confirm the client has handled
   its own obligations: HR and Legal informed/approving, data-protection basis
   established (under GDPR the usual basis is **legitimate interest**, not employee
   consent, with transparency that simulations occur generally), and any **works
   council / employee representative / union** consultation completed where required
   (this is legally mandatory in several EU jurisdictions, e.g. Germany's
   Betriebsrat). No secret individual performance profiling beyond what was agreed.

7. **Safe-word / abort.** Agree a stop procedure and named emergency contacts before
   launch. **Abort on distress:** if the simulation causes disproportionate anxiety,
   operational disruption, real reporting-line overload, or a genuine incident-response
   scramble, pause and coordinate. A single distressed employee escalating outweighs
   any metric.

8. **This is measurement and training — not a gotcha.** Report aggregate patterns
   and control gaps. Do **not** name-and-shame individuals, feed results into
   discipline/performance reviews, or frame findings as employee failure. The failure
   mode you are testing is the *system's*, not the person's.

**Golden rule:** if you would be uncomfortable defending a message, a pretext theme,
a target, or a captured data field to that employee, to HR, and to a regulator — do
not do it. When in doubt, ask the client sponsor and get it in writing.

---

## What this skill covers — index

| # | Reference | Use it when |
|---|-----------|-------------|
| 1 | [references/campaign-planning.md](references/campaign-planning.md) | Getting authorization/scope right, developing an ethical pretext, building target lists from OSINT, standing up infrastructure (domains, mail auth, TLS, GoPhish/King Phisher/SET), and building tracked landing pages |
| 2 | [references/execution-and-reporting.md](references/execution-and-reporting.md) | Controlled delivery, click/submit metrics without harming users, the AiTM/MFA-phishing (evilginx) concept for awareness, the immediate awareness redirect, brief vishing/smishing/physical pretext, and constructive awareness-first reporting |
| 3 | [references/sources.md](references/sources.md) | Public sources cited (GoPhish, SET, King Phisher, evilginx concept, OWASP, NIST SP 800-115, MITRE ATT&CK T1566, responsible-simulation guidance) |

## The engagement flow (at a glance)

1. **Authorize** — separate written SE authorization + scope + exclusions + HR/Legal/
   works-council + data-handling + abort/safe-word. *(No auth → stop.)*
2. **Plan** — pick learning objectives, design an ethical pretext, build the in-scope
   target list (OSINT via `offensive-osint`), and stand up isolated infrastructure.
3. **Build** — email template, tracked landing page, awareness redirect, GoPhish (or
   King Phisher / SET) campaign; test end-to-end against your own seed accounts.
4. **Deliver** — send controlled, rate-limited waves in the window; watch for distress
   and control-side alerts; be ready to abort.
5. **Measure** — sent / opened / clicked / submitted / reported, in aggregate; treat a
   high **report rate** as the real success metric.
6. **Report** — constructive, awareness-first, control-gap-oriented, no blame
   (`security-reporting`), and delete/redact captured data per the agreement.

## Related skills

- `safe-testing-doctrine` — the hard limits; SE is default-forbidden and gated here.
- `offensive-osint` — building the in-scope target list and pretext research.
- `pentest-methodology` — where SE fits in the overall engagement (NIST SP 800-115).
- `security-reporting` — turning results into a constructive, aggregate deliverable.
