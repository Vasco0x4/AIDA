---
name: safe-testing-doctrine
description: "MANDATORY safety and rules-of-engagement doctrine for every authorized security-testing skill in this base. Defines the hard limits that must never be crossed during a pentest/audit: no destruction (no delete/overwrite/encrypt/config-change), no availability impact (absolutely no DoS/DDoS, no resource exhaustion, no lockout storms, no crash-testing on prod), no impact on real users or their data (no spam/push/email/social-engineering unless explicitly contracted, no reading real user data beyond minimal proof, no mass account actions), strict scope enforcement, least-intrusive proof-of-concept, evidence handling, cleanup obligations, and stop conditions. Aligned to NIST SP 800-115, PTES, OWASP Testing Guide, and CFAA/legal-authorization principles. Every attack skill references this. Load it before ANY active testing to confirm what is and is not permitted."
version: 1.0.0
triggers:
  - rules of engagement
  - scope
  - authorization
  - safe testing
  - what am I allowed to do
  - is this in scope
  - pentest safety
  - do no harm
---

# Safe Testing Doctrine (READ BEFORE ANY ACTIVE TEST)

This is the non-negotiable safety contract for every skill in this security base.
All attack skills (`web-vuln-hunting`, `active-directory-attack-paths`,
`*-cve-exploitation`, `cloud-security-testing`, `api-security-testing`,
`network-service-exploitation`) inherit these rules. If any technique in another
skill conflicts with this doctrine, **this doctrine wins**.

Purpose: professional penetration testing and audit find and prove risk **without
harming the target, its data, or its users**. A finding is only useful if it was
obtained safely, legally, and reproducibly.

## 1. Authorization gate (must pass before touching anything)

Proceed only when ALL are true:
- [ ] Written authorization exists (signed RoE / SOW / in-scope bug-bounty brief).
- [ ] The exact target scope is known: in-scope domains, IPs/CIDRs, apps,
      accounts, AD domains — and the explicit **exclusions**.
- [ ] The testing window and any change-freeze / blackout periods are known.
- [ ] Emergency contacts and a stop/abort procedure are known.
- [ ] Data-handling and disclosure terms are agreed.

If any box is unchecked → **STOP and ask the operator**. Never "just try it."

## 2. Hard prohibitions (NEVER do these)

These are absolute. No exception without explicit, written, per-item approval.

**Availability / DoS — forbidden entirely:**
- No DoS or DDoS of any kind. No stress/load/flood testing. No traffic amplification.
- No resource-exhaustion payloads (billion-laughs XXE, ReDoS, zip bombs, GraphQL
  deep-nesting floods, decompression bombs, connection floods).
- No fork bombs, no fuzzing that crashes services, no "does it fall over?" tests
  on production.
- No brute force that ignores lockout policy; no mass-authentication that could
  **lock out real accounts** (account-lockout DoS). Always read the lockout
  policy first and stay under threshold−1.
- No forced reboots/shutdowns; no filling disks; no memory/CPU exhaustion.

**Destruction / integrity — forbidden:**
- Do not delete, drop, truncate, overwrite, encrypt, or corrupt any data, table,
  file, object, bucket, repo, or backup.
- Do not modify production configuration, firewall rules, GPOs, IAM policies, or
  schemas except a minimal, reversible change that is immediately restored and
  logged (and only when it's the sole way to prove impact and RoE allows it).
- Do not deploy ransomware-like, wiper, or self-propagating code. No worms.

**Users / third parties — forbidden unless explicitly contracted:**
- No phishing, social engineering, smishing, vishing, or pretexting of real staff.
- No sending email/SMS/push/chat messages to real users. No spam. No mass invites.
- No accessing, reading, exfiltrating, or storing real users' personal data
  beyond the **minimum** needed to prove a finding (then redact).
- No mass account actions (bulk password resets, bulk deletes, bulk invites).
- Never pivot to, scan, or touch out-of-scope or third-party/shared infrastructure.

**Persistence / stealth — controlled:**
- Do not leave backdoors, forged tickets, rogue accounts, added ACLs, or C2 alive.
  If created to prove impact, remove them and log the cleanup.
- Detection evasion is only for validating detection efficacy under explicit RoE,
  never to hide unauthorized activity.

## 3. Positive obligations (always do these)

- **Least-intrusive proof.** Prove the vulnerability with the smallest, safest
  PoC that a reviewer will accept. `id`/`whoami`, a benign canary file, reading
  one non-sensitive record, a DNS/HTTP callback — not full exploitation.
- **Read-only first.** Prefer read-only validation; escalate to a write only when
  read cannot prove impact, using your own test accounts and benign markers.
- **Rate-limit yourself.** Slow, targeted requests. Avoid scanner defaults that
  hammer targets. Respect the target's capacity, especially in business hours.
- **Use test accounts** you control for anything state-changing. Two accounts per
  role for access-control testing.
- **Log everything.** Timestamped request/response, tool, command, and target for
  every action, so activity is auditable and findings are reproducible.
- **Handle evidence as sensitive.** Encrypt credentials/hashes/PII at rest, store
  only what's needed, and securely delete after the report is accepted.
- **Clean up.** Remove uploaded files, created accounts/computers, added ACLs,
  tickets, scheduled tasks, and any test artifact. Deliver a cleanup list.

## 4. Stop conditions (halt immediately and notify)

Stop and contact the client when you:
- Discover you are outside scope, or the target isn't what was authorized.
- Encounter another actor's activity, a live breach, or evidence of prior compromise.
- Access highly sensitive data (health, financial, credentials, secrets at scale).
- Trigger an outage, instability, or unexpected state change.
- Find something whose safe exploitation you're unsure of — ask before proceeding.
- Reach a critical result (e.g. Domain Admin / RCE) earlier than expected.

## 5. Risky-technique gate (require extra confirmation)

Some techniques are legitimate but can disrupt live systems. Run analyze/dry-run
mode first, confirm they're in RoE, coordinate timing, and prefer off-hours:
- Network poisoning (Responder, mitm6), NTLM relay, ARP/DNS spoofing.
- Authentication coercion (PetitPotam, PrinterBug, DFSCoerce).
- Anything touching shared infrastructure (DCs, load balancers, caches, CI/CD).
- Password spraying (lockout risk), web cache poisoning (affects other users),
  request smuggling (affects other users).
See each attack skill's OPSEC note; when in doubt, ask.

## 6. Legal & standards alignment

- Authorization must be explicit and in writing; testing without it may violate
  law (e.g. CFAA, Computer Misuse Act, and local equivalents). Scope defines
  legality — stay inside it.
- This doctrine aligns with **NIST SP 800-115** (Technical Guide to Information
  Security Testing), **PTES** (Pre-engagement/RoE), **OWASP Testing Guide/ASVS**,
  and responsible-disclosure norms.
- See `references/roe-checklist.md` for a pre-engagement checklist and
  `references/safe-poc-patterns.md` for safe-vs-unsafe PoC examples per vuln class.

## Quick self-check before firing any payload

1. Is this target in scope and in the window? 
2. Could this delete, corrupt, or change data/config? → don't.
3. Could this reduce availability or lock out users? → don't.
4. Could this touch real users or their data? → minimize/avoid.
5. Is this the least-intrusive way to prove the point? → if not, downgrade.
6. Can I clean up and reproduce it? → log it.

If any answer is wrong, do not send it.
