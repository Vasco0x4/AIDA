# Kubernetes — Deep RBAC, Pod Security, API/Kubelet, Node Compromise

Deep cluster-internal reference. This goes beyond `cloud-security-testing`'s
K8s section (which covers managed control planes and cloud IAM bindings). Here
the focus is **RBAC privilege escalation, service-account token abuse, pod
security, exposed cluster components, and node-compromise paths — proven
read-only wherever possible.**

Base doctrine: `safe-testing-doctrine`. Confirm which clusters/namespaces are in
scope. Default verbs are `get`/`describe`/`auth can-i`. No `delete`, no
`apply` of privileged pods except in a lab or under explicit RoE.

---

## 1. RBAC audit & privilege escalation

### 1.1 Enumerate your effective permissions (safest first step)

**HOW TO FIND (safe, read-only):**
```bash
kubectl auth can-i --list                              # everything current identity can do
kubectl auth can-i --list --namespace kube-system
kubectl auth can-i create pods                         # targeted checks
kubectl auth can-i '*' '*'                              # cluster-admin?
kubectl auth can-i create clusterrolebindings          # self-escalation primitive
kubectl auth can-i get secrets --all-namespaces

# Who am I / which service account
kubectl auth whoami 2>/dev/null
cat /var/run/secrets/kubernetes.io/serviceaccount/token   # (in-pod) SA token
cat /var/run/secrets/kubernetes.io/serviceaccount/namespace
```

**HOW TO FIND (RBAC graph, read-only):**
```bash
kubectl get clusterrolebindings,rolebindings -A -o wide
# Tools that enumerate who-can-do-what (read-only):
#   rakkess / access-matrix, kubectl-who-can, rbac-tool, kubiscan
kubectl who-can create pods -n kube-system
rbac-tool who-can '*' secrets
```

### 1.2 RBAC privilege-escalation primitives (report as findings)

These verbs let a low-priv identity become cluster-admin. Finding the *grant*
is the finding — you generally don't need to execute the escalation.

| Grant | Escalation path |
|-------|-----------------|
| `create pods` (esp. + hostPath/privileged allowed) | Schedule a pod mounting host `/` or the node's kubelet SA → node/cluster takeover |
| `create pods/exec` | Exec into existing higher-priv pods |
| `get/list secrets` | Read every SA token / TLS key in scope → impersonate those SAs |
| `create serviceaccounts/tokens` (TokenRequest) | Mint tokens for higher-priv SAs |
| `escalate`/`bind` on roles, or `create clusterrolebindings` | Bind yourself to `cluster-admin` |
| `create` on `pods` with `nodeName` + tolerations | Land on a control-plane node |
| `impersonate` (users/groups/SAs) | Act as `system:masters` |
| Workload controllers (`deployments`,`daemonsets`,`jobs`,`cronjobs`) | Indirect pod creation → same as `create pods` |

**HOW TO TEST safely:** Demonstrate with `--dry-run=server` and `auth can-i`
rather than actually creating the privileged object:
```bash
kubectl auth can-i create clusterrolebindings          # yes = self-escalation
# Prove without persisting: server-side dry run validates you *could* create it
kubectl create clusterrolebinding poc --clusterrole=cluster-admin \
  --serviceaccount=default:default --dry-run=server -o yaml
```
`--dry-run=server` runs admission/authorization checks but **does not persist**
the object — ideal minimal proof. Only create the real binding in a lab; if RoE
demands live proof, create it, screenshot, then `kubectl delete` and log it in
cleanup.

**Real reference:** MITRE ATT&CK T1078.004 / K8s privilege-escalation matrix;
CNCF/Kubernetes RBAC "privilege escalation prevention" docs; BadPods project
(Bishop Fox) catalogues the pod-based escalations.

**Detection:** Audit-log alerts on `clusterrolebindings` create, `secrets`
list-all, `impersonate`. **Remediation:** least-privilege Roles, no wildcard
verbs/resources, avoid `create pods` for app SAs, separate namespaces. CIS
Kubernetes 5.1.x.

---

## 2. Service-account token abuse

Every pod, by default (pre-1.24 behaviour / unless `automountServiceAccountToken:
false`), gets a mounted SA token. A stolen token = that SA's RBAC.

**HOW TO FIND (safe):**
```bash
# In-pod token & what it can do
TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
kubectl --token="$TOKEN" auth can-i --list
# Are tokens auto-mounted where they shouldn't be?
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.spec.automountServiceAccountToken}{"\n"}{end}'
# Legacy long-lived SA-token secrets (pre-1.24) still in the cluster:
kubectl get secrets -A --field-selector type=kubernetes.io/service-account-token
```

**HOW TO TEST safely:** Use the token only for `auth can-i --list` / a single
`get` to demonstrate scope. Do not use an over-privileged token to create
resources except in a lab. Record token scope, not the token value.

**Real reference:** Tesla 2018 (exposed Kubernetes dashboard → SA token →
cloud cred → cryptomining); MITRE ATT&CK T1528 (Steal Application Access Token).

**Detection:** Audit anomalous SA-token use from unexpected IPs/pods.
**Remediation:** `automountServiceAccountToken: false` by default; short-lived
bound tokens (TokenRequest, default ≥1.24); scope SAs tightly. CIS Kubernetes
5.1.5/5.1.6.

---

## 3. Pod security — privileged/hostPath/host-namespaces & PSA

### 3.1 Find insecure pods (read-only)

**HOW TO FIND (safe):**
```bash
kubeaudit all -k                                        # audits security-context issues
kubectl get pods -A -o json | jq -r '
  .items[] | select(
    .spec.hostPID or .spec.hostNetwork or .spec.hostIPC or
    (.spec.containers[].securityContext.privileged==true) or
    (.spec.volumes[]?.hostPath)
  ) | "\(.metadata.namespace)/\(.metadata.name)"'
# Pod Security Admission level enforced per namespace:
kubectl get ns -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.metadata.labels.pod-security\.kubernetes\.io/enforce}{"\n"}{end}'
```
High-risk fields: `privileged: true`, `hostPID/hostNetwork/hostIPC: true`,
`hostPath` volumes (esp. `/`, `/var/run/docker.sock`, `/etc`),
`allowPrivilegeEscalation: true`, `runAsUser: 0`, added capabilities,
`seccompProfile` unset.

### 3.2 Why each matters (escape/impact — see also containers.md §2-3)

- **privileged** → host takeover (mount host disk). Prove read-only with host
  hostname (lab/RoE).
- **hostPath `/`** → read/write host filesystem; drop into node.
- **hostPID** → see & (with caps) inject host processes: `ps -ef` shows host
  PIDs; read `/proc/1/root/...`.
- **hostNetwork** → reach node-local services (kubelet `:10250`, cloud IMDS
  `169.254.169.254`), sniff.
- **hostIPC** → access host shared memory.

**HOW TO TEST safely:** From an authorized pod with hostPID, prove with a
benign read (`ps -ef | head`, `cat /proc/1/comm`). With hostNetwork, prove IMDS
reachability with a **read-only** metadata GET of a role *name* only (see
`cloud-security-testing`). No writes, no pivot.

**Real reference:** BadPods (Bishop Fox) — 8 canonical over-privileged pod
specs and what each yields; Kubernetes Pod Security Standards docs.

**Detection:** PSA `restricted` enforcement; admission webhooks (Kyverno/OPA
Gatekeeper) denying these fields; Falco.
**Remediation:** enforce PSA `restricted` (or Kyverno/Gatekeeper policies);
drop all host namespaces/privileged/hostPath; `readOnlyRootFilesystem`,
`runAsNonRoot`, seccomp `RuntimeDefault`. CIS Kubernetes 5.2.x.

---

## 4. Exposed cluster components

### 4.1 Kubelet API (`:10250` read/write, `:10255` read-only)

An unauthenticated/anonymous kubelet lets you list pods and **exec** into them.

**HOW TO FIND (safe):**
```bash
curl -sk https://NODE:10250/pods | jq '.items[].metadata.name'   # anonymous listing?
curl -s  http://NODE:10255/pods                                  # read-only port
# with a token if required:
curl -sk -H "Authorization: Bearer $TOKEN" https://NODE:10250/pods
```
Listing pods anonymously = misconfig finding. The `exec`/`run` endpoints are the
weaponised part.

**HOW TO TEST safely:** Stop at the read-only `/pods` (and `/metrics`) proof. Do
not use the exec endpoint on a live target except in a lab.

**Real reference:** kube-hunter's classic "Anonymous kubelet" finding; multiple
cryptomining campaigns via open kubelets.
**Remediation:** `--anonymous-auth=false`, `--authorization-mode=Webhook`,
disable `:10255`, NetworkPolicy/firewall on kubelet ports. CIS Kubernetes 4.2.x.

### 4.2 API server anonymous access & exposed dashboard

**HOW TO FIND (safe):**
```bash
curl -sk https://APISERVER:6443/api                       # anonymous system:anonymous?
kubectl --insecure-skip-tls-verify --server https://APISERVER:6443 \
  --token="" auth can-i --list
# Dashboard exposure:
curl -sk https://HOST/  | grep -i 'kubernetes dashboard'
```
**Remediation:** disable anonymous auth (`--anonymous-auth=false`), never expose
the dashboard publicly / never grant it cluster-admin. CIS Kubernetes 1.2.1.

### 4.3 etcd exposure (`:2379`)

etcd stores all cluster state incl. **secrets in plaintext** if not
encrypted-at-rest.

**HOW TO FIND (safe):**
```bash
curl -sk https://NODE:2379/version                        # reachable?
# Authenticated read (with client certs, read-only):
ETCDCTL_API=3 etcdctl --endpoints=https://NODE:2379 \
  --cacert=ca.crt --cert=client.crt --key=client.key endpoint health
```
Do not dump all keys on a live target — prove reachability/`/version`, note
whether client-cert auth is required.

**Real reference:** Exposed etcd → full secret disclosure is a recurring
finding; Shodan regularly indexes open etcd.
**Remediation:** mTLS client-cert auth, firewall to control-plane only,
`--encryption-provider-config` (encrypt secrets at rest). CIS Kubernetes 2.x.

---

## 5. Secrets in ConfigMaps & weak secret storage

**HOW TO FIND (safe):**
```bash
# Secrets pasted into ConfigMaps (unencrypted, RBAC-permissive):
kubectl get configmaps -A -o yaml | grep -iE 'password|token|secret|api[_-]?key|BEGIN .*PRIVATE'
trivy k8s --report summary cluster                        # incl. exposed-secret checks
# Real Secrets are only base64, not encrypted — anyone with get-secret reads them:
kubectl get secret -A -o json | jq -r '.items[] | .metadata.namespace+"/"+.metadata.name'
```
**Remediation:** never store secrets in ConfigMaps; encryption-at-rest for
etcd; external secret managers (Vault/CSI Secrets Store); tight `secrets` RBAC.
CIS Kubernetes 5.4.x.

---

## 6. NetworkPolicy gaps (lateral movement)

Default Kubernetes networking is **flat** — every pod can reach every pod.

**HOW TO FIND (safe):**
```bash
kubectl get networkpolicies -A                            # none = flat network
# Namespaces with zero policies (no default-deny):
for ns in $(kubectl get ns -o name | cut -d/ -f2); do
  n=$(kubectl get netpol -n "$ns" --no-headers 2>/dev/null | wc -l)
  echo "$ns policies=$n"; done
```
**HOW TO TEST safely:** From an authorized pod, prove reachability with a
benign TCP connect to a service that should be isolated (`nc -zv svc.other-ns
port`) — a connect probe, not an exploit, no data.

**Remediation:** default-deny NetworkPolicy per namespace, explicit allowlists;
consider a CNI enforcing L3/L7 policy. CIS Kubernetes 5.3.2.

---

## 7. Admission control gaps

Missing admission control is *why* the pod-security issues above are exploitable.

**HOW TO FIND (safe):**
```bash
kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations
# PSA enforced? (see §3.1). Policy engines present?
kubectl get pods -A | grep -iE 'kyverno|gatekeeper|opa'
kubectl api-resources | grep -iE 'policy|constraint'
```
**Remediation:** enforce Pod Security Admission `restricted` + Kyverno/OPA
Gatekeeper policies (block privileged/hostPath/latest tags/unsigned images).

---

## 8. Node-compromise paths (summary)

Common chains, each already covered above — report the *first enabling step*:
1. `create pods` + no PSA → privileged/hostPath pod → mount node `/` → node root.
2. Over-mounted SA token on a node-privileged SA → API takeover.
3. Anonymous kubelet exec → command in existing pod → SA token → escalate.
4. hostNetwork pod → cloud IMDS → node IAM role (hand off to
   `cloud-security-testing`).
5. Exposed etcd → all secrets → impersonate any SA.

Prove the entry condition read-only; only chain to node in a lab/RoE with a
benign host marker.

---

## 9. Tooling notes (read-only usage)

```bash
kube-bench run                       # CIS Kubernetes Benchmark (node/control-plane); read-only
kube-hunter --remote CLUSTER_IP      # or --passive first; ACTIVE probes can be intrusive
kubeaudit all -k                     # security-context audit
amicontained                         # in-pod confinement report
trivy k8s cluster --report summary   # vuln+misconfig+secret across cluster (read-only)
```
**Peirates** (in-pod K8s post-exploitation) is powerful but **many menu options
mutate/escalate** (create privileged pods, mount host, harvest & use tokens).
Use only its enumeration/`auth can-i`-style read functions, and only under RoE;
prefer plain `kubectl auth can-i --list` for reporting. Never run its
escalation modules on a shared/prod cluster.

`kube-hunter` was archived by Aqua (2024) but still runs; prefer `--passive` and
remote/network scanning modes before active in-cluster probes.
