# GCP — Authorized Assessment Reference

Read-only bias. Confirm identity/scope first:

```bash
gcloud auth list                       # active account
gcloud config list                     # project, account
gcloud projects list                   # projects in scope — check against RoE
PROJECT=$(gcloud config get-value project)
```

Baseline with read-only scanners:

```bash
prowler gcp --project-ids $PROJECT -M html json-ocsf      # CIS GCP mapping
scout gcp --user-account --report-dir ./scout-gcp          # ScoutSuite GCP
```

---

## 1. IAM privilege escalation, service-account keys & impersonation

GCP privesc almost always routes through **service accounts (SAs)**: minting a
key, impersonating, or `actAs`-passing an SA into a compute resource.

### HOW TO FIND (read-only)
```bash
# Project IAM policy — who has broad roles?
gcloud projects get-iam-policy $PROJECT --format=json
# Flags: roles/owner, roles/editor, roles/iam.serviceAccountTokenCreator,
#        roles/iam.serviceAccountUser (actAs), roles/*.admin to broad members,
#        allUsers / allAuthenticatedUsers on any binding.

# Service accounts and their user-managed keys (long-lived key risk)
gcloud iam service-accounts list --project $PROJECT
gcloud iam service-accounts keys list --iam-account <sa-email>   # USER_MANAGED keys?

# Who can impersonate an SA? (TokenCreator on the SA resource)
gcloud iam service-accounts get-iam-policy <sa-email>
```
Red flags: user-managed SA keys (esp. old/unrotated); `roles/editor` handed out
broadly (it includes many escalation primitives); `iam.serviceAccountTokenCreator`
or `iam.serviceAccountUser` binding an ordinary user to a high-priv SA; `allUsers`.

### HOW IT'S ABUSED (safe methodology)
- **`iam.serviceAccountKeys.create`** → mint a key for a high-priv SA and
  authenticate as it.
- **`iam.serviceAccountTokenCreator`** → generate short-lived access tokens for
  the target SA (impersonation), chainable A→B→C.
- **`iam.serviceAccounts.actAs` + create-compute (GCE/Cloud Function/Run)** →
  attach a high-priv SA to a resource you control and read its token.

**SAFE PoC:** report the exploitable binding (member → permission → reachable
SA/role). Rhino/Praetorian catalogue these. If RoE requires live proof, use
impersonation read-only and stop at an identity check:
```bash
# Prove impersonation reachability WITHOUT using the elevated token for data:
gcloud auth print-access-token --impersonate-service-account=<target-sa> >/dev/null \
  && echo "impersonation of <target-sa> succeeded"     # then STOP
```
Do not mint persistent keys; if you must, delete + log them same session.

### Real public reference
Rhino Security Labs "Privilege Escalation in GCP – Part 1 (IAM)"; Praetorian
"GCP Service Account-based Privilege Escalation paths"; HackTricks Cloud
GCP-IAM-Privesc; Stratus Red Team `impersonate-service-accounts`.

### Detection
Cloud Audit Logs: `GenerateAccessToken`, `CreateServiceAccountKey`,
`SetIamPolicy`, compute-create with an unusual SA; Event Threat Detection SA
anomalies.

### Remediation
Disable user-managed key creation (org policy
`iam.disableServiceAccountKeyCreation`), prefer impersonation/Workload Identity,
least-privilege custom roles (avoid Editor/Owner), scope `actAs`/TokenCreator
tightly, rotate keys. CIS GCP IAM controls (1.x).

---

## 2. Public GCS buckets & object exposure

### HOW TO FIND (read-only)
```bash
gcloud storage buckets list --project $PROJECT
# Bucket IAM — allUsers / allAuthenticatedUsers = public
gcloud storage buckets get-iam-policy gs://<bucket>
gsutil iam get gs://<bucket>          # legacy equivalent
# Public Access Prevention + uniform bucket-level access
gcloud storage buckets describe gs://<bucket> \
  --format="default(public_access_prevention,uniform_bucket_level_access)"
```
Red flags: binding to `allUsers` or `allAuthenticatedUsers`;
`public_access_prevention: inherited/unspecified` instead of `enforced`.

### HOW IT'S ABUSED (SAFE)
```bash
# Anonymous listability:
gsutil ls gs://<bucket>
# Prove read with ONE small benign object, then redact. No bulk download.
```

### Real public reference
Public GCS leak disclosures; Sourcery/FortWatch cloud-bucket exposure writeups;
CIS GCP Storage.

### Detection
Data Access audit logs (`storage.objects.get/list`) from anonymous principals;
SCC public-bucket findings.

### Remediation
Enforce Public Access Prevention (org policy), uniform bucket-level access,
remove `allUsers`/`allAuthenticatedUsers`, signed URLs with expiry. CIS GCP
Storage controls.

---

## 3. GCP metadata server (SSRF → SA token)

The GCP metadata server (`metadata.google.internal` / `169.254.169.254`) hands
out the attached SA's token and requires the `Metadata-Flavor: Google` header.
SSRF against a GCE/GKE/Cloud Run workload can retrieve it.

### HOW TO FIND (read-only config)
```bash
# Which VMs attach which SA + scopes? Legacy v1 metadata enabled?
gcloud compute instances describe <vm> --zone <z> \
  --format="default(serviceAccounts,metadata)"
```
Red flags: instances using the **default compute SA** with
`cloud-platform` scope; legacy metadata endpoints enabled.

### HOW IT'S ABUSED (SAFE — stop at identity, not data)
The SSRF entry point lives in `web-vuln-hunting`. On the GCP side, prove
reachability only:
```bash
# Header is required — proves the metadata reach:
curl -s -H "Metadata-Flavor: Google" \
 "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
# Returns the SA EMAIL (identity). STOP HERE. Do NOT fetch .../token.
```
Reading the SA **email** proves the SSRF→metadata reach without pulling a live
token.

### Real public reference
GCP metadata SSRF disclosures; HackTricks Cloud GCP metadata; Google metadata
docs.

### Detection
Audit logs: SA token used from off-instance IP; SSRF patterns hitting
`metadata.google.internal` in app logs.

### Remediation
Least-privilege custom SA (not default compute SA), narrow scopes, disable
legacy metadata (`disable-legacy-endpoints=true`), GKE Workload Identity, patch
SSRF. CIS GCP compute controls.

---

## 4. Exposed compute, Firestore & databases

### HOW TO FIND (read-only)
```bash
# Firewall rules open to the world on mgmt ports
gcloud compute firewall-rules list \
  --format="table(name,sourceRanges.list():label=SRC,allowed[].map().firewall_rule().list():label=ALLOW)"
# Look for 0.0.0.0/0 on 22/3389/3306/5432/6379/27017.

# Public compute images/snapshots shared broadly
gcloud compute images list --no-standard-images
# Cloud SQL public IP + authorized networks
gcloud sql instances list \
  --format="table(name,ipAddresses[].ipAddress,settings.ipConfiguration.authorizedNetworks[].value)"
```
Red flags: `0.0.0.0/0` firewall ingress on management/db ports; Cloud SQL with
public IP + authorized network `0.0.0.0/0`; Firestore/Datastore rules allowing
open read/write; publicly shared images.

### HOW IT'S ABUSED (SAFE)
Report reachability (banner grab per `network-service-exploitation`); do not
brute-force. For Firestore in Datastore/Native mode, insecure security rules
(`allow read, write: if true`) expose data — report the rule, read at most one
benign document.

### Real public reference
CIS GCP networking/Cloud SQL controls; public Firebase/Firestore open-rules
disclosures.

### Detection
VPC flow/firewall logs; SCC open-firewall and public-IP findings.

### Remediation
Restrict firewall source ranges, use IAP/bastion instead of public SSH/RDP,
Cloud SQL private IP + tight authorized networks, lock Firestore security rules.
CIS GCP networking controls.

---

## 5. Secrets & keys (code / CI / state)

Same discipline as AWS §7: scan repos/IaC/Terraform state with `trivy fs
--scanners secret,misconfig` and TruffleHog; treat GCS-stored `terraform.tfstate`
as sensitive (SA keys, DB passwords in plaintext). Validate any discovered SA
key only with an identity check (`gcloud auth activate-service-account
--key-file=… ` then `gcloud auth list`) and STOP; delete the local key after.
Remediate by encrypting/locking state, Secret Manager for secrets, Workload
Identity Federation for CI instead of exported SA keys.
