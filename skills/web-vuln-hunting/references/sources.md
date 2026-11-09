# Sources / Provenance — web-vuln-hunting

This skill is a synthesis of public, reputable web-security knowledge. It encodes
patterns and methodology, not verbatim private report data.

## Standards & taxonomy
- OWASP Top 10 (2021) — https://owasp.org/Top10/
- OWASP Web Security Testing Guide (WSTG) — https://owasp.org/www-project-web-security-testing-guide/
- OWASP ASVS — https://owasp.org/www-project-application-security-verification-standard/
- OWASP Cheat Sheet Series — https://cheatsheetseries.owasp.org/
- CWE — https://cwe.mitre.org/

## Disclosed-report sources (patterns, aggregated)
- HackerOne Hacktivity (public disclosures) — https://hackerone.com/hacktivity
- Bugcrowd disclosures & VRT — https://bugcrowd.com/vulnerability-rating-taxonomy
- Intigriti public bug reports / research — https://www.intigriti.com/researchers

## Research & technique references (per class)
- Broken access control / IDOR — OWASP WSTG-ATHZ, PortSwigger Web Security Academy (access control)
- SSRF — PortSwigger SSRF labs & research; OWASP SSRF cheat sheet; cloud metadata (AWS/GCP/Azure docs)
- Injection (SQL/NoSQL/cmd/SSTI/XXE/LDAP) — OWASP WSTG-INPV; PortSwigger SSTI research; sqlmap docs; OWASP XXE cheat sheet
- XSS — PortSwigger XSS cheat sheet (https://portswigger.net/web-security/cross-site-scripting/cheat-sheet); DOMPurify mXSS research
- Auth/JWT/OAuth/SAML — PortSwigger OAuth/JWT labs; jwt_tool docs; RFC 6749/6819; OWASP JWT cheat sheet; SAML Raider
- Business logic & race conditions — PortSwigger "Smashing the state machine" (single-packet attack) & business-logic labs
- CSRF/CORS/redirect/clickjacking — OWASP WSTG-CLNT/SESS; PortSwigger CORS labs
- GraphQL/API — OWASP API Security Top 10; graphql-cop / clairvoyance docs
- Subdomain takeover — EdOverflow can-i-take-over-xyz; nuclei-templates takeovers
- Request smuggling — PortSwigger "HTTP Desync Attacks" (James Kettle)
- Web cache poisoning/deception — PortSwigger "Practical Web Cache Poisoning" (James Kettle); Omer Gil cache deception

## Tooling docs
Burp Suite, ffuf/feroxbuster, nuclei (projectdiscovery), sqlmap, tplmap/SSTImap,
jwt_tool, arjun, katana/gau, interactsh, Param Miner, graphql-cop, clairvoyance,
subzy — see each project's official documentation.

> Verify any technique against the current target/app behavior and the program's
> scope before use. Methodology reflects public knowledge as generally documented.
