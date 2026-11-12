"""Local deterministic simulators. No outbound network functions or real payments."""
import json
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

messages = []
lock = threading.Lock()


class SMTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        self.wfile.write(b"220 audit3 synthetic SMTP\r\n")
        data, in_data = bytearray(), False
        for _ in range(5000):
            line = self.rfile.readline(4096)
            if not line:
                break
            if in_data:
                if line == b".\r\n":
                    with lock:
                        if len(messages) < 100:
                            messages.append(data.decode(errors="replace"))
                    self.wfile.write(b"250 captured locally\r\n")
                    data, in_data = bytearray(), False
                elif len(data) < 65536:
                    data.extend(line)
                continue
            verb = line.split(b" ")[0].strip().upper()
            if verb == b"QUIT":
                self.wfile.write(b"221 bye\r\n")
                break
            if verb == b"DATA":
                in_data = True
                self.wfile.write(b"354 end with dot\r\n")
            else:
                self.wfile.write(b"250 OK\r\n")


class HTTP(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            result = {"simulator": "audit3", "production": False, "messages": list(messages)} if self.path == "/mail" else {"simulator": "audit3", "production": False, "status": "synthetic", "id": "fixture-001"}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Audit3-Simulator", "true")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def do_POST(self):
        size = min(int(self.headers.get("Content-Length", "0")), 65536)
        self.rfile.read(size)
        self.do_GET()

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    smtp = socketserver.ThreadingTCPServer(("0.0.0.0", 1025), SMTP)
    smtp.daemon_threads = True
    threading.Thread(target=smtp.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), HTTP).serve_forever()
