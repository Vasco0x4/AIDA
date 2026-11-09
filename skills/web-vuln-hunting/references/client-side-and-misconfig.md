# CSRF / CORS / Open Redirect / Clickjacking / Headers

## CSRF
Test state-changing requests (POST/PUT/DELETE, and GET that mutates):
- No CSRF token, or token not validated / not tied to session / reusable / static.
- Token only checked when present → **omit it** and see if the request succeeds.
- `SameSite` cookie missing or `None` without other protection.
- **Method / content-type bypass**: change `POST`→`GET`; JSON endpoint accepts
  `Content-Type: text/plain` or form-encoding (no preflight → CSRF possible).
- Referer-based check → strip Referer with `<meta name="referrer" content="no-referrer">`.
PoC:
```html
<form action="https://TARGET/api/email" method="POST">
  <input name="email" value="attacker@evil.com">
</form><script>document.forms[0].submit()</script>
```
JSON-CSRF via `fetch` when server ignores content-type.

## CORS misconfiguration
```bash
curl -s -I https://TARGET/api/me -H "Origin: https://evil.com" | grep -i access-control
```
Vulnerable when:
- `Access-Control-Allow-Origin` **reflects arbitrary Origin** + `...-Allow-Credentials: true`
  → attacker page reads authenticated responses (ATO/data theft).
- Reflects `null` origin (sandboxed iframe/data URI sends `Origin: null`).
- Weak regex: `evil-TARGET.com`, `TARGET.com.evil.com`, `TARGETevil.com`.
- Trusts any subdomain when one subdomain has XSS.
PoC page fetches `/api/me` with credentials and exfiltrates the JSON.

## Open redirect
Params: `redirect`, `next`, `url`, `return`, `dest`, `continue`, `returnUrl`,
`callback`, `checkout_url`, `image_url`.
```
?next=https://evil.com    ?next=//evil.com    ?next=https:/evil.com
?next=https://TARGET.evil.com   ?next=/\evil.com   ?next=https://evil.com%2f%2e%2e
?next=https://evil.com%00.TARGET.com    whitelisted@evil.com
```
Impact alone is low, but chains into OAuth token theft, SSRF, and phishing —
report as a chain component.

## Clickjacking
Missing `X-Frame-Options` / `frame-ancestors` CSP on sensitive actions:
```html
<iframe src="https://TARGET/settings/delete" style="opacity:.0001"></iframe>
```
Only report where a meaningful action can be framed (state change / ATO).

## Security header / misconfig sweep
```bash
curl -sI https://TARGET | grep -iE 'strict-transport|content-security|x-frame|x-content-type|referrer-policy|permissions-policy'
```
Also flag: verbose stack traces / debug pages (`/actuator`, `/debug`,
`.env`, `.git/`, source maps), directory listing, default creds on admin panels,
exposed `.DS_Store`/backup files. Report only with concrete impact.

## Real disclosed-report patterns
- CORS reflecting Origin + credentials → read victim's private API data.
- Open redirect in `redirect_uri` chained to OAuth code theft (see auth).
- JSON endpoint accepting `text/plain` → CSRF changed account email.

## Severity
CORS credentialed data theft → High. CSRF on sensitive action → Medium–High.
Open redirect / clickjacking standalone → Low (High as chain).

## Remediation to recommend
Per-request CSRF tokens + `SameSite=Lax/Strict`; strict CORS allow-list (never
reflect Origin with credentials, never trust `null`); validate redirect targets
against an allow-list; set `frame-ancestors`, HSTS, `X-Content-Type-Options`,
and a strong CSP; disable debug/actuator in prod.
