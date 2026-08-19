#!/usr/bin/env python3
"""Offline HTTP regression for the competition UI; never connects to the robot."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import redirect_stderr


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "competition_ui.py"
SPEC = importlib.util.spec_from_file_location("competition_ui", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("cannot load competition_ui.py")
UI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UI)


class FakeUiServer(UI.UiServer):
    def __init__(self, maintenance_controls: bool):
        super().__init__(
            ("127.0.0.1", 0),
            UI.RequestHandler,
            target="mi@offline.invalid",
            identity=Path("/tmp/unused-mi-dog-test-identity"),
            maintenance_controls=maintenance_controls,
        )
        self.start_entered = threading.Event()
        self.release_start = threading.Event()
        self.calls: list[str] = []
        self.calls_lock = threading.Lock()

    def run_tool(self, command: list[str], timeout: int) -> dict:
        action = command[-1]
        with self.calls_lock:
            self.calls.append(action)
        if action == "start":
            self.start_entered.set()
            if not self.release_start.wait(timeout=3):
                raise RuntimeError("offline start test was not released")
        return {
            "ok": True,
            "returncode": 0,
            "stdout": f"fake_action={action}\n",
            "stderr": "",
            "values": {"fake_action": action},
        }

    def camera_process(self) -> subprocess.Popen:
        code = (
            "import os,struct,time\n"
            "os.write(2,b'e'*131072)\n"
            "payload=b'\\xff\\xd8'+b'x'*196+b'\\xff\\xd9'\n"
            "for _ in range(40):\n"
            " os.write(1,struct.pack('>I',len(payload))+payload);time.sleep(.02)\n"
        )
        return subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def request(base: str, path: str, *, token: str | None = None, payload=None):
    headers = {}
    data = None
    method = "GET"
    if token is not None:
        headers["X-Mi-Dog-Token"] = token
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
        method = "POST"
    http_request = urllib.request.Request(
        base + path, data=data, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(http_request, timeout=5)
        return response.status, response
    except urllib.error.HTTPError as error:
        return error.code, error


def json_request(base: str, path: str, *, token: str | None = None, payload=None):
    status, response = request(base, path, token=token, payload=payload)
    body = json.loads(response.read())
    response.close()
    return status, body


def start_server(maintenance_controls: bool):
    server = FakeUiServer(maintenance_controls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    return server, thread, base


def stop_server(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    if thread.is_alive():
        raise AssertionError("offline UI server did not stop")


def main() -> int:
    access_log = io.StringIO()
    with redirect_stderr(access_log):
        server, thread, base = start_server(False)
        try:
            status, response = request(base, "/")
            page = response.read().decode()
            response.close()
            assert status == 200
            assert 'name="mi-dog-maintenance-controls" content="false"' in page
            assert 'data-posture="stand"' in page and 'id="cameraStream"' in page
            assert "唯一人工入口" in page
            assert "确认放回点并 CONTINUE" in page
            token = server.token

            status, health = json_request(base, "/api/health")
            assert status == 200 and health["maintenance_controls"] is False
            environment_result = UI.UiServer.run_tool(
                server,
                [sys.executable, "-c", "import os; print(os.environ['MI_DOG_MAINTENANCE_CONTROLS'])"],
                2,
            )
            assert environment_result["stdout"].strip() == "0"
            timeout_result = UI.UiServer.run_tool(
                server,
                [
                    sys.executable,
                    "-c",
                    "import subprocess,sys,time; "
                    "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
                    "print(p.pid,flush=True); time.sleep(30)",
                ],
                1,
            )
            assert timeout_result["returncode"] == 124
            child_pid = int(timeout_result["stdout"].strip())
            child_stat = Path(f"/proc/{child_pid}/stat")
            if child_stat.exists():
                assert child_stat.read_text().split()[2] == "Z"
            status, _ = json_request(
                base, "/api/jog", token=token, payload={"direction": "forward"})
            assert status == 403
            status, _ = json_request(
                base, "/api/posture", token=token, payload={"action": "stand"})
            assert status == 403
            status, _ = json_request(
                base, "/api/posture", token=token, payload={"action": "invalid"})
            assert status == 400

            # Referee/operator events remain available through the sole UI
            # backend even though manual direction and posture are denied.
            for action, payload in (
                    ("status", {"action": "status"}),
                    ("pause", {"action": "pause"}),
                    ("restart", {"action": "restart"}),
                    ("select-stage", {"action": "select-stage", "stage": 3}),
                    ("continue-stage", {"action": "continue-stage", "stage": 3})):
                status, body = json_request(base, "/api/action", token=token, payload=payload)
                assert status == 200 and body["values"]["fake_action"] == action
            status, _ = json_request(
                base, "/api/action", token=token,
                payload={"action": "continue-stage", "stage": 0})
            assert status == 400

            status, _ = json_request(base, "/api/camera/token")
            assert status == 403
            status, authorization = json_request(
                base, "/api/camera/token", token=token)
            assert status == 200 and authorization["stream_token"] != token
            stream_token = authorization["stream_token"]
            status, stream = request(
                base, f"/api/camera/stream?token={stream_token}")
            assert status == 200
            data = stream.read(260)
            assert b"--mi-dog-frame" in data and b"Content-Type: image/jpeg" in data
            stream.close()
            status, _ = json_request(
                base, f"/api/camera/stream?token={stream_token}")
            assert status == 403, "camera stream token must be single-use"
            expired_token = server.issue_camera_token()
            with server.camera_token_lock:
                server.camera_stream_tokens[expired_token] = time.monotonic() - 1
            status, _ = json_request(
                base, f"/api/camera/stream?token={expired_token}")
            assert status == 403, "expired camera stream token must be rejected"
            status, metrics = json_request(
                base, "/api/camera/metrics", token=token)
            assert status == 200 and metrics["frames"] >= 1
        finally:
            stop_server(server, thread)

        server, thread, base = start_server(True)
        try:
            token = server.token
            status, response = request(base, "/")
            page = response.read().decode()
            response.close()
            assert status == 200
            assert 'name="mi-dog-maintenance-controls" content="true"' in page
            environment_result = UI.UiServer.run_tool(
                server,
                [sys.executable, "-c", "import os; print(os.environ['MI_DOG_MAINTENANCE_CONTROLS'])"],
                2,
            )
            assert environment_result["stdout"].strip() == "1"
            status, _ = json_request(
                base, "/api/posture", token=token, payload={"action": "stand"})
            assert status == 200

            start_result = {}

            def issue_start():
                start_result["status"], start_result["body"] = json_request(
                    base, "/api/action", token=token, payload={"action": "start"})

            start_thread = threading.Thread(target=issue_start)
            start_thread.start()
            assert server.start_entered.wait(timeout=2)
            status, _ = json_request(
                base, "/api/action", token=token, payload={"action": "pause"})
            assert status == 409, "non-emergency writes must be serialized"
            status, _ = json_request(
                base, "/api/posture", token=token, payload={"action": "lie-down"})
            assert status == 409, "posture must share the robot write lock"
            status, _ = json_request(
                base, "/api/jog", token=token, payload={"direction": "forward"})
            assert status == 409, "jog must share the robot write lock"
            stop_started = time.monotonic()
            status, _ = json_request(
                base, "/api/action", token=token, payload={"action": "stop"})
            assert status == 200 and time.monotonic() - stop_started < 1.0
            server.release_start.set()
            start_thread.join(timeout=2)
            assert not start_thread.is_alive() and start_result["status"] == 200
            assert "stop" in server.calls
        finally:
            server.release_start.set()
            stop_server(server, thread)

    logs = access_log.getvalue()
    assert stream_token not in logs
    assert "token=<redacted>" in logs
    app_source = (ROOT / "ui" / "app.js").read_text()
    assert 'confirmations[actionName]' in app_source
    assert '"continue-stage"' in app_source
    assert "encodeURIComponent(token)" not in app_source
    server_source = (ROOT / "scripts" / "competition_ui.py").read_text()
    assert "pkill -f '^python3 - --topic" in server_source
    assert "exec timeout 120s python3" in server_source
    posture_source = (ROOT / "scripts" / "robot_posture.sh").read_text()
    assert "hard_minimum_soc = 30" in posture_source
    assert "ParameterType.PARAMETER_INTEGER" in posture_source
    assert "hard_minimum_soc <= candidate <= 100" in posture_source
    safe_environment = os.environ.copy()
    safe_environment.pop("MI_DOG_MAINTENANCE_CONTROLS", None)
    posture_result = subprocess.run(
        [str(ROOT / "scripts" / "robot_posture.sh"), "stand"],
        env=safe_environment, capture_output=True, text=True, timeout=2, check=False)
    assert posture_result.returncode == 3
    assert "posture_refused=maintenance_controls_disabled" in posture_result.stderr
    jog_result = subprocess.run(
        [str(ROOT / "scripts" / "robot_jog.sh"), "forward"],
        env=safe_environment, capture_output=True, text=True, timeout=2, check=False)
    assert jog_result.returncode == 3
    assert "jog_refused=maintenance_controls_disabled" in jog_result.stderr
    print("competition_ui_offline=PASS")
    print("competition_mode_manual_controls=DENIED")
    print("concurrent_write=HTTP_409")
    print("stop_dispatch_bypasses_lock=PASS")
    print("camera_token=ONE_TIME_REDACTED")
    print("camera_stderr_drain=PASS")
    print("posture_soc_parameter_guard=PASS")
    print("direct_manual_script_gate=PASS")
    print("timeout_process_group_cleanup=PASS")
    print("ui_referee_event_flow=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
