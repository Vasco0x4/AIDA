---
name: cloud-security-testing
description: "Operational playbook for authorized cloud security assessment across AWS, Azure/Entra ID, GCP, and Kubernetes/containers. Focuses on the common, high-frequency misconfigurations and vuln classes that appear in public breach reports, CIS Benchmarks, and OWASP Cloud-Native guidance: over-permissioned IAM and privilege-escalation paths (iam:PassRole, sts:AssumeRole, GCP impersonation, Entra consent/role abuse, managed identities), public storage exposure (S3/GCS/Azure Blob), metadata/SSRF credential theft (IMDSv1 vs IMDSv2, Azure/GCP metadata — Capital One), public compute exposure (public snapshots/AMIs, Lambda env secrets, exposed databases), Kubernetes exposure (anonymous auth, exposed kubelet/API server/dashboards, over-privileged RBAC, secrets in configmaps, privileged pods), and secrets in code/CI-CD/Terraform state. For each class: safe read-only enumeration (aws/az/gcloud CLI describe-list-get, ScoutSuite, Prowler, Pacu, kube-bench/kube-hunter, kubectl auth can-i), a SAFE proof-of-concept methodology, a real public reference, detection, and remediation mapped to CIS controls. Use when planning or executing an authorized cloud pentest/config audit, reviewing IAM or storage exposure, reproducing a cloud finding, or writing cloud findings with remediation."
version: 1.0.0
triggers:
  - aws pentest
  - azure pentest
  - gcp pentest
  - cloud pentest
  - cloud security assessment
  - iam privilege escalation
  - s3 bucket
  - public bucket
  - imds ssrf
  - metadata service
  - kubernetes security
  - k8s pentest
  - entra id
  - azure ad
  - oauth consent grant
  - managed identity
  - service account impersonation
  - scoutsuite
  - prowler
  - pacu
  - kube-hunter
  - cloud misconfiguration
  - terraform state
---

# Cloud Security Testing (Authorized Assessment)

Operational playbook for finding, safely proving, and reporting the cloud
misconfigurations that actually cause breaches — over-permissioned IAM,
public storage, metadata/SSRF credential theft, exposed compute/databases,
and weak Kubernetes posture. Optimized for **authorized** cloud pentests,
configuration audits, and in-scope engagements. Grounded in public breach
post-mortems (Capital One 2019), CIS Benchmarks, OWASP Cloud-Native guidance,
and vendor security docs.

The strong bias throughout is **read-only enumeration**: `describe` / `list` /
`get` API calls and read-only audit tools (ScoutSuite, Prowler, CIS scanners)
find the overwhelming majority of real cloud findings without touching a single
resource. Reach for write actions only when the Rules of Engagement (RoE)
explicitly authorize a scoped, reversible, logged change to prove impact.

## ⚠️ Safety — read first (inherits `safe-testing-doctrine`)

This skill operates under the mandatory `safe-testing-doctrine`. Load it before
any active work. Cloud-specific hard limits on top of the base doctrine:

- **Authorization + account scope.** Confirm written RoE naming the exact
  in-scope **account IDs / subscription IDs / project IDs**, regions, and
  services. Cloud blast radius crosses accounts fast — never pivot into an
  account, subscription, or project not named in scope. Verify which identity
  you are with `aws sts get-caller-identity` / `az account show` /
  `gcloud auth list` before touching anything.
- **NO DoS / availability impact.** No resource exhaustion, no mass API calls
  that trip throttling or rack up cost, no stopping/rebooting instances, no
  scaling actions. Cloud rate limits and billing make noisy testing itself a
  form of impact.
- **Read-only by default. NO deletion or modification** of cloud resources.
  Use `Describe*` / `List*` / `Get*` only. A write, create, tag, or config
  change is permitted **only** when RoE explicitly allows a **scoped,
  reversible, logged** change (e.g. create a throwaway resource you delete in
  the same session, snapshot-and-restore). Record every mutating call.
- **NO reading real customer data.** For public/exposed storage, list keys and
  read **at most ONE small benign object** to prove access, then stop and
  **redact** it in evidence. Never bulk-download. Never exfiltrate PII/PHI/card
  data — proving *listability* and *one header* is enough for the report.
- **Discovered live credentials: prove, don't use.** If enumeration or an SSRF
  chain yields real credentials/tokens, prove they are valid with an **identity
  check only** — `aws sts get-caller-identity`, `az account show`,
  `gcloud auth list` — and STOP. Do not enumerate data, escalate, or move
  laterally with them beyond what the RoE authorizes. For the SSRF→metadata
  chain, stopping at reading the **role name** is the safe PoC.
- **NO leaving created resources.** Anything you create under an authorized,
  scoped exception (a test IAM user, a temp key, a pod, a snapshot copy) must be
  **cleaned up** in the same engagement and logged in the report. Keep a
  teardown checklist.
- **Least-privilege enumeration.** Run audit tooling with a dedicated
  read-only principal (`ReadOnlyAccess` / `SecurityAudit` / Viewer) wherever
  possible, not admin. This bounds accidental impact and models real least
  privilege.
- **Evidence handling.** Store findings, ARNs, and screenshots in an
  engagement-scoped location; redact secrets and customer data before they
  land in the report.

If scope, account IDs, or authorization are unclear, **STOP** and ask the
operator before issuing any API call.

## How to use this skill

1. **Confirm identity + scope.** `sts get-caller-identity` / `az account show`
   / `gcloud config list`. Note account/subscription/project IDs against RoE.
2. **Baseline with a read-only scanner.** Run ScoutSuite and/or Prowler
   (AWS/Azure/GCP) or kube-bench/kube-hunter (K8s) with a read-only principal.
   These surface most misconfigurations with zero writes.
3. **Triage by impact.** Prioritize identity (privesc/wildcards), public
   storage/compute exposure, and metadata/SSRF chains — these map to the
   highest-severity public breaches.
4. **Prove safely.** Use the SAFE PoC methodology per finding class in the
   reference files. Stop at the minimum proof (identity check, one benign
   object, role name).
5. **Report** with CIS control mapping, detection guidance, and remediation.
   Use `security-reporting` for the write-up.

## Toolbox (read-only bias)

| Tool | Scope | Note |
|------|-------|------|
| `aws` / `az` / `gcloud` CLI | all | Native `describe`/`list`/`get` = safest enumeration |
| **ScoutSuite** | AWS/Azure/GCP/K8s | Read-only multi-cloud audit; needs `ReadOnlyAccess`/`SecurityAudit` |
| **Prowler** | AWS/Azure/GCP/K8s | Read-only; CIS/NIST/PCI compliance mapping |
| **Pacu** | AWS | Post-exploitation framework — many modules mutate; use enum/privesc-scan (`--offline`) modules only under RoE |
| **CloudSploit / Cloudsplaining** | AWS/multi | Read-only policy & config analysis |
| **kube-bench** | K8s | CIS Kubernetes Benchmark checker (read-only) |
| **kube-hunter** | K8s | Passive/active recon — use `--passive` first; active probes can be intrusive |
| **Trivy** | images/IaC/K8s | Vuln + misconfig + secret scanning (read-only) |
| **ROADrecon / MicroBurst / AzureHound** | Azure/Entra | Enumeration; some modules mutate — read RoE |

## Index — area → reference file

| Area | Reference |
|------|-----------|
| AWS: IAM privesc, S3, IMDS/SSRF, snapshots/AMIs, Lambda, RDS, keys | [references/aws.md](references/aws.md) |
| Azure / Entra ID: RBAC & consent abuse, app registrations, managed identity, Blob, CosmosDB | [references/azure-entra.md](references/azure-entra.md) |
| GCP: SA key abuse & impersonation, IAM privesc, GCS, metadata, Firestore | [references/gcp.md](references/gcp.md) |
| Kubernetes & containers: API/kubelet exposure, anon auth, RBAC, secrets, privileged pods, dashboards | [references/kubernetes-containers.md](references/kubernetes-containers.md) |
| Public source URLs consulted | [references/sources.md](references/sources.md) |

## Cross-references

- **SSRF that reaches cloud metadata** — the web-app entry point for the
  Capital One-style chain is in `web-vuln-hunting` (SSRF section). This skill
  covers the cloud side (IMDSv1/v2, what to do with a stolen role) and keeps
  the PoC to reading a **role name**.
- **External attack surface / bucket discovery** — `offensive-osint` covers
  cloud bucket permutation/discovery from outside the account.
- **Reporting** — `security-reporting`; **engagement phases** —
  `pentest-methodology`.
