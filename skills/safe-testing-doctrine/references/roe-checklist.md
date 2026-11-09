# Pre-Engagement / Rules-of-Engagement Checklist (PTES + NIST SP 800-115)

Fill this out and confirm before any active testing. If a field is unknown, the
engagement is not ready — ask.

## Authorization
- [ ] Signed authorization / SOW / bug-bounty scope reference: __________
- [ ] Authorizing party has authority over the assets (asset owner, not just IT): __________
- [ ] Get-out-of-jail / authorization letter available on-hand during testing.

## Scope — in
- [ ] Domains / subdomains: __________
- [ ] IP ranges / CIDRs: __________
- [ ] Applications / APIs / URLs: __________
- [ ] AD domains / forests / hosts: __________
- [ ] Cloud accounts / subscriptions / projects: __________
- [ ] User roles / test accounts provided: __________

## Scope — OUT (exclusions)
- [ ] Excluded hosts/paths/subdomains: __________
- [ ] Third-party / shared / SaaS infrastructure (usually out): __________
- [ ] Production systems that must not be disrupted: __________
- [ ] Data classes that must not be accessed: __________

## Test type & depth
- [ ] Black / grey / white box: __________
- [ ] External / internal / assumed-breach: __________
- [ ] Credentialed? provided creds: __________

## Constraints & timing
- [ ] Testing window (dates/hours): __________
- [ ] Blackout / change-freeze periods: __________
- [ ] Off-hours required for risky tests? __________
- [ ] Rate/volume limits agreed: __________

## Explicitly permitted risky techniques (default = NOT permitted)
- [ ] Network poisoning / relay (Responder, mitm6, ntlmrelayx): Y / N
- [ ] Authentication coercion (PetitPotam, PrinterBug, DFSCoerce): Y / N
- [ ] Password spraying (with lockout limits): Y / N — threshold: ___ window: ___
- [ ] Phishing / social engineering: Y / N (usually a separate SOW)
- [ ] Exploitation to code execution (vs. proof-only): Y / N
- [ ] Post-exploitation / lateral movement / privilege escalation: Y / N
- [ ] Data exfiltration proof (synthetic/marked data only): Y / N

## Explicitly forbidden (baseline — confirm)
- [ ] No DoS/DDoS, load, or stress testing. (always)
- [ ] No destruction/modification of data or config. (always)
- [ ] No account-lockout DoS. (always)
- [ ] No messaging real users. (always)

## Communications
- [ ] Primary technical contact + phone (24/7 for incidents): __________
- [ ] Escalation contact: __________
- [ ] Stop/abort keyword & procedure: __________
- [ ] Reporting channel & cadence (daily check-in? critical-finding SLA?): __________
- [ ] Secure evidence-handling & disclosure terms: __________

## Deconfliction
- [ ] Blue team / SOC aware? (purple-team vs. covert): __________
- [ ] Source IPs to allow-list or NOT: __________
- [ ] How to distinguish tester traffic from a real attacker: __________

## Sign-off
- [ ] Client sign-off obtained: name/date __________
- [ ] Tester acknowledges Safe Testing Doctrine hard limits: __________
