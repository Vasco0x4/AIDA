"""Read-only provider requests. Tokens never follow cross-origin redirects."""
import hashlib
import ipaddress
import json
import re
import socket
import time
from urllib.parse import urlsplit, quote
import httpx
from services.appsec_source import MAX_ARCHIVE, SourceError
from utils.crypto import _fernet


class GitError(SourceError):
    pass


def origin_url(value):
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise GitError('Invalid server port.') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or not re.fullmatch(r'[A-Za-z0-9.\-\[\]:]+', parsed.netloc)
            or (port is not None and not 1 <= port <= 65535)):
        raise GitError('Enter an HTTPS server origin without credentials or paths, for example https://gitlab.company.com.')
    return 'https://' + parsed.netloc.lower()


def validate_network(url, allow_private):
    host = urlsplit(url).hostname
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, urlsplit(url).port or 443, type=socket.SOCK_STREAM)}
    except (OSError, ValueError):
        raise GitError('Git server hostname could not be resolved.') from None
    local_ranges = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')]
    if not addresses or any(not a.is_global and not (allow_private and any(a in n for n in local_ranges)) for a in addresses):
        raise GitError('Git server resolves to a blocked network. Private Git servers require explicit private-network permission; loopback and link-local are never allowed.')


def seal(token):
    if not isinstance(token, str) or not 8 <= len(token) <= 4096 or any(c.isspace() or ord(c) < 32 for c in token):
        raise GitError('Enter a valid access token without whitespace.')
    try:
        return 'enc::' + _fernet().encrypt(token.encode()).decode()
    except Exception:
        raise GitError('Credential encryption is unavailable. No token was stored.') from None


def unseal(value):
    try:
        if not value.startswith('enc::'):
            raise ValueError()
        return _fernet().decrypt(value[5:].encode()).decode()
    except Exception:
        raise GitError('Stored credential is unavailable. Replace the token.') from None


class GitProvider:
    def __init__(self, connection):
        self.provider = connection.provider
        self.origin = origin_url(connection.origin)
        self.private = connection.allow_private_network
        self.token = unseal(connection.token_encrypted)
        self.api = ('https://api.github.com' if self.origin == 'https://github.com' else self.origin + '/api/v3') if self.provider == 'github' else self.origin + '/api/v4'

    def request(self, url, *, archive=False, authenticated=True, redirect=False):
        expected = urlsplit(self.api).netloc
        target = urlsplit(url)
        allowed_codeload = self.provider == 'github' and self.origin == 'https://github.com' and target.netloc == 'codeload.github.com'
        if target.scheme != 'https' or target.username or target.password or target.fragment or (target.netloc != expected and not (allowed_codeload and not authenticated)):
            raise GitError('Provider returned an unsupported archive destination.')
        validate_network(url, self.private)
        headers = {'User-Agent': 'AIDA-AppSec', 'Accept': 'application/octet-stream' if archive else 'application/json'}
        if authenticated:
            headers['Authorization' if self.provider == 'github' else 'PRIVATE-TOKEN'] = 'Bearer ' + self.token if self.provider == 'github' else self.token
        limit = MAX_ARCHIVE if archive else 4 * 1024 * 1024
        deadline = time.monotonic() + 60
        try:
            with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
                with client.stream('GET', url, headers=headers) as response:
                    if response.status_code in {301, 302, 303, 307, 308} and redirect:
                        location = response.headers.get('location', '')
                        if len(location) > 4096:
                            raise GitError('Archive redirect is invalid.')
                        return None, location
                    if response.status_code != 200:
                        raise GitError(f'Git provider returned HTTP {response.status_code}. Check token expiry, repository permissions, SSO authorization and rate limits.')
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > limit or time.monotonic() > deadline:
                            raise GitError('Git response exceeded its size or time limit.')
                    return bytes(data), None
        except httpx.HTTPError:
            raise GitError('Cannot reach the Git server securely. Check connectivity and its TLS certificate.') from None

    def get(self, suffix):
        raw, _ = self.request(self.api + suffix)
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            raise GitError('Git provider returned invalid JSON.') from None

    def check(self):
        data = self.get('/user')
        account = data.get('login' if self.provider == 'github' else 'username') if isinstance(data, dict) else None
        if not isinstance(account, str) or not account:
            raise GitError('Token identity could not be verified.')
        return account[:160]

    def normalize(self, data):
        if not isinstance(data, dict):
            raise GitError('Invalid repository metadata.')
        ident = str(data.get('id', ''))
        path = data.get('full_name' if self.provider == 'github' else 'path_with_namespace', '')
        parts = path.split('/') if isinstance(path, str) else []
        if not re.fullmatch(r'[1-9][0-9]{0,19}', ident) or len(parts) < 2 or len(path) > 500 or any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', p) for p in parts):
            raise GitError('Unsupported repository identifier or path.')
        return {'provider_id': ident, 'path': path, 'default_branch': str(data.get('default_branch') or 'main')[:160],
                'private': bool(data.get('private')) if self.provider == 'github' else data.get('visibility') != 'public'}

    def repositories(self, page):
        suffix = f'/user/repos?per_page=50&page={page}&sort=full_name' if self.provider == 'github' else f'/projects?membership=true&simple=true&per_page=50&page={page}&order_by=id&sort=asc'
        rows = self.get(suffix)
        if not isinstance(rows, list):
            raise GitError('Invalid repository listing.')
        return [self.normalize(row) for row in rows]

    def repo(self, ident):
        if not re.fullmatch(r'[1-9][0-9]{0,19}', str(ident)):
            raise GitError('Invalid repository ID.')
        item = self.normalize(self.get(('/repositories/' if self.provider == 'github' else '/projects/') + str(ident)))
        if item['provider_id'] != str(ident):
            raise GitError('Repository identity changed; review the grant.')
        return item

    def fetch(self, ident, ref):
        item = self.repo(ident)
        prefix = '/repos/' + item['path'] if self.provider == 'github' else '/projects/' + str(ident) + '/repository'
        data = self.get(prefix + '/commits/' + quote(ref, safe=''))
        sha = data.get('sha' if self.provider == 'github' else 'id', '')
        if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise GitError('Provider did not resolve a full commit SHA.')
        url = self.api + prefix + (f'/zipball/{sha}' if self.provider == 'github' else f'/archive.zip?sha={sha}&include_lfs_blobs=false')
        raw, location = self.request(url, archive=True, redirect=self.provider == 'github')
        if location:
            # github.com returns a short-lived codeload URL. Never forward the PAT.
            parsed = urlsplit(location)
            if self.origin == 'https://github.com':
                if parsed.netloc != 'codeload.github.com' or not parsed.path.startswith('/' + item['path'] + '/'):
                    raise GitError('Unsupported GitHub archive redirect.')
                raw, _ = self.request(location, archive=True, authenticated=False)
            else:
                if parsed.netloc != urlsplit(self.origin).netloc:
                    raise GitError('Cross-origin enterprise archive redirects are not supported.')
                raw, _ = self.request(location, archive=True)
        return sha, raw, hashlib.sha256(raw).hexdigest()
