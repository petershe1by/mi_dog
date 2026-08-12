#!/usr/bin/env python3
"""Local-only web UI for safe CyberDog competition operations."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"
CONTROL_SCRIPT = ROOT / "scripts" / "competition_control.sh"
JOG_SCRIPT = ROOT / "scripts" / "robot_jog.sh"
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

    def do_GET(self) -> None:
        path = urlparse(self.path).path
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
