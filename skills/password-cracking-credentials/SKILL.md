---
name: password-cracking-credentials
description: "Offline password/hash cracking methodology with hashcat and John the Ripper — the cracking layer for every hash the rest of this skill base collects (Kerberoast/AS-REP, NTLM/LM/NTDS.dit, NetNTLMv1/v2, WPA 22000, JWT, /etc/shadow, ZIP/Office/PDF/RAR/7z/KeePass, and web-app hashes bcrypt/md5crypt/sha512crypt). Covers hash identification (hashid, name-that-hash, format cues), choosing the hashcat -m mode with a verified table of common modes (1000 NTLM, 5600 NetNTLMv2, 13100 Kerberoast RC4, 19600/19700 Kerberoast AES, 18200 AS-REP, 22000 WPA, 1800 sha512crypt, 3200 bcrypt, 16500 JWT, 13400 KeePass, 9600 Office2013, 11600 7-Zip, and more), attack strategy and ordering (wordlist -> wordlist+rules -> mask/brute -> hybrid -> combinator), rules (best64, OneRuleToRuleThemAll) and masks, wordlist curation (rockyou, SecLists, weakpass, CeWL, mentalist), keyspace estimation, GPU vs CPU, benchmarking, potfile management, and end-to-end per-source recipes with *2john extractors (zip2john, office2john, keepass2john, unshadow). Authorized, in-scope engagements only — crack ONLY hashes lawfully obtained from authorized systems; cracking is OFFLINE, never online-brute live services. Use for: hashcat, john the ripper, crack hash, hash identification, kerberoast crack, ntlm crack, ntds crack, netntlmv2 crack, wpa crack, mask attack, wordlist, rules, potfile, zip2john, office2john, keepass crack, jwt crack, shadow crack."
version: 1.0.0
triggers:
  - hashcat
  - john the ripper
  - jtr
  - crack hash
  - crack password
  - hash cracking
  - hash identification
  - identify hash
  - hashid
  - name-that-hash
  - hashcat mode
  - kerberoast crack
  - as-rep crack
  - ntlm crack
  - ntds crack
  - netntlmv2 crack
  - wpa crack
  - hashcat 22000
  - jwt crack
  - hashcat 16500
  - mask attack
  - brute force mask
  - wordlist
  - rockyou
  - seclists
  - weakpass
  - hashcat rules
  - best64
  - onerule
  - potfile
  - unshadow
  - shadow crack
  - zip2john
  - office2john
  - keepass2john
  - keepass crack
  - cewl
---

# Password & Hash Cracking (Authorized Offline Credential Recovery)

Operational playbook for the **offline** cracking layer of an authorized engagement.
Every other skill in this base *collects* credential material — Kerberoast/AS-REP
tickets (`active-directory-attack-paths`), NTDS.dit / SAM / LSASS dumps, NetNTLMv2
from Responder, WPA handshakes/PMKID (`wireless-security`), JWTs and app password
hashes (`web-vuln-hunting`), archive/document hashes. **This skill turns those hashes
into plaintext**, then hands the results to `security-reporting`.

Cracking is **compute against a hash you already hold** — it is not an attack on any
live system. The workflow: **identify the hash -> pick the right `hashcat -m` mode ->
run the cheapest attack that is likely to work (wordlist) -> escalate (rules -> mask
-> hybrid -> combinator) -> manage the potfile -> report and destroy**.

Assumes a Linux host with `hashcat` (v6+, GPU strongly preferred), `john`
(John the Ripper *jumbo*), the `*2john` extractors, `hashid` / `name-that-hash`,
and wordlists (`rockyou.txt`, SecLists, weakpass) plus rule files (`best64.rule`,
`OneRuleToRuleThemAll.rule`).

## ⚠️ Safety — inherits `safe-testing-doctrine`

Load **`safe-testing-doctrine`** before cracking anything. This skill inherits every
hard limit there. Offline cracking is low-risk *to availability* but high-risk *to
confidentiality* — you are handling live credentials. **Hard rules:**

- **Scope only.** Crack **only** hashes that were **lawfully extracted from systems
  named in signed written authorization / RoE**. A hash from an out-of-scope host,
  a third party, a breach corpus tied to real people, or "found lying around" is
  **out of bounds** — possessing and cracking others' credentials is a crime (CFAA
  and equivalents) even if you never log in with them.
- **Cracking is OFFLINE — that is the whole point.** You run `hashcat`/`john`
  against a captured hash on **your own hardware**. This does **not** touch the
  target. **Do NOT confuse this with online brute-force / password spraying against
  a live login, LDAP, SMB, RDP, or any authentication service** — that is the
  **forbidden lockout / account-lockout DoS**. Guessing against live services lives
  in `active-directory-attack-paths` / `network-service-exploitation` and is bounded
  by lockout policy; **this skill never sends a single packet to the target.**
- **No third-party cracking services.** Do **not** upload client hashes to online
  crackers, "hash lookup" sites, rainbow-table web services, or shared/cloud GPU
  pools you do not control. The hash leaves your custody the moment you paste it.
  Crack locally.
- **Cracked credentials are the most sensitive artifact you produce.** Store hash
  files, potfiles, and cracked-password lists **encrypted at rest**; never commit
  them to git or a shared drive; in the report show **masked / truncated** passwords
  and statistics (e.g. "37/512 (7.2%) cracked; 12 in top-100 rockyou; 4 reused across
  accounts"), not full plaintext dumps unless the client explicitly requests them in
  an encrypted channel. **Wipe hashes, potfiles, and plaintext** (`shred`/secure
  delete) when the engagement closes, per the doctrine's evidence rules.
- **Use cracked creds only within authorized follow-on testing.** A recovered
  password may be used to demonstrate impact **only** against in-scope systems and
  only if the RoE permits that follow-on step; otherwise it is a reported finding,
  not a login.
- **Don't validate live.** Confirm a crack by re-hashing offline (hashcat prints the
  match), not by logging into the service.

Stop and consult the engagement lead if a hash's origin is unclear, if a capture set
appears to contain out-of-scope or personal accounts, or if the RoE is silent on
whether recovered credentials may be used for follow-on access.

## Index — pick the area

| Area | Reference file | Covers |
|------|----------------|--------|
| Hash ID, mode selection, attack strategy, rules, masks, wordlists, tuning, potfiles | `references/hashcat-john.md` | The full modes table (verified `-m` numbers), attack-mode (`-a`) reference, identification workflow, attack ordering, rule/mask/wordlist curation, keyspace estimation, GPU/CPU & benchmarking, potfile & distributed concepts |
| End-to-end per-source recipes | `references/per-source-recipes.md` | Copy-paste command chains for Kerberoast, AS-REP, NTLM/LM, NTDS.dit, NetNTLMv1/v2, WPA (22000), JWT (16500), Linux shadow (`unshadow`+john), and archives/documents (`zip2john`/`office2john`/`pdf2john`/`rar2john`/`7z2john`/`keepass2john`) |
| Provenance & sources | `references/sources.md` | Public citations: hashcat wiki (example-hashes, mode/attack docs), John the Ripper docs, hash-id tools, rule sets, wordlists |

## The 60-second decision flow

1. **What produced this hash?** Origin usually tells you the mode faster than any
   tool — a `$krb5tgs$23$` string is Kerberoast RC4 (13100), a 32-hex string from a
   SAM/NTDS dump is NTLM (1000), `WPA*02*...` is 22000, `$6$` is sha512crypt (1800).
   See the format-cue table in `references/hashcat-john.md`.
2. **Confirm** with `name-that-hash -f <file>` or `hashid -m -j <hash>` (both print
   the hashcat `-m` and John format). Treat their output as *candidates*, not gospel
   — bare hex is ambiguous (NTLM vs MD5 vs MD4 all 32-hex); context decides.
3. **Pick the cheapest attack likely to work.** Fast hash (NTLM, raw-MD5, NetNTLMv2)?
   Go straight to big wordlist + `OneRuleToRuleThemAll`. Slow hash (bcrypt, sha512crypt,
   KeePass, WPA)? Be frugal — targeted wordlist + `best64`, small masks; brute-force is
   usually hopeless. See the strategy ladder.
4. **Run, then escalate** only as budget allows: `rockyou` -> `rockyou`+rules ->
   targeted mask from the password policy -> hybrid -> combinator.
5. **Harvest the potfile**, compute stats, **report masked**, then **destroy**.

## Cross-references

- **`active-directory-attack-paths`** — where Kerberoast/AS-REP tickets, NTDS.dit,
  SAM/LSASS, and NetNTLMv2 (Responder) hashes come from, and the *online* guessing
  rules (spraying, lockout policy) that this skill deliberately does **not** do.
- **`wireless-security`** — WPA2/WPA3 handshake & PMKID capture that feeds `-m 22000`.
- **`web-vuln-hunting`** — JWTs, exposed application password hashes (bcrypt/argon2/
  md5crypt), and secret leaks that feed the web-app cracking recipes.
- **`network-service-exploitation`** — service hashes (SNMP, database, SSH keys) and
  the online-auth boundary this skill must not cross.
- **`security-reporting`** — how to present cracked-credential findings (masked
  stats, password-policy weakness, reuse analysis) and the cleanup checklist.
