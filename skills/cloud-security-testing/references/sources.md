# Sources — Public references consulted

All material below is public. URLs verified during research (Aug 2026).

## Breach post-mortems & case studies
- Capital One 2019 SSRF→IMDS incident — Wiz Cloud Threat Landscape:
  https://threats.wiz.io/all-incidents/capital-one-incident-march-2019
- Capital One SSRF / privileged AWS keys — Appsecco (Riyaz Walikar):
  https://blog.appsecco.com/an-ssrf-privileged-aws-keys-and-the-capital-one-breach-4c3c2cded3af
- Capital One SSRF/IMDS blast radius (retrospective) — hackaws.cloud:
  https://hackaws.cloud/blog/capital-one-ssrf-imds-blast-radius
- Capital One breach lessons — Huntress:
  https://www.huntress.com/threat-library/data-breach/capital-one-data-breach

## AWS IAM privilege escalation
- Rhino Security Labs — AWS IAM Privilege Escalation: Methods and Mitigation:
  https://rhinosecuritylabs.com/aws/aws-privilege-escalation-methods-mitigation/
  (Part 2) https://rhinosecuritylabs.com/aws/aws-privilege-escalation-methods-mitigation-part-2/
- RhinoSecurityLabs/AWS-IAM-Privilege-Escalation (GitHub, method catalog):
  https://github.com/RhinoSecurityLabs/AWS-IAM-Privilege-Escalation
- Tenable — Auditing iam:PassRole:
  https://www.tenable.com/blog/auditing-iampassrole-a-problematic-privilege-escalation-permission
- Praetorian — Privilege Escalation in AWS with PassRole Attacks:
  https://www.praetorian.com/blog/privilege-escalation-in-aws-with-passrole-attacks/
- Cloudsplaining — Privilege Escalation glossary:
  https://cloudsplaining.readthedocs.io/en/latest/glossary/privilege-escalation/

## Tools (read-only audit / post-exploitation)
- Prowler — multi-cloud (AWS/Azure/GCP/K8s) auditing:
  https://jonathansblog.co.uk/prowler-cloud-security-auditing
- ScoutSuite — multi-cloud security auditing:
  https://jonathansblog.co.uk/scoutsuite-multi-cloud-security-auditing
- ScoutSuite AWS checklist w/ commands — RedFox Security:
  https://www.redfoxsec.com/blog/scoutsuite-aws-checklist-complete-aws-security-testing-and-pentesting-guide-with-commands
- Pacu checklist w/ commands — RedFox Security:
  https://www.redfoxsec.com/blog/pacu-checklist-for-aws-security-testing-pentesting-with-commands
- Cloud pentesting tools (Pacu/ScoutSuite/Prowler) — Red Team Guide:
  https://redteamguide.com/tools/cloud-pentesting-tools-2026/
- What is a CIS Benchmark — Prowler glossary:
  https://prowler.com/cloud-security-glossary/what-is-a-cis-benchmark

## Storage exposure (S3 / GCS / Azure Blob)
- Cloud storage buckets exposed publicly — Sourcery vuln DB:
  https://www.sourcery.ai/vulnerabilities/cloud-storage-public-buckets
- Public S3/GCS/Azure bucket leaks — FortWatch:
  https://fortwatch.ai/blog/public-cloud-buckets-s3-gcs-azure-leak-data
- Exploiting misconfigurations in Azure/AWS/GCP — Cyber Codex:
  https://aenosh-rajora.gitbook.io/cyber-codex/exploiting-misconfigurations-in-azure-aws-and-gcp

## Azure / Entra ID
- Cobalt — Microsoft Entra ID Pentesting: A Comprehensive Guide:
  https://www.cobalt.io/learning-center/microsoft-entra-id-pentesting-comprehensive-guide-azure-environment
- Cloud-Architekt AzureAD-Attack-Defense — ConsentGrant.md:
  https://github.com/Cloud-Architekt/AzureAD-Attack-Defense/blob/main/ConsentGrant.md
- Elastic Security — Entra ID Illicit Consent Grant via Registered Application:
  https://www.elastic.co/security-labs/entra-id-oauth-phishing-detection
- SlashID — Illicit Consent-Granting & App Backdooring (Entra persistence):
  https://www.slashid.dev/blog/entra-app-backdooring/
- Microsoft — Protect against consent phishing:
  https://docs.azure.cn/en-us/entra/identity/enterprise-apps/protect-against-consent-phishing

## GCP
- Rhino Security Labs — Privilege Escalation in GCP Part 1 (IAM):
  https://rhinosecuritylabs.com/gcp/privilege-escalation-google-cloud-platform-part-1/
- Praetorian — GCP Service Account-based Privilege Escalation paths:
  https://www.praetorian.com/blog/google-cloud-platform-gcp-service-account-based-privilege-escalation-paths/
- HackTricks Cloud — GCP IAM Privesc:
  https://cloud.hacktricks.wiki/en/pentesting-cloud/gcp-security/gcp-privilege-escalation/gcp-iam-privesc.html
- Stratus Red Team — Impersonate GCP Service Accounts:
  https://stratus-red-team.cloud/attack-techniques/GCP/gcp.privilege-escalation.impersonate-service-accounts/

## Kubernetes & containers
- Datadog Security Labs — Unauthenticated privileged access to K8s API Server:
  https://securitylabs.datadoghq.com/cloud-security-atlas/vulnerabilities/unauthenticated-api-server/
- raesene — Let's talk about anonymous access to Kubernetes:
  https://raesene.github.io/blog/2023/03/18/lets-talk-about-anonymous-access-to-Kubernetes/
- kube-hunter KB — KHV051 Exposed Privileged Containers via Secure Kubelet Port:
  https://aquasecurity.github.io/kube-hunter/kb/KHV051.html
- Kubernetes docs — RBAC Good Practices:
  https://kubernetes.io/docs/concepts/security/rbac-good-practices/
- Kubernetes docs — Authenticating (anonymous auth):
  https://kubernetes.io/docs/reference/access-authn-authz/authentication/
- SecureFlag — Broken Authorization in Kubernetes:
  https://knowledge-base.secureflag.com/vulnerabilities/broken_authorization/broken_authorization_kubernetes.html
- kube-bench / kube-hunter hardening guide — Medium (bavicnative):
  https://medium.com/@bavicnative/kubernetes-security-hardening-a-detailed-guide-using-kube-bench-and-kube-hunter-5aa18368197d

## Standards / benchmarks (referenced throughout)
- CIS Benchmarks (AWS Foundations, Azure, GCP, Kubernetes) — https://www.cisecurity.org/cis-benchmarks
- OWASP Cloud-Native Security / OWASP Top 10 — https://owasp.org
- AWS / Azure / GCP provider security documentation (IMDSv2, managed identities,
  Workload Identity, metadata server, Block Public Access, Public Access
  Prevention) — vendor docs.
