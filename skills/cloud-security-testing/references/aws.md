# AWS — Authorized Assessment Reference

Read-only bias throughout. Confirm identity/scope first:

```bash
aws sts get-caller-identity            # who am I / which account
aws configure list-profiles            # which profiles exist
aws ec2 describe-regions --query 'Regions[].RegionName' --output text
```

Baseline the whole account with read-only scanners before manual work:

```bash
# Prowler — CIS/NIST compliance mapping, read-only
prowler aws --profile audit -M html json-ocsf
prowler aws --profile audit -s iam s3 ec2 rds cloudtrail kms   # targeted services

# ScoutSuite — read-only multi-service audit (needs ReadOnlyAccess/SecurityAudit)
scout aws --profile audit --report-dir ./scout-out

# Pacu — enumeration/analysis modules only (many modules mutate; read RoE)
#   iam__enum_permissions, iam__privesc_scan (--offline uses gathered data)
```

---

## 1. Over-permissioned IAM, wildcard policies, privilege-escalation paths

### HOW TO FIND (read-only)
```bash
# List principals and inline/attached policies
aws iam list-users
aws iam list-roles --query 'Roles[].{Name:RoleName,Trust:AssumeRolePolicyDocument}'
aws iam list-policies --scope Local --only-attached

# Pull a policy document and look for wildcards
aws iam get-policy-version --policy-arn <arn> \
  --version-id $(aws iam get-policy --policy-arn <arn> --query 'Policy.DefaultVersionId' --output text) \
  --query 'PolicyVersion.Document'

# What can THIS identity actually do (offline analysis, no calls made against targets):
#   Cloudsplaining flags "resource exposure" + privesc from an authz details file
aws iam get-account-authorization-details > authz.json
cloudsplaining scan --input-file authz.json

# Pacu privesc scanner (offline analysis of already-enumerated perms)
#   run: iam__enum_permissions  then  iam__privesc_scan --offline
```
Red flags: `"Action": "*"`, `"Resource": "*"`, `"Effect": "Allow"` with
`iam:*`, `sts:AssumeRole` on `*`, `iam:PassRole` paired with a compute-create
permission, `iam:CreatePolicyVersion`, `iam:AttachUserPolicy`,
`iam:UpdateAssumeRolePolicy`, `lambda:CreateFunction`+`lambda:InvokeFunction`.

### HOW IT'S ABUSED (safe methodology)
Rhino Security Labs catalogued 20+ escalation primitives. The point of the
audit is to **identify** the path, not run it against production. Classic paths:
- **`iam:PassRole` + `ec2:RunInstances`** — pass a high-priv role to a new
  instance you control, read creds from its metadata.
- **`iam:PassRole` + `lambda:CreateFunction` + `lambda:InvokeFunction`** — run
  code as a passed high-priv role.
- **`iam:CreatePolicyVersion`** — set a new default policy version granting `*`.
- **`iam:UpdateAssumeRolePolicy` + `sts:AssumeRole`** — rewrite a role's trust
  policy to trust yourself, then assume it.

**SAFE PoC:** report the exploitable graph edge from Cloudsplaining/Pacu
`--offline` output (principal → permission → reachable admin). If the RoE
requires live proof, do it in a **scoped throwaway**: create a test role, pass
it, assume it, run `sts get-caller-identity` to show the elevated identity, then
delete every created object in the same session and log it. Never escalate
against real production roles.

### Real public reference
Rhino Security Labs, "AWS IAM Privilege Escalation – Methods and Mitigation"
(and the RhinoSecurityLabs/AWS-IAM-Privilege-Escalation repo). Tenable /
Praetorian `iam:PassRole` write-ups.

### Detection
CloudTrail: `CreatePolicyVersion`, `AttachUserPolicy`, `UpdateAssumeRolePolicy`,
`PassRole` events, `RunInstances`/`CreateFunction` with an unusual role,
`AssumeRole` from unexpected principals. GuardDuty
`PrivilegeEscalation:IAMUser/*`.

### Remediation (CIS AWS Foundations)
Least privilege; no wildcard `Action`/`Resource`; scope `iam:PassRole` with a
`Condition` on the role ARN; avoid attaching admin to users; use permission
boundaries and SCPs. CIS 1.15–1.17 (policies to roles/groups, least privilege).

---

## 2. Long-lived access keys & cross-account trust

### HOW TO FIND
```bash
aws iam list-access-keys --user-name <u>
aws iam get-credential-report --output text --query Content | base64 -d > cred_report.csv
# look for access_key_1_last_rotated older than 90d, unused active keys,
# root account with active keys/no MFA
aws iam get-account-summary        # AccountMFAEnabled, root key presence

# Cross-account trust: any role trusting an external/"*" principal
aws iam list-roles --query \
 'Roles[?contains(to_string(AssumeRolePolicyDocument),`":root"`)].RoleName'
```
Red flags: keys older than 90 days, unused keys still active, root access keys,
trust policies with `"Principal":{"AWS":"*"}` or a foreign account with no
`sts:ExternalId` condition (confused-deputy risk).

### HOW IT'S ABUSED
Leaked long-lived keys are the #1 cloud initial-access vector. **SAFE PoC** for
a discovered key: prove validity with `aws sts get-caller-identity` **only**,
then stop. Do not enumerate data or escalate.

### Real public reference
CIS AWS Foundations Benchmark (key rotation, root MFA); countless public GitHub
key leaks (`AKIA…`).

### Detection
CloudTrail credential use from new ASN/geo; `access_key` unused-then-used;
GuardDuty `UnauthorizedAccess:IAMUser/InstanceCredentialExfiltration`.

### Remediation
Rotate keys ≤90d, remove root keys, enforce MFA, prefer roles/SSO over static
keys, add `sts:ExternalId` on cross-account trusts. CIS 1.4, 1.5, 1.11, 1.14.

---

## 3. Public S3 buckets & sensitive object exposure

### HOW TO FIND (read-only)
```bash
aws s3api list-buckets --query 'Buckets[].Name' --output text
# Account-level Block Public Access
aws s3control get-public-access-block --account-id <acct>
# Per-bucket controls
aws s3api get-public-access-block --bucket <b>
aws s3api get-bucket-acl --bucket <b>              # AllUsers / AuthenticatedUsers grants?
aws s3api get-bucket-policy --bucket <b>           # Principal:"*" ?
aws s3api get-bucket-encryption --bucket <b>
```
Red flags: ACL grant to `http://acs.amazonaws.com/groups/global/AllUsers`,
bucket policy `"Principal":"*"` with `s3:GetObject`/`s3:ListBucket`, BPA
disabled.

### HOW IT'S ABUSED (SAFE)
List keys, then read **at most ONE small benign object** to prove access:
```bash
aws s3 ls s3://<bucket> --no-sign-request                 # anonymous listability
aws s3api head-object --bucket <bucket> --key <benign-key> --no-sign-request
# If proving read is required, fetch ONE small non-sensitive object, then redact.
```
Do **not** bulk `aws s3 sync`. Proving *listability* + one header is enough.

### Real public reference
Capital One 2019 (private buckets read via stolen role); years of public S3
leak disclosures. OWASP Cloud-Native storage guidance.

### Detection
S3 server access logs / CloudTrail data events for `ListBucket`/`GetObject`
from anonymous or foreign principals; Access Analyzer public-access findings;
Macie for sensitive-data discovery.

### Remediation
Enable account + bucket **Block Public Access**, remove `AllUsers`/`*` grants,
default SSE-KMS, `aws:SecureTransport` condition, enable Access Analyzer.
CIS S3 controls (public access block, encryption, SSL).

---

## 4. Metadata / SSRF → credential theft (IMDSv1 vs IMDSv2)

This is the Capital One 2019 chain: an SSRF in a WAF reached the EC2 Instance
Metadata Service (IMDS) at `169.254.169.254`, retrieved the instance role's
temporary credentials, and those creds (over-permissioned) listed and read
private S3 buckets — 106M records.

### HOW TO FIND (read-only, config audit)
```bash
# Are instances still allowing IMDSv1 (token optional)?  HttpTokens=optional = weak
aws ec2 describe-instances --query \
 'Reservations[].Instances[].{Id:InstanceId,Tokens:MetadataOptions.HttpTokens,Hop:MetadataOptions.HttpPutResponseHopLimit}'
```
Red flags: `HttpTokens: optional` (IMDSv1 allowed), `HopLimit > 1` (lets
containers/SSRF reach IMDS). Prowler/ScoutSuite both flag IMDSv1.

### HOW IT'S ABUSED (SAFE — stop at the role NAME)
The web-app SSRF entry point lives in `web-vuln-hunting`. On the cloud side,
the safe proof of the metadata reach is reading the **role name only**:
```bash
# IMDSv1 (weak) — no token needed:
curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/
# -> returns the ROLE NAME. STOP HERE. Do NOT append the role name to fetch keys.

# IMDSv2 (hardened) requires a token first (demonstrates the control works):
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/iam/security-credentials/
```
Retrieving the **role name** proves the SSRF→IMDS reach without ever pulling
live credentials. Never fetch the `security-credentials/<role>` document.

### Real public reference
Capital One breach (March/July 2019), Paige Thompson; catalyst for IMDSv2.
Wiz Cloud Threat Landscape and Appsecco write-ups.

### Detection
CloudTrail: instance-role credentials used from an **off-instance** IP
(GuardDuty `InstanceCredentialExfiltration`); WAF/app logs showing requests to
`169.254.169.254`.

### Remediation
Enforce **IMDSv2** (`HttpTokens: required`), set `HttpPutResponseHopLimit: 1`,
or disable IMDS where unused; least-privilege instance roles; egress controls.
CIS EC2 metadata controls. Enforce org-wide with SCP requiring
`ec2:MetadataHttpTokens=required`.

---

## 5. Public snapshots, AMIs, and exposed compute

### HOW TO FIND
```bash
# EBS snapshots shared publicly (owned by this account)
aws ec2 describe-snapshots --owner-ids self \
  --query 'Snapshots[?contains(to_string(@),`all`)==`true`]'
aws ec2 describe-snapshot-attribute --snapshot-id <id> --attribute createVolumePermission
# AMIs made public
aws ec2 describe-images --owners self --filters "Name=is-public,Values=true"
# RDS snapshots shared public
aws rds describe-db-snapshots --snapshot-type public --include-public
# Security groups open to the world on mgmt ports
aws ec2 describe-security-groups --query \
 'SecurityGroups[?IpPermissions[?contains(to_string(IpRanges),`0.0.0.0/0`)]].GroupId'
```
Red flags: snapshot/AMI `createVolumePermission`/`launchPermission` = `all`;
SG ingress `0.0.0.0/0` on 22/3389/3306/5432/6379/9200/27017.

### HOW IT'S ABUSED (SAFE)
Public snapshots let anyone create a volume and read the filesystem (creds,
keys). **SAFE PoC:** report the snapshot ID + `all` permission from
`describe-snapshot-attribute` — no need to copy/mount it. For open SGs, a
banner grab (see `network-service-exploitation`) proves exposure; do not
brute-force or exploit.

### Real public reference
Numerous public-snapshot/AMI disclosures; CIS EC2/RDS public-share checks.

### Detection
Config rules for public snapshots/AMIs; CloudTrail
`ModifySnapshotAttribute`/`ModifyImageAttribute` with `all`.

### Remediation
Remove public share, encrypt snapshots, restrict SGs to known CIDRs, use SSM
Session Manager instead of public SSH/RDP. CIS 5.x (SG/network).

---

## 6. Lambda env-var secrets & exposed databases

### HOW TO FIND
```bash
aws lambda list-functions --query 'Functions[].FunctionName' --output text
aws lambda get-function-configuration --function-name <fn> \
  --query 'Environment.Variables'          # plaintext secrets?
# RDS public accessibility
aws rds describe-db-instances --query \
 'DBInstances[?PubliclyAccessible==`true`].[DBInstanceIdentifier,Endpoint.Address]'
```
Red flags: API keys/passwords in Lambda env vars; `PubliclyAccessible: true`
on RDS.

### HOW IT'S ABUSED (SAFE)
Report the secret's presence and **redact the value** in evidence — do not use
it. For a discovered credential, at most one identity/validity check, then stop.

### Detection
CloudTrail `GetFunctionConfiguration` from unusual principals; Macie/Secrets
scanners.

### Remediation
Move secrets to Secrets Manager/SSM Parameter Store (KMS-encrypted), set RDS
`PubliclyAccessible=false`, restrict via SG + private subnets. CIS RDS controls.

---

## 7. Secrets in code / CI-CD / Terraform state

### HOW TO FIND (read-only)
```bash
# Terraform state stored in S3 often contains PLAINTEXT secrets/outputs
aws s3api get-bucket-policy --bucket <tfstate-bucket>   # public? versioned?
# Scan code/IaC/state files (read-only)
trivy fs --scanners secret,misconfig ./repo
trufflehog filesystem ./repo
```
Red flags: `terraform.tfstate` in a readable bucket; secrets in CI config
(`.gitlab-ci.yml`, GitHub Actions), committed `AKIA…` keys.

### HOW IT'S ABUSED (SAFE)
Terraform state stores resource attributes (DB passwords, private keys) in
plaintext. **SAFE PoC:** show the state file is readable and that it *contains*
a secret field — redact the value. Validate a discovered key only with
`sts get-caller-identity`.

### Real public reference
`offensive-osint` secret-regex catalog; HashiCorp guidance on encrypting remote
state; public CI/CD secret-leak disclosures.

### Detection
Secret scanners in CI (Trivy/TruffleHog/git-secrets); CloudTrail on tfstate
bucket access.

### Remediation
Encrypt + lock down remote state (private bucket, SSE-KMS, DynamoDB lock),
never commit secrets, use OIDC federation for CI instead of static keys, rotate
any exposed key immediately.
