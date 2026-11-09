# Sources — Consulted Public References

Public tool documentation and research consulted while writing this skill. Verify
current tool flags/modes against the linked upstream docs before use — options evolve.

## Wi-Fi — tools

- Aircrack-ng suite documentation — https://www.aircrack-ng.org/documentation.html
  (airmon-ng, airodump-ng, aircrack-ng)
- hcxdumptool (ZerBea) — https://github.com/ZerBea/hcxdumptool
- hcxtools (ZerBea) — https://github.com/ZerBea/hcxtools
  (hcxpcapngtool, hcxhashtool; workflow: hcxdumptool → hcxpcapngtool → hcxhashtool → hashcat/JtR)
- hashcat — WPA-PBKDF2-PMKID+EAPOL mode 22000 (supersedes 2500/16800) —
  https://hashcat.net/hashcat/  and  https://hashcat.net/wiki/doku.php?id=cracking_wpawpa2
- wifite2 (derv82) — https://github.com/derv82/wifite2  and  https://www.kali.org/tools/wifite/
- Kismet — https://www.kismetwireless.net/docs/
- bettercap Wi-Fi module — https://www.bettercap.org/modules/wifi/
- wash / reaver (WPS enumeration & attack) — https://github.com/t6x/reaver-wps-fork-t6x
- bully (WPS) — https://github.com/aanarchyy/bully
- pixiewps (pixie-dust) — https://github.com/wiire-a/pixiewps
- WiGLE (passive wardriving OSINT / API) — https://wigle.net/  ,  https://api.wigle.net/

## Wi-Fi — research

- Dragonblood (Vanhoef & Ronen) — https://wpa3.mathyvanhoef.com/  ,
  paper: https://papers.mathyvanhoef.com/dragonblood.pdf  (WPA3/SAE downgrade & side-channel;
  CVE-2019-9494 cache side-channel and related CVE-2019-9495..9499)
- KRACK (Vanhoef) — https://www.krackattacks.com/  (WPA2 key-reinstallation;
  CVE-2017-13077 and CVE-2017-13078..13088)
- US-CERT / vendor KRACK advisories — https://www.kb.cert.org/vuls/id/228519

## WPA-Enterprise / EAP evil-twin

- eaphammer (s0lst1c3) — https://github.com/s0lst1c3/eaphammer  (--creds, GTC downgrade, cert-wizard)
- hostapd-wpe — https://github.com/OpenSecurityResearch/hostapd-wpe  (and Kali package)
- pi-pwnbox-rogueap wiki — WPA/WPA2-Enterprise (MGT) Rogue AP Evil Twin —
  https://github.com/koutto/pi-pwnbox-rogueap/wiki

## Bluetooth / BLE

- BlueZ (bluetoothctl, hcitool, btmgmt) — https://www.bluez.org/  ,  http://www.bluez.org/documentation/
- gatttool / BlueZ GATT — part of BlueZ; usage: https://hacktricks.wiki/en/todo/radio-hacking/pentesting-ble-bluetooth-low-energy.html
- bettercap BLE module — https://www.bettercap.org/modules/ble/
- Ubertooth One (ubertooth-btle) — https://github.com/greatscottgadgets/ubertooth  ,
  https://ubertooth.readthedocs.io/
- nRF Sniffer for Bluetooth LE (Nordic) — https://www.nordicsemi.com/Products/Development-tools/nRF-Sniffer-for-Bluetooth-LE
- crackle (legacy BLE LTK recovery) — https://github.com/mikeryan/crackle
- OWASP / HackTricks BLE pentest notes — https://hacktricks.wiki/en/todo/radio-hacking/pentesting-ble-bluetooth-low-energy.html

## RFID / NFC

- Proxmark3 (RfidResearchGroup / Iceman fork) — https://github.com/RfidResearchGroup/proxmark3
  ,  MIFARE Classic commands: https://github.com/RfidResearchGroup/proxmark3/blob/master/doc/cheatsheet.md
- libnfc — https://github.com/nfc-tools/libnfc
- mfoc (nested attack) — https://github.com/nfc-tools/mfoc
- mfcuk (darkside attack) — https://github.com/nfc-tools/mfcuk
- MIFARE Classic static-encrypted-nonce research (2024) — https://eprint.iacr.org/2024/1275.pdf

## Frameworks / doctrine (cross-referenced skills)

- NIST SP 800-115 (Technical Guide to Information Security Testing) —
  https://csrc.nist.gov/pubs/sp/800/115/final
- PTES — http://www.pentest-standard.org/
- MITRE ATT&CK — https://attack.mitre.org/
