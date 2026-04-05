"""
Assessment Template Service
Pre-configured templates for common pentest types
"""

TEMPLATES = {
    "web_app": {
        "id": "web_app",
        "name": "Web Application",
        "icon": "globe",
        "description": "Full web application pentest: OWASP Top 10, authentication, authorization, injection, XSS, CSRF, etc.",
        "category": "Website",
        "default_scope": "Web application security assessment including frontend, backend API, authentication mechanisms, session management, and business logic.",
        "default_limitations": "No denial-of-service testing. No social engineering. Testing limited to provided scope.",
        "default_objectives": "Identify vulnerabilities in the web application following OWASP Testing Guide methodology.",
        "phases": [
            {"number": "1.0", "title": "Reconnaissance", "content": "## Reconnaissance\n- [ ] DNS enumeration\n- [ ] Subdomain discovery\n- [ ] Technology fingerprinting (Wappalyzer)\n- [ ] Web server identification\n- [ ] CMS detection\n- [ ] JavaScript framework analysis\n- [ ] robots.txt / sitemap.xml review"},
            {"number": "2.0", "title": "Scanning & Enumeration", "content": "## Scanning & Enumeration\n- [ ] Port scanning (nmap)\n- [ ] Directory/file bruteforcing (ffuf/gobuster)\n- [ ] Parameter discovery\n- [ ] Hidden endpoint enumeration\n- [ ] API endpoint mapping\n- [ ] Vulnerability scanning (nuclei)"},
            {"number": "3.0", "title": "Vulnerability Analysis", "content": "## Vulnerability Analysis (OWASP Top 10)\n- [ ] A01: Broken Access Control\n- [ ] A02: Cryptographic Failures\n- [ ] A03: Injection (SQLi, NoSQLi, LDAP, XSS)\n- [ ] A04: Insecure Design\n- [ ] A05: Security Misconfiguration\n- [ ] A06: Vulnerable Components\n- [ ] A07: Authentication Failures\n- [ ] A08: Software Integrity Failures\n- [ ] A09: Logging & Monitoring Failures\n- [ ] A10: SSRF"},
            {"number": "4.0", "title": "Exploitation", "content": "## Exploitation\n- [ ] SQL injection exploitation\n- [ ] XSS (Reflected, Stored, DOM)\n- [ ] CSRF attacks\n- [ ] IDOR / Broken Access Control\n- [ ] File upload bypass\n- [ ] Authentication bypass\n- [ ] Session hijacking\n- [ ] Business logic flaws"},
            {"number": "5.0", "title": "Post-Exploitation", "content": "## Post-Exploitation\n- [ ] Data exfiltration assessment\n- [ ] Privilege escalation\n- [ ] Lateral movement\n- [ ] Persistence mechanisms\n- [ ] Impact assessment"},
            {"number": "6.0", "title": "Reporting", "content": "## Reporting\n- [ ] Document all findings with PoC\n- [ ] CVSS scoring\n- [ ] Remediation recommendations\n- [ ] Executive summary"},
        ],
        "suggested_tools": ["nmap", "ffuf", "gobuster", "nuclei", "nikto", "sqlmap", "wpscan", "curl", "dirb"],
    },

    "api": {
        "id": "api",
        "name": "API Security",
        "icon": "code",
        "description": "REST/GraphQL API security assessment: authentication, authorization, injection, rate limiting, data exposure.",
        "category": "API",
        "default_scope": "API security assessment covering authentication, authorization, input validation, rate limiting, and data exposure.",
        "default_limitations": "No load testing or DoS. Testing limited to documented and discovered API endpoints.",
        "default_objectives": "Identify API vulnerabilities following OWASP API Security Top 10.",
        "phases": [
            {"number": "1.0", "title": "API Discovery", "content": "## API Discovery\n- [ ] OpenAPI/Swagger documentation review\n- [ ] Endpoint enumeration\n- [ ] API versioning analysis\n- [ ] Authentication mechanism identification\n- [ ] Rate limiting assessment\n- [ ] CORS policy review"},
            {"number": "2.0", "title": "Authentication & Authorization", "content": "## Authentication & Authorization\n- [ ] JWT token analysis\n- [ ] OAuth flow testing\n- [ ] API key security\n- [ ] Token expiration/rotation\n- [ ] Broken Object Level Authorization (BOLA)\n- [ ] Broken Function Level Authorization"},
            {"number": "3.0", "title": "Input Validation", "content": "## Input Validation\n- [ ] SQL injection\n- [ ] NoSQL injection\n- [ ] Command injection\n- [ ] SSRF via API parameters\n- [ ] Mass assignment\n- [ ] Parameter tampering\n- [ ] Content-Type manipulation"},
            {"number": "4.0", "title": "Data Exposure", "content": "## Data Exposure\n- [ ] Excessive data exposure\n- [ ] Sensitive data in responses\n- [ ] Error message information leakage\n- [ ] Debug endpoints\n- [ ] Stack traces\n- [ ] PII exposure"},
            {"number": "5.0", "title": "Business Logic", "content": "## Business Logic\n- [ ] Rate limiting bypass\n- [ ] Race conditions\n- [ ] Workflow bypass\n- [ ] Price manipulation\n- [ ] Privilege escalation via API"},
            {"number": "6.0", "title": "Reporting", "content": "## Reporting\n- [ ] Document all findings with PoC\n- [ ] CVSS scoring\n- [ ] Remediation recommendations"},
        ],
        "suggested_tools": ["curl", "ffuf", "nuclei", "sqlmap", "nmap"],
    },

    "infrastructure": {
        "id": "infrastructure",
        "name": "Infrastructure",
        "icon": "server",
        "description": "Network infrastructure pentest: port scanning, service enumeration, vulnerability assessment, exploitation.",
        "category": "External Infra",
        "default_scope": "External/internal network infrastructure security assessment including servers, services, and network devices.",
        "default_limitations": "No denial-of-service. No physical access testing. Scope limited to provided IP ranges.",
        "default_objectives": "Identify network-level vulnerabilities, misconfigurations, and potential entry points.",
        "phases": [
            {"number": "1.0", "title": "Network Reconnaissance", "content": "## Network Reconnaissance\n- [ ] Host discovery (ping sweep)\n- [ ] Port scanning (TCP/UDP)\n- [ ] Service version detection\n- [ ] OS fingerprinting\n- [ ] DNS enumeration\n- [ ] WHOIS / ASN analysis\n- [ ] Network topology mapping"},
            {"number": "2.0", "title": "Service Enumeration", "content": "## Service Enumeration\n- [ ] SSH version & config\n- [ ] HTTP/HTTPS services\n- [ ] FTP/SFTP\n- [ ] SMB shares\n- [ ] SNMP\n- [ ] Database services (MySQL, PostgreSQL, MSSQL)\n- [ ] Mail services (SMTP, POP3, IMAP)\n- [ ] RDP/VNC"},
            {"number": "3.0", "title": "Vulnerability Assessment", "content": "## Vulnerability Assessment\n- [ ] CVE scanning (nuclei, nmap scripts)\n- [ ] Default credentials check\n- [ ] SSL/TLS configuration\n- [ ] Outdated software versions\n- [ ] Misconfigurations\n- [ ] Open relays"},
            {"number": "4.0", "title": "Exploitation", "content": "## Exploitation\n- [ ] Exploit known CVEs\n- [ ] Password brute-force (hydra)\n- [ ] Default credential access\n- [ ] Service-specific exploits\n- [ ] Reverse shells"},
            {"number": "5.0", "title": "Post-Exploitation", "content": "## Post-Exploitation\n- [ ] Privilege escalation (linpeas/winpeas)\n- [ ] Credential harvesting\n- [ ] Lateral movement\n- [ ] Data exfiltration paths\n- [ ] Persistence assessment"},
            {"number": "6.0", "title": "Reporting", "content": "## Reporting\n- [ ] Document all findings\n- [ ] Network diagram with findings\n- [ ] Remediation priorities"},
        ],
        "suggested_tools": ["nmap", "nuclei", "hydra", "nikto", "gobuster", "smbclient", "ssh", "nc"],
    },

    "mobile": {
        "id": "mobile",
        "name": "Mobile Application",
        "icon": "smartphone",
        "description": "Mobile app security: static/dynamic analysis, API backend, data storage, certificate pinning.",
        "category": "Mobile",
        "default_scope": "Mobile application security assessment (Android/iOS) including the app, its API backend, and data storage.",
        "default_limitations": "Testing on provided test devices/emulators only. No App Store/Play Store manipulation.",
        "default_objectives": "Identify mobile-specific vulnerabilities following OWASP Mobile Testing Guide.",
        "phases": [
            {"number": "1.0", "title": "Static Analysis", "content": "## Static Analysis\n- [ ] APK/IPA decompilation\n- [ ] Hardcoded secrets/API keys\n- [ ] Insecure storage configurations\n- [ ] Certificate pinning implementation\n- [ ] Code obfuscation review\n- [ ] Permission analysis"},
            {"number": "2.0", "title": "Dynamic Analysis", "content": "## Dynamic Analysis\n- [ ] Traffic interception (proxy setup)\n- [ ] Certificate pinning bypass\n- [ ] Runtime manipulation (Frida)\n- [ ] Local data storage inspection\n- [ ] Clipboard monitoring\n- [ ] Screenshot protection"},
            {"number": "3.0", "title": "API Backend Testing", "content": "## API Backend Testing\n- [ ] API endpoint mapping\n- [ ] Authentication testing\n- [ ] Authorization bypass\n- [ ] Input validation\n- [ ] Data exposure"},
            {"number": "4.0", "title": "Data Security", "content": "## Data Security\n- [ ] Local storage (SharedPreferences, Keychain)\n- [ ] Database encryption (SQLite)\n- [ ] Log file analysis\n- [ ] Backup analysis\n- [ ] Cache review"},
            {"number": "5.0", "title": "Reporting", "content": "## Reporting\n- [ ] Document findings with screenshots\n- [ ] CVSS scoring\n- [ ] Remediation recommendations"},
        ],
        "suggested_tools": ["nmap", "curl", "ffuf", "nuclei", "sqlmap"],
    },

    "active_directory": {
        "id": "active_directory",
        "name": "Active Directory",
        "icon": "network",
        "description": "AD assessment: user enumeration, Kerberos attacks, privilege escalation, GPO analysis, domain compromise.",
        "category": "Internal Infra",
        "default_scope": "Active Directory environment security assessment including domain controllers, group policies, trust relationships, and privilege paths.",
        "default_limitations": "No permanent changes to AD. No account lockouts. Coordinated with IT team.",
        "default_objectives": "Identify AD misconfigurations and attack paths that could lead to domain compromise.",
        "phases": [
            {"number": "1.0", "title": "AD Enumeration", "content": "## AD Enumeration\n- [ ] Domain controller identification\n- [ ] User enumeration\n- [ ] Group enumeration\n- [ ] Computer enumeration\n- [ ] Trust relationships\n- [ ] GPO analysis\n- [ ] Service accounts discovery"},
            {"number": "2.0", "title": "Authentication Attacks", "content": "## Authentication Attacks\n- [ ] AS-REP Roasting\n- [ ] Kerberoasting\n- [ ] Password spraying\n- [ ] NTLM relay\n- [ ] Pass-the-Hash\n- [ ] Pass-the-Ticket\n- [ ] Silver/Golden Ticket"},
            {"number": "3.0", "title": "Privilege Escalation", "content": "## Privilege Escalation\n- [ ] BloodHound path analysis\n- [ ] ACL abuse\n- [ ] Delegation abuse\n- [ ] GPO abuse\n- [ ] Certificate abuse (ADCS)\n- [ ] Local admin reuse"},
            {"number": "4.0", "title": "Lateral Movement", "content": "## Lateral Movement\n- [ ] PsExec / WMI / WinRM\n- [ ] RDP pivoting\n- [ ] SMB shares\n- [ ] Credential harvesting\n- [ ] Token impersonation"},
            {"number": "5.0", "title": "Domain Compromise", "content": "## Domain Compromise\n- [ ] Domain Admin paths\n- [ ] DCSync\n- [ ] NTDS.dit extraction\n- [ ] Persistence mechanisms\n- [ ] Impact assessment"},
            {"number": "6.0", "title": "Reporting", "content": "## Reporting\n- [ ] Attack path diagrams\n- [ ] BloodHound graphs\n- [ ] Remediation priorities"},
        ],
        "suggested_tools": ["nmap", "smbclient", "hydra", "nc"],
    },

    "blank": {
        "id": "blank",
        "name": "Blank Assessment",
        "icon": "file",
        "description": "Start from scratch with no pre-configured phases or scope.",
        "category": "",
        "default_scope": "",
        "default_limitations": "",
        "default_objectives": "",
        "phases": [],
        "suggested_tools": [],
    },
}


def get_all_templates():
    """Return all available templates"""
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "icon": t["icon"],
            "description": t["description"],
            "category": t["category"],
            "suggested_tools": t["suggested_tools"],
        }
        for t in TEMPLATES.values()
    ]


def get_template(template_id: str):
    """Return a full template by ID"""
    return TEMPLATES.get(template_id)
