"""
tools/helper.py POST /launch: what the UI's "Launch agent" button can make
the host run. The terminal is never opened: the launcher is replaced by a
recorder.
"""
import http.server
import json
import shlex
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import helper  # noqa: E402

ORIGIN = "https://localhost:31337"


@pytest.fixture
def launched(monkeypatch):
    """Commands the helper would have opened a terminal with."""
    commands = []

    def fake_run(argv, **kwargs):
        # macOS: osascript -e '... do script "<cmd>" ...'
        script = argv[2]
        cmd = script.split('do script "', 1)[1].rsplit('"', 1)[0]
        commands.append(cmd.replace('\\"', '"').replace("\\\\", "\\"))

        class Done:
            returncode, stderr = 0, ""
        return Done()

    def fake_popen(argv, **kwargs):
        commands.append(argv[-1].removesuffix("; exec bash"))

    monkeypatch.setattr(helper.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    monkeypatch.setattr(helper.subprocess, "Popen", fake_popen)
    return commands


@pytest.fixture
def url():
    server = http.server.HTTPServer(("127.0.0.1", 0), helper.HelperHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def post(url, body, origin=ORIGIN):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(f"{url}/launch", data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_agent_mode_runs_aida_run(url, launched):
    status, body = post(url, {"assessment_name": "Target Corp", "mode": "agent"})
    assert status == 200 and body["mode"] == "agent"
    [cmd] = launched
    cd, run = cmd.split(" && ")
    assert shlex.split(cd) == ["cd", str(helper.AIDA_ROOT)]
    assert shlex.split(run) == [str(helper.AIDA_ROOT / "aida"), "run", "Target Corp"]


def test_default_mode_runs_the_host_cli(url, launched):
    assert post(url, {"assessment_name": "target"})[0] == 200
    assert shlex.split(launched[0].split(" && ")[1])[1:] == ["--assessment", "target"]


@pytest.mark.parametrize("name", [
    "x; rm -rf ~", "$(id)", "`id`", "a'b", 'a"b', "line\nbreak", "trailing\n", "", "a" * 129, 42,
])
def test_unsafe_names_are_refused(url, launched, name):
    status, _ = post(url, {"assessment_name": name, "mode": "agent"})
    assert status == 400
    assert launched == []


@pytest.mark.parametrize("mode", ["shell", "agent; id", None, ["agent"]])
def test_unknown_modes_are_refused(url, launched, mode):
    assert post(url, {"assessment_name": "target", "mode": mode})[0] == 400
    assert launched == []


def status_cors(url, origin):
    req = urllib.request.Request(f"{url}/status", headers={"Origin": origin})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.headers.get("Access-Control-Allow-Origin")


def test_status_is_readable_by_the_ui_only(url):
    # The UI checks /status to choose between "Open in terminal" and
    # showing the command; the browser needs the CORS header to read it.
    assert status_cors(url, ORIGIN) == ORIGIN
    assert status_cors(url, "https://evil.example") is None


@pytest.mark.parametrize("origin", [None, "https://evil.example", "https://localhost:31337.evil.example"])
def test_other_origins_are_refused(url, launched, origin):
    assert post(url, {"assessment_name": "target", "mode": "agent"}, origin=origin)[0] == 403
    assert launched == []
