"""Local mock careers site for development and automated tests. NOT a real employer; never used in production.

Routes: /apply/ok (works), /apply/captcha, /apply/login, /apply/mfa, /apply/silent (accepts form but never confirms),
/apply/error (HTTP 500), /apply/slow (never answers within the timeout).
"""

import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

FORM = """<!doctype html><html><body><h1>Apply: Mock Role</h1>
<form method="post" enctype="multipart/form-data">
<label>Full name <input name="full_name" required></label>
<label>Email <input type="email" name="email" required></label>
<label>Phone <input name="phone"></label>
<label>Resume <input type="file" name="resume"></label>
<label>Cover letter <textarea name="cover_letter"></textarea></label>
<label><input type="checkbox" name="consent" required> I agree to the privacy notice</label>
<button type="submit">Submit application</button></form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "MockCareers/1.0"
    submissions: list[dict] = []

    def log_message(self, *a):  # silence
        pass

    def _send(self, body: str, status: int = 200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/apply/ok" or path == "/apply/silent":
            self._send(FORM)
        elif path == "/apply/captcha":
            self._send("<html><body><form><div class='g-recaptcha'>Please verify you are human (CAPTCHA)</div></form></body></html>")
        elif path == "/apply/login":
            self._send("<html><body><p>Please sign in to continue</p><form><input name=u><button type=submit>Go</button></form></body></html>")
        elif path == "/apply/mfa":
            self._send(FORM.replace("<h1>", "<p>Enter the verification code we sent you</p><h1>"))
        elif path == "/apply/error":
            self._send("boom", 500)
        elif path == "/apply/slow":
            time.sleep(6)
            self._send(FORM)
        elif path == "/__submissions":
            import json
            self._send(json.dumps(Handler.submissions))
        else:
            self._send("not found", 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        Handler.submissions.append({"path": path, "bytes": len(raw), "has_resume": b'filename="' in raw})
        if path == "/apply/ok":
            ref = "MOCK-" + uuid.uuid4().hex[:8].upper()
            self._send(f"<html><body><h1>Thank you for applying</h1><p>Your application has been received. Reference: {ref}</p></body></html>")
        elif path == "/apply/silent":
            self._send("<html><body><p>OK</p></body></html>")
        else:
            self._send("not found", 404)


def start(host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{host}:{srv.server_address[1]}"


if __name__ == "__main__":
    s, url = start(port=8765)
    print("Mock careers site at", url)
    threading.Event().wait()
