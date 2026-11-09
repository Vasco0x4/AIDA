# ICS/OT Protocol Reference (Passive Analysis, No Writes)

> **Read this with the safety rules in mind.** Everything below describes protocols so
> you can **recognize and interpret them in a passive capture** and explain the risk.
> The read/enumeration functions are documented so you understand traffic you *observe*
> — not as an invitation to send them. **Write/control functions are documented only to
> explain why they are forbidden.** On live equipment: passive only, never write.

## Why OT protocols are inherently exposed
Almost every classic industrial protocol (Modbus, DNP3, S7comm, ENIP/CIP, BACnet,
IEC-104, PROFINET) was designed decades ago for **isolated, trusted networks**. As a
class they share the same gaps:
- **No authentication** — the device trusts any correctly-formed packet on the wire.
- **No encryption / integrity** — payloads are plaintext, trivially read and spoofed;
  replay works.
- **No authorization** — a read and a "move the valve" write look the same to the
  device; there is no notion of "who is allowed."

This is *why* passive capture reveals so much (everything is cleartext) and *why* any
injected write is so dangerous (the device will simply obey). The correct remediation is
never "add a password to Modbus" (you usually can't) — it is **compensating controls**:
segmentation, IDMZ, read-only conduits, and protocol-aware firewalls that **deny write
function codes** (IEC 62443 zones & conduits). MITRE ATT&CK for ICS **T0855 Unauthorized
Command Message** is the technique these controls defend against.

---

## Modbus / Modbus-TCP — **TCP/502**
- **What it is:** the oldest and most widespread industrial protocol. Master/slave
  (client/server) register model. Ubiquitous in water/wastewater, building automation,
  energy, manufacturing.
- **Data exposed (passively):** device role, unit IDs, and the **function codes** in
  flight. Read functions you may *observe*: `0x01` Read Coils, `0x02` Read Discrete
  Inputs, `0x03` Read Holding Registers, `0x04` Read Input Registers. From these you can
  infer what process values and I/O the device handles.
- **Why writes are forbidden:** write function codes physically actuate plant. `0x05`
  **Write Single Coil** and `0x0F` Write Multiple Coils can **energize/de-energize a
  digital output** — i.e., open/close a valve, start/stop a pump, trip a relay. `0x06`
  **Write Single Register** / `0x10` Write Multiple Registers can **change a setpoint or
  analog output**. There is no authentication, so the PLC will execute it. Sending any
  of these to live equipment can cause a physical event or safety incident. **Never.**
- **Passive analysis:** `tshark -r cap.pcap -Y modbus` — enumerate talkers and
  `modbus.func_code` values seen; a capture full of `0x03` reads maps the register space
  a HMI polls. Presence of write function codes on the wire tells you who commands what.

## DNP3 (Distributed Network Protocol 3) — **TCP/20000** (also serial)
- **What it is:** dominant in North American electric utilities and water SCADA for
  telemetry and control between masters and outstations (RTUs/IEDs).
- **Data exposed:** outstation/master addresses, object/point data (analog & binary
  points), event/class polling. Read-style you may observe: **Read** (func 1), and
  solicited/unsolicited responses carrying point values — a rich picture of the process.
- **Why writes are forbidden:** DNP3 has explicit control functions — **Operate** (func
  4), **Direct Operate** (func 5/6), preceded by **Select** — targeting CROB (Control
  Relay Output Block) and analog output points. These **directly command breakers,
  switches, and setpoints on the grid or plant.** Legacy DNP3 is cleartext with no auth
  (Secure Authentication / DNP3-SA exists but is often not deployed), so an injected
  operate is obeyed. Issuing these on live gear can trip power or move water
  infrastructure. **Never.**
- **Passive analysis:** Wireshark `dnp3` dissector decodes application-layer function
  and object groups; observe control-function presence to identify command paths.

## Siemens S7comm / S7comm-plus — **TCP/102** (ISO-TSAP / COTP)
- **What it is:** Siemens SIMATIC S7 PLC protocol (S7-300/400 classic S7comm; S7-1200/
  1500 use S7comm-plus with added integrity but still attackable in legacy configs).
- **Data exposed:** via passive capture you can identify the PLC, and S7 "SZL/read" style
  exchanges reveal module, firmware, and rack/slot info; data reads expose process
  variables and DB (data block) contents.
- **Why writes are forbidden:** S7 supports **write** to memory/data blocks and
  **PLC control** operations — **STOP/START the CPU** and **download logic/firmware**.
  A STOP halts the controller (loss of control); a logic download alters what the process
  does (this is the class of action Stuxnet abused). On live plant these cause immediate
  disruption or worse. **Never** send them.
- **Passive analysis:** `s7comm` dissector; identify CPU function codes and read/write
  requests present. Fingerprint firmware from observed responses for CVE mapping — no
  active `s7-info` needed if the traffic is already captured.

## EtherNet/IP + CIP — **TCP/44818 (explicit), UDP/2222 (implicit I/O), UDP/44818 (discovery)**
- **What it is:** Common Industrial Protocol over Ethernet; heavily used by Rockwell/
  Allen-Bradley (Logix), Omron, and others. Explicit messaging (44818) for
  config/read/write; implicit I/O (2222) for cyclic real-time data.
- **Data exposed:** ListIdentity/identity objects reveal vendor, product code, serial,
  firmware, device name — a full fingerprint. Attribute reads expose configuration and
  tag data.
- **Why writes are forbidden:** CIP **Set_Attribute_Single/All** and service requests can
  change configuration and tag values; forward-open plus writes can alter controller
  state, and there are documented CIP services to **stop/reset** Logix controllers.
  Changing a tag can move an actuator; a reset drops control. Unauthenticated → obeyed.
  **Never write to live gear.**
- **Passive analysis:** `enip`/`cip` dissectors decode identity and service codes; capture
  the cyclic 2222 I/O to understand real-time control relationships.

## BACnet / BACnet-IP — **UDP/47808 (0xBAC0)**
- **What it is:** building automation (HVAC, lighting, access, energy) — Level 1/2 of
  building OT.
- **Data exposed:** Who-Is/I-Am device discovery, object lists, ReadProperty of present-
  value, device names, vendor IDs — a full inventory of building controllers and points.
- **Why writes are forbidden:** **WriteProperty / WritePropertyMultiple** change present-
  values and setpoints (e.g., override a damper, a setpoint, or a priority array).
  Overriding building controls can disable ventilation, cause pressure/temperature
  excursions, or unlock doors. Unauthenticated. **Never write.**
- **Passive analysis:** `bacnet`/`bvlc` dissectors; passively observed Who-Is/I-Am gives
  the device census without you sending a single Who-Is.

## OPC-UA — **TCP/4840**
- **What it is:** the modern, security-capable OT protocol (unified architecture) used
  for supervisory data exchange, often at Level 2/3 and across the IDMZ.
- **Data exposed:** endpoint discovery reveals security policies offered; the concern is
  when it is deployed with **SecurityPolicy=None / no encryption / anonymous access**,
  exposing the address space (nodes, values, methods) freely.
- **Why writes are forbidden:** OPC-UA supports **Write** to node values and **Call** of
  server methods, which can drive downstream control. When misconfigured to allow
  anonymous/None, these are unauthenticated in practice. **Never write to live systems.**
- **Passive analysis:** `opcua` dissector; from a capture note whether sessions use
  `None`/anonymous (a finding) vs. Sign&Encrypt with certificates (good). This is a
  key **misconfiguration to report**, checkable passively.

## IEC 60870-5-104 (IEC-104) — **TCP/2404**
- **What it is:** telecontrol protocol dominant in European/international electric power
  SCADA (and beyond); the TCP/IP profile of IEC 60870-5-101.
- **Data exposed:** ASDU addressing, information-object addresses, monitoring information
  (measured values, status) via interrogation and spontaneous reports — maps the RTU's
  telemetry.
- **Why writes are forbidden:** IEC-104 has explicit **command** ASDU types — single/
  double command (C_SC/C_DC), setpoint commands (C_SE), and general interrogation. Commands
  **operate breakers and setpoints on the power system.** No authentication in the base
  standard. Injecting a command can trip substation equipment — a grid safety/reliability
  event. **Never.**
- **Passive analysis:** `iec60870_104`/`104apci`/`104asdu` dissectors decode APCI/ASDU;
  observe which command types traverse the link to map control authority.

## PROFINET — **(PN-DCP L2; PN-IO real-time; context over UDP/34964 DCE/RPC)**
- **What it is:** Siemens-led industrial Ethernet for real-time I/O, common on plant
  floors alongside PROFIBUS.
- **Data exposed:** PN-DCP identify/hello (Layer-2, no IP) reveals station names, MACs,
  device roles; real-time frames show cyclic I/O relationships.
- **Why writes/active is forbidden:** PN-DCP **Set** can change a device's name/IP; RT
  frames drive I/O. Even DCP-Identify (active discovery) is Layer-2 broadcast that some
  fragile devices handle poorly. Stay passive; **never** issue DCP-Set or manipulate RT.
- **Passive analysis:** `pn_dcp` / `pn_rt` dissectors; passive PN-DCP hello frames give a
  station inventory with zero transmission from you.

## IEC 61850 (MMS / GOOSE / SV) — **MMS TCP/102; GOOSE & Sampled Values on Layer-2 multicast**
- **What it is:** the substation automation standard. MMS for client/server (over the
  same 102 as S7's ISO stack), **GOOSE** for fast Layer-2 protection/trip messaging,
  **Sampled Values** for digitized CT/VT measurements.
- **Data exposed:** MMS reveals the substation data model (logical nodes, datasets);
  GOOSE/SV multicast is visible passively on the process/station bus.
- **Why writes/injection is forbidden:** GOOSE carries **protection trip** signals; a
  spoofed/injected GOOSE frame can **operate a breaker** or block a trip — a direct
  power-safety hazard (well-documented attack research). MMS control can operate switchgear.
  **Never inject GOOSE/SV or issue MMS control** on a live substation. Passive capture of
  GOOSE/SV is fine and highly informative.
- **Passive analysis:** `goose`, `sv`, and `mms` dissectors; passively verify whether
  GOOSE integrity/signing is in use and map the protection scheme.

---

## Reporting protocol findings (remediation framing)
For every unauthenticated protocol observed, the finding is not "protocol X is insecure"
(it is, by design) but **"protocol X is reachable across a boundary it should not cross /
lacks compensating controls."** Remediation per IEC 62443 / NIST 800-82r3:
- Place the protocol inside a defined **zone**; permit it only through a controlled
  **conduit**.
- Use a **protocol-aware / industrial firewall** to enforce **read-only** where possible
  and **deny write/control function codes** across the conduit.
- Terminate control traffic at the **IDMZ**; use **data diodes** for one-way historian
  egress.
- Migrate to secured variants where feasible (**DNP3-SA**, **OPC-UA with Sign&Encrypt +
  certificates**, IEC 62351 for 61850/104) — but treat as long-term, engineer-led change.
- Restrict engineering functions (S7 STOP/START, CIP reset, logic download) to specific
  hosts on a management conduit with strong auth and monitoring.
