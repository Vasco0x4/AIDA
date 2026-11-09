# Sources — public references consulted

Authorized, defensive security-testing content. All material below is public.

## OWASP API Security Top 10 (2023)
- OWASP API Security Project — https://owasp.org/www-project-api-security/
- 2023 Top 10 index (all ten risks, official titles/codes) —
  https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- 2023 edition header — https://owasp.org/API-Security/editions/2023/en/0x00-header/
- Per-risk pages (API1–API10) linked from the index above, e.g.
  - API1 BOLA — https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
  - API3 BOPLA — https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
  - API4 Unrestricted Resource Consumption — https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
  - API6 Sensitive Business Flows — https://owasp.org/API-Security/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/
  - API7 SSRF — https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/
  - API9 Improper Inventory Management — https://owasp.org/API-Security/editions/2023/en/0xa9-improper-inventory-management/
  - API10 Unsafe Consumption of APIs — https://owasp.org/API-Security/editions/2023/en/0xaa-unsafe-consumption-of-apis/
- OWASP WSTG (Web Security Testing Guide) — https://owasp.org/www-project-web-security-testing-guide/
- Salt Security — OWASP API Security Top 10 explained — https://salt.security/blog/owasp-api-security-top-10-explained
- apisecurity.io — OWASP API Security Top 10 — https://apisecurity.io/owasp-api-security-top-10/
- Cloudflare Learning — What is the OWASP API Security Top 10 —
  https://www.cloudflare.com/learning/security/api/owasp-api-security-top-10/
- OWASP API Pentesting checklist (community) — https://github.com/0x48756773/OWASP-API-Checklist

## PortSwigger Web Security Academy (GraphQL / API)
- GraphQL API vulnerabilities — https://portswigger.net/web-security/graphql
- Find GraphQL API vulnerabilities with Burp — https://portswigger.net/blog/find-graphql-api-vulnerabilities-with-burp-suite-professional
- GraphQL introspection enabled (KB) — https://portswigger.net/kb/issues/00200512_graphql-introspection-enabled

## Tooling documentation
- Kiterunner (Assetnote, contextual API content discovery) — https://github.com/assetnote/kiterunner
- Assetnote wordlists (routes-large.kite) — https://wordlists-cdn.assetnote.io/ ,
  research: https://www.assetnote.io/resources/research/contextual-content-discovery-youve-forgotten-about-the-api-endpoints
- arjun (HTTP parameter discovery) — https://github.com/s0md3v/Arjun
- graphql-cop (GraphQL misconfig scanner) — https://github.com/dolevf/graphql-cop
- clairvoyance (GraphQL schema recovery via field suggestions) — https://github.com/nikitastupin/clairvoyance
- BatchQL (GraphQL batching tests) — https://github.com/assetnote/batchql
- jwt_tool — https://github.com/ticarpi/jwt_tool
- grpcurl / grpcui — https://github.com/fullstorydev/grpcurl , https://github.com/fullstorydev/grpcui
- nuclei — https://github.com/projectdiscovery/nuclei
- Postman (API client for auth/role diffing) — https://www.postman.com/
- Burp Suite (proxy, OpenAPI import, GraphQL/Protobuf) — https://portswigger.net/burp
- ffuf (fuzzing) — https://github.com/ffuf/ffuf

## Bug-bounty disclosure sources (report patterns)
- HackerOne Hacktivity (public disclosures) — https://hackerone.com/hacktivity

## Standards cross-reference
- NIST SP 800-115 — https://csrc.nist.gov/pubs/sp/800/115/final
- PTES — http://www.pentest-standard.org/
