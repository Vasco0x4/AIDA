# Sources — Public references consulted

All material below is public. URLs verified during research (Aug 2026).

## OWASP
- OWASP Top 10 CI/CD Security Risks (project):
  https://owasp.org/www-project-top-10-ci-cd-security-risks/
- CICD-SEC-4 Poisoned Pipeline Execution:
  https://owasp.org/www-project-top-10-ci-cd-security-risks/CICD-SEC-04-Poisoned-Pipeline-Execution
- CICD-SEC-4 (source md, GitHub):
  https://github.com/OWASP/www-project-top-10-ci-cd-security-risks/blob/main/CICD-SEC-04-Poisoned-Pipeline-Execution.md
- OWASP Kubernetes Security Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html
- OWASP Docker Security Cheat Sheet:
  https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html

## CIS Benchmarks
- CIS Docker Benchmark: https://www.cisecurity.org/benchmark/docker
- CIS Kubernetes Benchmark: https://www.cisecurity.org/benchmark/kubernetes
- kube-bench (CIS checker): https://github.com/aquasecurity/kube-bench

## CNCF / Kubernetes docs
- Kubernetes RBAC: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Pod Security Admission: https://kubernetes.io/docs/concepts/security/pod-security-admission/
- Securing a Cluster: https://kubernetes.io/docs/tasks/administer-cluster/securing-a-cluster/
- Service Account tokens (TokenRequest / bound tokens):
  https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/

## SLSA framework
- SLSA v1.0 spec: https://slsa.dev/spec/v1.0/
- What's new in SLSA v1.0: https://slsa.dev/spec/v1.0/whats-new
- SLSA provenance: https://slsa.dev/spec/v1.0/provenance
- Build levels (L0–L3): https://slsa.dev/spec/v1.0/levels

## MITRE ATT&CK
- ATT&CK for Containers (matrix): https://attack.mitre.org/matrices/enterprise/containers/
- T1610 Deploy Container: https://attack.mitre.org/techniques/T1610/
- T1611 Escape to Host: https://attack.mitre.org/techniques/T1611/
- T1528 Steal Application Access Token: https://attack.mitre.org/techniques/T1528/

## Disclosed incidents & research
- SolarWinds / SUNBURST (build-system compromise) — CISA:
  https://www.cisa.gov/news-events/alerts/2020/12/13/active-exploitation-solarwinds-software
- Codecov Bash Uploader compromise (2021):
  https://about.codecov.io/security-update/
- Alex Birsan — Dependency Confusion (2021):
  https://medium.com/@alex.birsan/dependency-confusion-4a5d60fec610
- XZ Utils backdoor CVE-2024-3094 — Andres Freund oss-security disclosure:
  https://www.openwall.com/lists/oss-security/2024/03/29/4
- XZ backdoor — CISA advisory:
  https://www.cisa.gov/news-events/alerts/2024/03/29/reported-supply-chain-compromise-affecting-xz-utils-data-compression-library-cve-2024-3094
- XZ backdoor — Unit42 threat brief:
  https://unit42.paloaltonetworks.com/threat-brief-xz-utils-cve-2024-3094/
- tj-actions/changed-files compromise CVE-2025-30066 — CISA alert:
  https://www.cisa.gov/news-events/alerts/2025/03/18/supply-chain-compromise-third-party-tj-actionschanged-files-cve-2025-30066-and-reviewdogaction
- tj-actions — Wiz analysis:
  https://www.wiz.io/blog/github-action-tj-actions-changed-files-supply-chain-attack-cve-2025-30066
- tj-actions — GitHub Advisory GHSA-mrrh-fwg8-r2c3:
  https://github.com/advisories/GHSA-mrrh-fwg8-r2c3
- tj-actions — Unit42 threat assessment:
  https://unit42.paloaltonetworks.com/github-actions-supply-chain-attack/
- Tesla Kubernetes dashboard cryptojacking (RedLock, 2018):
  https://redlock.io/blog/cryptojacking-tesla

## Container-escape CVEs
- CVE-2019-5736 (runc /proc/self/exe overwrite) — Dragon Sector disclosure:
  https://seclists.org/oss-sec/2019/q1/119
- CVE-2019-5736 — NVD: https://nvd.nist.gov/vuln/detail/CVE-2019-5736
- CVE-2024-21626 Leaky Vessels (runc fd leak / WORKDIR) — Snyk:
  https://snyk.io/blog/cve-2024-21626-runc-process-cwd-container-breakout/
- Leaky Vessels — Wiz: https://www.wiz.io/blog/leaky-vessels-container-escape-vulnerabilities
- CVE-2024-21626 — NVD: https://nvd.nist.gov/vuln/detail/CVE-2024-21626
- Red Hat RHSB-2024-001 (Leaky Vessels):
  https://access.redhat.com/security/vulnerabilities/RHSB-2024-001

## Tools (read-only scanning / audit / post-exploitation)
- Trivy: https://aquasecurity.github.io/trivy/
- Syft (SBOM) & Grype: https://github.com/anchore/syft / https://github.com/anchore/grype
- dive (layer explorer): https://github.com/wagoodman/dive
- crane / skopeo: https://github.com/google/go-containerregistry / https://github.com/containers/skopeo
- kube-hunter (Aqua, archived): https://github.com/aquasecurity/kube-hunter
- kubeaudit: https://github.com/Shopify/kubeaudit
- amicontained: https://github.com/genuinetools/amicontained
- Peirates (K8s post-exploitation): https://github.com/inguardians/peirates
- BadPods (over-privileged pod specs): https://github.com/BishopFox/badPods
- cosign / sigstore: https://docs.sigstore.dev/cosign/overview/
- gitleaks / trufflehog: https://github.com/gitleaks/gitleaks / https://github.com/trufflesecurity/trufflehog
- checkov / tfsec / kics: https://www.checkov.io/ / https://github.com/aquasecurity/tfsec / https://kics.io/
- actionlint / zizmor (Actions static analysis): https://github.com/rhysd/actionlint / https://github.com/woodruffw/zizmor
- StepSecurity Harden-Runner: https://www.stepsecurity.io/
- Falco (runtime detection): https://falco.org/
- hadolint (Dockerfile linter): https://github.com/hadolint/hadolint

## Standards & guidance
- NIST SP 800-190 Application Container Security Guide:
  https://csrc.nist.gov/pubs/sp/800/190/final
- NIST SP 800-204D (software supply chain, CI/CD):
  https://csrc.nist.gov/pubs/sp/800/204/d/final
- US EO 14028 / NTIA SBOM minimum elements:
  https://www.ntia.gov/report/2021/minimum-elements-software-bill-materials-sbom
- CNCF Software Supply Chain Best Practices:
  https://github.com/cncf/tag-security/tree/main/community/resources/software-supply-chain-security
