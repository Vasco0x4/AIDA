# Sources & Public Provenance

All material in this skill is derived from public, authoritative documentation.
Consult these for the canonical, current details.

## OWASP — methodology, requirements, controls
- OWASP Code Review Guide — https://owasp.org/www-project-code-review-guide/
- OWASP Application Security Verification Standard (ASVS) — https://owasp.org/www-project-application-security-verification-standard/
- ASVS in the OWASP Developer Guide — https://devguide.owasp.org/en/03-requirements/05-asvs/
- OWASP Cheat Sheet Series — https://cheatsheetseries.owasp.org/
  - Injection Prevention, SQL Injection Prevention, Query Parameterization
  - Cross Site Scripting Prevention, DOM based XSS Prevention
  - Deserialization, XML External Entity (XXE) Prevention
  - Server-Side Request Forgery (SSRF) Prevention
  - Cryptographic Storage, Password Storage, Secrets Management
  - Authorization, Access Control, Input Validation
- OWASP Static Code Analysis (community) — https://owasp.org/www-community/controls/Static_Code_Analysis
- OWASP Threat Modeling Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html
- OWASP Threat Modeling Process — https://owasp.org/www-community/Threat_Modeling_Process
- OWASP Threat Dragon (DFD tool) — https://owasp.org/www-project-threat-dragon/
- OWASP Top 10 — https://owasp.org/www-project-top-ten/
- OWASP Web Security Testing Guide (WSTG) — https://owasp.org/www-project-web-security-testing-guide/

## CWE / CVE
- 2024 CWE Top 25 Most Dangerous Software Weaknesses (MITRE) — https://cwe.mitre.org/top25/
- CISA advisory: 2024 CWE Top 25 — https://www.cisa.gov/news-events/alerts/2024/11/20/2024-cwe-top-25-most-dangerous-software-weaknesses
- CWE list / individual weaknesses — https://cwe.mitre.org/data/index.html

## SAST tooling
- Semgrep docs — https://semgrep.dev/docs/
  - Taint analysis / taint mode overview — https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/overview
  - Writing rules — https://semgrep.dev/docs/writing-rules/overview
  - Rule syntax (patterns, pattern-sources/sinks/sanitizers) — https://semgrep.dev/docs/writing-rules/rule-syntax
  - Semgrep Registry — https://semgrep.dev/r
- CodeQL docs — https://codeql.github.com/docs/
  - About data flow analysis — https://codeql.github.com/docs/writing-codeql-queries/about-data-flow-analysis/
  - Analyzing data flow in Java — https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-java/
  - Data flow cheat sheet for JavaScript — https://codeql.github.com/docs/codeql-language-guides/data-flow-cheat-sheet-for-javascript/
  - CodeQL CLI — https://docs.github.com/en/code-security/codeql-cli
- Commercial/other SAST concepts: SonarQube/SonarSource (https://www.sonarsource.com/),
  Snyk Code (https://docs.snyk.io/), PVS-Studio taint analysis (https://pvs-studio.com/)

## Secret scanning
- gitleaks — https://github.com/gitleaks/gitleaks
- trufflehog — https://github.com/trufflesecurity/trufflehog

## Dependency SCA / IaC
- OWASP Dependency-Check — https://owasp.org/www-project-dependency-check/
- OSV / osv-scanner — https://osv.dev/ , https://github.com/google/osv-scanner
- Go govulncheck — https://go.dev/blog/govulncheck
- pip-audit — https://github.com/pypa/pip-audit
- Trivy — https://trivy.dev/
- Checkov — https://www.checkov.io/ ; tfsec — https://github.com/aquasecurity/tfsec ; KICS — https://kics.io/

## Threat modeling / frameworks
- Microsoft STRIDE / Threat Modeling — https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats
- NIST SP 800-115 (Technical Guide to Information Security Testing) — https://csrc.nist.gov/pubs/sp/800/115/final
- MITRE ATT&CK — https://attack.mitre.org/

Note: some public blogs/aggregators were consulted during research for
corroboration, but the authoritative references above take precedence. Standards
and tool docs evolve — verify version-specific details (ASVS version, CWE Top 25
year, Semgrep/CodeQL syntax) against the primary sources when it matters.
