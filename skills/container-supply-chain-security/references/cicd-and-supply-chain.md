# CI/CD Security & Software Supply Chain

Reference for the OWASP Top 10 CI/CD Security Risks (CICD-SEC-1..10), Poisoned
Pipeline Execution, runner/token abuse, and the software supply chain
(dependency confusion, typosquatting, SBOM, signing, provenance, IaC scanning).

Base doctrine: `safe-testing-doctrine`. **Do not** commit real secrets to
trigger a pipeline, do not exfiltrate secrets off-platform, do not publish
packages to real public feeds, and do not push malicious images to shared
registries. Prove gaps with benign markers on your own fork/feature branch and
revert.

---

## Part A — OWASP Top 10 CI/CD Security Risks

Reference framework throughout: OWASP Top 10 CI/CD Security Risks
(CICD-SEC-1..10). Map every finding to its CICD-SEC ID in the report.

| ID | Risk |
|----|------|
| CICD-SEC-1 | Insufficient Flow Control Mechanisms |
| CICD-SEC-2 | Inadequate Identity & Access Management |
| CICD-SEC-3 | Dependency Chain Abuse |
| CICD-SEC-4 | Poisoned Pipeline Execution (PPE) |
| CICD-SEC-5 | Insufficient PBAC (Pipeline-Based Access Controls) |
| CICD-SEC-6 | Insufficient Credential Hygiene |
| CICD-SEC-7 | Insecure System Configuration |
| CICD-SEC-8 | Ungoverned Usage of 3rd-Party Services |
| CICD-SEC-9 | Improper Artifact Integrity Validation |
| CICD-SEC-10 | Insufficient Logging & Visibility |

### A.1 Poisoned Pipeline Execution — CICD-SEC-4 (most exploited)

An attacker who can influence files the pipeline executes (CI config, referenced
scripts, Makefiles, build hooks) runs code in the build environment and steals
its secrets/tokens. Three variants:
- **Direct (D-PPE):** attacker edits the pipeline definition itself (`.github/
  workflows/*.yml`, `.gitlab-ci.yml`, `Jenkinsfile`).
- **Indirect (I-PPE):** pipeline config is protected, but the pipeline runs
  files the attacker *can* edit (`Makefile`, `npm run build` scripts, test
  code, `tox.ini`, pre-commit).
- **Public (3PE / pwn-request):** a fork PR triggers a privileged workflow
  (`pull_request_target`, self-hosted runner on PRs) that runs untrusted code
  with repo secrets.

**HOW TO FIND (safe, read-only):**
```bash
# GitHub: workflows that run on untrusted input with secrets in scope
grep -RniE 'pull_request_target|workflow_run' .github/workflows/
grep -RniE 'actions/checkout' .github/workflows/ | grep -i 'ref'      # checking out PR head?
grep -RniE '\$\{\{\s*github\.event\.(issue|pull_request|comment)' .github/workflows/  # script injection sink
# Static analysers for PPE / expression injection:
actionlint
zizmor .github/workflows/                     # PPE, injection, unpinned actions
# Self-hosted runner used on public/fork PRs?
grep -RniE 'runs-on:\s*(self-hosted|\[.*self-hosted)' .github/workflows/
```

**HOW TO TEST safely (RoE + your own fork/branch only):** Demonstrate the sink
with a **benign** command that proves code execution and secret *scope* without
disclosing values:
```yaml
# On YOUR fork/feature branch only. Benign PoC — no secret exfil.
- run: |
    echo "PPE-POC $(whoami)@$(hostname)"
    echo "secrets in env: $(env | grep -c -i 'TOKEN\|SECRET')"   # COUNT only, never print values
```
For the classic expression-injection sink, prove with a harmless string, never a
reverse shell. Revert the branch and record in cleanup. **Never** print token
values or send them off-platform.

**Real reference:** OWASP CICD-SEC-4; the **tj-actions/changed-files** compromise
(CVE-2025-30066, Mar 2025) — a malicious payload dumped runner memory and leaked
CI secrets to logs across 23k+ repos (root cause: compromised PAT →
reviewdog/action-setup → tj-actions). CISA alert + Wiz/Unit42/StepSecurity
write-ups.

**Detection:** required-review on workflow changes; alert on
`pull_request_target` + PR checkout; StepSecurity Harden-Runner egress
monitoring; secret-scanning of logs.
**Remediation:** never run untrusted code with secrets; use `pull_request` (no
secrets) for fork CI; least-privilege `GITHUB_TOKEN` (`permissions:` block);
approvals for first-time contributors; no self-hosted runners on public repos.

### A.2 Insufficient Flow Control — CICD-SEC-1 (branch protection gaps)

**HOW TO FIND (safe):**
```bash
gh api repos/OWNER/REPO/branches/main/protection            # required reviews? status checks?
gh api repos/OWNER/REPO/rulesets
gh repo view OWNER/REPO --json defaultBranchRef
# Can a single actor push to main / merge own PR / bypass review?
```
Findings: no required reviews, admins can bypass, force-push allowed, no
required status checks, no CODEOWNERS on pipeline files.
**Remediation:** required reviews (≥1, disallow self-approval), required checks,
no force-push, CODEOWNERS on `.github/`, signed commits. CICD-SEC-1.

### A.3 Identity/token abuse & OIDC — CICD-SEC-2 / CICD-SEC-6

- **Over-scoped `GITHUB_TOKEN`** (`permissions: write-all`) → tamper with the
  repo/releases.
- **OIDC cloud federation with loose trust** — a `sub`/`aud` condition that
  matches any repo/branch lets other workflows assume the cloud role.

**HOW TO FIND (safe):**
```bash
grep -RniE 'permissions:' .github/workflows/                    # default = too broad?
grep -RniE 'id-token:\s*write' .github/workflows/               # OIDC in use
# Cloud side: inspect the trust policy condition (read-only) — is repo:*/ref:* too loose?
aws iam get-role --role-name gha-deploy --query 'Role.AssumeRolePolicyDocument'
```
**HOW TO TEST safely:** Report the loose `sub` condition as the finding.
Demonstrating cross-repo assumption should be done only in a lab; if RoE
authorises, dump the OIDC token **claims** (decode the JWT header/payload — no
signature use) to show the `sub`/`aud`, without actually assuming the role.
**Real reference:** OWASP CICD-SEC-2/-6; numerous disclosed GitHub OIDC
misconfigs allowing role assumption from unintended repos/branches.
**Remediation:** minimal `permissions:`; tightly scope OIDC trust to
`repo:ORG/REPO:ref:refs/heads/main` (and environment); short-lived tokens; no
long-lived cloud keys in CI. 

### A.4 Self-hosted runner compromise — CICD-SEC-5/-7

Non-ephemeral self-hosted runners persist state between jobs; a poisoned job can
implant into the host, and fork PRs can land code on them.

**HOW TO FIND (safe):** identify self-hosted runners (§A.1 grep), check whether
they are ephemeral, whether they run on public repos, and their network egress.
**Remediation:** ephemeral runners (fresh VM per job), never on public repos,
network egress allowlist, hardened images, no shared runners across trust
boundaries.

### A.5 Insufficient Logging — CICD-SEC-10

Check audit logging is on for the SCM/CI, retained, and monitored (pipeline
config changes, secret access, runner registration).

---

## Part B — Software Supply Chain

### B.1 Dependency confusion — CICD-SEC-3

If an internal package name (e.g. `@acme/auth-lib`, `acme-internal-utils`) is
**not** reserved on the public registry, an attacker publishes a higher-version
public package with that name and the build pulls the malicious public one.

**HOW TO FIND (safe, read-only):**
```bash
# Enumerate internal/private names referenced in manifests & lockfiles
jq -r '.dependencies,.devDependencies | keys[]?' package.json
grep -RhoE '^[A-Za-z0-9._-]+' requirements.txt 2>/dev/null
# Are those names claimed on the public registry? (read-only existence check)
npm view @acme/auth-lib version 2>&1 | head -1          # 404 = unclaimed = confusable
pip index versions acme-internal-utils 2>&1 | head -1
# Is the private scope pinned to a registry? (config that prevents confusion)
cat .npmrc 2>/dev/null; grep -i 'index-url\|extra-index-url' pip.conf 2>/dev/null
```
A private name that returns 404 publicly **and** an install config that falls
back to the public registry = confusable.

**HOW TO TEST safely:** The finding is the *unclaimed name + fallback config*.
**Do not** publish a real package to npm/PyPI to "prove" it. If RoE requires a
live proof, coordinate with the client to publish a **benign, clearly-marked
placeholder** to a controlled/internal registry (or use `--dry-run`), never a
callback/exfil payload on the public feed.

**Real reference:** Alex Birsan, *"Dependency Confusion"* (2021) — benign
DNS-callback packages executed inside Apple, Microsoft, PayPal, Shopify, Tesla
and others; whitehat, bug-bounty paid. This is the canonical case; mirror its
**benign** methodology.

**Detection:** dependency-firewall/proxy (Artifactory/Nexus/Cloudsmith) that
blocks public resolution of internal names; alerts on new public packages
matching internal namespaces.
**Remediation:** reserve internal names/scopes publicly; pin private packages to
a specific internal registry (`.npmrc` scope→registry, pip `--index-url` only);
verify integrity hashes; namespace with a claimed org scope.

### B.2 Typosquatting & malicious packages — CICD-SEC-3

**HOW TO FIND (safe):**
```bash
# Compare declared deps against known-good names; look for near-misses & recent installs
trivy fs --scanners vuln .                     # flags known-malicious versions in some feeds
# Manual: check for typo'd popular names (e.g. python "requsts", "python3-dateutil"),
# postinstall scripts, and packages published very recently by low-rep authors.
npm view <pkg> maintainers time.created
jq '.scripts' package.json                     # suspicious pre/postinstall
```
**Real reference:** numerous PyPI/npm typosquat campaigns (`crossenv`,
`python3-dateutil`, `colourama`, etc.); ongoing.
**Remediation:** allowlist dependencies, review new deps, disable install
scripts where possible (`npm ci --ignore-scripts`), use a curated proxy.

### B.3 Lockfile & integrity — CICD-SEC-9

**HOW TO FIND (safe):**
```bash
ls package-lock.json yarn.lock Pipfile.lock poetry.lock go.sum Cargo.lock 2>/dev/null
# Are integrity hashes present & enforced?
grep -c 'integrity' package-lock.json
grep -c 'hash' poetry.lock
# Is CI using pinned installs?  npm ci (not npm install) / pip --require-hashes
grep -RniE 'npm ci|--require-hashes|--frozen-lockfile' .github/ ci/ Makefile 2>/dev/null
```
**Remediation:** commit lockfiles, enforce hashes (`npm ci`,
`pip install --require-hashes`, `--frozen-lockfile`), pin transitive deps.

### B.4 SBOM generation & review — CICD-SEC-9

**HOW TO FIND / GENERATE (safe, read-only):**
```bash
syft dir:. -o spdx-json > sbom.spdx.json        # or: syft <image> -o cyclonedx-json
trivy image --format cyclonedx -o sbom.json <image>
grype sbom:sbom.spdx.json                        # vuln-match the SBOM
# Verify an artifact ships an SBOM attestation:
cosign download sbom <image> 2>/dev/null || echo "no SBOM attached"
```
**Remediation:** generate & publish SBOMs (SPDX/CycloneDX) per build, attach as
signed attestations, gate on SBOM-based vuln policy. Aligns with SLSA provenance
and US EO 14028 / NTIA minimum-SBOM elements.

### B.5 Artifact signing & provenance — cosign / sigstore / SLSA — CICD-SEC-9

**HOW TO FIND / VERIFY (safe, read-only):**
```bash
# Is the image signed? Verify (keyless / Fulcio identity):
cosign verify --certificate-identity-regexp '.*' \
  --certificate-oidc-issuer-regexp '.*' registry.example.com/app:1.4.2
# Verify SLSA build provenance attestation:
cosign verify-attestation --type slsaprovenance \
  --certificate-identity-regexp '.*' \
  --certificate-oidc-issuer-regexp '.*' registry.example.com/app:1.4.2
# Inspect provenance predicate (builder id, source repo, materials):
cosign download attestation registry.example.com/app:1.4.2 | jq -r '.payload' | base64 -d | jq
```
`cosign verify*` is read-only. Unsigned images / no provenance / a provenance
`builderId` that isn't the expected build platform = finding.

**SLSA build track (map remediation to a level):**
- **L1** — provenance exists (builder id, source, artifact digest); forgeable.
- **L2** — hosted build platform generates & **signs** provenance
  automatically → tamper-evident.
- **L3** — hardened, isolated builds; signing keys inaccessible to build steps →
  strong tamper-resistance and non-falsifiable provenance.

**Real reference:** SLSA v1.0 spec (slsa.dev); Sigstore/cosign docs; **SolarWinds
(2020)** — build-system compromise injected SUNBURST into signed artifacts, the
motivating case for build-integrity/provenance; **Codecov (2021)** — modified
Bash Uploader exfiltrated CI env-var secrets, motivating uploader integrity
verification (SHA checksum).

**Detection:** admission controllers (Kyverno/Sigstore policy-controller/
Connaisseur) that **require valid signatures + provenance** before deploy.
**Remediation:** sign all artifacts (keyless sigstore), generate & verify SLSA
provenance (target L2→L3), enforce signature/provenance at admission, verify
third-party tool checksums (the Codecov lesson).

### B.6 XZ backdoor (CVE-2024-3094) — build-time supply-chain lesson

A multi-year social-engineering campaign by maintainer persona "Jia Tan"
implanted a backdoor into **xz-utils / liblzma 5.6.0 and 5.6.1**; the malicious
code hid in test fixtures and activated during the **build** (via `configure`/
`m4` macros) to hook OpenSSH's `sshd` RSA verification for pre-auth RCE. Caught
by Andres Freund (Microsoft) noticing ~500 ms extra `sshd` latency.

**HOW TO FIND (safe):**
```bash
xz --version                              # 5.6.0 / 5.6.1 = suspect (CVE-2024-3094)
trivy fs --scanners vuln /               # flags vulnerable xz/liblzma
# Watch for build-time code in test blobs / obfuscated m4 in dependencies.
```
**Real reference:** CVE-2024-3094 (CVSS 10); Freund's oss-security disclosure;
CISA/Red Hat advisories. Lesson: review **build scripts and test fixtures**, not
just source; pin & verify upstream; prefer reproducible builds (SLSA).
**Remediation:** downgrade/patch xz; SBOM to find exposure; reproducible builds;
scrutinise build-time artifacts and maintainer changes.

### B.7 Secrets in repos & CI config — CICD-SEC-6

**HOW TO FIND (safe, read-only):**
```bash
gitleaks detect --source . --redact             # scans working tree
gitleaks detect --source . --log-opts="--all"   # full git history
trufflehog git file://. --only-verified         # verifies live secrets
trivy fs --scanners secret .
```
Validate any hit read-only (see `offensive-osint` validators), record 4-6 chars,
flag for rotation. **Remediation:** secret managers/OIDC (no static creds),
pre-commit secret scanning, history purge + rotation. CICD-SEC-6.

---

## Part C — Infrastructure-as-Code scanning

**HOW TO FIND (safe, read-only):**
```bash
checkov -d .                                     # Terraform/CFN/K8s/Helm/ARM/Dockerfile
tfsec .                                          # Terraform-focused
trivy config .                                   # IaC + Dockerfile misconfig
kics scan -p .                                   # multi-IaC
# Terraform state can contain plaintext secrets — check it's remote+encrypted+locked:
grep -RniE 'backend "s3"|backend "azurerm"|backend "gcs"' *.tf
```
Common findings: public security-group/`0.0.0.0/0`, unencrypted storage, public
buckets, permissive IAM, hardcoded secrets, plaintext Terraform state, missing
logging. Cross-reference `cloud-security-testing` for the cloud-resource impact.
**Remediation:** fix flagged rules, encrypt & lock remote state, gate IaC scans
in CI (fail on high), least-privilege modules. Maps to CIS cloud benchmarks.

---

## Quick triage checklist (all read-only)

```bash
# CI/CD
grep -RniE 'pull_request_target|self-hosted|permissions:' .github/workflows/
actionlint; zizmor .github/workflows/
gh api repos/OWNER/REPO/branches/main/protection
# Supply chain
syft dir:. -o spdx-json | tee sbom.json ; grype sbom:sbom.json
npm view <internal-pkg> version              # dependency-confusion existence check
cosign verify <image> ; cosign verify-attestation --type slsaprovenance <image>
gitleaks detect --source . --redact
# IaC
checkov -d . ; tfsec . ; trivy config .
```
Report each with its CICD-SEC ID and/or SLSA level, detection, and remediation.
