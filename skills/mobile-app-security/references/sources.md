# Sources — Public references consulted

All content derives from public documentation and disclosed research. Verify tool/OWASP naming
against the primary sources below (checked 2025–2026).

## OWASP Mobile Application Security (MAS) — primary standard
- OWASP MASVS (Mobile Application Security Verification Standard), v2.1.0 — 8 categories:
  https://mas.owasp.org/MASVS/
- MASVS-PLATFORM checklist: https://mas.owasp.org/checklists/MASVS-PLATFORM/
- OWASP MASTG (Mobile Application Security Testing Guide) — techniques, tests, tools:
  https://mas.owasp.org/MASTG/
- MASTG releases (v2 graduated from beta, 2025): https://github.com/OWASP/mastg/releases
- MASTG-TOOL-0050 Frida-ios-dump: https://mas.owasp.org/MASTG/tools/ios/MASTG-TOOL-0050/
- MASTG-TECH-0061 Dumping Keychain Data: https://mas.owasp.org/MASTG/techniques/ios/MASTG-TECH-0061/

## OWASP Mobile Top 10 (2024)
- Project page: https://owasp.org/www-project-mobile-top-10/
- 2024 risk list (M1–M10): https://owasp.org/www-project-mobile-top-10/2023-risks/
- Source index: https://github.com/OWASP/www-project-mobile-top-10/blob/master/index.md

## Instrumentation & tooling docs
- Frida (docs, releases, CodeShare): https://frida.re/docs/home/ , https://codeshare.frida.re/
- frida-ios-dump (AloneMonkey): https://github.com/AloneMonkey/frida-ios-dump
- Objection (runtime mobile toolkit): https://github.com/sensepost/objection
- MobSF (Mobile Security Framework): https://github.com/MobSF/Mobile-Security-Framework-MobSF
- jadx (dex-to-Java decompiler): https://github.com/skylot/jadx
- apktool: https://apktool.org/ , https://github.com/iBotPeaches/Apktool
- Drozer (Android IPC/attack-surface): https://github.com/WithSecureLabs/drozer
- class-dump (Obj-C headers): https://github.com/nygard/class-dump
- Ghidra: https://ghidra-sre.org/  |  Hopper: https://www.hopperapp.com/
- adb (platform-tools): https://developer.android.com/tools/adb
- Android Developer — network security config / cleartext:
  https://developer.android.com/privacy-and-security/security-config
- nuclei (backend/API checks post-pinning-bypass): https://github.com/projectdiscovery/nuclei

## Pinning / root / jailbreak bypass references
- Universal Android SSL pinning bypass (CodeShare pcipolloni):
  https://codeshare.frida.re/@pcipolloni/universal-android-ssl-pinning-bypass-with-frida/
- Frida Android SSL/root/emulator bypass script list:
  https://github.com/secfb/Frida-Android-SSL-Pinning-Script
- FridaBypassKit (root/SSL/emulator/debug bypass): https://github.com/okankurtuluss/FridaBypassKit
- RedFox — SSL pinning bypass with Frida (Android): https://www.redfoxsec.com/blog/ssl-pinning-bypass-for-android-using-frida
- Zensar — Android SSL pinning bypass (Frida + Objection):
  https://www.zensar.com/insights/blog/technology/cloud-infrastructure-and-security/android-ssl-pinning-bypass-using-frida

## Public disclosure / finding-class references
- Oversecured — Android deep-link vulnerabilities → account takeover:
  https://oversecured.com/blog/android-deep-link-vulnerabilities
- Android intent redirection (attack class writeups):
  https://medium.com/@0x3adly/android-intent-redirection-a-hackers-gateway-to-internal-components-ebe126bbb2e0
- WebView → account takeover via deep link (finding pattern):
  https://medium.com/@source_to_sink/android-webview-exploitation-from-deep-link-to-account-takeover-62f7a3e1da15
- HackerOne Hacktivity (mobile-tagged disclosed reports — Shopify Arrive magic-link, etc.):
  https://hackerone.com/hacktivity
- CVE-2022-28799 (TikTok Android deeplink → WebView JS-interface → ATO): https://nvd.nist.gov/vuln/detail/CVE-2022-28799

## iOS pentest workflow references
- iOS app pentesting (jailbreak, Frida, MASVS L1-L2):
  https://secra.es/en/blog/ios-app-pentesting-jailbreak-frida
- iOS keychain / certificate + private-key dumping (Echelon):
  https://echeloncyber.com/intelligence/entry/ios-app-pentest-dumping-certificate-and-private-key-from-keychain

## Cross-referenced skills in this base
- `safe-testing-doctrine` (mandatory RoE), `web-vuln-hunting`, `api-security-testing`,
  `web-cve-exploitation`, `security-reporting`.
