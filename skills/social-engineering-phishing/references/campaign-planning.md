# Campaign Planning — Authorization, Pretext, Infrastructure, GoPhish

> Do not read this as a "how to phish" manual. It is a controlled procedure for a
> **contracted, explicitly-authorized** awareness assessment against a client's own
> in-scope employees. Every step assumes the SKILL.md ⚠️ Safety section is satisfied.
> If SE is not separately in writing, stop here.

---

## 1. Pre-engagement: authorization & scoping (the gate)

`safe-testing-doctrine` forbids social engineering by default. Before any planning,
confirm a **separate, SE-specific written authorization** exists and pin down scope.
NIST SP 800-115 places SE in the *planning* phase and stresses it must be a *learning
tool, not a punitive measure*.

### Authorization checklist (all must be true)

- [ ] **SE named explicitly** in a signed SOW / RoE rider / authorization letter —
      not implied by a general pentest scope.
- [ ] **Signatory has authority** to consent on the organization's behalf.
- [ ] **Techniques enumerated**: email phishing? spear-phishing? vishing? smishing?
      physical pretext? Only what is listed is permitted.
- [ ] **Target scope defined**: which departments/roles/individuals are in scope, and
      the **explicit exclusions** (opted-out individuals, VIPs, protected roles,
      employees on leave, high-risk teams like clinicians on shift).
- [ ] **No-harm rules written down**: no financial loss, no reusable real credentials,
      forbidden pretext themes listed, immediate awareness redirect required.
- [ ] **Testing window** + any blackout periods (month-end close, incidents, layoffs).
- [ ] **HR + Legal informed/approving**; **data-protection basis** established (GDPR:
      typically *legitimate interest* with general transparency, not per-employee
      consent); **works council / employee reps / union** consulted where legally
      required (e.g., DE Betriebsrat).
- [ ] **Data-handling terms**: what is captured, how minimized/redacted, where stored,
      retention, and a deletion date.
- [ ] **Safe-word / abort procedure** and named emergency contacts (client SOC, sponsor).
- [ ] **Blue-team coordination decided**: is the SOC informed (announced) or is this a
      controlled unannounced test with a small witting group? Even "unannounced" tests
      need a witting sponsor and an abort path.

If any box is unchecked → **STOP and escalate to the sponsor.** Never "just try it."

### Data handling of anything captured

- Capture the **minimum** that proves the learning point — ideally *the fact that a
  submission occurred*, not the secret.
- **Never** store, reuse, replay, validate, or transmit real passwords or session
  tokens. If a field is unavoidably captured, redact/truncate/hash immediately.
- Store evidence encrypted, access-limited, and delete on the agreed date. Record the
  deletion in the report's cleanup section (`security-reporting`).

---

## 2. Define learning objectives first

Design the campaign around what the client wants to *learn and improve*, not around
"how many can we catch." Typical objectives:

- Baseline susceptibility to a generic credential-harvest lure.
- Whether employees **report** suspicious mail (the metric that actually matters).
- Whether a specific control catches it (mail filtering, MFA prompt, URL rewriting).
- Resilience of a specific high-risk group to a *plausible, workplace-relevant* pretext.

State the objective, the success metric (favor **report rate**), and the difficulty
tier (obvious → subtle) in the plan.

---

## 3. Pretext development (ethical by construction)

A pretext is the plausible story that makes the message believable. MITRE ATT&CK
T1566 sub-techniques frame the delivery: `.001` attachment, `.002` link, `.003` via a
third-party service.

**Allowed, workplace-relevant themes** (plausible, low-harm):
- Routine IT/SaaS notices (password expiry for a *simulation-only* portal, storage
  quota, a shared document on an internal-looking system).
- Benign operational notices (parking, cafeteria, an all-hands survey, a policy
  acknowledgment) — kept generic and non-coercive.
- Vendor/tool update notices for tools the org plausibly uses (kept generic).

**Forbidden themes** (from the Safety section — never use):
- Layoffs, terminations, disciplinary action, pay/bonus/benefits changes.
- Bereavement, medical/health scares, personal/family emergencies.
- Immigration/legal threats, or anything exploiting fear, trauma, or protected
  characteristics.

Ethical pretext design rules:
- Plausible **without** weaponizing personal life or genuine fear.
- Difficulty calibrated to the objective — you can teach with a *moderately* tricky
  lure without a cruel one.
- Include realistic-but-teachable red flags (lookalike domain, urgency, generic
  greeting) so the debrief has concrete lessons.
- Brand carefully: cloning the client's own internal brand for training is common and
  usually in scope; **impersonating a real external third party** (a named bank,
  a real vendor's live brand) invites legal/trademark problems — confirm with the
  sponsor and prefer client-owned or clearly fictitious branding.

---

## 4. Target list from OSINT (in scope only)

Build the recipient list from **authorized, in-scope** sources. Use `offensive-osint`
for the collection tradecraft (email-format discovery, employee enumeration, job-post
tech-stack signals) — but constrain it hard:

- Only individuals **within the authorized scope**; apply every exclusion.
- Prefer a **client-provided roster** where possible; OSINT-derived lists must be
  reconciled against the in-scope roster and exclusions before use.
- Do not collect or use personal/off-work contact details, personal email, or
  personal phone numbers unless the SOW explicitly authorizes that channel.
- Record provenance for each target so the report can show the list was in-scope.

---

## 5. Infrastructure (isolated, controlled, attributable to you)

Stand up dedicated infrastructure that is clearly *yours* and *disposable*, never
reused client production systems.

### Domains
- Register a dedicated, disposable lookalike/simulation domain for the campaign.
- Keep it attributable to the assessment (internal WHOIS notes, a benign root page
  identifying it as authorized testing infrastructure).
- Note for the report: real AiTM kits often use **newly-registered domains** and
  Let's Encrypt certs — a detection signal you can highlight constructively.

### Mail authentication & deliverability
- Configure **SPF, DKIM, DMARC** on the sending domain so mail is well-formed and
  deliverability is controlled (you want a *controlled* test, not a spam-cannon).
- Coordinate allow-listing with the client only if the objective is to test *human*
  behavior independent of the mail filter; otherwise leave filters in place to also
  measure the control. Decide and document which you are testing.
- **Never** spoof a real external domain in a way that abuses another org's identity.

### TLS
- Serve the landing page over HTTPS (Let's Encrypt is fine) so the simulation behaves
  realistically and browsers don't add confounding warnings.

### Tooling (open-source, purpose-built for authorized simulation)
- **GoPhish** (getgophish.com) — Go-based simulation platform: sending profiles,
  email templates, landing pages, target groups, campaigns, and a tracking dashboard.
  See §6. Well-suited to controlled, measured awareness campaigns.
- **King Phisher** — campaign tool for creating/managing spear-phishing simulations,
  tracking metrics, and (in scope) demonstrating credential exposure.
- **Social-Engineer Toolkit (SET)** by TrustedSec — spear-phishing menu, website
  cloning, and Credential Harvester method for demonstrations. Powerful and blunt;
  use its cloning/harvester features **only** within scope and route submissions to
  your awareness redirect, capturing minimal proof (not reusable secrets).

Keep all infrastructure isolated from client production, logged, and torn down at the
end (record teardown in the report cleanup list).

---

## 6. GoPhish setup (reference workflow)

GoPhish bundles the four building blocks and a dashboard. Configure in this order,
then test end-to-end against **your own seed inboxes** before touching any real target.

1. **Sending Profile** — SMTP host/credentials and the `From` address (the identity
   the recipient appears to receive mail from). Use your dedicated simulation domain.
2. **Email Template** — the message body. Import HTML, use GoPhish template variables
   (e.g., recipient name), and include the tracking link. Keep the pretext within the
   ethical rules above. GoPhish can embed a tracking pixel (open tracking) — decide
   whether open-tracking is in scope for your privacy posture.
3. **Landing Page** — the page shown when a recipient clicks. GoPhish assigns each
   recipient a unique `rid` parameter to attribute the visit. If demonstrating
   credential exposure is in scope, GoPhish can note that a submission occurred and
   then **redirect** — configure "Redirect to" to point at your **awareness page**
   (§ execution-and-reporting). Capture the *fact of submission*, not reusable
   secrets; do not persist real passwords.
4. **Users & Groups** — import the in-scope, exclusion-filtered target list.
5. **Campaign** — bind profile + template + landing page + group, set the launch
   time (and optional send-by schedule to rate-limit waves), and launch. The
   dashboard reports **sent / opened / clicked / submitted** in aggregate.

**Pre-flight test (mandatory):** run the full campaign against a small group of your
own seed accounts first. Verify the awareness redirect fires, that no reusable secret
is stored, that links resolve, and that metrics record correctly. Only then schedule
real waves.

Continue to `references/execution-and-reporting.md` for delivery, metrics, the AiTM
concept, and constructive reporting.
