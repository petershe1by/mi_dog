#!/usr/bin/env python3
"""Authenticated loopback proxy for an explicitly requested public UI tunnel."""

from __future__ import annotations

import argparse
import base64
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import sys


HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, upstream_host, upstream_port, username, password):
        super().__init__(address, ProxyHandler)
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        raw = f"{username}:{password}".encode()
        self.expected_authorization = "Basic " + base64.b64encode(raw).decode()


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *_args):
        # Paths can contain one-time UI camera tokens. Never log them.
        return

    def unauthorized(self):
        body = b"Authentication required\n"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Mi Dog UI"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def proxy(self):
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, self.server.expected_authorization):
            self.unauthorized()
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {
            key: value for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP | {"authorization", "host"}
        }
        connection = http.client.HTTPConnection(
            self.server.upstream_host, self.server.upstream_port, timeout=130)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP:
                    self.send_header(key, value)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            connection.close()

    do_GET = proxy
    do_POST = proxy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=8765)
    parser.add_argument("--username", default="mi-dog")
    parser.add_argument("--password", default="")
    args = parser.parse_args()
    password = args.password or secrets.token_urlsafe(24)
    server = ProxyServer(
        (args.bind, args.port), args.upstream_host, args.upstream_port,
        args.username, password)
    print(f"Public UI auth proxy: http://{args.bind}:{args.port}/", flush=True)
    print(f"Public UI username: {args.username}", flush=True)
    print(f"Public UI password: {password}", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
