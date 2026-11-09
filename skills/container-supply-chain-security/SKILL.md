---
name: container-supply-chain-security
description: "Operational playbook for authorized security testing of containers, Kubernetes, CI/CD pipelines, and the software supply chain. Goes deeper than the cloud skill's Kubernetes section. Covers Docker/OCI image analysis (layer/history secrets, Dockerfile misconfig, dive/trivy/syft), dangerous runtime posture (--privileged, CAP_SYS_ADMIN and other capabilities, host mounts, exposed docker.sock, hostPID/hostNetwork/hostIPC), and CONTAINER ESCAPE techniques (privileged, mounted docker socket, /proc & cgroups release_agent, CVE-2019-5736 runc, CVE-2024-21626 Leaky Vessels) — described safely and marked when risky. Deep Kubernetes: RBAC audit (kubectl auth can-i --list), service-account token abuse, pod security (privileged pods, hostPath, PSA/PSP), exposed etcd/kubelet/API server, network-policy gaps, secrets in configmaps, admission control, node-compromise paths, and read-only use of kube-bench/kube-hunter/kubeaudit/amicontained/Peirates. CI/CD security around the OWASP Top 10 CI/CD Security Risks (CICD-SEC-1..10): Poisoned Pipeline Execution (direct/indirect/public), secrets exfiltration, OIDC/token abuse, self-hosted runner compromise, untrusted/unpinned third-party Actions, branch-protection & flow-control gaps. Software supply chain: dependency confusion (Alex Birsan), typosquatting, malicious packages, lockfile integrity, SBOM (syft), artifact signing and provenance (cosign/sigstore/SLSA), and IaC scanning (checkov/tfsec/kics). Grounded in OWASP, CIS Docker/Kubernetes Benchmarks, CNCF/Kubernetes docs, the SLSA framework, MITRE ATT&CK, and disclosed incidents (SolarWinds, Codecov, dependency confusion, XZ CVE-2024-3094, tj-actions CVE-2025-30066). For each finding: how to FIND it with safe commands, how to TEST safely, a real public reference, detection, and remediation mapped to CIS/SLSA controls. Authorized, in-scope engagements only — strong read-only scanning bias; escape PoCs only in a lab or under explicit RoE. Use when planning or executing an authorized container/K8s/CI-CD/supply-chain assessment, hardening review, or writing those findings."
version: 1.0.0
triggers:
  - docker security
  - container security
  - kubernetes rbac
  - kubernetes security
  - container escape
  - privileged container
  - docker socket
  - kube-hunter
  - kube-bench
  - kubeaudit
  - peirates
  - ci/cd security
  - poisoned pipeline
  - github actions security
  - self-hosted runner
  - dependency confusion
  - typosquatting
  - sbom
  - syft
  - supply chain security
  - image scanning
  - trivy
  - grype
  - cosign
  - sigstore
  - slsa provenance
  - iac scanning
  - checkov
  - tfsec
---

# Container & Supply-Chain Security (Authorized Testing)

Operational playbook for finding, safely proving, and reporting weaknesses in
**container images, Kubernetes clusters, CI/CD pipelines, and the software
supply chain**. This is the deep companion to `cloud-security-testing`: that
skill covers managed-K8s exposure from the cloud/IAM side; this skill goes
deeper into cluster-internal RBAC, pod security, container-escape technique,
pipeline poisoning, and dependency/artifact integrity.

Grounded in public material: OWASP (CI/CD Security Top 10, Kubernetes & Docker
Security Cheat Sheets), CIS Docker/Kubernetes Benchmarks, CNCF/Kubernetes docs,
the SLSA framework, MITRE ATT&CK (Containers matrix), and disclosed incidents
(SolarWinds, Codecov, Alex Birsan's dependency confusion, XZ CVE-2024-3094,
tj-actions CVE-2025-30066).

The strong bias throughout is **read-only scanning and enumeration**: image
scanners (`trivy`, `grype`, `syft`, `dive`), `kubectl auth can-i --list`,
`kube-bench`, `kubeaudit`, and static IaC scanners find the overwhelming
majority of real findings without mutating anything. Container-escape and
pipeline-poisoning proofs are the sharp edge — they are for **your own lab or
an explicitly RoE-authorized target**, kept to the minimum proof, and several
of them can crash a node (marked ⚠️ below).

## ⚠️ Safety — read first (inherits `safe-testing-doctrine`)

This skill operates under the mandatory `safe-testing-doctrine`. Load it before
any active work. Container/K8s/CI-CD-specific hard limits on top of the base
doctrine:

- **No destruction.** Do not delete or overwrite images, tags, registries,
  clusters, namespaces, pipelines, workflow files, or artifacts. No
  `kubectl delete`, no `docker rmi`, no registry deletions, no force-pushes to
  protected branches. Scanning and `get`/`describe`/`auth can-i` are the
  default verbs.
- **No DoS / availability impact.** No fork/CPU/memory bombs in containers, no
  crash-testing kubelet/API server, no flooding a registry or CI system with
  builds. Several **container-escape PoCs can panic or destabilise the node**
  (cgroup `release_agent`, some kernel-primitive escapes) — those are marked
  ⚠️ and are lab-only unless the RoE explicitly authorises node disruption in a
  maintenance window.
- **Escape PoCs: lab or explicit RoE only.** Reproduce container escapes on a
  disposable lab node/cluster you own, or on an in-scope target only with
  written authorisation. Prove escape with a benign marker (read `/etc/hostname`
  of the host, `id` in the host namespace, list host processes) — never
  pivot, never touch other tenants, never persist.
- **Don't poison shared systems.** Do not push malicious/backdoored images to
  shared registries. Do not publish typosquat/dependency-confusion packages to
  real public feeds (npm/PyPI/RubyGems/Maven) — demonstrate the *gap* (an
  internal name resolvable publicly, an unscoped install order) using a
  **private, controlled, clearly-marked** proof package or a dry-run, never a
  live public upload. Do not commit real secrets to trigger a pipeline.
- **CI/CD: reversible, minimal, logged.** When RoE authorises a Poisoned
  Pipeline Execution proof, use a benign command (`whoami`, `env | grep -c
  SECRET` without printing values, an OIDC token *claims* dump without using
  the token) on a **feature branch / your own fork**, then revert. Never
  exfiltrate real secrets off-platform; redact them in evidence.
- **Registry & token hygiene.** Treat any credential, service-account token, or
  registry pull secret you encounter as sensitive: record its existence and
  scope, do not reuse it beyond minimal proof, and flag it for rotation in the
  report.
- **No leftover artifacts. Cleanup.** Remove any test image, pod, job,
  namespace label, branch, or workflow you created. Track every mutation in a
  cleanup list for the report (see `security-reporting`).

Complements `cloud-security-testing` (managed-K8s control plane, cloud IAM
bindings to clusters, IMDS from pods). Use `pentest-methodology` for phases and
`security-reporting` for write-ups.

## Toolbox (read-only bias)

| Tool | Scope | Note |
|------|-------|------|
| **trivy** | image / fs / repo / IaC / K8s / SBOM | Vuln + misconfig + secret + license scan; read-only workhorse |
| **grype** + **syft** | image / fs | `syft` = SBOM generation; `grype` = vuln match against SBOM/image |
| **dive** | image | Layer-by-layer explorer; find secrets & wasted layers |
| **docker** / **crane** / **skopeo** | image/registry | Inspect history, config, manifests **without pulling/running** (crane/skopeo) |
| **kubectl** | cluster | `auth can-i --list`, `get`, `describe` — safest enumeration |
| **kube-bench** | cluster/node | CIS Kubernetes Benchmark checker (read-only) |
| **kube-hunter** | cluster | Recon; run `--passive` / remote first (active probes can be intrusive). Aqua-archived but still usable |
| **kubeaudit** | manifests/cluster | Audits pods for security-context issues (read-only) |
| **amicontained** | in-container | Reports capabilities, namespaces, seccomp — "am I in a container and how locked down" |
| **Peirates** | cluster (in-pod) | K8s post-exploitation — **many modules mutate/escalate**; use enumeration/`auth can-i`-style options only, under RoE |
| **checkov / tfsec / kics** | IaC (Terraform/CFN/K8s/Helm) | Static misconfig scanners (read-only) |
| **gitleaks / trufflehog** | repo/history | Secret scanning of source & git history (read-only) |
| **cosign / sigstore** | artifacts | Verify signatures & SLSA provenance (`cosign verify` = read-only) |
| **actionlint / zizmor** | GitHub workflows | Static analysis of Actions workflows for PPE/injection |

## How to use this skill

1. **Confirm scope + RoE.** Which registries, clusters/namespaces, repos, and
   CI systems are in scope. Confirm whether escape PoCs and any pipeline
   execution are authorised, and in which environment (lab vs. staging vs.
   prod-with-window).
2. **Enumerate read-only first.** Scan images (`trivy`, `syft`/`grype`, `dive`),
   audit the cluster (`kubectl auth can-i --list`, `kube-bench`, `kubeaudit`),
   and scan repos/IaC (`gitleaks`, `checkov`). This finds most issues.
3. **Map to the right reference** using the index below.
4. **Prove safely.** Use the per-finding SAFE method. Stop at minimum proof.
   Mark and gate ⚠️ node-disrupting escapes to lab/RoE.
5. **Report** with CIS/SLSA control mapping, detection, and remediation.

## Index — area → reference file

| Area | Reference |
|------|-----------|
| Docker/OCI images (history/layer secrets, Dockerfile misconfig, dive/trivy/syft), runtime posture (`--privileged`, capabilities, host mounts, docker.sock), **container escapes** (privileged, docker.sock, /proc release_agent, CVE-2019-5736, CVE-2024-21626) | [references/containers.md](references/containers.md) |
| Kubernetes deep: RBAC audit & privesc, service-account token abuse, pod security (privileged/hostPath/hostPID/PSA), exposed etcd/kubelet/API, network-policy gaps, secrets in configmaps, admission control, node-compromise paths, kube-hunter/Peirates/amicontained | [references/kubernetes.md](references/kubernetes.md) |
| CI/CD & supply chain: OWASP CICD-SEC-1..10, Poisoned Pipeline Execution, secrets exfil, OIDC/token abuse, self-hosted runners, unpinned Actions, dependency confusion, typosquatting, lockfile integrity, SBOM (syft), signing & provenance (cosign/sigstore/SLSA), IaC scanning | [references/cicd-and-supply-chain.md](references/cicd-and-supply-chain.md) |
| Public source URLs consulted | [references/sources.md](references/sources.md) |

## Cross-references

- **Managed-K8s control plane & cloud IAM to clusters** (EKS/GKE/AKS, IMDS
  from pods, node IAM roles) — `cloud-security-testing`.
- **Exposed Docker/K8s API as a network service** (unauth `:2375`, kubelet
  `:10250`) — `network-service-exploitation` has the discovery side; this skill
  covers what to do with access, safely.
- **Named container/orchestrator CVEs** (fingerprint + safe validation) —
  `cve-knowledge-base`; web-facing CI apps (GitLab, Jenkins) —
  `web-cve-exploitation`.
- **Secrets found in images/repos/CI** — validate with `offensive-osint`
  read-only validators; **reporting/scoring** — `security-reporting`.
