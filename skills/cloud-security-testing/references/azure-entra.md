# Azure / Entra ID — Authorized Assessment Reference

Read-only bias. Confirm identity/scope first:

```bash
az login                    # or --service-principal for an audit SP
az account show             # tenantId, subscriptionId — check against RoE
az account list -o table
gcloud auth list            # (n/a) — Azure uses az; listed for muscle memory
```

Baseline with read-only scanners:

```bash
# Prowler for Azure (read-only, CIS/Microsoft Cloud Security Benchmark)
prowler azure --az-cli-auth -M html json-ocsf
# ScoutSuite for Azure
scout azure --cli --report-dir ./scout-azure
# Entra/AzureAD enumeration (read-only): ROADrecon gather, AzureHound collect
```

> Note: Azure splits into **Entra ID** (identity/tenant, formerly Azure AD) and
> **Azure Resource Manager** (subscriptions/resources). Findings live in both.

---

## 1. Over-privileged RBAC & Azure role assignments

### HOW TO FIND (read-only)
```bash
# All role assignments in the subscription — look for Owner/Contributor sprawl
az role assignment list --all -o table
az role assignment list --all --query \
 "[?roleDefinitionName=='Owner' || roleDefinitionName=='Contributor'].{p:principalName,r:roleDefinitionName,s:scope}" -o table
# Custom roles with wildcard actions
az role definition list --custom-role-only true \
 --query "[?contains(to_string(permissions[].actions),'*')].roleName"
# Classic administrators / subscription-scope grants
```
Red flags: `Owner`/`Contributor` at subscription/management-group scope for
many principals or service principals; custom roles with `"actions":["*"]`;
`User Access Administrator` (can grant itself more).

### HOW IT'S ABUSED (safe methodology)
`User Access Administrator` or `Owner` can create new role assignments →
self-escalate. **SAFE PoC:** report the assignment graph (principal → role →
scope) from `az role assignment list`; don't create assignments. If RoE demands
live proof, use a scoped throwaway assignment you remove and log.

### Real public reference
Cobalt "Microsoft Entra ID Pentesting" guide; Microsoft Cloud Security
Benchmark identity controls.

### Detection
Entra audit logs: `Add role assignment`; Azure Activity Log
`Microsoft.Authorization/roleAssignments/write`.

### Remediation
Least privilege, PIM (just-in-time roles), no standing Owner, custom roles
without wildcards, scope at resource-group not subscription. CIS Azure IAM.

---

## 2. Entra app registrations, OAuth consent abuse & illicit consent grants

### HOW TO FIND (read-only)
```bash
# App registrations and their credentials (secrets/certs)
az ad app list --query "[].{name:displayName,appId:appId}" -o table
az ad app credential list --id <appId>          # long-lived secrets/expiry
# Service principals with risky Graph app roles / OAuth grants
az ad sp list --all --query "[].{n:displayName,id:appId}" -o table
# OAuth2 permission grants (delegated) and app role assignments (via Graph/ROADrecon)
#   ROADrecon: roadrecon gather ; roadrecon plugin policies / gui
```
Red flags: apps granted high-privilege Graph **application** permissions
(`Directory.ReadWrite.All`, `Application.ReadWrite.All`, `RoleManagement...`,
`Mail.Read`), multi-tenant apps, long-lived client secrets, tenant-wide admin
consent to third-party/unknown apps, `OAuth2PermissionGrant.ReadWrite.All`.

### HOW IT'S ABUSED (safe methodology)
**Illicit consent grant / OAuth phishing**: a user (or admin) is tricked into
consenting to a malicious app, giving it a persistent, MFA-bypassing token to
Graph data. An app with `Application.ReadWrite.All` can add a new credential to
a privileged app (app backdooring) for persistence. **SAFE PoC in an audit:**
enumerate and *report* which apps hold dangerous consented scopes and which
have long-lived secrets — do not register a malicious app or perform consent
phishing against real users (that is out of scope unless explicitly contracted
per `safe-testing-doctrine`).

### Real public reference
Cloud-Architekt AzureAD-Attack-Defense `ConsentGrant.md`; Elastic Security
"Entra ID Illicit Consent Grant via Registered Application"; SlashID
"Illicit Consent-Granting & App Backdooring"; Microsoft "Protect against
consent phishing."

### Detection
Entra audit: `Consent to application`, `Add app role assignment to service
principal`, `Add service principal credentials`. Elastic/Sentinel consent-grant
rules.

### Remediation
Restrict user consent (admin-consent workflow), disable/limit third-party app
registration, review enterprise-app permissions, short-lived cert-based creds,
Conditional Access. CIS Azure application controls.

---

## 3. Managed identities & Azure IMDS (SSRF → token theft)

Azure's metadata endpoint at `169.254.169.254` issues managed-identity access
tokens. SSRF against a VM/App Service with a managed identity yields a Graph/ARM
token — the Azure analogue of the Capital One IMDS chain.

### HOW TO FIND (read-only config)
```bash
# Which VMs / app services have (system/user) managed identities?
az vm identity show --name <vm> -g <rg>
az webapp identity show --name <app> -g <rg>
# What can that identity do? (role assignments for its principalId)
az role assignment list --assignee <identity-principalId> -o table
```
Red flags: managed identity with Contributor/Owner at broad scope + an
internet-facing app that could be SSRF'd.

### HOW IT'S ABUSED (SAFE — stop at token metadata, not data use)
The SSRF web entry lives in `web-vuln-hunting`. On the Azure side, the metadata
call requires the `Metadata:true` header (proves the reachability):
```bash
# From inside an authorized test host, demonstrate reachability only:
curl -s -H "Metadata:true" \
 "http://169.254.169.254/metadata/instance?api-version=2021-02-01"
# Requesting a token proves the identity is exposed; DO NOT then call Graph/ARM
# with it to read data. Prove validity at most with 'az account show'-equivalent
# identity check, then STOP.
```
Report that an internet-reachable app has a managed identity with excessive
roles — the impact is clear without exfiltration.

### Real public reference
Cobalt Entra pentest guide (managed-identity SSRF); Microsoft IMDS docs.

### Detection
ARM Activity Log: managed-identity token used from unexpected resource; Entra
sign-in logs for the MI service principal.

### Remediation
Least-privilege MI roles, restrict IMDS egress, prefer user-assigned MIs with
tight scope, patch SSRF. Microsoft Cloud Security Benchmark.

---

## 4. Public Blob storage & container exposure

### HOW TO FIND (read-only)
```bash
# Storage accounts allowing public blob access
az storage account list --query \
 "[].{name:name,allowBlobPublic:allowBlobPublicAccess,network:networkRuleSet.defaultAction}" -o table
# Container public access level
az storage container list --account-name <acct> --auth-mode login \
 --query "[].{name:name,public:properties.publicAccess}" -o table
```
Red flags: `allowBlobPublicAccess: true`, container `publicAccess: blob` or
`container`, `defaultAction: Allow` (no network restriction).

### HOW IT'S ABUSED (SAFE)
Anonymous blob enumeration/read. **SAFE PoC:** list blobs and read **ONE small
benign blob** to prove access, then redact:
```bash
# Anonymous listing of a public container:
az storage blob list --account-name <acct> --container-name <c> --auth-mode anonymous -o table
```
No bulk download.

### Real public reference
Public Azure Blob leak disclosures; Cyber Codex "Exploiting Misconfigurations
in Azure/AWS/GCP"; CIS Azure Storage.

### Detection
Storage analytics/diagnostic logs for anonymous reads; Defender for Storage.

### Remediation
Set `allowBlobPublicAccess=false`, container access `private`, network rules
default-deny, SAS with expiry, private endpoints. CIS Azure Storage controls.

---

## 5. Exposed databases (Cosmos DB, SQL) & key sprawl

### HOW TO FIND
```bash
# Cosmos DB firewall / public network access
az cosmosdb list --query "[].{n:name,public:publicNetworkAccess,ipRules:ipRules}" -o table
# Azure SQL servers allowing Azure-services / 0.0.0.0 firewall rule
az sql server firewall-rule list --server <srv> -g <rg> -o table
# Storage / Cosmos account keys (long-lived shared keys)
```
Red flags: `publicNetworkAccess: Enabled` with no IP rules; SQL firewall rule
`0.0.0.0`–`0.0.0.0` (allow all Azure) or `0.0.0.0`–`255.255.255.255`; primary
account keys used instead of Entra auth.

### HOW IT'S ABUSED (SAFE)
Report reachability + weak auth. If a connection string/key is discovered, one
identity/validity check maximum, then stop — no data reads.

### Detection
Defender for Cloud database recommendations; Activity Log firewall-rule writes.

### Remediation
Private endpoints, disable public network access, Entra auth over shared keys,
rotate keys, firewall to known IPs. CIS Azure database controls.
