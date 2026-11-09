# Infra & Transport: Subdomain Takeover / Request Smuggling / Cache Poisoning

## Subdomain takeover
A DNS record (CNAME/A) points to a de-provisioned third-party service you can
claim. Easy, high-severity.
```bash
subfinder -d TARGET -all | dnsx -cname -resp -o cnames.txt
nuclei -l subs.txt -t http/takeovers/                 # fingerprint claimable services
subzy run --targets subs.txt
```
Look for dangling CNAMEs to: S3/CloudFront, GitHub Pages, Heroku, Azure
(`*.azurewebsites.net`, `trafficmanager.net`), Shopify, Fastly, Netlify,
Surge, Readme, Zendesk, Statuspage, Unbounce, Cargo, Tumblr. The service's
"no such bucket/app" page = claimable. **Prove by claiming and serving a benign
marker file** (e.g. your HackerOne username), never malicious content.

Also: **NS takeover** (dangling delegation), and dangling records after infra
teardown. Severity High (full subdomain control → cookie scope, phishing, OAuth).

## HTTP Request Smuggling (desync)
Front-end and back-end disagree on request boundaries (`Content-Length` vs
`Transfer-Encoding`). Enables request hijacking, cache poisoning, auth bypass.
```
Use Burp "HTTP Request Smuggler" (Param Miner author) → run "Smuggle probe".
CL.TE, TE.CL, TE.TE, and HTTP/2 downgrade (H2.CL / H2.TE) variants.
```
Detect with **timing** (delayed response on a crafted split) before exploiting.
Manual CL.TE skeleton:
```
POST / HTTP/1.1
Host: TARGET
Content-Length: 4
Transfer-Encoding: chunked

0

X   <- smuggled prefix consumed by next victim request
```
Impact: capture other users' requests, bypass front-end authz, poison cache.
Be careful — smuggling can affect real users; keep probes benign and coordinate
with the client. Report timing-confirmed desync even without full exploitation.

## Web cache poisoning
Unkeyed input reflected in a cacheable response poisons the cache for all users.
```
Param Miner → "Guess headers/params" to find unkeyed inputs.
Classic: X-Forwarded-Host / X-Forwarded-Scheme / X-Host reflected into links,
         then cached → redirect all users to attacker (or inject XSS).
```
Method: send `X-Forwarded-Host: evil.com`, confirm reflection, confirm the
response is cached (`X-Cache: hit`, `Age:`), verify a second clean request gets
the poisoned copy. Cache-buster in your requests so you don't harm real users
while testing; only demonstrate on a benign path.

## Web cache deception
Trick the cache into storing a victim's private page under a static-looking URL:
```
https://TARGET/account/settings/nonexistent.css
```
If the app serves account data but the cache stores it by extension, an attacker
can then fetch the cached private page. Confirm with two accounts.

## TLS / transport quick checks
```bash
testssl.sh --fast https://TARGET      # weak ciphers, TLS1.0/1.1, cert issues
```
Flag missing HSTS, mixed content, expired/mismatched certs, weak protocols.
Usually Low/Medium unless it enables interception.

## Real disclosed-report patterns
- Dangling CNAME to unclaimed S3 bucket → subdomain takeover.
- `X-Forwarded-Host` reflected + cached → open-redirect/XSS for all users.
- CL.TE desync captured other users' session cookies.
- Cache deception exposed account pages via `.css` suffix.

## Severity
Smuggling with request capture / cache poisoning affecting all users →
High–Critical. Subdomain takeover → High. TLS hardening only → Low/Medium.

## Remediation to recommend
Remove dangling DNS on service teardown; use consistent HTTP parsing / reject
ambiguous `CL`+`TE`, prefer HTTP/2 end-to-end; include all reflected inputs in
the cache key or don't reflect them; cache by content-type/auth-state, not just
extension; enforce modern TLS + HSTS.
