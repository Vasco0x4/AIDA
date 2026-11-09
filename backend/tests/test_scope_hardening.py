"""Fail-closed scope behavior for local, redirect and DNS-rebinding targets."""
from __future__ import annotations

import ipaddress

from services.agent.scope import parse_scope


def test_loopback_requires_explicit_authorization():
    scope = parse_scope("example.com, 10.0.0.0/24")
    assert not scope.host_in_scope("127.0.0.1")
    assert not scope.host_in_scope("localhost")
    allowed, denied = scope.check_command("curl http://127.0.0.1:3000/")
    assert not allowed
    assert "127.0.0.1" in denied


def test_explicit_loopback_scope_supports_isolated_labs():
    scope = parse_scope("http://127.0.0.1:3000, exclude 127.0.0.2")
    assert scope.host_in_scope("127.0.0.1")
    assert not scope.host_in_scope("127.0.0.2")


def test_wildcard_exclusion_also_covers_subdomains():
    scope = parse_scope("*.example.com, exclude *.internal.example.com")
    assert scope.host_in_scope("www.example.com")
    assert not scope.host_in_scope("api.internal.example.com")
    assert not scope.host_in_scope("internal.example.com")


def test_resolved_address_must_not_rebind_to_special_use_network():
    scope = parse_scope("lab.example.test")
    allowed, reason = scope.check_resolved_host(
        "lab.example.test", ["192.0.2.10"], resolver=lambda host: [ipaddress.ip_address("169.254.169.254")],
    )
    assert not allowed
    assert reason == "dns_rebinding"


def test_explicit_private_cidr_is_allowed_for_local_lab():
    scope = parse_scope("10.20.0.0/16")
    allowed, reason = scope.check_resolved_host("10.20.0.5", ["10.20.0.5"])
    assert allowed
    assert reason is None
