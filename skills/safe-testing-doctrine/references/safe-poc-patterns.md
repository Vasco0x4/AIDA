# Safe vs. Unsafe Proof-of-Concept Patterns

For each vuln class: how to PROVE it safely vs. what would cross the doctrine.
Always pick the safe column. The goal is a reviewer-convincing PoC with zero harm.

## RCE / command injection
- ✅ Run `id`, `whoami`, `hostname`, `cat /etc/hostname`, or write one benign
  canary file (`/tmp/pentest-<id>.txt`) and read it back.
- ✅ Out-of-band: `nslookup <token>.oast.fun` / HTTP callback to your collaborator.
- ❌ Reverse shells left running, downloading tools, `rm`, encrypting files,
  pivoting, installing persistence, dumping full filesystems.

## SQL injection
- ✅ Prove with `SELECT @@version`, `current_user`, `SLEEP(3)` (short), or count
  of rows; dump a single non-sensitive record or a schema name.
- ❌ `--dump` of whole tables of real PII, `DROP`/`DELETE`/`UPDATE`, stacked
  destructive queries, long/heavy `SLEEP`/`BENCHMARK` (that's a DoS).

## SSRF
- ✅ Trigger a DNS/HTTP callback; read a benign metadata field (e.g. IAM role
  *name*) to prove reachability.
- ❌ Exfiltrating live cloud credentials and using them, internal port-sweeping
  at scale, hammering internal services, gopher-writing to internal datastores.

## XSS
- ✅ `document.title` change, `console.log`, a benign `alert(document.domain)` in
  your own session, or a single beacon of a NON-sensitive value to your collaborator.
- ❌ Mass cookie theft from real users, stored payloads that fire for every real
  visitor, keylogging real users, self-propagating XSS.

## Access control / IDOR
- ✅ Read ONE other object you control (a second test account), or read one field
  and immediately redact; screenshot proving cross-account access.
- ❌ Enumerating and downloading thousands of real users' records "to show scale."
  Prove with 1–2 objects and estimate scale in prose.

## Authentication / brute force / spraying
- ✅ Spray ONE password across users, staying under lockout threshold−1, within
  the reset window; test rate-limits with a handful of attempts.
- ❌ High-rate credential brute force, ignoring lockout (locks out real users =
  DoS), OTP flooding.

## File upload
- ✅ Upload a benign proof file and show it's retrievable/executable in a test
  path; a webshell that only runs `id` then is deleted by you.
- ❌ Leaving a live webshell, uploading into shared/prod content, overwriting
  existing files.

## Deserialization / template injection
- ✅ Non-destructive gadget proving execution (`id`, sleep, DNS callback).
- ❌ Destructive gadgets, memory-exhaustion chains, leaving RCE primitives live.

## XXE
- ✅ Read a single benign file (`/etc/hostname`) or trigger an OOB callback.
- ❌ Billion-laughs / entity-expansion (DoS), recursive external entities,
  large-file reads that exhaust memory.

## GraphQL / API
- ✅ Introspection, one aliased batch to show rate-limit bypass, read one object
  cross-tenant.
- ❌ Deeply-nested/aliased query floods (DoS), dumping full datasets, mass
  mutation.

## AD / internal
- ✅ Kerberoast a targeted account and crack offline; shadow-credentials on a test
  object and clean up; DCSync ONE account (e.g. a canary) to prove rights; screenshot
  BloodHound path.
- ❌ Mass password resets, forced coercion during business hours without sign-off,
  leaving golden/silver tickets or rogue accounts, dumping the entire NTDS.dit of a
  production domain when one account proves the right (coordinate for full dump).

## Web cache poisoning / request smuggling
- ✅ Use a cache-buster / unique path so only YOUR request is affected; prove the
  primitive on a benign endpoint.
- ❌ Poisoning shared cache keys that serve real users, smuggling that hijacks real
  users' requests at scale.

## Golden rule
If proving it fully would harm data, availability, or real users, prove the
**primitive** (that the flaw exists and what it would allow) and describe the
impact in the report instead of executing it.
