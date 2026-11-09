# Dynamic Instrumentation — Frida & Objection

Inherits `safe-testing-doctrine`. **Instrument only on YOUR OWN test device/emulator, with an
in-scope app and test accounts.** These scripts bypass client-side protections (SSL pinning,
root/jailbreak detection) so you can observe the app's behavior and its **in-scope** API traffic —
they are **not** authorization to attack the backend beyond scope or to pirate/repackage the app.
Keep all patched builds and frida-server on your test device and remove them at cleanup.

Why bypass at all: these bypasses assess **MASVS-RESILIENCE** / **Mobile Top 10 M7 (Insufficient
Binary Protections)** and are prerequisites for observing traffic to test **M5** and the backend.

## 0. Setup

### Android (frida-server on rooted device/emulator)
```bash
pip install frida-tools objection
frida --version                                   # note version, match server to it
# Download matching frida-server for the device arch (e.g. arm64) from Frida releases:
adb push frida-server-<ver>-android-arm64 /data/local/tmp/frida-server
adb shell "chmod 755 /data/local/tmp/frida-server"
adb shell "su -c '/data/local/tmp/frida-server &'"
frida-ps -Uai                                     # confirm connectivity; list apps
```
Non-rooted option: repackage the APK with **frida-gadget** via `objection patchapk -s target.apk`
(install the patched build on YOUR test device only; never distribute).

### iOS (frida via jailbreak)
Install Frida from repo `https://build.frida.re` on the jailbroken device, connect over USB:
```bash
frida-ps -Uai
```

### Objection quick start (both platforms)
```bash
objection -g com.target.app explore               # spawn+attach an interactive runtime shell
# Inside objection:
ios> ios sslpinning disable
android> android sslpinning disable
android> android root disable
ios> ios jailbreak disable
```

## 1. SSL / TLS certificate pinning bypass  (tests M5 interception)

Goal: route app traffic through Burp (CA already installed per android.md / ios.md). If it fails,
the app pins → bypass, then intercept.

### Objection (fastest first try)
```bash
objection -g com.target.app explore
android> android sslpinning disable        # hooks OkHttp, TrustManager, WebViewClient, etc.
ios> ios sslpinning disable                # hooks SecTrustEvaluate, NSURLSession, TrustKit, etc.
```

### Frida — universal Android script (community, e.g. httptoolkit / FridaBypassKit / codeshare)
```bash
# Load a maintained universal pinning-bypass script at spawn:
frida -U -f com.target.app -l frida-android-pinning-bypass.js --no-pause
# Or a well-known CodeShare script:
frida -U -f com.target.app --codeshare pcipolloni/universal-android-ssl-pinning-bypass-with-frida --no-pause
```

**Targeted OkHttp3 CertificatePinner hook** (illustrative — benign, forces validation to pass):
```javascript
// okhttp3-pin-bypass.js  — run: frida -U -f com.target.app -l okhttp3-pin-bypass.js --no-pause
Java.perform(function () {
  try {
    var CertificatePinner = Java.use('okhttp3.CertificatePinner');
    // check(String, List) and check$okhttp(...) validate the server cert chain against pins.
    CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation =
      function (host, peerCertificates) {
        console.log('[+] OkHttp CertificatePinner.check() bypassed for ' + host);
        return;   // return without throwing -> pin check passes
      };
  } catch (e) { console.log('[-] OkHttp not present: ' + e); }

  // Generic TrustManager neutralization (custom X509TrustManager):
  try {
    var TrustManager = Java.registerClass({
      name: 'com.pentest.TrustAll',
      implements: [Java.use('javax.net.ssl.X509TrustManager')],
      methods: {
        checkClientTrusted: function () {},
        checkServerTrusted: function () {},
        getAcceptedIssuers: function () { return []; }
      }
    });
    var SSLContext = Java.use('javax.net.ssl.SSLContext');
    SSLContext.init.overload(
      '[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom'
    ).implementation = function (km, tm, sr) {
      console.log('[+] SSLContext.init() -> injecting permissive TrustManager');
      this.init(km, [TrustManager.$new()], sr);
    };
  } catch (e) { console.log('[-] TrustManager hook failed: ' + e); }
});
```

**iOS pinning:** `objection -g <bundle> explore` → `ios sslpinning disable`, or a Frida script
hooking `SecTrustEvaluate*` / TrustKit `pinValidator`. After bypass, confirm requests now appear
in Burp. **Remediation to report:** pinning is defense-in-depth, not a substitute for server-side
authz; but its **absence/bypassability** is the M5 finding when combined with weak backend authz.

## 2. Android root detection bypass  (tests M7 / MASVS-RESILIENCE)

**HOW TO FIND detection:** grep decompiled source for the tells:
```bash
grep -rniE "test-keys|/system/xbin/su|/system/bin/su|busybox|isDeviceRooted|RootBeer|magisk|superuser|which su|checkRootMethod" out_jadx/sources
```

**HOW TO TEST / bypass safely:**
```bash
objection -g com.target.app explore
android> android root disable          # hooks common root checks (files, packages, props, RootBeer)
```
**Frida targeted hooks** (benign — make root checks report "clean"):
```javascript
// root-bypass.js
Java.perform(function () {
  // 1) Hide su / root binaries from File.exists()
  var File = Java.use('java.io.File');
  var rootPaths = ['su','magisk','busybox','superuser','/system/xbin/su','/system/bin/su'];
  File.exists.implementation = function () {
    var p = this.getAbsolutePath();
    for (var i = 0; i < rootPaths.length; i++)
      if (p.toLowerCase().indexOf(rootPaths[i]) !== -1) { console.log('[+] hide ' + p); return false; }
    return this.exists();
  };
  // 2) RootBeer (very common lib) -> always false
  try {
    var RootBeer = Java.use('com.scottyab.rootbeer.RootBeer');
    RootBeer.isRooted.implementation = function () { console.log('[+] RootBeer.isRooted -> false'); return false; };
  } catch (e) {}
  // 3) Runtime.exec("which su") -> harmless command
  var Runtime = Java.use('java.lang.Runtime');
  Runtime.exec.overload('java.lang.String').implementation = function (cmd) {
    if (cmd.indexOf('su') !== -1 || cmd.indexOf('which') !== -1) cmd = 'echo';
    return this.exec(cmd);
  };
});
// run: frida -U -f com.target.app -l root-bypass.js --no-pause
```
**Disclosed pattern / remediation:** client-side root detection is trivially bypassable with Frida;
report it as **M7 insufficient binary protection** — recommend layered controls (Play Integrity /
attestation server-side, obfuscation, RASP) while stressing that **security decisions must be
enforced server-side**, not gated on a bypassable client check.

## 3. iOS jailbreak detection bypass  (tests M7 / MASVS-RESILIENCE)

**HOW TO FIND:** look in class-dump headers / Ghidra for checks of `/Applications/Cydia.app`,
`/bin/bash`, `/usr/sbin/sshd`, `cydia://` URL scheme canOpenURL, `fork()`, `NSFileManager
fileExistsAtPath`.
```bash
grep -rniE "Cydia|jailbr|/bin/bash|/usr/sbin/sshd|MobileSubstrate|canOpenURL|fileExistsAtPath" headers/
```
**HOW TO TEST / bypass safely:**
```bash
objection -g com.target.app explore
ios> ios jailbreak disable
# Or Frida hooking fileExistsAtPath: to hide jailbreak artifacts:
frida -U -f com.target.app -l ios-jb-bypass.js --no-pause
```
```javascript
// ios-jb-bypass.js  (benign — hides common jailbreak file artifacts)
var jbPaths = ['/Applications/Cydia.app','/bin/bash','/usr/sbin/sshd','/etc/apt','/private/var/lib/apt/'];
var fm = ObjC.classes.NSFileManager;
Interceptor.attach(fm['- fileExistsAtPath:'].implementation, {
  onEnter: function (args) { this.path = new ObjC.Object(args[2]).toString(); },
  onLeave: function (retval) {
    if (jbPaths.indexOf(this.path) !== -1) { console.log('[+] hide ' + this.path); retval.replace(0x0); }
  }
});
```
Same remediation framing as root detection (M7): enforce server-side, treat client detection as
defense-in-depth only.

## 4. Method tracing & runtime inspection

```bash
# Discover & trace methods by pattern (great for auth/crypto/pinning logic):
frida-trace -U -j '*!*login*' com.target.app                     # Java methods matching *login*
frida-trace -U -m '-[* * decrypt*]' com.target.app               # Obj-C selectors
frida-trace -U -i 'CCCrypt' com.target.app                       # native CommonCrypto calls (iOS)
```
Objection runtime helpers:
```bash
android> android hooking list activities
android> android hooking search classes Crypto
android> android hooking watch class_method com.target.app.Auth.signRequest --dump-args --dump-return
ios>     ios hooking list classes
ios>     ios hooking watch method "-[LoginManager validatePin:]" --dump-args --dump-backtrace
```
Use tracing to: recover the request-signing/crypto scheme, see plaintext before encryption, and
confirm where secrets originate — then report with `security-reporting`.

## 5. Runtime manipulation (safe, minimal)

Overriding a return value to demonstrate a **client-side-only** control is a legitimate PoC (e.g.
force a `isPremium()`/`isBiometricPassed()` client check to `true` to prove the gate is not
server-enforced). Keep it minimal and on your test account:
```javascript
Java.perform(function () {
  var C = Java.use('com.target.app.Entitlements');
  C.isPremium.implementation = function () { console.log('[+] isPremium -> true (client gate PoC)'); return true; };
});
```
**Do not** use runtime manipulation to defraud, unlock paid features for real use, or alter other
users' data — that violates the doctrine. The PoC proves the missing server-side check; the fix is
server-side enforcement. Then test whether the backend actually accepts the elevated action
(in-scope only) via `api-security-testing`.

## Cleanup checklist (record for the report)
- Kill and remove `/data/local/tmp/frida-server`; uninstall any `objection patchapk` build.
- Uninstall the test app; wipe pulled app data / decrypted IPAs from your workstation.
- Remove Burp CA from the device system store; disable the Wi-Fi proxy.
- Note every device modification in the report's cleanup section (`security-reporting`).
