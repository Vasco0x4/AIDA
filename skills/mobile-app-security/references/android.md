# Android — Static & Platform Testing

Inherits `safe-testing-doctrine`. Test only apps you own or have written scope for, on **your own**
device/emulator with **test accounts**. Package name and backend hosts must be explicitly in scope.

## 0. Setup & recon

### Test device / emulator
```bash
# Rooted emulator (Android Studio AVD, or genymotion). Google-APIs image + writable system:
emulator -avd Pixel_API_34 -writable-system -no-snapshot
adb root && adb remount              # writable /system for CA install on older APIs
adb devices -l
```

### APK acquisition (authorized sources ONLY)
```bash
# Preferred: client-provided APK / your own signed build.
# From a device where the app is legitimately installed and in-scope:
adb shell pm list packages | grep -i <keyword>
adb shell pm path com.target.app            # -> package:/data/app/.../base.apk (+ splits)
adb pull /data/app/~~xxxx==/com.target.app-yyy==/base.apk ./target.apk
# Split APKs: pull every split.*.apk too and merge for analysis if needed.
```
Do **not** pull APKs from unofficial "APK mirror" sites — provenance/integrity unknown and may
be repackaged. Prefer the exact build the client hands you.

### Decompile — jadx (Java/Smali source view)
```bash
jadx -d out_jadx target.apk                 # decompiled Java + resources to out_jadx/
jadx-gui target.apk                          # interactive; great for xref/search
# Search for interesting strings:
grep -rniE "http://|api_key|secret|password|token|BEGIN RSA|firebaseio|s3\.amazonaws" out_jadx/sources | head
```

### Decompile — apktool (manifest + smali + resources, repackable)
```bash
apktool d target.apk -o out_apktool          # decoded AndroidManifest.xml, res/, smali/
# Rebuild (ONLY on your test device, for instrumentation demos — never distribute):
apktool b out_apktool -o patched.apk
apksigner sign --ks test.keystore patched.apk
```

### MobSF static scan (fast triage of the whole app)
```bash
# Run MobSF locally (Docker):
docker run -it --rm -p 8000:8000 opensecurity/mobile-security-framework-mobsf:latest
# Upload target.apk via http://localhost:8000 (or REST API):
curl -F 'file=@target.apk' http://localhost:8000/api/v1/upload -H "Authorization:$MOBSF_KEY"
# MobSF flags: exported components, cleartext, weak crypto, hardcoded secrets, trackers, permissions.
```
Treat MobSF output as leads, not findings — **verify each manually** before reporting.

## 1. Manifest & permissions review  (MASVS-PLATFORM / M8)

```bash
grep -nE "android:exported|permission|allowBackup|debuggable|usesCleartextTraffic|intent-filter|<data" \
  out_apktool/AndroidManifest.xml
```
Check for:
- `android:debuggable="true"` → app debuggable in prod (info leak / runtime tamper). **MSTG/MASTG-RESILIENCE.**
- `android:allowBackup="true"` (or unset on old targets) → `adb backup` may exfiltrate app data. **MASVS-STORAGE.**
- `android:usesCleartextTraffic="true"` or missing/permissive `network_security_config.xml`. **MASVS-NETWORK / M5.**
- Dangerous/over-broad permissions vs. app function. **M6 privacy.**
- `minSdkVersion` low → weaker platform defaults (cleartext allowed <28, backups, etc.).

### Backup exfiltration test (safe, read-only)
```bash
adb backup -f app.ab -noapk com.target.app     # if allowBackup; extract with abe.jar
# HOW TO TEST: confirm sensitive data appears in the backup. Report; do not keep real user data.
```

## 2. Exported components & IPC  (MASVS-PLATFORM / M8, M4)

**HOW TO FIND** — enumerate exported Activities/Services/Providers/Receivers:
```bash
# From decoded manifest: android:exported="true" OR any component with an <intent-filter> (implicitly exported <31).
grep -nB2 -A6 'android:exported="true"' out_apktool/AndroidManifest.xml
# Drozer (dynamic enumeration on device):
drozer console connect
run app.package.attacksurface com.target.app
run app.activity.info -a com.target.app
run app.provider.info -a com.target.app
```

**HOW TO TEST safely** — invoke exported components with benign inputs from adb (your device):
```bash
# Launch an exported Activity directly (auth bypass if it skips a login gate):
adb shell am start -n com.target.app/.SecretActivity
# Send data to an exported Activity:
adb shell am start -n com.target.app/.WebActivity -e url "https://example.com/CANARY"
# Start an exported Service / send a broadcast:
adb shell am startservice -n com.target.app/.ExportedService
adb shell am broadcast -a com.target.app.ACTION_X --es data "canary"
# Query an exported/world-readable ContentProvider (and test path traversal / SQLi):
adb shell content query --uri content://com.target.app.provider/users
drozer> run app.provider.query content://com.target.app.provider/ --vertical
drozer> run scanner.provider.injection -a com.target.app     # SQLi in provider
drozer> run scanner.provider.traversal -a com.target.app     # ../ file read
```

**Intent redirection (M4/M8):** an exported component that extracts an `Intent` from extras and
calls `startActivity()`/`sendBroadcast()` on it lets an attacker reach **non-exported** internal
components or steal results.
```bash
grep -rniE "getParcelableExtra\(.*Intent|\(Intent\).*getSerializable|startActivity\(.*getIntent" out_jadx/sources
```
**Disclosed pattern:** exported "trampoline"/redirector activities that forward attacker-supplied
Intents into privileged internal screens — the Oversecured intent-redirection class, seen in many
HackerOne mobile reports. **Remediation:** don't forward untrusted Intents; validate component,
set `exported=false`, use signature permissions, sanitize extras.

## 3. Deep links & URL handling  (MASVS-PLATFORM / M4)

**HOW TO FIND** deep links (custom scheme + App Links):
```bash
grep -nB2 -A8 "<intent-filter" out_apktool/AndroidManifest.xml | grep -iE "scheme|host|BROWSABLE|autoVerify"
# Danger combo: exported + BROWSABLE + android:scheme + no autoVerify + no param validation.
```

**HOW TO TEST safely** — fire the deep link from adb / a canary page:
```bash
adb shell am start -a android.intent.action.VIEW -d "targetapp://open?next=https://example.com/CANARY"
adb shell am start -a android.intent.action.VIEW -d "https://app.target.com/reset?token=TESTTOKEN"
```
Look for: the app loading an attacker URL in a WebView, deep link that passes a `redirect`/`next`
into an OAuth flow (token/magic-link theft), or a deep link reaching an auth-gated screen.

**Disclosed pattern:** Shopify **Arrive** magic-link token interception, and CVE-2022-28799
(TikTok) where an unvalidated deeplink forced the WebView to load an arbitrary site that reached
an attached JavaScript interface → account takeover. **Remediation:** use verified App Links
(`autoVerify=true` + `assetlinks.json`), allowlist redirect hosts, never pass tokens through
open redirect params, validate every deep-link parameter.

## 4. WebView issues  (MASVS-PLATFORM / M4)

**HOW TO FIND** dangerous WebView config in jadx:
```bash
grep -rniE "addJavascriptInterface|setJavaScriptEnabled\(true\)|setAllowFileAccess|setAllowUniversalAccessFromFileURLs|setAllowFileAccessFromFileURLs|loadUrl|shouldOverrideUrlLoading" out_jadx/sources
```
Findings:
- `addJavascriptInterface()` + attacker-controllable URL → JS can call native bridge methods
  (RCE-class on old targets; data theft / privileged actions on modern). **M4.**
- `setAllowFileAccessFromFileURLs`/`UniversalAccess...` true + `file://` load → local file read /
  SOP bypass; combine with an exported deep link that controls the URL.
- Missing `shouldOverrideUrlLoading` allowlist → open redirect into the trusted WebView.

**HOW TO TEST safely:** via the exported deep link (section 3) point the WebView at a **canary**
page you host that calls the exposed JS bridge, e.g. `AndroidBridge.getToken()`, and observe the
returned value in your page logs. Use benign JS only. **Remediation:** avoid
`addJavascriptInterface` (or `@JavascriptInterface`-gate + host allowlist), disable file access,
load only trusted HTTPS origins, validate URLs. Cross-ref `web-vuln-hunting` (XSS→bridge).

## 5. Insecure data storage  (MASVS-STORAGE / M9, M1)

**HOW TO FIND** — inspect the app sandbox on your test device after exercising features:
```bash
adb shell run-as com.target.app ls -la /data/data/com.target.app/   # if debuggable; else root
adb shell "su -c 'ls -laR /data/data/com.target.app/'"
# Key locations:
#  shared_prefs/*.xml   (SharedPreferences — often plaintext tokens)
#  databases/*.db       (SQLite — pull & open with sqlite3)
#  files/, cache/       (misc; cached PII, downloaded docs)
adb pull /data/data/com.target.app/shared_prefs/ ./sp
grep -riE "token|password|pin|jwt|secret|refresh" ./sp
adb shell "su -c 'sqlite3 /data/data/com.target.app/databases/app.db \".tables\"'"
```
Findings: auth tokens/PII in **SharedPreferences** or **SQLite** in cleartext; sensitive files on
external storage (world-readable historically); data readable via `allowBackup`.

**Android Keystore / crypto misuse (M10):** grep for keys and crypto:
```bash
grep -rniE "SharedPreferences|MODE_WORLD_READABLE|Cipher\.getInstance\(\"AES/ECB|IvParameterSpec\(new byte|\"DES|MD5|SHA1\b|hardcoded|SecretKeySpec\(\"" out_jadx/sources
```
- Keys hardcoded in code/resources instead of Android Keystore. **M1/M10.**
- `AES/ECB`, static IV, DES/3DES, MD5/SHA1 for security. **M10 MASVS-CRYPTO.**
- Not using `EncryptedSharedPreferences`/Keystore-backed keys.

**Secrets in code & resources (M1):**
```bash
grep -rniE "AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|sk_live_|xox[baprs]-|-----BEGIN|firebaseio\.com|amazonaws\.com" out_jadx/sources out_apktool/res
strings out_apktool/assets/* 2>/dev/null | grep -iE "key|secret|token"
```
**Disclosed pattern:** Google Maps / Firebase / AWS keys and open Firebase DBs hardcoded in APKs —
a recurring HackerOne class; misconfigured `firebaseio.com` reachable unauthenticated. **Remediation:**
keep secrets server-side, use short-lived tokens, restrict API keys by package+SHA1, use Keystore.

**Logging leaks (M6/M9):**
```bash
grep -rniE "Log\.(d|v|i|e)\(|System\.out\.print" out_jadx/sources | grep -iE "token|password|user|card"
adb logcat | grep -i com.target.app        # observe at runtime while logging in
```

## 6. Network / TLS  (MASVS-NETWORK / M5)

- Confirm cleartext: `usesCleartextTraffic`, `network_security_config.xml` domains, `http://` in code.
- Confirm certificate pinning presence (OkHttp `CertificatePinner`, `TrustManager`,
  `network_security_config` `<pin-set>`). Pinning **bypass** for interception → `frida-dynamic.md`.

### Burp interception setup (Android)
```bash
# 1. Proxy: Burp listens on all interfaces:8080. On device: Wi-Fi proxy = <host-ip>:8080.
# 2. Install Burp CA as a *system* CA (user CAs ignored by apps targeting API 24+):
openssl x509 -inform DER -in cacert.der -out burp.pem            # export Burp cert -> DER -> PEM
HASH=$(openssl x509 -inform PEM -subject_hash_old -in burp.pem | head -1)
cp burp.pem $HASH.0
adb root && adb remount
adb push $HASH.0 /system/etc/security/cacerts/
adb shell chmod 644 /system/etc/security/cacerts/$HASH.0
adb reboot
# Android 14+: system CA store moved to APEX (/apex/com.android.conscrypt/...); use a rooted
# emulator, Magisk "Move Certificates" / "Cert-Fixer" module, or inject via Frida instead.
```
If traffic still fails after CA install → app is **pinning**; go to `frida-dynamic.md`.

## 7. Auth / session in the mobile context  (MASVS-AUTH / M3)

- Where are tokens stored (section 5) and how are they refreshed? Long-lived tokens in
  SharedPreferences = high impact if device compromised.
- Biometric/`local-auth` gate that only controls UI, not the API call → bypass by calling the API
  directly (test the in-scope backend via the pinning-bypassed proxy).
- Client-side-only authorization: hidden screens reachable via exported Activity / deep link.
- Once you can see API traffic, pivot IDOR/BOLA/JWT/OAuth to `api-security-testing` &
  `web-vuln-hunting` (mobile apps expose the same REST/GraphQL backends).

## 8. Supply chain (M2)
List bundled SDKs/libraries and versions (MobSF "Components"/trackers, `out_jadx` package tree),
flag known-vulnerable/abandoned SDKs and excessive third-party trackers. Report outdated components
with `web-cve-exploitation` where a CVE applies.

---
Every finding → map to MASVS control + MASTG test + Mobile Top 10 item, score in `security-reporting`.
