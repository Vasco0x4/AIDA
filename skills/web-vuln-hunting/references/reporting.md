# Triage, Severity & Reporting

## Before you report — rule out false positives
- Reproduce from a clean session / incognito; confirm it's not self-only.
- Confirm real impact, not a WAF echo or a harmless reflection.
- Check scope and duplicates (program's known-issues / your prior reports).
- Minimize the PoC to the fewest steps and benign markers.

## Severity rubric (map to program's CVSS)
| Severity | Examples |
|---|---|
| **Critical** | RCE, SQLi dumping data, SSRF→cloud creds, pre-auth ATO/auth bypass, mass IDOR of PII, full admin takeover |
| **High** | Stored XSS hitting admins, IDOR write/privesc, CORS credentialed data theft, subdomain takeover, MFA/reset bypass, request smuggling w/ capture |
| **Medium** | Reflected XSS w/ interaction, CSRF on sensitive action, business-logic economic abuse, blind SSRF interaction, verbose info leak w/ impact |
| **Low** | Open redirect, clickjacking, missing headers, self-XSS, non-sensitive info disclosure |
| **Info** | Best-practice deviations with no demonstrated impact |

CVSS quick anchors: AV:N + full compromise ≈ 9–10; auth-required data theft ≈
6–8; user-interaction client-side ≈ 4–6.

## Report template
```
Title: <Vuln class> in <feature> allows <impact>

Severity: <Critical/High/...>  (CVSS: <vector> = <score>)

Affected: <URL(s) / endpoint / parameter>

Summary:
<1–3 sentences: what, where, why it matters to the business.>

Steps to Reproduce:
1. <exact request / action, incl. accounts used>
2. ...
   (attach raw HTTP requests/responses, screenshots, or a short PoC)

Proof of Concept:
<minimal payload / curl / HTML PoC — benign>

Impact:
<what an attacker gains: data, accounts, funds, footprint.>

Remediation:
<specific fix, referencing the class remediation notes.>

References:
<OWASP / CWE id / prior disclosures if useful.>
```

## Ethics reminders
- Stay in scope; stop at proof of impact — don't pivot, exfiltrate, or persist.
- Don't access more real user data than needed; report immediately if you
  stumble onto sensitive data.
- No DoS, no destructive payloads, no social engineering unless explicitly allowed.
- Keep evidence private; follow the program's disclosure policy.
