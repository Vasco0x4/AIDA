# Kubernetes & Containers — Authorized Assessment Reference

Read-only bias. Confirm context/scope first:

```bash
kubectl config current-context        # which cluster — check against RoE
kubectl config get-contexts
kubectl cluster-info
kubectl auth whoami                   # who am I (v1.26+)
```

Baseline with read-only / CIS scanners:

```bash
# kube-bench — CIS Kubernetes Benchmark node/control-plane checks (read-only)
kube-bench run --targets master,node,etcd,policies

# kube-hunter — start PASSIVE (active probes can be intrusive)
kube-hunter --remote <api-host> --passive
# (Only add active with explicit RoE.)

# Trivy — image, IaC and cluster misconfig + secret scanning (read-only)
trivy k8s --report summary cluster
trivy image <registry>/<image>:<tag>
```

---

## 1. Exposed API server & anonymous authentication

### HOW TO FIND (read-only)
```bash
# Is the API server reachable unauthenticated? (anonymous-auth)
curl -sk https://<api>:6443/version
curl -sk https://<api>:6443/api           # 200 + data unauth = anonymous access
# From inside, check what 'system:anonymous' can do:
kubectl auth can-i --list --as=system:anonymous
kubectl auth can-i get pods --as=system:anonymous -A
```
Red flags: API server on a public IP; `--anonymous-auth=true` (default) with
RBAC bindings granting `system:anonymous`/`system:unauthenticated` anything;
`system:anonymous` able to list secrets/pods.

### HOW IT'S ABUSED (SAFE)
Anonymous + a permissive `ClusterRoleBinding` (e.g. binding
`system:unauthenticated` to `cluster-admin`) = unauthenticated cluster takeover.
**SAFE PoC:** demonstrate the reachability (`/version`) and the authorization
gap (`kubectl auth can-i --as=system:anonymous`) — do **not** create workloads
or read real secrets. Reporting "anonymous can `get secrets`" is sufficient
impact; do not dump them.

### Real public reference
Datadog Security Labs "Unauthenticated privileged access to Kubernetes API
Server"; raesene "Let's talk about anonymous access to Kubernetes."

### Detection
API audit logs: requests by `system:anonymous`; unexpected `create`/`list
secrets` from unauthenticated users.

### Remediation
`--anonymous-auth=false` on kube-apiserver (unmanaged clusters), never bind
`system:anonymous`/`unauthenticated` to real roles, put the API behind private
networking/authorized networks. CIS Kubernetes Benchmark 3.x (API server).

---

## 2. Exposed kubelet (read-only port & secure port)

### HOW TO FIND (read-only)
```bash
# Kubelet secure API (10250) — anonymous?
curl -sk https://<node>:10250/pods                 # lists pods if anon-auth on
curl -sk https://<node>:10250/runningpods/
# Legacy read-only port (10255, usually disabled):
curl -s http://<node>:10255/pods
```
Red flags: `10250` answering `/pods` unauthenticated
(`--anonymous-auth=true`, no `--authorization-mode=Webhook`); `10255` open.

### HOW IT'S ABUSED (SAFE)
Anonymous kubelet access exposes pod specs and, via `/exec` /`/run`, command
execution in existing privileged containers (kube-hunter KHV051). **SAFE PoC:**
show `/pods` is readable unauthenticated — do **not** invoke `/exec`/`/run` to
execute in a container (that is code execution/impact). Report the exposure.

### Real public reference
kube-hunter KB **KHV051** "Exposed Existing Privileged Containers Via Secure
Kubelet Port."

### Detection
Node/network logs for `10250`/`10255` access from non-control-plane IPs.

### Remediation
`--anonymous-auth=false`, `--authorization-mode=Webhook`, `--read-only-port=0`,
restrict kubelet ports via network policy/host firewall. CIS Kubernetes 4.2
(kubelet).

---

## 3. Over-privileged ServiceAccounts & RBAC

### HOW TO FIND (read-only)
```bash
# What can the default SA in a namespace do?
kubectl auth can-i --list --as=system:serviceaccount:<ns>:default -n <ns>
# Dangerous verbs across the cluster:
kubectl auth can-i create pods --all-namespaces
kubectl auth can-i '*' '*' --as=system:serviceaccount:<ns>:<sa>
# Find bindings to cluster-admin / wildcard roles
kubectl get clusterrolebindings -o json | \
  jq -r '.items[] | select(.roleRef.name=="cluster-admin") | .subjects'
kubectl get clusterroles -o json | \
  jq -r '.items[] | select(.rules[]?.verbs[]?=="*" and .rules[]?.resources[]?=="*") | .metadata.name'
```
Red flags: SAs with `create pods`, `create pods/exec`, `get secrets`,
`escalate`/`bind`, `impersonate`, or `*`/`*`; default SA token auto-mounted with
broad rights; `cluster-admin` bound to a namespace SA.

### HOW IT'S ABUSED (safe methodology)
`create pods` + `get secrets` lets a compromised pod mount all secrets or launch
a privileged pod to break out to the node. **SAFE PoC:** enumerate the capability
with `kubectl auth can-i` — do not actually create a privileged pod or read
secrets. The `can-i` output is the evidence.

### Real public reference
Kubernetes docs "RBAC Good Practices"; SecureFlag "Broken Authorization in
Kubernetes."

### Detection
Audit logs for `pods/exec`, `secrets get/list`, role/binding creation by SAs.

### Remediation
Least-privilege Roles (namespace-scoped), no wildcards, `automountServiceAccount
Token: false` where unused, avoid binding `cluster-admin`, restrict
`escalate`/`bind`/`impersonate`. CIS Kubernetes 5.1 (RBAC).

---

## 4. Secrets in ConfigMaps / unencrypted etcd

### HOW TO FIND (read-only)
```bash
# Secrets accidentally placed in ConfigMaps (base64 ≠ encryption anyway)
kubectl get configmaps -A -o yaml | grep -Ei 'password|secret|token|key|api[_-]?key'
# Is etcd encryption-at-rest configured? (control plane)
#   check kube-apiserver --encryption-provider-config (via kube-bench 1.2.x/3.x)
# Env vars with inline secrets in pod specs:
kubectl get pods -A -o yaml | grep -Ei 'value:.*(password|token|secret)'
```
Red flags: credentials in ConfigMaps or pod env values; no
`--encryption-provider-config` (Secrets stored plaintext base64 in etcd).

### HOW IT'S ABUSED (SAFE)
Report presence of a secret in a ConfigMap and **redact** the value; do not
reuse it. One identity/validity check maximum if it is a cloud key.

### Real public reference
Kubernetes docs "Encrypting Secret Data at Rest"; CIS Kubernetes secrets
controls.

### Detection
Audit logs on ConfigMap/Secret reads; image/IaC secret scanners (Trivy) in CI.

### Remediation
Use Secrets (not ConfigMaps) + KMS encryption provider for etcd, external secret
stores (Vault/CSI), never bake secrets into images/env. CIS Kubernetes 5.4.

---

## 5. Privileged pods & weak Pod Security

### HOW TO FIND (read-only)
```bash
# Privileged / host-namespace / hostPath pods already running
kubectl get pods -A -o json | jq -r '.items[] |
  select(.spec.containers[]?.securityContext?.privileged==true
    or .spec.hostNetwork==true or .spec.hostPID==true
    or (.spec.volumes[]?.hostPath!=null)) |
  "\(.metadata.namespace)/\(.metadata.name)"'
# Is Pod Security Admission enforcing 'restricted'/'baseline'?
kubectl get ns -o json | jq -r '.items[] |
  "\(.metadata.name): \(.metadata.labels["pod-security.kubernetes.io/enforce"] // "none")"'
```
Red flags: `privileged: true`, `hostPID`/`hostNetwork`/`hostIPC: true`,
`hostPath` mounts of `/`, `allowPrivilegeEscalation: true`, running as root,
no PSA `enforce` label / no admission policy (OPA/Kyverno).

### HOW IT'S ABUSED (safe methodology)
A privileged pod (or `hostPath: /`) is a node-breakout primitive: mount the host
filesystem, read kubelet creds, pivot to cluster-admin. **SAFE PoC:** report the
existing privileged pod spec and the missing PSA enforcement — do **not** create
a privileged pod or perform the breakout on production. If RoE explicitly allows
a live PoC, do it in a scoped throwaway namespace/pod you delete and log.

### Real public reference
kube-hunter KHV051 (privileged containers); Kubernetes Pod Security Standards.

### Detection
Admission logs / audit for privileged pod creation; falco runtime rules
(privileged, hostPath, sensitive mounts).

### Remediation
Enforce Pod Security Admission `restricted`, drop capabilities,
`allowPrivilegeEscalation:false`, no host namespaces/hostPath, non-root, use
Kyverno/OPA Gatekeeper policies. CIS Kubernetes 5.2 (Pod Security).

---

## 6. Exposed dashboards & management UIs

### HOW TO FIND (read-only)
```bash
# Kubernetes Dashboard exposed without auth / via NodePort/LoadBalancer
kubectl get svc -A | grep -Ei 'dashboard|grafana|kiali|argocd|kubeflow'
# Check for the dashboard endpoint (proxy or direct):
curl -sk https://<node>:<nodeport>/                # dashboard reachable unauth?
```
Red flags: Kubernetes Dashboard exposed via NodePort/LoadBalancer with a
`cluster-admin`-bound SA and skip-login enabled; other admin UIs (ArgoCD,
Grafana, Kubeflow) internet-exposed with default/no auth.

### HOW IT'S ABUSED (SAFE)
An unauthenticated dashboard bound to a privileged SA = full cluster control
(the Tesla 2018-style exposure). **SAFE PoC:** show the UI loads without auth and
report the SA it runs as — do not deploy workloads or read secrets through it.

### Real public reference
Public exposed-Kubernetes-Dashboard breach writeups (e.g. crypto-mining via open
dashboards); Kubernetes Dashboard access-control docs.

### Detection
Ingress/service logs for external access to dashboard/admin UIs; audit logs for
dashboard SA actions.

### Remediation
Do not expose the dashboard publicly (kubectl proxy / VPN only), bind it to a
minimal SA (not cluster-admin), require auth, network policy. CIS Kubernetes
controls + platform ingress hardening.

---

## Container image hygiene (supporting checks)

```bash
trivy image --scanners vuln,secret,misconfig <image>:<tag>   # CVEs + baked secrets
```
Report critical CVEs, baked-in secrets, running-as-root, and `latest`-tag drift.
Remediate with minimal/distroless base images, non-root user, pinned digests,
and registry scanning in CI.
