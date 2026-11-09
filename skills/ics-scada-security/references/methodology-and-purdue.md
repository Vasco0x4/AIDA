# Methodology, Purdue Model & the Passive-First Doctrine

> Reinforcing the prime directive: **OT devices run physical processes.** The default
> action is to *observe*, never to *provoke*. This file explains the reference
> architecture you are mapping, the boundary that matters most, why SIS is untouchable,
> and the exact safe order of work. Read `SKILL.md`'s ⚠️ Safety section first.

---

## 1. The Purdue Enterprise Reference Architecture (Purdue model)

NIST SP 800-82r3 and IEC 62443 both use the Purdue model as the mental map for OT
network segmentation. Levels run from the physical process up to the corporate
enterprise. Knowing which level a device sits at tells you **how fragile it is and how
close it is to the physical process** — and therefore how carefully you must tread.

| Level | Name | Typical assets | Fragility / caution |
|-------|------|----------------|---------------------|
| **Level 0** | Physical process | Sensors, actuators, valves, motors, drives, field instruments | The physical world. Signals here *are* the process. Never inject. |
| **Level 1** | Basic control | **PLCs, RTUs, IEDs, safety controllers** | Real-time control loops. **Most fragile to scans/malformed packets — has crashed on version probes.** Writes here move plant. |
| **Level 2** | Area supervisory control | **HMIs, SCADA servers, engineering workstations (EWS)** | Operator screens & logic-programming stations. Compromise = ability to command Level 1. |
| **Level 3** | Site operations | Historians, MES, batch, domain controllers, patch/AV servers for OT | Site-wide OT management. Bridge to IT. |
| **Level 3.5 (IDMZ)** | Industrial DMZ | Jump hosts, replicated historians, proxies, data diodes / unidirectional gateways | The controlled buffer between OT and IT. **The key boundary.** |
| **Level 4** | Site business / IT | ERP, email, business apps for the site | Standard IT. |
| **Level 5** | Enterprise | Corporate IT, cloud, internet edge | Standard IT / internet. |

**Consequence rule:** the *lower* the level, the *closer* to physical harm and the
*less* tolerant of unexpected traffic. Passive observation is safe at every level;
active traffic risk **increases sharply** as you go down toward Level 1/0.

### Safety Instrumented Systems (SIS) — OFF-LIMITS
SIS (safety PLCs, Emergency Shutdown / ESD, Burner Management / BMS, High-Integrity
Pressure Protection / HIPPS) are a **separate protective layer**, often at "Level 1"
alongside basic-control PLCs but functionally isolated (IEC 61511 / SIL-rated). Their
whole job is to bring the process to a safe state and protect human life. **You do not
scan, probe, query, or send any traffic to SIS. Ever.** Interfering with a safety
function can directly cause injury or a catastrophic event. SIS is out of scope by
default; if a client insists it be assessed, that is a passive-only, engineer-led,
separately-authorized activity — and even then err toward *not touching it*. The 2017
TRITON/TRISIS malware, which targeted Triconex SIS controllers, is the canonical
warning of why this layer is sacrosanct.

---

## 2. The IT/OT boundary — where the real risk (and the real attack path) lives

The single most important architectural feature is the **IT/OT boundary**, ideally
enforced by an **Industrial DMZ (IDMZ / Level 3.5)**. Real OT compromises rarely start
by "hacking a PLC"; they start in IT (phishing, VPN, exposed remote access) and
**pivot down** through a flat or poorly-segmented boundary. IEC 62443's zones-and-
conduits model exists precisely to control this.

What to assess (passively, and on the IT side with normal IT technique within scope):
- Is there an actual IDMZ, or does IT talk **directly** to Level 2/1? (Flat network =
  top finding.)
- Remote-access paths into OT (vendor VPNs, jump hosts, RDP, TeamViewer/AnyDesk, cellular
  routers on RTUs). These are frequent real entry points.
- Data diodes / unidirectional gateways for historian egress (good practice per NIST
  800-82r3) vs. bidirectional firewall rules that permit control traffic upward.

The IT side of this boundary (jump hosts, historian IT interfaces, remote-access
servers, OT Active Directory) is often testable as **normal IT** — see
`network-service-exploitation` and `active-directory-attack-paths` — but always confirm
scope, and remember anything that can reach down into Level 1/2 must be handled with OT
caution.

---

## 3. Passive-first discovery — the primary method

This is where the majority of an OT assessment happens, and it carries **essentially
zero risk to the process** because you transmit nothing to control equipment.

### 3.1 Get the traffic without injecting traffic
- **Network TAP (preferred):** a passive hardware tap on a mirror-worthy link copies
  frames to your capture host with no effect on the live link. Fully passive; the safest
  option. Fails safe (many taps are passive optical/copper).
- **SPAN / port-mirror (switch-configured):** ask the OT network engineer to mirror the
  relevant port(s)/VLAN(s) to your capture port. Configuring SPAN is a switch-management
  action — have the engineer do it and watch for switch CPU load on old gear. Your
  capture NIC should be **receive-only** (consider a physical TX-disabled cable or
  `ip link set <if> promisc on` with no IP configured) so your host cannot accidentally
  emit onto the OT segment.
- **Placement:** capture near aggregation points where Level 2↔Level 1 traffic and
  IDMZ↔OT traffic transit, to see the most devices and conversations.

Practical capture hygiene:
```bash
# Bring the capture interface up with NO IP address so the host can't talk on OT.
sudo ip addr flush dev eth1
sudo ip link set eth1 up promisc on
# Capture to disk for offline analysis (rotate files, no live probing):
sudo tcpdump -i eth1 -w ot_capture_%Y%m%d_%H%M%S.pcap -G 3600 -Z root
```

### 3.2 Analyze offline with ICS-aware tools
- **Wireshark / tshark with ICS dissectors** — Wireshark ships dissectors for Modbus,
  DNP3, S7comm, ENIP/CIP, BACnet, IEC 60870-5-104, OPC-UA, PROFINET, and more. Load the
  pcap and read the conversations; **do not** use Wireshark's active features against OT.
  Useful offline passes:
  ```bash
  # Inventory talkers and protocols seen (all read from the pcap, nothing sent):
  tshark -r ot_capture.pcap -q -z conv,ip
  tshark -r ot_capture.pcap -q -z io,phs        # protocol hierarchy
  tshark -r ot_capture.pcap -Y modbus -T fields -e ip.src -e ip.dst -e modbus.func_code
  ```
- **GRASSMARLIN** (NSA-released, open-source) — purpose-built **passive** ICS network
  mapper. Ingests live SPAN/TAP or pcap and produces a device inventory and topology
  graph with OT protocol awareness. Designed for exactly this job: situational awareness
  with no active probing.
- **ntop / ntopng, Zeek/Malcolm** — passive flow and protocol visibility; Zeek with ICS
  protocol parsers (and CISA's Malcolm distribution) gives searchable passive logs.
- **Commercial passive OT-monitoring** (Nozomi, Claroty, Dragos, Tenable OT) — many OT
  owners already run one; its passive inventory is a legitimate data source to request.

### 3.3 Build the passive asset inventory
From the capture alone you can typically derive, per device: IP/MAC, vendor (MAC OUI),
role (PLC/HMI/EWS/historian), protocols spoken, function codes observed, firmware/model
hints in protocol banners, and the conversation map (who commands whom). That inventory
plus the topology **is the backbone of the report** — achieved without sending a single
packet to a controller.

---

## 4. Framework mapping (cite these in findings)

- **NIST SP 800-82r3 — Guide to OT Security** (Sept 2023): the U.S. baseline. Endorses
  defense-in-depth on the Purdue model, **favors passive over active techniques**,
  consequence-driven risk analysis, IDMZ, and data diodes. Map architecture and
  monitoring findings here.
- **IEC 62443**: the international ICS security standard series. **Zones & conduits**
  (62443-3-2), system requirements & security levels SL 1-4 (62443-3-3), component
  requirements (62443-4-2), secure development lifecycle (62443-4-1). Frame all
  segmentation/remediation against zones-and-conduits.
- **MITRE ATT&CK for ICS** (https://attack.mitre.org/matrices/ics/): adversary TTPs for
  OT. Key tactics to reference: *Initial Access*, *Lateral Movement*, *Collection*,
  *Inhibit Response Function*, *Impair Process Control* (TA0106, e.g. **T0855
  Unauthorized Command Message** — the technique your "no writes" rule prevents), and
  *Impact* (e.g. Loss of Availability/Control/Safety). Map observed exposure to the
  techniques it would enable.
- **CISA ICS advisories & recommended practices**: authoritative source for OT product
  CVEs and defensive guidance (e.g., "Defense in Depth" strategies, secure remote
  access). Cite specific ICSA-YY-NNN advisories for device CVEs (see
  `references/exposure-and-cves.md`).

---

## 5. The strict gate for ANY active testing

Most OT assessments should conclude on passive discovery + OSINT + architecture review.
Active testing is the exception, not the goal. If — and only if — it is genuinely
required and the client wants it:

**All of these must be true before a single active packet touches OT:**
- [ ] **Explicit written OT-owner approval** naming the exact assets and actions.
- [ ] **On-site control engineer supervising** in real time, able to intervene.
- [ ] **Maintenance window / planned downtime**, or a dedicated **test rig / lab /
      digital twin** — never against live production running a process.
- [ ] **NOT a SIS device** and not on a segment carrying SIS traffic.
- [ ] **Rollback / restart plan** ready; client expects possible instability and reboot.
- [ ] Emergency contacts and an agreed **abort signal** in place.

Even then, keep active work **read-only and minimal**:
- Prefer identifying by passive means already gathered.
- If a probe is authorized, use the **least-intrusive** technique, one device at a time,
  slowly, watching the engineer's HMI for any deviation between each step.
- **Never** send write/control/operate/stop/start/download functions to any device.
- If using Nmap, avoid it against Level 1 where possible; if authorized, understand that
  ICS NSE scripts (e.g. `modbus-discover`, `s7-info`, `enip-info`, `bacnet-info`,
  `omron-info`) **send protocol requests** and some devices tolerate this poorly. Rate-
  limit hard (`--scan-delay`, `-T2` or slower, no aggressive timing), scope to single
  hosts, and stop at the first sign of trouble. `plcscan` and Redpoint/DigitalBond NSE
  scripts carry the same caution — they are **active** and can disturb fragile PLCs.
- Abort immediately on any unresponsiveness, alarm, or process deviation (stop
  conditions from `SKILL.md`).

If any checkbox is unmet: **do not do active testing.** Report what passive methods
found and note that active validation was out of safe scope. That is a correct,
professional outcome for OT.
