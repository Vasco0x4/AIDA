# iOS — Static & Platform Testing

Inherits `safe-testing-doctrine`. Test only apps you own or have written scope for, on **your own**
jailbroken test device with **test accounts**. A proper iOS assessment generally needs a **physical
jailbroken device** (Simulator runs x86/arm slices without FairPlay/Keychain fidelity).

## 0. Setup & recon

### Test device
- Physical iPhone with a **public jailbreak** matching its iOS (e.g. checkra1n/palera1n for
  checkm8 devices, Dopamine for rootless jailbreaks). Install **Frida** from the Sileo/Cydia repo
  `https://build.frida.re`, plus OpenSSH.
```bash
# Frida over USB (device connected):
frida-ps -Uai                     # list installed apps + running procs, get the bundle id
```

### IPA acquisition & decryption (authorized only)
App Store IPAs are **FairPlay-encrypted**; you need the decrypted binary from a jailbroken device.
Use only client-provided IPAs or apps you are authorized to test.
```bash
# frida-ios-dump (AloneMonkey) — pulls a decrypted IPA from the jailbroken device (MASTG-TOOL-0050):
python3 dump.py -H 127.0.0.1 -p 2222 com.target.app -o target-decrypted.ipa
# Objection alternative:
objection explore -g com.target.app        # then within: env / plugins
# Unpack the IPA:
unzip target-decrypted.ipa -d ipa_out       # Payload/<App>.app/<binary>, Info.plist, embedded.mobileprovision
```

### Binary class dump & inspection
```bash
class-dump ipa_out/Payload/*.app/<AppBinary> -H -o headers/   # Obj-C class/method hierarchy
otool -L ipa_out/Payload/*.app/<AppBinary>                    # linked libraries
otool -l ipa_out/Payload/*.app/<AppBinary> | grep -A5 cryptid # cryptid 1 => still encrypted; 0 => decrypted
nm ipa_out/Payload/*.app/<AppBinary> | grep -i "pin\|jailbr\|root"
strings -a ipa_out/Payload/*.app/<AppBinary> | grep -iE "http://|api_key|secret|token|BEGIN"
# Deeper RE: load the binary in Ghidra or Hopper for Swift/native logic and detection routines.
```
Note: `class-dump` mainly reveals **Objective-C**; for **Swift** use Ghidra/Hopper and Frida
runtime enumeration (`frida-trace`, `ObjC`/`Swift` bridges).

### MobSF (also scans IPAs)
Upload `target-decrypted.ipa` to MobSF for static triage (Info.plist, ATS, permissions, hardcoded
secrets, weak crypto). Verify every flag manually.

## 1. Info.plist & entitlements review  (MASVS-PLATFORM / M8)

```bash
plutil -p ipa_out/Payload/*.app/Info.plist
# or convert binary plist to xml:
plutil -convert xml1 -o - ipa_out/Payload/*.app/Info.plist
```
Check:
- **`NSAppTransportSecurity`** — `NSAllowsArbitraryLoads=true` or per-domain exceptions = cleartext
  / weakened TLS allowed. **MASVS-NETWORK / M5.**
- **`CFBundleURLTypes`** — custom **URL schemes** the app registers (attack surface, section 3).
- **`com.apple.developer.associated-domains`** (in entitlements/`embedded.mobileprovision`) —
  **universal links** hosts.
- Permission usage strings (`NS*UsageDescription`) vs. actual need → privacy (M6).
- `UIFileSharingEnabled` / `LSSupportsOpeningDocumentsInPlace` → iTunes/Files exposure of app docs.

## 2. Insecure data storage  (MASVS-STORAGE / M9, M1)

App sandbox lives under `/var/mobile/Containers/Data/Application/<UUID>/`. Find it and browse:
```bash
# Via Objection (no need to know the UUID):
objection -g com.target.app explore
ios> env                                   # prints Bundle/Documents/Library/Caches paths
ios> ls Library/Preferences
ios> file download Library/Preferences/com.target.app.plist ./prefs.plist
plutil -p ./prefs.plist                     # look for tokens / PII in NSUserDefaults plist
```
Findings:
- **NSUserDefaults / *.plist** storing tokens, PII, PINs in cleartext. **M9.**
- **SQLite / Realm / Core Data** files under `Documents/` or `Library/` with sensitive data
  unencrypted (pull and open with `sqlite3`).
- Cached data / screenshots (`Library/Caches`, snapshot images on backgrounding leaking sensitive
  screens). **M6.**
- Files written with wrong **Data Protection class** (`NSFileProtectionNone`) → readable when
  device locked.

### Keychain analysis  (MASVS-STORAGE/CRYPTO / M9, M1)
```bash
# Objection dumps Keychain items for the app (MASTG-TECH-0061):
objection -g com.target.app explore
ios> ios keychain dump
ios> ios keychain dump --json ./keychain.json
# keychain-dumper (device tool) is an alternative for a broad keychain read on jailbroken devices.
```
Findings: secrets stored with weak `kSecAttrAccessible` (e.g. `...Always` /
`...AlwaysThisDeviceOnly`) instead of `...WhenUnlockedThisDeviceOnly`; sensitive creds retrievable
without user presence. **Disclosed pattern:** auth tokens / session cookies / private keys
extractable from the Keychain and app plists — recurring iOS bug-bounty class. **Remediation:**
use Keychain with `WhenUnlockedThisDeviceOnly` + biometric-gated access control
(`SecAccessControl`, `.biometryCurrentSet`), never store secrets in NSUserDefaults/plists.

### Secrets in the binary / bundle (M1)
```bash
strings -a ipa_out/Payload/*.app/<AppBinary> | grep -iE "AKIA|AIza|sk_live|-----BEGIN|amazonaws|firebaseio"
grep -rniE "api[_-]?key|secret|password|token" ipa_out/Payload/*.app/*.plist ipa_out/Payload/*.app/*.json
```

## 3. URL schemes & universal links  (MASVS-PLATFORM / M4)

**HOW TO FIND:** `CFBundleURLTypes` (custom schemes) and associated-domains (universal links) from
section 1.

**HOW TO TEST safely** — open the scheme/link on your test device:
```bash
# Trigger a custom URL scheme:
frida -U -f com.apple.mobilesafari                    # or use Notes -> tap the link
# Simulator equivalent:
xcrun simctl openurl booted "targetapp://open?next=https://example.com/CANARY"
# Universal link: open https://app.target.com/... and confirm the app claims it.
```
Look for: unauthenticated actions triggered by URL scheme (classic **Skype "call any number"**
URL-scheme abuse), tokens/redirects passed through scheme params, a scheme param used to drive a
`WKWebView` load. **Remediation:** treat URL-scheme/universal-link input as untrusted, require
user confirmation for sensitive actions, prefer universal links (verified via
`apple-app-site-association`) over custom schemes, validate all params.

## 4. WebView (WKWebView / UIWebView)  (MASVS-PLATFORM / M4)

```bash
grep -rniE "UIWebView|WKWebView|evaluateJavaScript|WKScriptMessageHandler|allowFileAccessFromFileURLs|loadFileURL" headers/
```
Findings: deprecated **UIWebView** (no process isolation); `WKScriptMessageHandler` message
handlers callable from attacker-loaded content; file access flags allowing local file read;
loading attacker-controlled URLs (via a URL scheme, section 3). Test by pointing the WebView at a
benign **canary** page that posts to the message handler; observe the bridged call.
Cross-ref `web-vuln-hunting`.

## 5. Pasteboard & general platform hygiene  (MASVS-PLATFORM / M6)

```bash
# Hook the general pasteboard at runtime to see sensitive data copied:
frida-trace -U -m "-[UIPasteboard string]" -m "-[UIPasteboard setString:]" com.target.app
```
Findings: app copies passwords/OTPs/tokens to the **general pasteboard** (readable by any app);
no `UIPasteboard.itemProviders` expiry. Also check: background snapshot leaks sensitive screen
(secure-field masking on `applicationWillResignActive`), verbose `NSLog`/`os_log` leaking secrets
(observe via macOS Console.app / `idevicesyslog`).

## 6. Network / TLS  (MASVS-NETWORK / M5)
- ATS review (section 1). Confirm cert **pinning** (`SecTrustEvaluate`, TrustKit, AFNetworking
  pinning, `URLSession` delegate `didReceiveChallenge`). Bypass for interception → `frida-dynamic.md`.
- **Burp setup (iOS):** device Wi-Fi proxy → Burp; install Burp CA via `http://burp` → Settings →
  General → About → Certificate Trust Settings → **enable full trust** for the CA. If traffic still
  fails, the app is pinning → Frida/Objection bypass in `frida-dynamic.md`.

## 7. Auth / session & binary protections
- Token storage (Keychain vs plist, section 2), refresh handling, biometric gate that only guards
  UI vs. the API call (test the in-scope backend directly through the proxy).
- **Jailbreak detection** (MASVS-RESILIENCE / M7): find and bypass in `frida-dynamic.md`. Also
  check anti-debugging (`ptrace(PT_DENY_ATTACH)`), and whether the app ships without any binary
  protection where the threat model warrants it.
- Pivot in-scope API issues (IDOR/BOLA/JWT/OAuth) to `api-security-testing` & `web-vuln-hunting`.

---
Map each finding to MASVS control + MASTG test + Mobile Top 10 item; score in `security-reporting`.
