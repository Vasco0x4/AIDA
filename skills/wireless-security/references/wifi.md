# Wi-Fi — Recon, WPA2 (PMKID & Handshake), WPA3/Dragonblood, WPA-Enterprise, WPS

**Passive-first, no-deauth doctrine applies to everything below.** You capture by
*listening* and by exploiting the AP-only PMKID path — never by transmitting
deauthentication/disassociation frames. Crack **offline**, only against the
authorized network. Re-read the `⚠️ Safety` section in `SKILL.md` before any RF work.

---

## 0. Interface prep (monitor mode)

```bash
sudo airmon-ng check                     # list processes that may interfere
sudo airmon-ng check kill                # stop NetworkManager/wpa_supplicant if needed
sudo airmon-ng start wlan0               # -> creates wlan0mon (monitor mode)
iw dev                                    # confirm interface + type
# Cleanup when finished:
sudo airmon-ng stop wlan0mon && sudo systemctl restart NetworkManager
```

hcxdumptool prefers to manage the interface itself (it will set monitor mode); you do
not need airmon-ng when using it.

---

## 1. Passive recon & enumeration

Goal: enumerate in-scope APs and clients, security modes, channels, WPS state, and
hidden SSIDs — all by **receiving** frames only.

### airodump-ng survey (read-only capture)
```bash
# Full-band survey (2.4/5 GHz depending on adapter), write CSV/pcap for later review:
sudo airodump-ng wlan0mon -w survey --output-format pcap,csv
# Then focus on the AUTHORIZED BSSID/channel only:
sudo airodump-ng -c <CH> --bssid <AP_BSSID> -w target wlan0mon
```
Columns of interest: `ENC` (WPA2/WPA3), `AUTH` (PSK/MGT=Enterprise/SAE), `CIPHER`,
`ESSID`, associated `STATION`s. `MGT` under AUTH means WPA-Enterprise (EAP).

### Kismet (passive, multi-band, good logging)
```bash
sudo kismet -c wlan0mon            # web UI at http://localhost:2501
```
Kismet passively catalogs APs/clients, device types, probe requests, and can reveal
**hidden SSIDs** when a client that knows the name probes for or associates to it —
purely by observation, no active probing required.

### bettercap Wi-Fi recon (observation only)
```bash
sudo bettercap -iface wlan0mon
> wifi.recon on
> set wifi.show.sort clients desc
> wifi.show
```
> **Do NOT** use `wifi.deauth`, `wifi.assoc`, or any bettercap frame-injection command
> — those are forbidden DoS/forced-disconnect actions.

### Hidden SSIDs
A hidden network omits the SSID in beacons. Recover it **passively** by observing a
legitimate client's association or directed probe (the SSID appears in the
Probe/Assoc frames). Waiting for a natural association is in-scope; sending deauth to
force a re-association is **not**.

### WiGLE (passive OSINT — pre-engagement)
Query **WiGLE.net** (wardriving database) for previously observed APs at the target's
coordinates/SSID to understand the RF footprint **before** you arrive — purely
passive open-source intelligence. Use the web query or API:
```bash
# API (requires WiGLE account token); search by SSID or bounding box:
curl -s -u "$WIGLE_USER:$WIGLE_TOKEN" \
  "https://api.wigle.net/api/v2/network/search?ssid=<AUTHORIZED_SSID>"
```
Only pivot on assets that are in scope.

**Remediation notes for recon findings:** disable SSID broadcast is *not* a real
control (recoverable); reduce beacon info leakage; use unique per-site SSIDs; monitor
for rogue APs with a WIDS.

---

## 2. WPA2-PSK — capture (passively) and crack (offline)

Two capture paths. **Prefer PMKID** — it is collected from the AP alone, needs no
connected client, and requires **no disconnect of anyone**. The 4-way handshake path
is captured by **waiting** for a natural reconnect. **No deauth on either path.**

### 2a. PMKID capture (AP-only, no client, no deauth) — preferred

`hcxdumptool` requests the PMKID from the AP's first EAPOL message (RSN PMKID in
Message 1). Modern versions still capture opportunistically without attacking clients.

```bash
# Capture to pcapng. Restrict to the authorized BSSID with a filter list to avoid
# touching out-of-scope APs:
echo "<AP_BSSID_no_colons>" > authorized_bssids.txt      # e.g. aabbccddeeff
sudo hcxdumptool -i wlan0 -o wpa.pcapng \
     --enable_status=1 \
     --bpf=<optional_bpf> \
     -c <CH>
# (Consult `hcxdumptool --help` on your installed version for the current filter flag
#  name — recent builds use BPF filters / --bpfc; older used --filterlist_ap. The
#  point is: SCOPE THE CAPTURE to the authorized BSSID only.)
```
> hcxdumptool historically had client-attack options; **do not enable any option that
> deauthenticates, disassociates, or floods clients.** PMKID does not need them.

### 2b. 4-way handshake capture (wait for natural reconnect, NO deauth)

```bash
# Park on the authorized AP's channel and WAIT. A handshake is recorded when a client
# associates naturally (device wakes, roams, or your OWN test client reconnects).
sudo airodump-ng -c <CH> --bssid <AP_BSSID> -w handshake wlan0mon
# Top-right of airodump shows "WPA handshake: <BSSID>" once captured.
```
Speeding this up is allowed **only** by legitimate means you control: power-cycle
**your own** test client/AP so it reconnects. **Never transmit deauth** to force
someone off. If no natural handshake appears in the window, fall back to PMKID (2a),
which needs no client at all.

Validate a capture without cracking:
```bash
aircrack-ng handshake-01.cap             # lists whether a valid handshake is present
```

### 2c. Convert to hashcat 22000 format

Mode **22000** is the current unified WPA format (supersedes deprecated 2500/16800)
and covers **both** PMKID and EAPOL handshakes.

```bash
hcxpcapngtool -o hash.hc22000 wpa.pcapng          # or handshake.cap converted
# Optionally scope/filter the hash list to the authorized ESSID/BSSID:
hcxhashtool -i hash.hc22000 --essid=<AUTHORIZED_SSID> -o target.hc22000
```

### 2d. Crack OFFLINE on your own hardware

```bash
# Dictionary attack (authorized handshake only, on your own box, offline):
hashcat -m 22000 target.hc22000 /usr/share/wordlists/rockyou.txt
# Rule-based:
hashcat -m 22000 target.hc22000 wordlist.txt -r rules/best64.rule
# Targeted mask (e.g. known 8-digit default pattern):
hashcat -m 22000 target.hc22000 -a 3 ?d?d?d?d?d?d?d?d
# aircrack-ng equivalent (CPU):
aircrack-ng -w wordlist.txt handshake-01.cap
```
Do **not** submit client hashes to online/third-party cracking services. Delete
hashes and captures per RoE when done.

### Automated (wifite2) — use with the no-deauth flags

`wifite` orchestrates capture+crack but **defaults to sending deauth** to speed
handshake capture. That is forbidden here. If you use it at all, restrict it to
**non-disruptive** modes:
```bash
# PMKID-only (no client interaction, no deauth):
sudo wifite --pmkid --no-deauth -b <AP_BSSID>
```
Prefer the manual PMKID path (2a) so you retain explicit control over what is
transmitted.

**Remediation:** long, high-entropy random PSK (WPA2 offline cracking is only
feasible against weak/guessable passphrases); rotate PSK; prefer WPA3-SAE (resists
offline dictionary attacks by design); consider 802.1X/Enterprise; disable PMKID
caching where not needed / use per-client PSK (WPA3 or vendor "PPSK").

---

## 3. WPA3 / SAE — Dragonblood & transition-mode concepts

WPA3-Personal replaces the PSK 4-way exchange with **SAE (Simultaneous
Authentication of Equals / "Dragonfly")**, which is resistant to the offline
dictionary attack that breaks WPA2-PSK. The relevant weaknesses are **implementation
and deployment** flaws, documented by Mathy Vanhoef & Eyal Ronen as **Dragonblood**
(2019).

Concepts to assess (no active DoS — these are design/config reviews and, where a PoC
is authorized, controlled lab work only):

- **Transition-mode downgrade.** A network in **WPA3-Transition mode** advertises both
  WPA2 and WPA3 so legacy clients can connect. An attacker can induce a client to use
  the WPA2 path (a rogue AP advertising only WPA2 for that SSID), capturing a
  **partial WPA2 handshake** that is then dictionary-attacked **offline** — defeating
  WPA3's protection. *Finding:* transition mode present. *Remediation:* move to
  **WPA3-only** once all clients support it; segment legacy devices onto a separate
  SSID/VLAN.
- **Security-group downgrade.** The SAE handshake negotiates an elliptic-curve group;
  an attacker can try to force a weaker group. *Remediation:* patch AP/client
  firmware; disable weak groups.
- **Timing side-channel** (against Dragonfly). Password-dependent timing in the
  hunting-and-pecking of the password element leaks information usable in a
  partition-oracle/dictionary attack.
- **Cache-based side-channel — CVE-2019-9494.** Micro-architectural cache leakage
  during SAE reveals password-element info (requires code execution on the victim
  device — a client-side flaw). Related IDs from the disclosure include CVE-2019-9495
  through CVE-2019-9499 (EAP-pwd / hostapd / wpa_supplicant).

**How to assess safely:** confirm the mode from beacons/RSN elements
(`airodump-ng` / `wireshark` RSN + AKM suite = SAE vs PSK), check firmware versions
of APs/clients against the vendor's Dragonblood patches, and flag transition mode.
Any downgrade PoC must be run **only** against your own controlled test SSID/clients,
never against bystanders, and never via deauth/jamming. KRACK is covered next.

**Remediation:** patch to post-Dragonblood firmware (hostapd ≥ 2.8 fixes,
wpa_supplicant updates), WPA3-only where feasible, use SAE-PK / H2E (hash-to-element)
which removes the timing side-channel, and strong passphrases as defense in depth.

---

## 4. KRACK (WPA2 key-reinstallation) — awareness / patch verification

**KRACK** (Vanhoef, 2017) abuses the WPA2 4-way (and group/FT) handshake by forcing
**reinstallation of an already-in-use key** (nonce/replay-counter reset), enabling
decryption/replay/forging of frames. It is primarily a **client-side** flaw. Core CVE
**CVE-2017-13077** (PTK-TK reinstall) plus CVE-2017-13078..13088 for the other
variants (group key, FT handshake, etc.).

For an authorized assessment this is a **patch-state finding**, not something to weaponize:
- Enumerate client/AP OS + firmware and check they carry the Oct-2017 KRACK fixes.
- Note that patched clients reject the reinstalled key.
- **Do not** attempt the active MitM/channel-based PoC against real clients (it
  requires manipulating/replaying handshake frames — off-limits here).

**Remediation:** apply vendor KRACK patches to APs and especially clients; enable
802.11w (PMF) where available.

---

## 5. WPA-Enterprise (802.1X / EAP) — evil-twin credential capture (controlled test only)

WPA-Enterprise authenticates each user via **EAP** to a RADIUS server. The classic
assessment finding is **missing/weak server-certificate validation on clients**: if a
client does not verify the RADIUS server certificate (or the user can click through a
cert warning), a **rogue AP** presenting the same SSID can complete enough of the EAP
exchange to capture the credential/handshake.

> **CONTROLLED-TEST ONLY.** Stand up the rogue AP **only** against **your own
> authorized test SSID with your own authorized test accounts**, isolated from real
> users, with the client's informed consent. A look-alike Enterprise SSID in a real
> workplace will capture innocent employees' domain credentials — that is
> **forbidden**. **No deauth to herd clients over.** Tear the AP down immediately after
> the test window.

### EAP method exposure
- **EAP-MSCHAPv2 (PEAP / EAP-TTLS)**: the MSCHAPv2 challenge/response is captured by
  the rogue RADIUS and cracked **offline** (weak DES-based, effectively a single
  DES-key brute force → the NT hash). This is the highest-value capture.
- **GTC downgrade**: after a client accepts the rogue cert, some tools negotiate
  **EAP-GTC** to capture the **plaintext** password.
- **EAP-TLS** (mutual certs) is resistant — no password to steal — but check for
  weak/exportable client certs and enrollment gaps.

### eaphammer (modern) — capture creds from YOUR test users
```bash
# Generate a self-signed RADIUS cert (or use one matching your test CA):
./eaphammer --cert-wizard
# Evil-twin credential capture against your OWN authorized test SSID:
sudo ./eaphammer -i wlan0 --channel <CH> --auth wpa-eap \
     --essid <YOUR_TEST_SSID> --creds
# eaphammer will auto-attempt a GTC downgrade to grab plaintext where the client allows it.
```
Captured MSCHAPv2 challenge/response → crack **offline**:
```bash
# hashcat mode 5500 = NetNTLMv1 / MSCHAPv2:
hashcat -m 5500 mschapv2.hash wordlist.txt
# or asleap for the classic flow.
```

### hostapd-wpe (the underlying rogue-RADIUS)
```bash
# hostapd-wpe (WPE = Wireless Pwnage Edition) logs the EAP identity + MSCHAPv2
# challenge/response for offline cracking. Configure hostapd-wpe.conf with YOUR test
# SSID/channel, then:
sudo hostapd-wpe /etc/hostapd-wpe/hostapd-wpe.conf
```

**Remediation (the real fix, and the point of the finding):**
- Enforce **server-certificate validation** on every client via managed config
  (Group Policy / MDM): pin the CA and the RADIUS server **CN/SAN**; do **not** allow
  users to accept unknown certs.
- Prefer **EAP-TLS** (client certs) over password-based PEAP/TTLS-MSCHAPv2.
- Disable EAP-GTC where not required; disable insecure fallback.
- Use a private CA dedicated to Wi-Fi; short-lived certs; 802.11w (PMF).

---

## 6. WPS — PIN / pixie-dust (conceptual; can LOCK the AP)

WPS lets clients join with an 8-digit **PIN**. Design flaws let the PIN be recovered:
- **Online PIN brute force** (Reaver/Bully): the PIN is validated in two halves
  (~11,000 tries), historically feasible — **but** most modern APs implement **WPS
  lockout**, disabling WPS after a few failed attempts. Hammering it is an
  **availability impact** and is not permitted against production.
- **Pixie-dust** (offline, Dominique Bongard 2014): exploits weak randomness (E-S1/E-S2
  nonces) in vulnerable chipsets (Ralink, Realtek, Broadcom, MediaTek) to recover the
  PIN from a **single** exchange — no repeated guessing, and a successful WPS attack
  yields the **PSK directly** without any handshake cracking.

> **Caution & scope:** WPS PIN attacks can **lock the AP** (degraded service = DoS
> risk). Treat WPS as **conceptual/opportunistic**. If in RoE, test **only on your own
> lab AP**, expect lockouts, and stop on the first sign of lockout. Never brute-force a
> production AP's WPS.

Enumerate WPS state (passive, read-only):
```bash
sudo wash -i wlan0mon                     # lists APs with WPS enabled + locked state
```
Conceptual pixie-dust (lab AP only), tools: `reaver -K 1` / `bully --pixiewps` /
`wifite --wps-only --pixie`. Prefer to simply **report that WPS is enabled** as the
finding rather than exploit it.

**Remediation:** **disable WPS entirely** on all APs (the only robust fix); if WPS is
required, disable external-registrar PIN and use push-button only, ensure firmware
with lockout + fixed RNG.

---

## Reporting

Feed findings to `security-reporting`: weak PSK (offline-cracked authorized
handshake), WPA3 transition-mode downgrade exposure, missing EAP server-cert
validation (evil-twin cred capture in controlled test), WPS enabled/pixie-dust
susceptibility, unpatched KRACK/Dragonblood firmware. Score with CVSS, give the
concrete remediation above, and include the cleanup list (monitor mode off, rogue AP
removed, captures/hashes deleted).
