# Bluetooth / BLE — Discovery, GATT Enumeration, Pairing, Sniffing

**Read-first, own-devices-only doctrine.** Enumerate and **read** before you ever
consider writing. Test **only** Bluetooth/BLE devices you own or that are named in the
RoE. **No connection floods, no jamming, no forced-disconnect** — those are DoS and
forbidden. Writing to a characteristic can change device state (unlock, actuate,
brick) — treat writes as high-risk and only against your own test device with a known
recovery path.

Assumes BlueZ on Linux: `bluetoothctl`, `hcitool`/`hciconfig` (legacy),
`btmgmt`, `gatttool`/`bluetoothctl` GATT, plus `bettercap` BLE module and an
**Ubertooth One** for sniffing.

---

## 1. Adapter prep

```bash
hciconfig -a                 # list adapters (hci0), state, address
sudo hciconfig hci0 up       # bring up
bluetoothctl                 # interactive shell
[bluetooth]# power on
[bluetooth]# show            # controller info / supported features
```

---

## 2. Discovery (passive-ish scan)

### Classic Bluetooth (BR/EDR)
```bash
# Inquiry scan for discoverable classic devices:
bluetoothctl
[bluetooth]# scan on
# Legacy: hcitool scan   (classic)  /  hcitool inq  (with clock offset/class)
sudo hcitool -i hci0 scan
```
Note: non-discoverable classic devices won't appear in a normal inquiry. Do **not**
brute-force address ranges (that is intrusive/DoS-adjacent).

### BLE (LE advertising scan — passive receive)
```bash
# bluetoothctl BLE scan:
[bluetooth]# menu scan
[bluetooth]# transport le
[bluetooth]# scan on          # shows advertising LE devices, RSSI, names, service UUIDs
# Legacy passive LE scan:
sudo hcitool lescan --passive
# btmgmt:
sudo btmgmt find              # LE + BR/EDR discovery
```
Advertising packets are broadcast by the device; receiving them is passive. Record
MAC, name, advertised service UUIDs, TX power, and whether the address is random
(privacy) or public.

### bettercap BLE recon
```bash
sudo bettercap -eval "ble.recon on"
> ble.show                     # table of discovered BLE devices
```

---

## 3. GATT enumeration (READ-first)

BLE data is organized as **GATT**: *services* (UUID-named containers) hold
*characteristics* (UUID-named values) with *properties* (read/write/notify/indicate)
and optional *descriptors*. Enumerate the tree, then read the readable ones.

### bettercap
```bash
> ble.enum <MAC>               # dumps services, characteristics, properties, values
```

### bluetoothctl (BlueZ native GATT)
```bash
[bluetooth]# connect <MAC>
[bluetooth]# menu gatt
[bluetooth]# list-attributes <MAC>     # services/characteristics/descriptors
[bluetooth]# select-attribute <char-UUID>
[bluetooth]# read                      # read the characteristic value
```

### gatttool (legacy but explicit)
```bash
gatttool -b <MAC> --primary            # list primary services + handle ranges
gatttool -b <MAC> --characteristics    # list characteristics + value handles + props
gatttool -b <MAC> --char-read -a 0x002a # read the value at a handle
# Interactive:
gatttool -b <MAC> -I
> connect
> primary
> characteristics
> char-read-hnd 0x002a
```

**What to look for (read-only findings):**
- Sensitive values exposed as **readable without pairing/auth** (keys, PINs, tokens,
  firmware versions, user data).
- Characteristics with **write** property that control device behavior but require **no
  authentication/encryption** — an authorization gap. *Document the gap; do not
  actuate someone else's device.*
- **Notify/indicate** characteristics that stream data — subscribing reveals live
  values (`char-write-req <cccd-handle> 0100` enables notifications) — only on your
  own device.

> **Writes are high-risk.** A write can unlock a lock, disable a safety feature, or
> brick firmware. Only write to **your own** test device, with recovery available, and
> only to demonstrate a specific authorization/encryption gap already identified by
> reading. Never write to a device that is not yours.

---

## 4. Pairing / bonding weaknesses (assessment, not exploitation)

Bluetooth pairing security depends on the **Association Model** and, for BLE, the
**Security Manager Protocol (SMP)** pairing method:

- **Legacy Pairing / "Just Works"** — no MITM protection; keys can be derived/guessed;
  susceptible to passive-eavesdropping-then-decrypt if the pairing exchange was
  captured. *Finding:* device negotiates Just Works when it handles sensitive data.
- **Legacy BLE (pre-4.2) key exchange** is weak (crackable TK/STK — e.g. the classic
  *crackle* attack recovers the Long-Term Key from a captured legacy pairing).
- **No/weak encryption on the link** — characteristics readable/writable without an
  encrypted, authenticated connection.
- **Static / predictable passkeys** (0000/1234), fixed PINs on classic devices.
- **Address randomization off** — trackable device (privacy finding).

**How to assess safely:** observe the advertised/negotiated security level
(`bluetoothctl` shows pairing prompts; SMP method appears in a sniffed pairing). For
your own test device, attempt pairing with the intended model and confirm whether it
enforces MITM protection + encryption. Do **not** attempt to break the pairing of a
third-party device or capture a stranger's pairing exchange.

**Remediation:** require **LE Secure Connections** (BLE 4.2+, ECDH P-256) with an
authenticated model (Passkey/Numeric Comparison, not Just Works) for sensitive data;
enforce encryption + authorization on all sensitive characteristics; rotate/avoid
static passkeys; enable resolvable private addresses.

---

## 5. Sniffing (passive RF capture — your own devices)

Capturing BLE over the air is legitimate for **your own** devices to inspect the
pairing method and traffic. It is passive receive; **do not** jam or inject.

### Ubertooth One (BLE / classic experimentation)
```bash
ubertooth-util -v                       # confirm firmware/device
# Follow a BLE connection / capture advertising to a pcap for Wireshark:
ubertooth-btle -f -c capture.pcap       # -f follow connections
wireshark capture.pcap                  # dissect ATT/SMP/GATT
```
Ubertooth can follow BLE connections and export to Wireshark (`btle` dissector). For
classic BR/EDR, sniffing is much harder (frequency hopping); Ubertooth offers limited
classic capability.

### nRF / dedicated sniffers
Nordic nRF52840 dongle + **nRF Sniffer for Bluetooth LE** plugs into Wireshark and is
a common, reliable BLE capture path for your own device analysis.

### bettercap
`ble.recon`/`ble.enum` capture advertising + GATT interaction logs (see §2–3).

**What sniffing reveals (own-device analysis):** the SMP pairing method (Just Works
vs authenticated), whether the link is encrypted, and — for legacy pairing — enough to
demonstrate LTK recovery (crackle) as a finding. Keep captures scoped to your own
device; delete per RoE.

---

## Reporting

Feed to `security-reporting`: unauthenticated readable/writable sensitive
characteristics, Just Works / legacy pairing on sensitive devices, unencrypted links,
static passkeys, missing address randomization, firmware/version exposure. Provide the
remediation in §4 and note that no third-party device was actuated and captures were
deleted.
