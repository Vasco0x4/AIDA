# Sources — Consulted Public References

Public, authoritative material grounding this skill. Frameworks and vendor/agency docs
should be treated as the primary references; cite the specific advisory/section in
findings.

## Core frameworks & standards
- NIST SP 800-82 Rev. 3 — *Guide to Operational Technology (OT) Security* (Sept 2023):
  https://csrc.nist.gov/pubs/sp/800/82/r3/final
- IEC 62443 series (zones & conduits, SL 1-4, component & system requirements) — overview:
  https://www.isa.org/standards-and-publications/isa-standards/isa-iec-62443-series-of-standards
- MITRE ATT&CK for ICS (matrix, tactics, techniques):
  https://attack.mitre.org/matrices/ics/
  - Impair Process Control (TA0106): https://attack.mitre.org/tactics/TA0106/
  - Unauthorized Command Message (T0855): https://attack.mitre.org/techniques/T0855/
- Purdue Enterprise Reference Architecture / Purdue model — background:
  https://en.wikipedia.org/wiki/Purdue_Enterprise_Reference_Architecture

## CISA — advisories & recommended practices
- CISA cybersecurity advisories (filter to ICS / ICS Medical):
  https://www.cisa.gov/news-events/cybersecurity-advisories
- CISA ICS recommended practices / defense-in-depth guidance:
  https://www.cisa.gov/resources-tools/resources/ics-recommended-practices

## Protocols
- ITI / ICS-Security-Tools — protocol port reference:
  https://github.com/ITI/ICS-Security-Tools/blob/master/protocols/PORTS.md
- INCIBE — Protocols and network security in ICS infrastructures (PDF):
  https://www.incibe.es/sites/default/files/contenidos/guias/doc/incibe_protocol_net_security_ics.pdf
- Wireshark — protocol reference / ICS dissectors (Modbus, DNP3, S7comm, ENIP/CIP, BACnet,
  IEC 60870-5-104, OPC-UA, PROFINET, IEC 61850 MMS/GOOSE/SV):
  https://www.wireshark.org/docs/dfref/
- Modbus specification (Modbus Organization): https://www.modbus.org/specs.php
- DNP3 (DNP Users Group): https://www.dnp.org/
- OPC-UA (OPC Foundation): https://opcfoundation.org/about/opc-technologies/opc-ua/

## Passive discovery & tooling
- GRASSMARLIN (NSA / open-source passive ICS network mapper):
  https://github.com/nsacyber/GRASSMARLIN
- CISA Malcolm (network traffic analysis with ICS/Zeek parsers):
  https://github.com/cisagov/Malcolm
- Nmap ICS/SCADA NSE scripts (USE WITH STRONG CAUTION — active):
  https://nmap.org/nsedoc/ (e.g. modbus-discover, s7-info, enip-info, bacnet-info, omron-info)
- Redpoint / DigitalBond ICS enumeration scripts (active — caution):
  https://github.com/digitalbond/Redpoint
- plcscan (active PLC scanner — caution): https://github.com/meeDamian/plcscan

## External-exposure OSINT
- Shodan (device search engine) and ICS map: https://www.shodan.io/ , https://icsmap.shodan.io/
- Censys (host/service search): https://search.censys.io/

## Historical context (why the safety rules exist)
- TRITON / TRISIS (Triconex SIS) — CISA/analysis references via CISA advisories above.
- Industroyer / CRASHOVERRIDE (IEC-101/104/61850) — CISA advisories above.
- Stuxnet (Siemens S7 logic manipulation) — widely documented public analyses.

*Note: search-result summaries and third-party blogs were used only to locate the
primary sources above; rely on the standards bodies, CISA, MITRE, and vendor
documentation for authoritative detail.*
