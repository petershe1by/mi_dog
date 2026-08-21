#!/usr/bin/env python3
"""Local-only web UI for safe CyberDog competition operations."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import secrets
import select
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"
CONTROL_SCRIPT = ROOT / "scripts" / "competition_control.sh"
JOG_SCRIPT = ROOT / "scripts" / "robot_jog.sh"
POSTURE_SCRIPT = ROOT / "scripts" / "robot_posture.sh"
CAMERA_STREAM_SCRIPT = ROOT / "scripts" / "robot_camera_stream.py"
CAMERA_TOPIC = "/mi_desktop_48_b0_2d_7a_fe_40/image"
ALLOWED_ACTIONS = {
    "status",
    "start",
    "continue",
    "select-stage",
    "continue-stage",
    "pause",
    "stop",
    "restart",
}
ALLOWED_JOGS = {
    "forward",
    "backward",
    "left",
    "right",
    "turn-left",
    "turn-right",
    "stop",
}
ALLOWED_POSTURES = {"stand", "lie-down"}
CAMERA_TOKEN_TTL_SECONDS = 15.0


class OperationBusyError(RuntimeError):
    """Raised when a second non-emergency robot write is attempted."""


def parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.replace("_", "").isalnum():
            values[key] = value
    return values


class UiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
            self, address, handler, *, target: str, identity: Path,
            maintenance_controls: bool = False):
        self.ssh_control_path: Path | None = None
        super().__init__(address, handler)
        self.target = target
        self.identity = identity
        self.maintenance_controls = maintenance_controls
        self.ssh_control_path = Path(
            f"/tmp/mi_dog_ui_{os.getuid()}_{os.getpid()}_{self.server_address[1]}.sock")
        self.token = secrets.token_urlsafe(32)
        self.operation_lock = threading.Lock()
        self.camera_session_lock = threading.Lock()
        self.camera_metrics_lock = threading.Lock()
        self.camera_token_lock = threading.Lock()
        self.camera_stream_tokens: dict[str, float] = {}
        self.camera_active = False
        self.camera_frames = 0
        self.camera_bytes = 0
        self.camera_started = 0.0
        self.camera_frame_times: list[float] = []

    def run_tool(self, command: list[str], timeout: int) -> dict:
        environment = os.environ.copy()
        environment["MI_DOG_TARGET"] = self.target
        environment["MI_DOG_SSH_BATCH_MODE"] = "1"
        environment["MI_DOG_SSH_IDENTITY"] = str(self.identity)
        environment["MI_DOG_SSH_CONTROL_PATH"] = str(self.ssh_control_path)
        environment["MI_DOG_FAST_EVENT"] = "1"
        environment["MI_DOG_MAINTENANCE_CONTROLS"] = (
            "1" if self.maintenance_controls else "0")
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                stdout, stderr = process.communicate()
            return {
                "ok": False,
                "returncode": 124,
                "stdout": stdout or "",
                "stderr": (stderr or "") + "\ncommand timed out",
                "values": {},
            }
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return {
            "ok": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": (stdout or "") + f"ui_round_trip_ms={elapsed_ms}\n",
            "stderr": stderr,
            "values": parse_key_values(stdout),
        }

    def run_exclusive_tool(self, command: list[str], timeout: int) -> dict:
        if not self.operation_lock.acquire(blocking=False):
            raise OperationBusyError(
                "another robot operation is active; use STOP for an emergency override")
        try:
            return self.run_tool(command, timeout)
        finally:
            self.operation_lock.release()

    def require_maintenance_controls(self) -> None:
        if not self.maintenance_controls:
            raise PermissionError(
                "manual movement and posture controls are disabled in competition mode")

    def control(self, action: str, stage: int | None = None) -> dict:
        if action not in ALLOWED_ACTIONS:
            raise ValueError("unsupported action")
        command = [str(CONTROL_SCRIPT), "--target", self.target]
        if action in {"select-stage", "continue-stage"}:
            if stage not in range(1, 7):
                raise ValueError("stage must be 1..6")
            command.extend(["--stage", str(stage)])
        command.append(action)
        timeout = 120 if action == "restart" else 25
        if action in {"status", "stop"}:
            return self.run_tool(command, timeout)
        return self.run_exclusive_tool(command, timeout)

    def jog(self, direction: str) -> dict:
        if direction not in ALLOWED_JOGS:
            raise ValueError("unsupported jog direction")
        self.require_maintenance_controls()
        command = [str(JOG_SCRIPT), direction]
        if direction == "stop":
            return self.run_tool(command, 20)
        return self.run_exclusive_tool(command, 20)

    def posture(self, action: str) -> dict:
        if action not in ALLOWED_POSTURES:
            raise ValueError("unsupported posture action")
        self.require_maintenance_controls()
        return self.run_exclusive_tool([str(POSTURE_SCRIPT), action], 65)

    def issue_camera_token(self) -> str:
        now = time.monotonic()
        token = secrets.token_urlsafe(18)
        with self.camera_token_lock:
            self.camera_stream_tokens = {
                value: expiry for value, expiry in self.camera_stream_tokens.items()
                if expiry > now
            }
            self.camera_stream_tokens[token] = now + CAMERA_TOKEN_TTL_SECONDS
        return token

    def consume_camera_token(self, token: str) -> bool:
        now = time.monotonic()
        with self.camera_token_lock:
            expiry = self.camera_stream_tokens.pop(token, None)
            return expiry is not None and expiry > now

    def camera_process(self) -> subprocess.Popen:
        remote_command = (
            "source /home/mi/mi_dog_ws/scripts/load_live_ros_env.sh; "
            f"pkill -f '^python3 - --topic {CAMERA_TOPIC} ' >/dev/null 2>&1 || true; "
            f"exec timeout 120s python3 - --topic {CAMERA_TOPIC} --max-fps 5 "
            "--jpeg-quality 68 --max-width 480"
        )
        command = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=2",
            "-o", f"ControlPath={self.ssh_control_path}",
            "-o", "ControlMaster=auto",
            "-o", "ControlPersist=30",
            "-o", "IdentitiesOnly=yes",
            "-i", str(self.identity),
            self.target,
            remote_command,
        ]
        script_input = CAMERA_STREAM_SCRIPT.open("rb")
        try:
            return subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=script_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        finally:
            script_input.close()

    def server_close(self) -> None:
        if self.ssh_control_path is not None and self.ssh_control_path.exists():
            try:
                subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", "-S", str(self.ssh_control_path),
                     "-O", "exit", self.target],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=2, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
        super().server_close()

    def camera_begin(self) -> None:
        with self.camera_metrics_lock:
            self.camera_active = True
            self.camera_frames = 0
            self.camera_bytes = 0
            self.camera_started = time.monotonic()
            self.camera_frame_times = []

    def camera_record(self, byte_count: int) -> None:
        stamp = time.monotonic()
        with self.camera_metrics_lock:
            self.camera_frames += 1
            self.camera_bytes += byte_count
            self.camera_frame_times.append(stamp)
            cutoff = stamp - 5.0
            self.camera_frame_times = [value for value in self.camera_frame_times if value >= cutoff]

    def camera_end(self) -> None:
        with self.camera_metrics_lock:
            self.camera_active = False

    def camera_metrics(self) -> dict:
        with self.camera_metrics_lock:
            stamps = list(self.camera_frame_times)
            fps = 0.0
            if len(stamps) >= 2 and stamps[-1] > stamps[0]:
                fps = (len(stamps) - 1) / (stamps[-1] - stamps[0])
            elapsed = (
                time.monotonic() - self.camera_started
                if self.camera_active and self.camera_started > 0.0 else 0.0)
            megabits_per_second = (
                self.camera_bytes * 8.0 / elapsed / 1_000_000.0
                if elapsed > 0.0 else 0.0)
            return {
                "ok": True,
                "active": self.camera_active,
                "fps": round(fps, 2),
                "frames": self.camera_frames,
                "megabytes": round(self.camera_bytes / 1_000_000.0, 2),
                "megabits_per_second": round(megabits_per_second, 2),
                "elapsed_seconds": round(elapsed, 1),
                "source_limit_fps": 5,
            }


class RequestHandler(BaseHTTPRequestHandler):
    server: UiServer

    def log_message(self, fmt: str, *args) -> None:
        # Never leave the one-time stream credential in access/error logs.
        safe_args = tuple(
            re.sub(r"([?&]token=)[^&\s]+", r"\1<redacted>", value)
            if isinstance(value, str) else value
            for value in args
        )
        sys.stderr.write("[ui] " + fmt % safe_args + "\n")

    def send_bytes(self, data: bytes, content_type: str, status=HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status=HTTPStatus.OK) -> None:
        self.send_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def read_json(self) -> dict:
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ValueError("Content-Type must be application/json")
        if self.headers.get("X-Mi-Dog-Token") != self.server.token:
            raise PermissionError("invalid UI token")
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 4096:
            raise ValueError("invalid request size")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("JSON object required")
        return payload

    @staticmethod
    def read_exact(pipe, byte_count: int, timeout: float) -> bytes | None:
        deadline = time.monotonic() + timeout
        chunks = []
        received = 0
        descriptor = pipe.fileno()
        while received < byte_count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([descriptor], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(descriptor, byte_count - received)
            if not chunk:
                return None
            chunks.append(chunk)
            received += len(chunk)
        return b"".join(chunks)

    def read_camera_frame(self, process: subprocess.Popen, timeout=15.0) -> bytes | None:
        if process.stdout is None:
            return None
        header = self.read_exact(process.stdout, 4, timeout)
        if header is None:
            return None
        byte_count = int.from_bytes(header, "big")
        if byte_count < 100 or byte_count > 5_000_000:
            return None
        return self.read_exact(process.stdout, byte_count, timeout)

    @staticmethod
    def drain_camera_stderr(pipe, chunks: bytearray, lock: threading.Lock) -> None:
        if pipe is None:
            return
        descriptor = pipe.fileno()
        while True:
            try:
                chunk = os.read(descriptor, 4096)
            except OSError:
                return
            if not chunk:
                return
            with lock:
                chunks.extend(chunk)
                if len(chunks) > 16_384:
                    del chunks[:-16_384]

    def stream_camera(self) -> None:
        if not self.server.camera_session_lock.acquire(blocking=False):
            self.send_json(
                {"ok": False, "error": "camera stream already in use"},
                HTTPStatus.CONFLICT,
            )
            return
        process = None
        stderr_thread = None
        stderr_chunks = bytearray()
        stderr_lock = threading.Lock()
        try:
            process = self.server.camera_process()
            stderr_thread = threading.Thread(
                target=self.drain_camera_stderr,
                args=(process.stderr, stderr_chunks, stderr_lock),
                name="mi-dog-camera-stderr",
                daemon=True,
            )
            stderr_thread.start()
            first_frame = self.read_camera_frame(process)
            if first_frame is None:
                error = "camera stream unavailable"
                with stderr_lock:
                    detail = bytes(stderr_chunks).decode(
                        "utf-8", errors="replace").strip()
                if detail:
                    error = detail[-2048:]
                self.send_json({"ok": False, "error": error}, HTTPStatus.BAD_GATEWAY)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=mi-dog-frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.server.camera_begin()
            frame = first_frame
            while frame is not None:
                self.wfile.write(b"--mi-dog-frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                self.server.camera_record(len(frame))
                frame = self.read_camera_frame(process, timeout=5.0)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.camera_end()
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if stderr_thread is not None:
                stderr_thread.join(timeout=1)
            self.server.camera_session_lock.release()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            template = (UI_ROOT / "index.html").read_text(encoding="utf-8")
            page = template.replace("__MI_DOG_TOKEN__", html.escape(self.server.token)).replace(
                "__MI_DOG_TARGET__", html.escape(self.server.target)
            ).replace(
                "__MI_DOG_MAINTENANCE_CONTROLS__",
                "true" if self.server.maintenance_controls else "false",
            )
            self.send_bytes(page.encode("utf-8"), "text/html; charset=utf-8")
            return
        static = {
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
        }
        if path in static:
            name, content_type = static[path]
            self.send_bytes((UI_ROOT / name).read_bytes(), content_type)
            return
        if path == "/api/status":
            if self.headers.get("X-Mi-Dog-Token") != self.server.token:
                self.send_json({"ok": False, "error": "invalid UI token"}, HTTPStatus.FORBIDDEN)
                return
            self.send_json(self.server.control("status"))
            return
        if path == "/api/health":
            self.send_json({
                "ok": True,
                "target": self.server.target,
                "maintenance_controls": self.server.maintenance_controls,
            })
            return
        if path == "/api/camera/token":
            if self.headers.get("X-Mi-Dog-Token") != self.server.token:
                self.send_json({"ok": False, "error": "invalid UI token"}, HTTPStatus.FORBIDDEN)
                return
            self.send_json({
                "ok": True,
                "stream_token": self.server.issue_camera_token(),
                "expires_in_seconds": CAMERA_TOKEN_TTL_SECONDS,
            })
            return
        if path == "/api/camera/metrics":
            if self.headers.get("X-Mi-Dog-Token") != self.server.token:
                self.send_json({"ok": False, "error": "invalid UI token"}, HTTPStatus.FORBIDDEN)
                return
            self.send_json(self.server.camera_metrics())
            return
        if path == "/api/camera/stream":
            query_token = parse_qs(parsed.query).get("token", [""])[0]
            if not self.server.consume_camera_token(query_token):
                self.send_json({"ok": False, "error": "invalid or expired stream token"}, HTTPStatus.FORBIDDEN)
                return
            self.stream_camera()
            return
        self.send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/action":
                action = str(payload.get("action", ""))
                stage_value = payload.get("stage")
                stage = int(stage_value) if stage_value is not None else None
                self.send_json(self.server.control(action, stage))
                return
            if path == "/api/jog":
                self.send_json(self.server.jog(str(payload.get("direction", ""))))
                return
            if path == "/api/posture":
                self.send_json(self.server.posture(str(payload.get("action", ""))))
                return
            self.send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
        except PermissionError as error:
            self.send_json({"ok": False, "error": str(error)}, HTTPStatus.FORBIDDEN)
        except OperationBusyError as error:
            self.send_json({"ok": False, "error": str(error)}, HTTPStatus.CONFLICT)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json({"ok": False, "error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:  # Keep the local UI alive and surface a compact error.
            self.send_json({"ok": False, "error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--target", default=os.environ.get("MI_DOG_TARGET", "mi@192.168.44.1"))
    parser.add_argument(
        "--identity",
        type=Path,
        default=Path(os.environ.get(
            "MI_DOG_SSH_IDENTITY",
            str(Path.home() / ".ssh" / "mi_dog_competition_ed25519"),
        )),
    )
    parser.add_argument("--open", action="store_true", help="Open the local UI in a browser")
    parser.add_argument(
        "--maintenance-controls",
        action="store_true",
        help="Explicitly enable manual jog/posture controls; keep disabled for competition",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    identity = args.identity.expanduser().resolve()
    if not identity.is_file():
        print(
            f"Missing SSH identity: {identity}\n"
            "Run ./scripts/setup_robot_ssh_key.sh once before starting the UI.",
            file=sys.stderr,
        )
        return 2
    server = UiServer(
        (args.bind, args.port),
        RequestHandler,
        target=args.target,
        identity=identity,
        maintenance_controls=args.maintenance_controls,
    )
    url = f"http://{args.bind}:{args.port}/"
    print(f"Mi Dog competition UI: {url}")
    print(f"Robot target: {args.target}")
    print(
        "Manual maintenance controls: "
        + ("ENABLED" if args.maintenance_controls else "disabled (competition mode)"))
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
