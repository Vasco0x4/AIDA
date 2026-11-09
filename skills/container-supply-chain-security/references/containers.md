# Containers — Docker/OCI Images, Runtime Posture & Escapes

Deep reference for Docker/OCI image analysis, dangerous runtime configuration,
and container-escape technique. **Read-only scanning is the default.**
Escape PoCs are lab/RoE only; node-disrupting ones are marked ⚠️.

Base doctrine: `safe-testing-doctrine`. Confirm registries, hosts, and whether
escape reproduction is authorised before any active step.

---

## 1. Image analysis — vulnerabilities, secrets, misconfig

### 1.1 Vulnerability & misconfig scan (trivy / grype+syft)

**HOW TO FIND (safe, read-only):**
```bash
# Vulnerabilities + misconfig + secrets + licenses in one pass
trivy image --scanners vuln,secret,misconfig registry.example.com/app:1.4.2

# SBOM-driven vuln matching (syft builds SBOM, grype matches)
syft registry.example.com/app:1.4.2 -o spdx-json > app.sbom.json
grype sbom:app.sbom.json

# Scan a running host's images or a saved tarball (no registry pull)
docker save app:1.4.2 -o app.tar && trivy image --input app.tar
```
Trivy and grype only read; they never modify or run the image. `trivy image`
resolves layers locally.

**Reference:** Aqua Trivy docs; Anchore Syft/Grype docs (see sources).

---

### 1.2 Secrets baked into layers / image history

Secrets deleted in a later layer **still exist in earlier layers** — the union
filesystem hides them but the blob remains.

**HOW TO FIND (safe):**
```bash
# Full history incl. build args and RUN commands (secrets often in ARG/ENV/RUN)
docker history --no-trunc registry.example.com/app:1.4.2
crane config registry.example.com/app:1.4.2 | jq '.history,.config.Env'   # no pull-run needed

# Layer-by-layer explorer — inspect what each layer added/removed
dive registry.example.com/app:1.4.2            # CI mode: dive --ci

# Dedicated secret scan across all layers
trivy image --scanners secret registry.example.com/app:1.4.2
```

**HOW TO TEST safely:** Extract the offending layer and confirm the secret is
present *and* whether it is live (validate read-only with `offensive-osint`
validators — e.g. an AWS key via `aws sts get-caller-identity`, a token via a
whoami-style read call). Record 4-6 chars, never the full secret, in evidence.
Flag for rotation.

**Real reference:** Countless disclosed images shipped `.env`, cloud keys, or
`.npmrc` tokens in intermediate layers; `ENV`/`ARG`-passed secrets appear in
`docker history`. OWASP Docker Security Cheat Sheet — Rule "no secrets in
image".

**Detection:** Registry-side image scanning (trivy in CI, admission-time scan);
secret-scanning gates before push.

**Remediation:** Use BuildKit `--secret` mounts (never `ARG` for secrets);
multi-stage builds; scan images pre-push; rotate any leaked credential.
CIS Docker Benchmark 4.10 (secrets not stored in Dockerfiles).

---

### 1.3 Dockerfile misconfiguration

**HOW TO FIND (safe):**
```bash
trivy config ./Dockerfile               # or: trivy fs --scanners misconfig .
checkov -f Dockerfile
hadolint Dockerfile                     # Dockerfile-specific linter
```
Common flags: `USER root` / no `USER` (runs as root), `latest` tags (no
pinning), `ADD` of remote URLs, `curl | sh` in `RUN`, missing
`--no-install-recommends`, world-writable dirs, embedded credentials.

**Remediation:** non-root `USER`, pinned base-image digests
(`FROM image@sha256:...`), minimal/distroless base, drop build tooling in final
stage. CIS Docker Benchmark 4.x.

---

## 2. Dangerous runtime posture (find before you ever think about escape)

Posture below is what *enables* escapes. Enumerate it read-only first — the
finding is often "this container is configured such that escape is trivial,"
which you can report **without** running the escape.

### 2.1 Privileged containers (`--privileged`)

`--privileged` grants all capabilities, disables seccomp/AppArmor confinement,
and exposes host devices (`/dev`) — effectively root on the host.

**HOW TO FIND (safe):**
```bash
# From the host / docker socket
docker inspect --format '{{.Name}} Privileged={{.HostConfig.Privileged}}' $(docker ps -q)

# From inside a container — am I privileged / what do I have?
amicontained                             # capabilities, namespaces, seccomp mode
capsh --print                            # effective capability set
cat /proc/self/status | grep Cap         # CapEff bitmask
ls -la /dev                              # privileged sees host block devices (sda, etc.)
```
Seeing host block devices (`/dev/sda`) or a full capability set
(`CapEff=000001ffffffffff`) indicates `--privileged`.

**Detection:** Runtime policy (Falco rule "Launch Privileged Container"),
admission control rejecting `privileged: true`.

**Remediation:** Never `--privileged`; grant specific capabilities only. CIS
Docker 5.4 / CIS Kubernetes 5.2.1.

---

### 2.2 Dangerous capabilities (CAP_SYS_ADMIN et al.)

Even without `--privileged`, individual capabilities enable escape.
`CAP_SYS_ADMIN`, `CAP_SYS_PTRACE`, `CAP_SYS_MODULE`, `CAP_DAC_READ_SEARCH`,
`CAP_NET_ADMIN`, `CAP_BPF` are the high-risk set.

**HOW TO FIND (safe):**
```bash
docker inspect --format '{{.HostConfig.CapAdd}}' <container>
amicontained | grep -i capab
grep Cap /proc/self/status                # decode: capsh --decode=<hex>
```

**Why it matters (describe, don't necessarily run):**
- `CAP_SYS_ADMIN` — enables the cgroup `release_agent` escape (§3.3) and mount
  operations. ⚠️ lab/RoE only.
- `CAP_SYS_MODULE` — load a kernel module → full host code execution. ⚠️.
- `CAP_DAC_READ_SEARCH` — arbitrary host file read via `open_by_handle_at`
  ("Shocker"): read-only-ish but reads host files.
- `CAP_SYS_PTRACE` (+ hostPID) — inject into host processes.

**Remediation:** `--cap-drop=ALL` then add only required caps; enforce via
Pod Security Admission `restricted`. CIS Docker 5.3.

---

### 2.3 Host mounts (hostPath / bind mounts)

Mounting host paths into a container is a direct escape vector — especially
`/`, `/etc`, `/var/run/docker.sock`, `/root`, `/proc`, or host `/`.

**HOW TO FIND (safe):**
```bash
docker inspect --format '{{json .Mounts}}' <container> | jq
# inside container:
mount | grep -Ev 'overlay|proc|sysfs|tmpfs|cgroup'   # unexpected host binds
cat /proc/mounts
findmnt
```

**HOW TO TEST safely:** If host `/` or `/etc` is mounted read-write, prove by
reading a benign host marker (e.g. `cat /host/etc/hostname`) — do **not** write.
If mounted read-write and RoE authorises, note that write-to-host (e.g.
dropping a cron file) is possible but keep the proof read-only.

**Remediation:** No hostPath to sensitive dirs; readOnly mounts; PSA blocks
hostPath in `restricted`. CIS Kubernetes 5.2.9 / 5.7.

---

### 2.4 Exposed Docker socket (`/var/run/docker.sock`)

A mounted docker socket = root on the host, because you can create a new
privileged container mounting host `/`.

**HOW TO FIND (safe):**
```bash
ls -l /var/run/docker.sock                       # present inside container?
docker inspect --format '{{json .Mounts}}' <c> | grep -i docker.sock
curl -s --unix-socket /var/run/docker.sock http://localhost/version   # read-only version call
curl -s --unix-socket /var/run/docker.sock http://localhost/containers/json
```
The `/version` and `/containers/json` GETs are read-only and prove reachability.

**HOW TO TEST safely (lab/RoE):** The weaponised proof is creating a container
that bind-mounts host `/` — this is a real host takeover; do it only in a lab.
For an in-scope target, **stop at the read-only `/version` call plus the
configuration finding** (socket is mounted) — that is sufficient proof of a
critical issue without spawning anything.

**Real reference:** Standard technique in MITRE ATT&CK T1610 (Deploy Container)
and countless CTFs/breaches; TeamTNT worms specifically hunted exposed docker
sockets.

**Detection:** Falco "Docker socket mounted in container"; audit
`hostPath: /var/run/docker.sock`.

**Remediation:** Never mount the socket; use rootless/socket-proxy with a strict
allowlist if API access is truly required. CIS Docker 5.31.

---

## 3. Container escapes (lab / explicit RoE only)

Prove escape with a benign marker only (host hostname, host process list, `id`
in the host mount namespace). Never pivot or persist. ⚠️ = can destabilise the
node — lab only unless RoE authorises node disruption in a window.

### 3.1 Privileged-container escape (mount the host disk)

**Concept:** In a `--privileged` container you can see host block devices and
mount them.
```bash
# LAB ONLY. Benign proof: read host filesystem, do not write.
fdisk -l                                # identify host disk, e.g. /dev/sda1
mkdir /hostmnt && mount /dev/sda1 /hostmnt
cat /hostmnt/etc/hostname               # PROOF: host's hostname != container's
umount /hostmnt                         # cleanup
```
**Remediation:** drop privileged; §2.1.

### 3.2 Docker-socket escape

**Concept:** With the socket mounted, launch a container mounting host `/`.
Weaponised — **lab only**. On a real target, report the mounted socket (§2.4)
without spawning. Remediation §2.4.

### 3.3 ⚠️ cgroup v1 `release_agent` escape (needs CAP_SYS_ADMIN)

**Concept:** With `CAP_SYS_ADMIN` and an unmasked cgroupfs, set a
`release_agent` that the host kernel executes when the cgroup empties. This is
the classic "notify_on_release" escape.
- ⚠️ Requires mounting cgroupfs and can leave host state / disrupt the node.
  **Lab only.**
- Benign proof: have the release_agent write host `uname -a` / hostname to a
  file you read back — never a reverse shell on a real target.

**Detection:** Falco "Write below /sys or release_agent"; PSA blocks the
required capability.
**Remediation:** drop `CAP_SYS_ADMIN`; cgroup v2; mask `/sys/fs/cgroup`.

### 3.4 CVE-2019-5736 — runc host `runc` binary overwrite

**Concept:** A malicious container could overwrite the host `runc` binary via
`/proc/self/exe` during `docker exec`/`runc exec`, gaining host code execution
next time runc runs. Affected runc < 1.0-rc7 (Docker < 18.09.2).

**HOW TO FIND (safe):**
```bash
runc --version ; docker version --format '{{.Server.Version}}'
```
Fingerprint the version; do **not** run the PoC on a real host (it overwrites
the host runc binary — destructive). Lab only for reproduction.

**Real reference:** Original disclosure by Adam Iwaniuk & Borys Popławski (Dragon
Sector), 2019; CVE-2019-5736. Patched in runc 1.0-rc7.
**Remediation:** upgrade runc/Docker; read-only host binaries; user namespaces.

### 3.5 CVE-2024-21626 — runc "Leaky Vessels" fd leak / WORKDIR escape

**Concept:** In runc ≤ 1.1.11 an internal file descriptor (typically `fd 7`)
referencing the **host** filesystem CWD leaks into the container before
`pivot_root`. Setting `process.cwd` / a Dockerfile `WORKDIR` to
`/proc/self/fd/7` (or higher) lands the process in the host filesystem —
container escape. Also exploitable by a malicious image at `runc run`.

**HOW TO FIND (safe):**
```bash
runc --version                                  # vulnerable if <= 1.1.11
docker info --format '{{.RuncCommit}}'
# Benign in-container check (lab): does a leaked host-fd exist?
ls -l /proc/self/fd/                             # look for a dir fd pointing at host paths
```

**HOW TO TEST safely (lab):** In a disposable lab, set `WORKDIR
/proc/self/fd/7` (or iterate low fds) and confirm the process CWD resolves to a
host path by reading host `/etc/hostname`. Never on a shared/prod node.

**Real reference:** Snyk "Leaky Vessels" (Rory McNamara), Jan 2024; CVE-2024-21626,
CVSS 8.6. Wiz/Palo Alto/Red Hat write-ups. Patched in runc 1.1.12.
**Detection:** Falco rule for leaked-fd/WORKDIR abuse; image scanning flags
vulnerable runc on nodes.
**Remediation:** upgrade runc ≥ 1.1.12 / patched Docker/containerd; scan base
images and node runtimes.

### 3.6 hostPID / hostNetwork / hostIPC (K8s-side)

Namespace sharing with the host enables process injection (hostPID), sniffing
and localhost-service access (hostNetwork), and shared-memory attacks
(hostIPC). Enumeration and safe testing are in
[references/kubernetes.md](kubernetes.md) §pod-security.

---

## 4. Quick triage checklist (all read-only)

```bash
trivy image --scanners vuln,secret,misconfig <image>     # image hygiene
dive <image>                                             # layer secrets
docker inspect <c> | jq '.[0].HostConfig | {Privileged,CapAdd,CapDrop,Binds,NetworkMode,PidMode}'
amicontained                                             # in-container confinement
grep Cap /proc/self/status                               # capabilities
mount | grep -Ev 'overlay|proc|sysfs|tmpfs|cgroup'       # host binds
ls -l /var/run/docker.sock 2>/dev/null                   # socket exposure
```
Findings here usually stand on their own (misconfiguration) — you rarely need to
run an escape to write a valid, high-severity report.
