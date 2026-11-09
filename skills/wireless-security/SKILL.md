---
name: wireless-security
description: "Authorized wireless security assessment for Wi-Fi (WPA2/WPA3, PSK & Enterprise/EAP), Bluetooth/BLE, and RFID/NFC. Covers passive Wi-Fi recon (airodump-ng, Kismet, bettercap, WiGLE OSINT), WPA2-PSK 4-way handshake capture by natural reconnect and PMKID capture (hcxdumptool/hcxtools) with OFFLINE hashcat -m 22000 cracking of authorized handshakes, WPA3/SAE Dragonblood downgrade/side-channel and transition-mode weaknesses, WPA-Enterprise EAP evil-twin credential capture in controlled tests (eaphammer, hostapd-wpe) and certificate-validation gaps, WPS PIN/pixie-dust concepts (can lock APs), Bluetooth/BLE discovery + GATT enumeration + pairing/sniffing (bluetoothctl, gatttool, bettercap BLE, Ubertooth), and RFID/NFC MIFARE Classic weaknesses + cloning with Proxmark3/mfoc/mfcuk. Capture-passively, no-deauth bias throughout. Authorized, in-scope engagements only — test only networks/devices you own or have explicit written authorization for; NO deauthentication, jamming, or forced disconnects (DoS, FORBIDDEN). Use for wifi pentest, wpa2 cracking, pmkid, wpa3, dragonblood, evil twin, eap creds, wps, bluetooth/ble, gatt, rfid/nfc, mifare."
version: 1.0.0
triggers:
  - wifi pentest
  - wireless security
  - wireless assessment
  - wpa2 cracking
  - wpa handshake
  - pmkid
  - hcxdumptool
  - hashcat wpa
  - hashcat 22000
  - aircrack
  - airodump
  - wpa3
  - sae
  - dragonblood
  - krack
  - evil twin
  - rogue ap
  - eap
  - wpa-enterprise
  - eaphammer
  - hostapd-wpe
  - wps
  - pixie dust
  - reaver
  - wifite
  - kismet
  - bettercap
  - wigle
  - bluetooth
  - ble
  - gatt
  - ubertooth
  - rfid
  - nfc
  - mifare
  - proxmark
---

# Wireless Security (Authorized Wi-Fi / BLE / RFID Assessment)

Operational playbook for the **passive-first** wireless kill chain on an authorized
engagement: recon → capture (passively) → **offline** analysis → controlled active
tests → remediation write-up. The bias throughout is **listen, don't disrupt** —
capture handshakes by waiting for natural client reconnects or by using PMKID (which
needs no client at all), crack **offline**, and reserve any active radio work for
your own controlled test SSIDs/devices.

Assumes a Linux attack host (Kali/parrot) with a monitor-mode-capable Wi-Fi adapter,
the `aircrack-ng` suite, `hcxdumptool`/`hcxtools`, `hashcat`, `kismet`, `bettercap`,
`wifite`, `eaphammer`, BlueZ (`bluetoothctl`, `hcitool`, `gatttool`), and — for
RFID — a `proxmark3` and/or `libnfc` (`mfoc`, `mfcuk`, `nfc-list`).

## ⚠️ Safety — inherits `safe-testing-doctrine`

Load **`safe-testing-doctrine`** before any active radio work. This skill inherits
every hard limit there. Wireless is uniquely dangerous because the medium is shared
and RF affects bystanders you cannot see. **Hard rules:**

- **Authorization & legality.** Test **only** Wi-Fi networks, Bluetooth/BLE devices,
  and RFID/NFC cards that **you own** or that are **named in signed written
  authorization / RoE**. Intercepting, decrypting, or capturing other people's
  communications is a **crime** in most jurisdictions (Wiretap Act / CFAA in the US,
  the Computer Misuse Act in the UK, equivalents elsewhere) even if you never use the
  data. When in doubt, do not capture.
- **ABSOLUTELY NO deauthentication, disassociation, jamming, or forced
  disconnects.** These are **denial-of-service** attacks against clients and are
  **FORBIDDEN** by this skill base. Do **not** run `aireplay-ng --deauth`,
  `mdk3/mdk4`, bettercap `wifi.deauth`, or any tool's "deauth to speed up capture"
  option. Capture 4-way handshakes by **waiting** for devices to reconnect naturally
  (power-cycle of *your own* test AP/client, or normal roaming), or — preferably —
  use **PMKID**, which is collected from the AP alone and needs no client and no
  disconnect. Any tool flag that transmits deauth/disassoc frames is off-limits.
- **No jamming / no RF floods.** No continuous beacon floods, no channel jamming, no
  BLE/Bluetooth connection floods, no NFC field abuse. These are DoS and are
  forbidden. Radio congestion harms bystanders and is often separately illegal
  (spectrum regulations).
- **Evil-twin / rogue-AP only in a controlled test.** Stand up a rogue AP
  (eaphammer/hostapd-wpe) **only** against **your own authorized test SSID with your
  own authorized test users/accounts**, in an isolated area, with the client's
  informed consent. **Never** operate a rogue AP to harvest credentials or traffic
  from **real bystanders** or any user not enrolled in the test. Broadcasting a
  look-alike SSID in a public/shared space captures innocent third parties — that is
  forbidden. **Tear down every rogue AP** the moment the test window ends.
- **Crack only what you were authorized to capture, offline.** Run
  `hashcat`/`aircrack-ng` **only** against handshakes/PMKIDs captured from the
  in-scope network, on your own hardware, **offline**. Do not upload client hashes to
  third-party cracking services.
- **WPS caution.** WPS PIN brute-force / pixie-dust can **lock the AP** (WPS
  lockout), degrading service — that is an availability impact. Treat WPS testing as
  **conceptual/opportunistic only**; if you test it at all, do so on your own lab AP,
  respect lockouts, and never hammer a production AP.
- **No third-party traffic capture or processing.** If you passively capture frames,
  do **not** decrypt, store, or analyze traffic belonging to anyone outside scope.
  Minimize retention; handle any captured material per the doctrine's evidence rules;
  securely delete captures when the engagement ends.
- **Cleanup.** Bring radios out of monitor mode, remove rogue APs and any test
  RADIUS/cert material, and delete captures/hashes per RoE when done.

Stop and consult the engagement lead if you observe out-of-scope SSIDs/devices, if a
capture would inevitably include bystander traffic, or if any AP shows signs of
service degradation.

## Index — pick the area

| Area | Reference file | Covers |
|------|----------------|--------|
| Wi-Fi (recon, WPA2 PMKID/handshake, WPA3/Dragonblood, Enterprise/EAP, WPS) | `references/wifi.md` | Passive discovery & enumeration, PMKID + 4-way capture (no-deauth), offline `hashcat -m 22000`, WPA3/SAE transition-mode & side-channel concepts, evil-twin EAP credential capture in controlled tests, WPS pixie-dust concepts |
| Bluetooth / BLE | `references/bluetooth-ble.md` | Discovery, GATT service/characteristic enumeration (read-first), pairing weaknesses, sniffing (Ubertooth/bettercap) |
| RFID / NFC | `references/rfid-nfc.md` | MIFARE Classic CRYPTO1 weaknesses, key recovery & cloning with Proxmark3 / mfoc / mfcuk — your own / authorized cards only |
| Public sources | `references/sources.md` | Cited tool docs and research URLs |

## Workflow at a glance

1. **Scope & authorize** — confirm exact in-scope SSIDs/BSSIDs, BLE devices, and
   cards in writing. Note channels, physical area, and test window.
2. **Passive recon** (`references/wifi.md`) — monitor mode, `airodump-ng`/Kismet
   survey, WiGLE OSINT. Identify AP, clients, security (WPA2/WPA3/Enterprise), WPS.
3. **Passive capture** — PMKID via `hcxdumptool` (no client needed) and/or wait for a
   natural 4-way handshake. **No deauth.**
4. **Offline analysis** — convert with `hcxpcapngtool`, crack with `hashcat -m 22000`
   on your own hardware.
5. **Controlled active tests** (only if in RoE) — WPA3 transition-mode review,
   Enterprise evil-twin against your own test users, WPS on your own lab AP.
6. **BLE / RFID** as scoped — read-first enumeration, own-cards-only cloning.
7. **Report** — hand findings to `security-reporting` with remediation.

For engagement sequencing across skills, see `engagement-orchestrator` and
`pentest-methodology`.
