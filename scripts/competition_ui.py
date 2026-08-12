#!/usr/bin/env python3
"""Local-only web UI for safe CyberDog competition operations."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import secrets
import select
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

    def __init__(self, address, handler, *, target: str, identity: Path):
        super().__init__(address, handler)
        self.target = target
        self.identity = identity
        self.token = secrets.token_urlsafe(32)
        self.camera_session_lock = threading.Lock()
        self.camera_metrics_lock = threading.Lock()
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
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            return {
                "ok": False,
                "returncode": 124,
                "stdout": error.stdout or "",
                "stderr": "command timed out",
                "values": {},
            }
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "values": parse_key_values(result.stdout),
        }

    def control(self, action: str, stage: int | None = None) -> dict:
        if action not in ALLOWED_ACTIONS:
            raise ValueError("unsupported action")
        command = [str(CONTROL_SCRIPT), "--target", self.target]
        if action in {"select-stage", "continue-stage"}:
            if stage not in range(1, 7):
                raise ValueError("stage must be 1..6")
            command.extend(["--stage", str(stage)])
        command.append(action)
        return self.run_tool(command, 120 if action == "restart" else 25)

    def jog(self, direction: str) -> dict:
        if direction not in ALLOWED_JOGS:
            raise ValueError("unsupported jog direction")
        return self.run_tool([str(JOG_SCRIPT), direction], 20)

    def posture(self, action: str) -> dict:
        if action not in ALLOWED_POSTURES:
            raise ValueError("unsupported posture action")
        return self.run_tool([str(POSTURE_SCRIPT), action], 65)

    def camera_process(self) -> subprocess.Popen:
        remote_command = (
            "set +u; "
            "source /opt/ros2/galactic/setup.bash >/dev/null 2>&1; "
            "source /opt/ros2/cyberdog/setup.bash >/dev/null 2>&1; "
            "source /home/mi/mi_dog_ws/install/setup.bash >/dev/null 2>&1; "
            "set -u; "
            "export ROS_DOMAIN_ID=42; "
            "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp; "
            "export CYCLONEDDS_URI=file:///etc/mi/cyclonedds.xml; "
            f"exec python3 - --topic {CAMERA_TOPIC} --max-fps 10 "
            "--jpeg-quality 72 --max-width 640"
        )
        command = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=2",
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
            return {
                "ok": True,
                "active": self.camera_active,
                "fps": round(fps, 2),
                "frames": self.camera_frames,
                "megabytes": round(self.camera_bytes / 1_000_000.0, 2),
                "source_limit_fps": 10,
            }


class RequestHandler(BaseHTTPRequestHandler):
    server: UiServer

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[ui] " + fmt % args + "\n")

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

    def stream_camera(self) -> None:
        if not self.server.camera_session_lock.acquire(blocking=False):
            self.send_json(
                {"ok": False, "error": "camera stream already in use"},
                HTTPStatus.CONFLICT,
            )
            return
        process = None
        try:
            process = self.server.camera_process()
            first_frame = self.read_camera_frame(process)
            if first_frame is None:
                error = "camera stream unavailable"
                if process.stderr is not None:
                    ready, _, _ = select.select([process.stderr.fileno()], [], [], 0)
                    if ready:
                        detail = os.read(process.stderr.fileno(), 2048).decode(
                            "utf-8", errors="replace").strip()
                        if detail:
                            error = detail
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
            self.server.camera_session_lock.release()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            template = (UI_ROOT / "index.html").read_text(encoding="utf-8")
            page = template.replace("__MI_DOG_TOKEN__", html.escape(self.server.token)).replace(
                "__MI_DOG_TARGET__", html.escape(self.server.target)
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
            self.send_json({"ok": True, "target": self.server.target})
            return
        if path == "/api/camera/metrics":
            if self.headers.get("X-Mi-Dog-Token") != self.server.token:
                self.send_json({"ok": False, "error": "invalid UI token"}, HTTPStatus.FORBIDDEN)
                return
            self.send_json(self.server.camera_metrics())
            return
        if path == "/api/camera/stream":
            query_token = parse_qs(parsed.query).get("token", [""])[0]
            if not secrets.compare_digest(query_token, self.server.token):
                self.send_json({"ok": False, "error": "invalid UI token"}, HTTPStatus.FORBIDDEN)
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
    server = UiServer((args.bind, args.port), RequestHandler, target=args.target, identity=identity)
    url = f"http://{args.bind}:{args.port}/"
    print(f"Mi Dog competition UI: {url}")
    print(f"Robot target: {args.target}")
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
