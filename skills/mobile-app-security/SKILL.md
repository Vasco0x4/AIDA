---
name: mobile-app-security
description: "Operational playbook for authorized mobile application penetration testing on Android and iOS, structured around OWASP MASVS v2.1.0, the OWASP MASTG, and the OWASP Mobile Top 10 (2024). Covers setup and recon (authorized APK/IPA acquisition, jadx/apktool/class-dump decompilation, MobSF static scans, AndroidManifest/Info.plist review, exported components, permissions, deep links and URL schemes), insecure local storage (SharedPreferences/plist/SQLite/Keychain/Keystore, secrets in code and resources, logging leaks), network security (TLS/cleartext, Burp interception, certificate pinning and bypass with Frida/Objection), platform interaction (exported Activities/Services/Providers/Receivers, intent redirection, iOS URL-scheme and universal-link abuse, WebView JS-bridge and file-access issues, pasteboard, backup flags), mobile auth/session and embedded API keys, and dynamic instrumentation with Frida/Objection (SSL pinning bypass, method tracing, root/jailbreak detection bypass, runtime manipulation). Each finding gives how-to-find tool commands, safe how-to-test steps, a real disclosed pattern, a MASVS/MASTG reference, and remediation. Authorized, in-scope engagements only — test apps you own or have written authorization for, instrument only on YOUR OWN test device/emulator with test accounts. Use for android pentest, ios pentest, apk/ipa analysis, Frida/Objection instrumentation, SSL pinning bypass, or writing mobile findings with remediation."
version: 1.0.0
triggers:
  - android pentest
  - ios pentest
  - apk analysis
  - ipa analysis
  - frida
  - objection
  - ssl pinning bypass
  - mastg
  - masvs
  - mobile top 10
  - jadx
  - apktool
  - mobsf
  - jailbreak bypass
  - root detection bypass
  - deep link
  - webview
  - keychain
  - android keystore
  - mobile app security
---

# Mobile Application Security Testing (Android & iOS)

Authorized, scoped mobile app pentesting mapped to **OWASP MASVS v2.1.0** (8 categories),
the **OWASP MASTG** (Mobile Application Security Testing Guide, v2 graduated from beta in 2025),
and the **OWASP Mobile Top 10 (2024)**. Static analysis, dynamic instrumentation with
Frida/Objection, and the common finding classes grounded in public bug-bounty disclosures.

## ⚠️ Safety — inherits `safe-testing-doctrine`

Load and obey **`safe-testing-doctrine`** before any active testing. Mobile-specific hard rules:

- **Authorization only.** Test an app **only** when you own it (your own app/publisher account)
  or you have **written scope** naming that app/package/bundle-ID. An app being on your phone is
  not authorization; a public app on the store is not authorization.
- **Instrument on YOUR OWN test device/emulator**, never on a victim's or a colleague's device.
  Use **test accounts** you control — never real users' credentials or data.
- **Scope is the app + its explicitly listed backend.** Frida SSL-pinning bypass reveals the app's
  API traffic; you may only test the backend endpoints that are **in scope**. Bypassing pinning is
  not permission to attack the server. Coordinate with `api-security-testing` scope.
- **No DoS, no resource exhaustion**, no crash-fuzzing production backends, no lockout storms.
- **Do not distribute** modified, repackaged, patched, or "cracked" APKs/IPAs. Frida/Objection
  patches and repackaged builds stay on **your** test device and are deleted at engagement end.
- **Least-intrusive PoC.** Prove the finding (one screenshot, one extracted secret redacted, one
  intercepted request) and stop. Don't exfiltrate real user data — mobile analysis often exposes
  other users' data via a broken API; capture minimal proof and report, per doctrine.
- **Cleanup:** uninstall test builds, remove frida-server, disable your proxy CA, wipe pulled app
  data and decrypted IPAs. Log every device change for the report's cleanup list.
- **Responsible disclosure** via `security-reporting`. Root/jailbreak bypass and repackaging are
  demonstrated to assess **MASVS-RESILIENCE** (M7 binary protection) — never to pirate.

## OWASP Mobile Top 10 (2024) → where covered

| # | Risk | Primary reference |
|---|------|-------------------|
| M1 | Improper Credential Usage (hardcoded keys, insecure cred storage) | android.md / ios.md — Storage & Secrets |
| M2 | Inadequate Supply Chain Security (3rd-party SDKs, build pipeline) | android.md — Recon/SDKs; cross-ref `api-security-testing` |
| M3 | Insecure Authentication/Authorization | android.md / ios.md — Auth; cross-ref `web-vuln-hunting` |
| M4 | Insufficient Input/Output Validation | android.md — WebView/IPC; ios.md — URL schemes |
| M5 | Insecure Communication (cleartext, weak TLS, no pinning) | Network sections + frida-dynamic.md |
| M6 | Inadequate Privacy Controls | android.md / ios.md — pasteboard, logs, PII |
| M7 | Insufficient Binary Protections (no root/tamper detection) | frida-dynamic.md |
| M8 | Security Misconfiguration (exported components, backup flags, debuggable) | android.md / ios.md — Platform |
| M9 | Insecure Data Storage | android.md / ios.md — Storage |
| M10 | Insufficient Cryptography | Storage sections (Keystore/Keychain misuse) |

## Index — area → reference file

| Area | Reference |
|------|-----------|
| Android: setup, APK acquisition, jadx/apktool/MobSF, manifest, exported components, deep links, storage, WebView, IPC, auth | `references/android.md` |
| iOS: setup, IPA acquisition/decryption, class-dump, Info.plist, plist/Keychain storage, URL schemes/universal links, pasteboard, WebView | `references/ios.md` |
| Dynamic instrumentation: Frida/Objection setup, SSL pinning bypass, root/jailbreak detection bypass, method tracing, runtime manipulation | `references/frida-dynamic.md` |
| Public source URLs (OWASP, tools, disclosures) | `references/sources.md` |

## Methodology at a glance

1. **Scope & authorize** — confirm package name / bundle ID in writing; provision a test device/emulator.
2. **Acquire** the build from an authorized source (client-provided APK/IPA, your own dev build).
3. **Static** — decompile (jadx/apktool, class-dump), run MobSF, review manifest/Info.plist,
   grep for secrets, map exported components / deep links / URL schemes.
4. **Dynamic** — install on test device, set up Burp + CA, bypass pinning with Frida/Objection,
   observe traffic, hook methods, test IPC and WebView, test root/jailbreak detection.
5. **Backend** — pivot in-scope API findings to `api-security-testing` / `web-vuln-hunting`.
6. **Report** — map each finding to MASVS/MASTG + Mobile Top 10, score with `security-reporting`.

## Core toolbox

- **Android:** `adb`, `jadx`/`jadx-gui`, `apktool`, `MobSF`, `frida`/`frida-server`, `objection`,
  `drozer`, `nuclei` (backend), Burp Suite, `apksigner`, `keytool`.
- **iOS:** `frida`/`frida-server` (via jailbreak), `objection`, `frida-ios-dump`, `class-dump`,
  `otool`/`nm`, `keychain-dumper` / Objection keychain dump, `plutil`, MobSF, Burp Suite,
  Ghidra/Hopper for binary analysis.

Cross-references: `web-vuln-hunting` (WebView/JS payloads, OAuth, IDOR on the API),
`api-security-testing` (the app's backend once pinning is bypassed), `security-reporting`
(CVSS, remediation write-ups, cleanup list).
