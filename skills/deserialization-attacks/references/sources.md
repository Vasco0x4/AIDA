# Sources / Provenance

Public sources consulted while building this skill (August 2026). Cite the vendor
advisory + CVE/KEV entry in client reports; gadget-tool repos are linked for understanding
mechanics only, never for pointing a mass-scanner at a client. Verify affected versions
against NVD/vendor PSIRT at test time.

## Standards / cheat sheets / catalogs
- OWASP Deserialization Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html
- OWASP "Insecure Deserialization" (community) — https://owasp.org/www-community/vulnerabilities/Insecure_Deserialization
- OWASP Top 10 A08:2021 Software and Data Integrity Failures — https://owasp.org/Top10/A08_2021-Software_and_Data_Integrity_Failures/
- CWE-502 Deserialization of Untrusted Data — https://cwe.mitre.org/data/definitions/502.html
- CISA Known Exploited Vulnerabilities (KEV) — https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- NVD / CVE — https://nvd.nist.gov/ , https://www.cve.org/
- PortSwigger Web Security Academy — Insecure deserialization labs/research — https://portswigger.net/web-security/deserialization
- GrrrDog Java-Deserialization-Cheat-Sheet — https://github.com/GrrrDog/Java-Deserialization-Cheat-Sheet
- swisskyrepo PayloadsAllTheThings / Insecure Deserialization — https://github.com/swisskyrepo/PayloadsAllTheThings/tree/master/Insecure%20Deserialization
- HackTricks — deserialization — https://hacktricks.wiki/en/pentesting-web/deserialization/

## Java / JVM
- ysoserial (frohoff; mbechler fork) — https://github.com/frohoff/ysoserial
- "Marshalling Pickles" (Frohoff & Lawrence, AppSecCali 2015) — foundational talk on Java gadget chains.
- marshalsec (mbechler) — SnakeYAML/JNDI/XStream payloads + LDAP/RMI ref servers — https://github.com/mbechler/marshalsec
- PortSwigger — Exploiting Java deserialization with Apache Commons — https://portswigger.net/web-security/deserialization/exploiting/lab-deserialization-exploiting-java-deserialization-with-apache-commons
- CVE-2015-4852 — Oracle WebLogic T3 Commons-Collections RCE — https://nvd.nist.gov/vuln/detail/CVE-2015-4852
- CVE-2017-9805 — Apache Struts 2 REST plugin XStream RCE — https://nvd.nist.gov/vuln/detail/CVE-2017-9805
- CVE-2022-1471 — SnakeYAML Constructor RCE (Snyk / GHSA-mjmj-j48q-9wg2) — https://github.com/advisories/GHSA-mjmj-j48q-9wg2 , https://snyk.io/blog/unsafe-deserialization-snakeyaml-java-cve-2022-1471/
- jackson-databind polymorphic typing CVEs (CVE-2017-7525 series, CVE-2019-14379/14439) — https://github.com/FasterXML/jackson-databind ; NCC Group / Doyensec analyses.
- XStream security framework (≥1.4.18) — https://x-stream.github.io/security.html
- JEP 290 Serialization Filtering / ObjectInputFilter — https://openjdk.org/jeps/290
- JNDI / Log4Shell CVE-2021-44228 leg — cross-ref web-cve-exploitation; https://logging.apache.org/log4j/2.x/security.html

## .NET / CLR
- ysoserial.net (pwntester) — https://github.com/pwntester/ysoserial.net
- Blacklist3r (NotSoSecure / GitHub) — machineKey / ViewState key discovery — https://github.com/NotSoSecure/Blacklist3r ; viewgen — https://github.com/0xacb/viewgen
- Claranet / NotSoSecure — Exploiting ViewState Deserialization using Blacklist3r and ysoserial.net — https://www.claranet.com/us/blog/2019-06-13-exploiting-viewstate-deserialization-using-blacklist3r-and-ysoserialnet
- Soroush Dalili — Exploiting deserialisation in ASP.NET via ViewState — https://soroush.me/blog/2019/04/exploiting-deserialisation-in-asp-net-via-viewstate/
- HackTricks — Exploiting __VIEWSTATE — https://hacktricks.wiki/en/pentesting-web/deserialization/exploiting-__viewstate-parameter.html
- Muñoz & Mirosh — "Friday the 13th: JSON Attacks" (BlackHat/DEF CON 2017) — Json.NET/TypeNameHandling gadgets.
- Microsoft Learn — BinaryFormatter obsolete/disabled/removed (SYSLIB0011; .NET 8 throws, .NET 9 removed) — https://learn.microsoft.com/dotnet/core/compatibility/serialization/8.0/binaryformatter-disabled ; https://devblogs.microsoft.com/dotnet/binaryformatter-removed-from-dotnet-9/
- Microsoft Learn — CA2300–CA2330 insecure deserializer analyzers — https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca2329
- CVE-2019-18935 — Telerik UI ASP.NET AJAX (cross-ref web-cve-exploitation) — Bishop Fox https://bishopfox.com/blog/cve-2019-18935-remote-code-execution-in-telerik-ui

## PHP
- phpggc (Ambionics / Charles Fol) — https://github.com/ambionics/phpggc
- Vickie Li — Diving into unserialize(): POP Chains — https://vickieli.dev/insecure%20deserialization/pop-chains/
- Sam Thomas — "It's a PHP unserialization vulnerability Jim, but not as we know it" (Phar, BlackHat 2018).
- Lexfo — PHP Generic Gadget Chains — https://blog.lexfo.fr/php-generic-gadget-chains.html
- Patchstack — PHP Object Injection — https://patchstack.com/academy/wordpress/vulnerabilities/php-object-injection/
- PHP manual — unserialize() allowed_classes — https://www.php.net/manual/en/function.unserialize.php

## Python
- Python docs — pickle security warning — https://docs.python.org/3/library/pickle.html
- David Hamann — Exploiting Python pickle — https://davidhamann.de/2020/04/05/exploiting-python-pickle/
- Trail of Bits — fickling — https://github.com/trailofbits/fickling
- picklescan — https://github.com/mmaitre314/picklescan
- HuggingFace/PyTorch pickle supply-chain research (2023–2025); safetensors — https://github.com/huggingface/safetensors
- PyYAML — yaml.safe_load / 6.0 safe default — https://pyyaml.org/wiki/PyYAMLDocumentation

## Ruby
- elttam — Ruby 2.x Universal RCE Deserialization Gadget Chain (Luke Jahnke) — https://www.elttam.com/blog/ruby-deserialization/
- devcraft.io — Universal Deserialisation Gadget for Ruby 2.x–3.x — https://devcraft.io/2021/01/07/universal-deserialisation-gadget-for-ruby-2-x-3-x.html
- PortSwigger lab — Ruby deserialization documented gadget chain — https://portswigger.net/web-security/deserialization/exploiting/lab-deserialization-exploiting-ruby-deserialization-using-a-documented-gadget-chain
- CVE-2019-5420 — Rails dev-mode Marshal.load RCE (ZDI) — https://www.thezdi.com/blog/2019/6/20/remote-code-execution-via-ruby-on-rails-active-storage-insecure-deserialization
- CVE-2013-0156 — Rails XML/YAML params object injection.

## Node.js
- CVE-2017-5941 — node-serialize unserialize() IIFE RCE (Ajin Abraham / OpsecX) — https://nvd.nist.gov/vuln/detail/CVE-2017-5941 ; ExploitDB 41289 — https://www.exploit-db.com/docs/english/41289-exploiting-node.js-deserialization-bug-for-remote-code-execution.pdf

## Tooling (testing aids)
- Burp "Java Deserialization Scanner" — https://github.com/federicodotta/Java-Deserialization-Scanner
- Freddy (Burp, .NET/Java/others) — https://github.com/nccgroup/freddy
- interactsh (OOB DNS/HTTP) — https://github.com/projectdiscovery/interactsh
- CodeQL UnsafeDeserialization queries — https://codeql.github.com/codeql-query-help/
- Semgrep registry (deserialization rules) — https://semgrep.dev/
