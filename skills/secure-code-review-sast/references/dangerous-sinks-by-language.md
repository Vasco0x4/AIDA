# Dangerous Sinks & Patterns by Language

Grep-able sink catalogs for a white-box audit. For each language: the dangerous
**sink** (where tainted data causes harm), the **bug class + CWE**, and the
**safe alternative**. Workflow: grep the sink -> trace its arguments **backward**
to an untrusted source (see `methodology-and-threat-modeling.md`) -> confirm no
sink-correct sanitizer on the path. A sink is only a bug when reached by
attacker-controlled data without adequate sanitization.

> Universal cross-class patterns to grep everywhere: `eval`, `exec`, `system`,
> deserialize/`load`, `md5`/`sha1`, `random`(non-crypto), `verify=False` /
> `InsecureSkipVerify`, `password`/`secret`/`api_key` string literals, string
> concatenation into SQL/paths/commands/HTML.

---

## JavaScript / TypeScript / Node.js

| Sink / pattern | Bug class (CWE) | Safe alternative |
|---|---|---|
| `eval()`, `new Function()`, `setTimeout("code")`, `vm.runInContext` | Code injection (CWE-95/94) | Never eval input; `JSON.parse`; parse with a real parser |
| `child_process.exec()/execSync()` with concat | OS command injection (CWE-78) | `execFile`/`spawn` with an **args array**, no shell |
| `db.query("...".concat(input))`, template-literal SQL | SQL injection (CWE-89) | Parameterized queries / bound params / ORM |
| `$where`, `$regex`, unfiltered query object from `req.body` | NoSQL injection (CWE-943) | Validate types; `mongo-sanitize`; reject operators |
| `res.render` / template with user data unescaped; `{{{ }}}` (Handlebars raw), `<%- %>` (EJS) | SSTI / XSS (CWE-1336/79) | Auto-escaping context; encode output |
| `element.innerHTML = input`, `document.write`, `dangerouslySetInnerHTML`, `$(sel).html(input)` | DOM XSS (CWE-79) | `textContent`; DOMPurify; framework escaping |
| `http.get(userUrl)`, `axios(userUrl)`, `fetch(userUrl)` | SSRF (CWE-918) | Allow-list host/scheme; block internal ranges & metadata IP |
| `fs.readFile(path.join(base, input))`, `res.sendFile(input)` | Path traversal (CWE-22) | `path.resolve` + verify prefix; allow-list filenames |
| `node-serialize.unserialize()`, `serialize-javascript` eval'd, `funcster` | Insecure deserialization -> RCE (CWE-502) | `JSON.parse`; never deserialize functions |
| `require(userInput)`, dynamic `import(userInput)` | Arbitrary module load (CWE-95) | Allow-list module names |
| `Math.random()` for tokens/IDs | Weak randomness (CWE-338) | `crypto.randomBytes` / `crypto.randomUUID` |
| `crypto.createHash('md5'/'sha1')` for passwords | Weak hash (CWE-327/916) | `bcrypt`/`scrypt`/`argon2` for passwords |
| `res.redirect(req.query.url)` | Open redirect (CWE-601) | Allow-list redirect targets |
| Prototype-pollution merges (`_.merge`, `Object.assign` from body) | Prototype pollution (CWE-1321) | Guard `__proto__`/`constructor`; safe merge |

---

## Python

| Sink / pattern | Bug class (CWE) | Safe alternative |
|---|---|---|
| `eval()`, `exec()`, `compile()` on input | Code injection (CWE-95) | `ast.literal_eval` for literals; avoid |
| `os.system()`, `subprocess.*(..., shell=True)`, `os.popen` | Command injection (CWE-78) | `subprocess.run([...], shell=False)` args list |
| `cursor.execute("... %s" % x)` / f-string / `.format` SQL | SQL injection (CWE-89) | `cursor.execute(sql, (params,))`; ORM |
| `pickle.loads`, `cPickle`, `shelve`, `dill.loads`, `pandas.read_pickle` | Insecure deserialization -> RCE (CWE-502) | `json`; never unpickle untrusted data |
| `yaml.load(x)` without `SafeLoader` | YAML deserialization -> RCE (CWE-502) | `yaml.safe_load` |
| `jinja2.Template(user).render()`, `render_template_string(user)` | SSTI (CWE-1336) | Never build templates from input; pass as data/context |
| `open(user_path)`, `send_file(user_path)`, `os.path.join(base, input)` | Path traversal (CWE-22) | `os.path.realpath` + prefix check; `werkzeug.safe_join` |
| `requests.get(user_url)`, `urllib.urlopen(user_url)` | SSRF (CWE-918) | Allow-list; block link-local `169.254.169.254`, RFC1918 |
| `etree.parse` / `xml.dom` / `xmlrpc` default parsers | XXE (CWE-611) | `defusedxml`; disable external entities/DTD |
| `hashlib.md5/sha1` for passwords | Weak hash (CWE-327) | `argon2`/`bcrypt`/`hashlib.scrypt` |
| `random.random()`/`randint` for secrets | Weak PRNG (CWE-338) | `secrets` module / `os.urandom` |
| `ssl._create_unverified_context()`, `verify=False` | Improper cert validation (CWE-295) | Verify TLS certs |
| `Django .extra()/.raw()`, `.objects.filter(**request.GET)` | SQLi / mass filter (CWE-89) | Parameterized `raw`; explicit field allow-list |

---

## Java / Kotlin

| Sink / pattern | Bug class (CWE) | Safe alternative |
|---|---|---|
| `Runtime.getRuntime().exec(cmd)`, `ProcessBuilder(cmd)` with concat | Command injection (CWE-78) | Args array, no shell; validate |
| `Statement.execute("..." + input)` | SQL injection (CWE-89) | `PreparedStatement` with `?` bind params |
| `ObjectInputStream.readObject()` on untrusted stream | Insecure deserialization -> RCE (CWE-502) | Avoid; `ObjectInputFilter` allow-list; data-only formats |
| `XMLDecoder.readObject()`, `XStream.fromXML()`, `Yaml.load()` (SnakeYAML), Jackson `enableDefaultTyping()`/polymorphic | Deserialization -> RCE (CWE-502) | SnakeYAML `SafeConstructor`; disable default typing; XStream allow-list |
| `DocumentBuilderFactory`/`SAXParser`/`XMLInputFactory` defaults | XXE (CWE-611) | `setFeature(disallow-doctype-decl,true)`; disable external entities |
| `new File(base + input)`, `Files.newInputStream(userPath)` | Path traversal (CWE-22) | Canonicalize + verify under base dir |
| `new URL(userUrl).openConnection()`, `RestTemplate`/`WebClient` on input | SSRF (CWE-918) | Allow-list host/scheme; block internal ranges |
| Spring SpEL `parser.parseExpression(input)`, `@Value` from input | Expression injection -> RCE (CWE-917) | Never eval user SpEL/OGNL |
| Freemarker/Velocity/Thymeleaf building templates from input | SSTI (CWE-1336) | Templates as static resources; data via model |
| `MessageDigest.getInstance("MD5"/"SHA-1")` for passwords | Weak hash (CWE-327) | BCrypt/PBKDF2/Argon2 (`Spring Security`) |
| `new Random()` for tokens; `"DES"`, `"AES/ECB"`, static IV | Weak crypto/PRNG (CWE-327/338) | `SecureRandom`; `AES/GCM` with random IV |
| `LdapContext.search(filter+input)` | LDAP injection (CWE-90) | Escape/parameterize LDAP filters |

---

## PHP

| Sink / pattern | Bug class (CWE) | Safe alternative |
|---|---|---|
| `eval()`, `assert(str)`, `create_function`, `preg_replace('/e')` | Code injection (CWE-95) | Remove; no eval of input |
| `system()`, `exec()`, `shell_exec()`, `passthru()`, backticks, `popen` | Command injection (CWE-78) | `escapeshellarg`/`escapeshellcmd`; avoid shell |
| `mysqli_query("...$input")`, string-built SQL | SQL injection (CWE-89) | PDO prepared statements with bound params |
| `unserialize($input)` | Object injection -> RCE (CWE-502) | `json_decode`; `unserialize($x,['allowed_classes'=>false])` |
| `include`/`require`/`include_once` with input | LFI/RFI -> RCE (CWE-98/22) | Allow-list; no user-controlled paths |
| `file_get_contents($userPath)`, `fopen`, `readfile` | Path traversal / SSRF via wrappers (CWE-22/918) | `basename` + allow-list; disable `allow_url_fopen`; block `phar://`,`http://` |
| Twig `{{ }}` from raw input / `Twig\Environment` from input | SSTI (CWE-1336) | Pass data as context, not template source |
| `echo $_GET['x']` unencoded | XSS (CWE-79) | `htmlspecialchars`/`htmlentities` on output |
| `md5()`/`sha1()` for passwords | Weak hash (CWE-327) | `password_hash(..., PASSWORD_BCRYPT/ARGON2ID)` |
| `mt_rand`/`rand`/`uniqid` for tokens | Weak PRNG (CWE-338) | `random_bytes`/`random_int` |
| `header("Location: ".$_GET['url'])` | Open redirect (CWE-601) | Allow-list |

---

## Go

| Sink / pattern | Bug class (CWE) | Safe alternative |
|---|---|---|
| `exec.Command("sh","-c", input)`, `exec.Command(userBin, ...)` | Command injection (CWE-78) | Fixed binary + validated args; never `sh -c` with input |
| `db.Query(fmt.Sprintf("...%s", input))` | SQL injection (CWE-89) | `db.Query(sql, args...)` placeholders (`$1`/`?`) |
| `template.HTML(input)`, `text/template` for HTML output | XSS (CWE-79) | `html/template` (auto-escapes); don't cast to `template.HTML` |
| `http.Get(userURL)`, `http.NewRequest(_, userURL, _)` | SSRF (CWE-918) | Validate host; custom `DialContext` blocking internal IPs |
| `os.Open(filepath.Join(base, input))`, `http.ServeFile(w,r,input)` | Path traversal (CWE-22) | `filepath.Clean` + `strings.HasPrefix` under base |
| `encoding/gob` / `encoding/json` into `interface{}` from untrusted, `text/template` parse of input | Type/logic issues, SSTI (CWE-502/1336) | Decode into concrete typed structs; static templates |
| `tls.Config{InsecureSkipVerify: true}` | Improper cert validation (CWE-295) | Verify certs |
| `math/rand` for tokens/keys | Weak PRNG (CWE-338) | `crypto/rand` |
| `md5`/`sha1` for passwords; `crypto/des`, ECB | Weak crypto (CWE-327) | `bcrypt`/`argon2`; AES-GCM |
| `os.Getenv` secret then logged; hardcoded consts | Secret exposure (CWE-798/532) | Secret manager; scrub logs |

---

## C# / .NET

| Sink / pattern | Bug class (CWE) | Safe alternative |
|---|---|---|
| `SqlCommand("..." + input)`, string-interpolated SQL | SQL injection (CWE-89) | Parameterized `SqlParameter`; EF LINQ |
| `Process.Start(...)` / `cmd /c` with concat | Command injection (CWE-78) | Args array; validate; avoid shell |
| `BinaryFormatter.Deserialize`, `SoapFormatter`, `NetDataContractSerializer`, `LosFormatter`, `ObjectStateFormatter` | Insecure deserialization -> RCE (CWE-502) | Avoid `BinaryFormatter` (deprecated); `System.Text.Json`; typed contracts |
| `JsonConvert` with `TypeNameHandling.All/Auto` | Polymorphic deser -> RCE (CWE-502) | `TypeNameHandling.None`; `System.Text.Json` |
| `__VIEWSTATE` without MAC / leaked `machineKey` | ViewState deser -> RCE (CWE-502) | Enable ViewState MAC; protect `machineKey` |
| `XmlDocument`/`XmlReader` with `DtdProcessing.Parse`, `XmlResolver` set | XXE (CWE-611) | `DtdProcessing.Prohibit`; `XmlResolver=null` |
| `File.ReadAllText(Path.Combine(base, input))` | Path traversal (CWE-22) | `Path.GetFullPath` + verify prefix |
| `HttpClient.GetAsync(userUrl)`, `WebRequest.Create(userUrl)` | SSRF (CWE-918) | Allow-list; block internal ranges/metadata |
| `Response.Redirect(Request["url"])` | Open redirect (CWE-601) | `Url.IsLocalUrl` / allow-list |
| `MD5`/`SHA1` for passwords; `DES`; ECB; static IV | Weak crypto (CWE-327) | `Rfc2898`/`PBKDF2`/`Argon2`; AES-GCM; `RandomNumberGenerator` |
| Razor `@Html.Raw(input)` | XSS (CWE-79) | Default Razor encoding; encode |
| `new Random()` for tokens | Weak PRNG (CWE-338) | `RandomNumberGenerator.GetBytes` |

---

## Ruby

| Sink / pattern | Bug class (CWE) | Safe alternative |
|---|---|---|
| `eval`, `instance_eval`, `class_eval`, `send(user, ...)` | Code injection (CWE-95) | Avoid; allow-list method names for `send` |
| `` `#{input}` `` backticks, `system("... #{input}")`, `%x[]`, `open("|cmd")` | Command injection (CWE-78) | `system(cmd, arg1, arg2)` array form; validate |
| `Model.where("name = '#{input}'")`, `find_by_sql("..#{}")` | SQL injection (CWE-89) | Parameterized `where("name = ?", input)`; hash conditions |
| `Marshal.load(input)`, `YAML.load(input)` (Psych pre-safe), `Oj.load` unsafe modes | Insecure deserialization -> RCE (CWE-502) | `YAML.safe_load`; `JSON.parse`; never `Marshal.load` untrusted |
| ERB `<%= raw input %>` / `.html_safe` on input; `render inline:` | XSS / SSTI (CWE-79/1336) | Default ERB escaping; never `html_safe` user data |
| `render file:`/`render params[:template]`, `send_file(params[:path])` | Path traversal / LFI (CWE-22) | Allow-list templates/paths |
| `open(user_url)` (open-uri), `Net::HTTP.get(user_url)` | SSRF (CWE-918) | Allow-list host/scheme; block internal IPs |
| `Digest::MD5/SHA1` for passwords | Weak hash (CWE-327) | `bcrypt` (`has_secure_password`)/`argon2` |
| `SecureRandom` good; `rand`/`Random` for tokens | Weak PRNG (CWE-338) | `SecureRandom.hex/uuid` |
| `redirect_to params[:url]` | Open redirect (CWE-601) | Allow-list / `only_path: true` |
| Mass-assignment `Model.new(params)` w/o strong params | Mass assignment (CWE-915) | `params.require(...).permit(...)` |

---

## Cross-cutting: hardcoded secrets & authz gaps (all languages)

**Hardcoded secrets (CWE-798)** — grep for `password =`, `passwd`, `secret`,
`api_key`, `apikey`, `token`, `AKIA` (AWS), `-----BEGIN * PRIVATE KEY-----`,
`Bearer `, connection strings, `client_secret`. Any high-entropy string literal
assigned to a credential-looking name is a lead. Confirm with `gitleaks`/
`trufflehog` (and check **git history**, not just HEAD). Safe pattern: env vars /
secret manager, never in source or config committed to VCS.

**Authorization gaps (CWE-862/863/639 IDOR)** — SAST rarely finds these; read by
hand. For every handler that references an object by an ID from the request:
*is there a check that the object belongs to (or is permitted for) the caller?*
Look for `findById(params.id)` with no ownership/role check, admin routes without
role guards, and "hidden" endpoints relying on obscurity. Also watch **mass
assignment** (binding a whole request body to a model exposes `is_admin`,
`role`, `balance`). Safe pattern: centralized, server-side, deny-by-default
authorization checked on every object reference; explicit field allow-lists.
