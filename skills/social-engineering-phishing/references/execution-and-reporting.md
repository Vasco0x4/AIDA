# Execution & Reporting — Delivery, Metrics, AiTM Concept, Constructive Reporting

> Continues `references/campaign-planning.md`. Everything here assumes the SKILL.md
> ⚠️ Safety gate is satisfied and infrastructure was tested end-to-end against your
> own seed accounts. This phase touches real people — proceed with the most care.

---

## 1. Controlled delivery

The goal is a **controlled measurement**, not a blast. Send deliberately.

- **Rate-limit in waves.** Schedule staggered sends (GoPhish send-by scheduling) so
  you don't flood mail infrastructure, don't trigger an availability problem, and can
  **stop between waves** if something goes wrong.
- **Stay inside the window** and honor blackout periods. Never send during an active
  incident, an org crisis, or a period the sponsor flagged.
- **Watch the human signal in real time.** Monitor for distress, help-desk overload,
  a real IR mobilization, or leadership concern. If any appears → invoke the abort
  procedure, notify the sponsor, and hold. (Safety §7: *abort on distress.*)
- **Deconflict with the blue team** per the agreed model. If unannounced, keep the
  witting sponsor informed so a genuine-looking event isn't mistaken for a real breach
  and escalated externally (e.g., to law enforcement or a cyber-insurer).
- **No collateral scope creep.** Auto-forwards, shared mailboxes, and distribution
  lists can carry your message to out-of-scope or third-party recipients — design
  recipients and links to avoid that.

---

## 2. Metrics — measure without harming users

Track in **aggregate**, tied to learning objectives, never as an individual scoreboard.

Core funnel (GoPhish reports these):
- **Sent** — delivered into the environment.
- **Opened** — email opened (open-tracking pixel; confirm it's within your privacy
  posture — some clients opt out of open tracking).
- **Clicked** — recipient followed the tracked link (each mapped via the unique `rid`).
- **Submitted** — recipient reached the point of entering data on the landing page.
- **Reported** — recipient reported the message as suspicious. **Treat this as the
  primary success metric** — a resilient workforce *reports*, and a rising report rate
  is the outcome you actually want.

Handling the "submitted" event safely:
- Record **that** a submission occurred (and optionally a redacted/hashed artifact as
  minimal proof) — **never** persist reusable real passwords or session cookies.
- Immediately fire the **awareness redirect** (next section). The submit event should
  lead straight to education, not to any real authentication or account action.
- Aggregate results by group/department/pretext difficulty for the report — do not
  publish per-person results or feed them into HR discipline.

Privacy discipline: collect the minimum needed to teach and improve controls; apply
the agreed retention and deletion; note the deletion in the report cleanup list.

---

## 3. The immediate awareness moment (redirect)

Every click/submit ends at a supportive, educational page — configured as the GoPhish
landing page "Redirect to" target, or as the landing page itself.

The awareness page should:
- State plainly this was an **authorized security-awareness simulation**.
- Be **reassuring and non-punitive** — no shaming, no public score, no "you failed."
- Show the **red flags** this specific lure contained (lookalike domain, urgency,
  generic greeting, unexpected link/attachment).
- Teach the **correct action**: how to report a suspicious message in *this* org
  (the report button / mailbox), and where to get help.
- Optionally link to a short micro-training, framed as growth, not remediation.

This turns a click into the highest-value teaching moment in the whole engagement.

---

## 4. AiTM / MFA-phishing (evilginx) — concept for awareness only

Modern phishing increasingly defeats MFA using **Adversary-in-the-Middle (AiTM)**
reverse-proxy kits — **evilginx** is the best-known open-source example. Cover this
**conceptually**, so the client understands the risk and can prioritize
phishing-resistant controls. This skill does **not** provide steps to stand up a live
credential-relay against people.

**The concept (for awareness):**
- An AiTM kit sits as a reverse proxy between the user and the *real* login page. The
  user sees a genuine-looking flow; the proxy relays every field — username, password,
  and the MFA response — to the legitimate site in real time.
- Because it captures the **post-authentication session cookie**, it bypasses OTP,
  TOTP, and push MFA: each of those is a shared secret the human can be induced to
  relay live. The stolen session token grants access without re-prompting MFA.

**Why it matters / how to test awareness responsibly:**
- The learning point is *"MFA is not a silver bullet against phishing; the human can
  be proxied."* You can teach and measure this with a **standard simulation** (an
  AiTM-*styled* lure that leads to your awareness page) — **without** operating a real
  relay or capturing anyone's real session.
- If a client's SOW genuinely requires demonstrating session-cookie theft, treat it as
  a high-sensitivity item requiring its own explicit written approval, an isolated
  environment, **test accounts only**, and immediate destruction of any token — never
  reuse. Default to the *conceptual/awareness* treatment.

**Constructive detection signals to hand the client** (report these as defensive wins):
- AiTM infra often uses **newly-registered domains** and Let's Encrypt certificates.
- Default evilginx artifacts historically include an ~8-char mixed-case URL path and
  telltale certificate strings (e.g., an "Evilginx" Organization / Root CA name) —
  useful hunting IOCs.
- **The durable fix:** phishing-resistant, **WebAuthn/FIDO2** authenticators (passkeys)
  bind authentication to the real origin's public key, so a proxied credential is
  useless — recommend this as the strategic remediation, alongside conditional-access,
  token-binding, and impossible-travel detections.

---

## 5. Vishing / smishing / physical pretext (brief)

Only if **each channel is explicitly authorized** in the SOW (a separate phone/SMS/
physical rider is often required, and recording calls has its own legal constraints).

- **Vishing (voice):** scripted, scenario-based calls to in-scope staff to test
  out-of-band verification and call-back procedures (a good BEC-resilience test). No
  cruel pretexts; identify as a simulation in the debrief; respect recording law.
- **Smishing (SMS):** simulated text lures. Requires an authorized channel and
  in-scope, work-context numbers only — **not** personal numbers unless explicitly
  contracted. Keep volume controlled; same ethical themes apply.
- **Physical pretext (brief):** tailgating, badge/lobby pretext, or drop-media tests,
  done only with written physical-assessment authorization, a carry letter ("get out
  of jail" letter) naming a client contact, and strict scope. Never intimidate, never
  create genuine confrontation, and disengage the moment someone is distressed.

All three inherit the same non-negotiables: named authorization, in-scope people only,
no real harm, immediate/eventual awareness debrief, abort on distress.

---

## 6. Constructive reporting (awareness, not blame)

Use `security-reporting` for structure and severity; this section covers the SE-specific
framing. NIST SP 800-115 is explicit: SE results are a **learning tool, not a punitive
measure**.

**Do:**
- Report **aggregate** metrics (sent/opened/clicked/submitted/**reported**) by group,
  pretext, and difficulty — never a per-employee shame list.
- Frame findings as **system and control gaps**: mail-filter efficacy, MFA phishing-
  resistance, reporting-tool adoption, help-desk verification procedures, time-to-report.
- **Celebrate the report rate** and fast reporters as the headline positive signal.
- Give **prioritized, constructive remediation**: WebAuthn/FIDO2 for phishing-resistant
  MFA, stronger reporting workflows and reinforcement, targeted micro-training for the
  groups/pretexts that struggled, and detections for the AiTM IOCs above.
- Include a **cleanup/attestation** section: infrastructure torn down, domains parked/
  released, and captured data redacted/**deleted** on the agreed date.
- Provide a positive **debrief** narrative the client can share org-wide to reinforce a
  no-shame culture.

**Don't:**
- Name individuals, rank employees, or route results into discipline/performance.
- Overstate risk with a scary raw click count divorced from context and controls.
- Retain any captured data beyond the agreed retention.

The engagement succeeds when the client is **better defended and their people feel
supported** — measured by a higher report rate and closed control gaps next time,
not by how many people clicked this time.
