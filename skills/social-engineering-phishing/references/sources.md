# Sources — Public References

All material in this skill is derived from public documentation, standards, and
vendor/practitioner guidance. Use these to verify claims and go deeper. Retrieved
2026-08.

## Simulation tooling (official docs / vendor)

- **GoPhish — official documentation** (landing pages, sending profiles, campaigns,
  `rid` tracking, redirects): https://docs.getgophish.com/user-guide/ and
  https://docs.getgophish.com/user-guide/documentation/landing-pages ;
  project: https://getgophish.com/
- **Social-Engineer Toolkit (SET)** by TrustedSec — spear-phishing menu, website
  cloning, Credential Harvester method (framework page):
  https://www.social-engineer.org/framework/se-tools/computer-based/social-engineer-toolkit-set/
  ; project: https://github.com/trustedsec/social-engineer-toolkit
- **King Phisher** — spear-phishing campaign tool, metrics tracking, credential
  demonstration: https://github.com/rsmusllp/king-phisher

## AiTM / MFA-phishing concept (awareness)

- **evilginx** (AiTM reverse-proxy concept — awareness reference only):
  https://github.com/kgretzky/evilginx2
- Cisco Talos — "State-of-the-art phishing: MFA bypass":
  https://blog.talosintelligence.com/state-of-the-art-phishing-mfa-bypass/
- Deepwatch Labs — "Catching the Phish: Detecting Evilginx & AiTM" (detection IOCs:
  new domains, Let's Encrypt, ~8-char path, evilginx cert strings):
  https://www.deepwatch.com/labs/catching-the-phish-detecting-evilginx-aitm/
- Aon Cyber Labs — "Bypassing MFA: A Forensic Look at Evilginx2":
  https://www.aon.com/cyber-solutions/aon_cyber_labs/bypassing-mfa-a-forensic-look-at-evilginx2-phishing-kit/
- WebAuthn / FIDO2 (phishing-resistant remediation): https://webauthn.guide/ and
  https://fidoalliance.org/

## Standards & frameworks

- **NIST SP 800-115** — Technical Guide to Information Security Testing and Assessment
  (social engineering in planning/execution; "learning tool, not punitive"):
  https://csrc.nist.gov/pubs/sp/800/115/final
- **MITRE ATT&CK — T1566 Phishing** and sub-techniques:
  https://attack.mitre.org/techniques/T1566/ ,
  .001 Attachment https://attack.mitre.org/techniques/T1566/001/ ,
  .002 Link https://attack.mitre.org/techniques/T1566/002/ ,
  .003 via Service https://attack.mitre.org/techniques/T1566/003/
- **OWASP** — phishing / social-engineering and security-awareness guidance
  (WSTG, Security Awareness, Phishing pages): https://owasp.org/ ;
  WSTG: https://owasp.org/www-project-web-security-testing-guide/

## Responsible-simulation & ethics guidance

- Hook Security — "A Guide to Responsible Phishing Simulations":
  https://www.hooksecurity.co/blog/responsible-phishing-simulations
- Hoxhunt — "Phishing Simulation Best Practices":
  https://hoxhunt.com/blog/phishing-simulation-best-practices
- TrustBuilder — "Ethical Phishing: Boosting Cybersecurity or Breeding Workplace
  Stress?" (employee-wellbeing, no-shame culture):
  https://www.trustbuilder.com/en/ethical-phishing/
- nFlo — "Phishing simulations: how to run them ethically and effectively"
  (authorization, HR/legal, works-council, GDPR legitimate-interest basis):
  https://nflo.tech/knowledge-base/phishing-simulations-social-engineering-tests-ethical-effective/

## In-repo cross-references

- `safe-testing-doctrine` — hard limits; SE forbidden by default, gated here.
- `offensive-osint` / `osint-methodology` — in-scope target lists and pretext research.
- `pentest-methodology` — engagement phases (NIST SP 800-115 alignment).
- `security-reporting` — constructive, aggregate, awareness-first deliverable.
