"""Versioned, conservative baseline rules. Findings are review candidates, not exploits."""
import ast
import hashlib
import json
import re
from pathlib import PurePosixPath

VERSION = 'baseline-1'
MAX_FINDINGS = 500
SECRET_PATTERNS = [
    ('private-key', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')),
    ('github-token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{30,255})\b')),
    ('aws-access-key', re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('credential-literal', re.compile(r'''(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[:=]\s*["']([^"'\r\n]{8,160})["']''')),
]
PLACEHOLDER = re.compile(r'(?i)(example|placeholder|changeme|your[_ -]|dummy|test[_-]|\$\{|process\.env|os\.environ|<[^>]+>)')
CODE_EXT = {'.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rb', '.php', '.cs'}


def redact(text):
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|\Z)', lambda match: '[REDACTED PRIVATE KEY]' + '\n' * match.group(0).count('\n'), text)
    for _, pattern in SECRET_PATTERNS:
        text = pattern.sub('[REDACTED SECRET]', text)
    return text


def finding(rule, category, severity, path, line, title, description, recommendation, confidence='medium', identity=''):
    # Never hash or persist the secret itself. Rule/path/line are sufficient for this snapshot.
    fingerprint = hashlib.sha256(f'{rule}|{path}|{line}|{identity}'.encode()).hexdigest()
    return dict(fingerprint=fingerprint, rule_id=rule, category=category, severity=severity,
                confidence=confidence, path=path, line=line, title=title,
                description=description, recommendation=recommendation)


def analyze(files):
    findings, dependencies, warnings = [], [], []
    python_files = js_files = 0
    def add(*args, **kwargs):
        if len(findings) < MAX_FINDINGS:
            findings.append(finding(*args, **kwargs))
    for path, content in sorted(files.items()):
        for rule, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(content):
                if rule == 'credential-literal' and PLACEHOLDER.search(match.group(1)):
                    continue
                add('secret.' + rule, 'secrets', 'high', path, content.count('\n', 0, match.start()) + 1,
                    'Potential embedded credential', 'A credential-shaped value was detected. Its value is intentionally omitted; validity has not been tested.',
                    'Inspect the location. If genuine, revoke or rotate the credential and move it to a secret store. Removing it from the latest commit does not remove Git history.')
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == '.py':
            python_files += 1
            try:
                tree = ast.parse(content)
                aliases = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for item in node.names:
                            aliases[item.asname or item.name] = item.name
                    elif isinstance(node, ast.ImportFrom):
                        for item in node.names:
                            aliases[item.asname or item.name] = f'{node.module}.{item.name}'
                def call_name(node):
                    if isinstance(node, ast.Name):
                        return aliases.get(node.id, node.id)
                    if isinstance(node, ast.Attribute):
                        return call_name(node.value) + '.' + node.attr
                    return ''
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    name = call_name(node.func)
                    kwargs = {k.arg: k.value for k in node.keywords}
                    rule = None
                    if name in {'eval', 'exec', 'builtins.eval', 'builtins.exec'}:
                        rule = ('dynamic-code', 'Dynamic code execution', 'Check whether untrusted input can reach this call.', 'Replace dynamic evaluation with an explicit parser or allowlisted operations.')
                    elif name in {'pickle.load', 'pickle.loads', 'dill.load', 'dill.loads'}:
                        rule = ('deserialization', 'Potential unsafe deserialization', 'Deserializing attacker-controlled data can execute code.', 'Use a non-executable format and validate its schema; never deserialize untrusted pickle data.')
                    elif name.startswith('subprocess.') and isinstance(kwargs.get('shell'), ast.Constant) and kwargs['shell'].value is True:
                        rule = ('shell', 'Shell-enabled subprocess', 'Shell interpretation can permit command injection when arguments contain untrusted data.', 'Pass an argument array with shell=False and validate inputs.')
                    elif name.startswith(('requests.', 'httpx.')) and isinstance(kwargs.get('verify'), ast.Constant) and kwargs['verify'].value is False:
                        rule = ('tls', 'TLS verification disabled', 'Certificate verification is explicitly disabled.', 'Enable certificate verification and configure a trusted CA bundle when required.')
                    if rule:
                        add('python.' + rule[0], 'code', 'medium' if rule[0] == 'tls' else 'high', path, node.lineno, *rule[1:])
            except (SyntaxError, RecursionError, ValueError):
                warnings.append(f'Python AST analysis unavailable for {path}; secret checks still ran.')
        elif suffix in {'.js', '.jsx', '.ts', '.tsx'}:
            js_files += 1
            rules = [
                (r'\beval\s*\(', 'eval', 'Dynamic JavaScript evaluation', 'Avoid eval; parse data without executing it.'),
                (r'\.innerHTML\s*=', 'innerhtml', 'HTML injection sink', 'Use textContent for text, or an audited sanitizer for intentional HTML.'),
                (r'\brejectUnauthorized\s*:\s*false\b', 'tls', 'TLS verification disabled', 'Keep certificate verification enabled.'),
            ]
            for line, text in enumerate(content.splitlines(), 1):
                if text.lstrip().startswith(('//', '*')):
                    continue
                for pattern, rule, title, remedy in rules:
                    if re.search(pattern, text):
                        add('javascript.' + rule, 'code', 'medium', path, line, title,
                            'A potentially dangerous construct was detected. Data flow and exploitability require review.', remedy, confidence='low')
        basename = PurePosixPath(path).name
        if basename in {'package.json', 'package-lock.json'}:
            try:
                data = json.loads(content)
                if basename == 'package.json':
                    for section in ('dependencies', 'devDependencies'):
                        for name, version in (data.get(section) or {}).items():
                            dependencies.append({'ecosystem': 'npm', 'name': str(name)[:200], 'version': str(version)[:200] if re.fullmatch(r'[0-9A-Za-z.*^~<>=| +_-]{1,200}', str(version)) else '[non-version specifier omitted]', 'path': path, 'kind': 'declared'})
                else:
                    for name, item in (data.get('packages') or {}).items():
                        if name and isinstance(item, dict) and item.get('version'):
                            dependencies.append({'ecosystem': 'npm', 'name': name.split('node_modules/')[-1][:200], 'version': str(item['version'])[:100] if re.fullmatch(r'[0-9A-Za-z.*+_-]{1,100}', str(item['version'])) else '[non-version specifier omitted]', 'path': path, 'kind': 'locked'})
            except (ValueError, AttributeError, TypeError):
                warnings.append(f'Could not read dependency manifest {path}.')
        elif basename.startswith('requirements') and basename.endswith('.txt'):
            for text in content.splitlines():
                match = re.match(r'^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*([<>=!~].*?)?\s*(?:#.*)?$', text)
                if match:
                    dependencies.append({'ecosystem': 'PyPI', 'name': match[1], 'version': redact(match[2] or 'unconstrained')[:200], 'path': path, 'kind': 'declared'})
    if len(findings) >= MAX_FINDINGS:
        warnings.append('Finding limit reached (500); split the repository into smaller snapshots.')
    if len(dependencies) > 2000:
        warnings.append('Dependency inventory limited to 2,000 entries.')
    return findings, {'engine_version': VERSION, 'python_files': python_files, 'javascript_files': js_files,
                      'dependencies': dependencies[:2000], 'warnings': warnings[:100],
                      'dependency_advisories': 'not_checked', 'ai': {'status': 'not_requested'}}


def ai_payload(files):
    selected, count = {}, 0
    for path, content in sorted(files.items()):
        if PurePosixPath(path).suffix.lower() not in CODE_EXT:
            continue
        # Omit secret-bearing lines and credentials; source still may contain sensitive business logic.
        safe = '\n'.join(f'{n}: {redact(line)}' for n, line in enumerate(redact(content).splitlines(), 1))
        if count + len(safe) > 40000 or len(selected) >= 20:
            continue
        selected[path] = safe
        count += len(safe)
    return selected


def parse_ai(content, files):
    data = json.loads(content)
    if not isinstance(data, dict) or not isinstance(data.get('findings'), list):
        raise ValueError('Invalid AI result schema')
    results = []
    for item in data['findings'][:30]:
        if not isinstance(item, dict):
            continue
        path, line = item.get('path'), item.get('line')
        if path not in files or type(line) is not int or not 1 <= line <= len(files[path].splitlines()):
            continue
        fields = [item.get(key) for key in ('title', 'description', 'recommendation')]
        if not all(isinstance(x, str) and x.strip() for x in fields):
            continue
        severity = item.get('severity', 'medium')
        if severity not in {'low', 'medium', 'high', 'critical'}:
            severity = 'medium'
        results.append(finding('ai.review', 'ai', severity, path, line,
                               redact(fields[0])[:200], redact(fields[1])[:2000], redact(fields[2])[:2000],
                               confidence='low', identity=fields[0][:200]))
    return results
