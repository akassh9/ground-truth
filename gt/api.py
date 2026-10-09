"""Request handling for the live Check, shared by the dev server (gt/serve.py) and Vercel (api/check.py).

Each check costs real money, so there are input limits, an optional passcode (CHECK_PASSCODE in the
environment; open when unset) and a per-process cache of answers.
"""
import hashlib
import json
import os
import urllib.error
from http.server import BaseHTTPRequestHandler

from gt.check import check, cited_ids_ok

LIMITS = {"name": 120, "url": 300, "about": 4000}
_answers = {}


def handle(body):
    passcode = os.environ.get("CHECK_PASSCODE")
    if passcode and body.get("passcode") != passcode:
        return 401, {"error": "This check needs the passcode from the application email.", "passcode_required": True}
    fields = {k: str(body.get(k) or "").strip()[:n] for k, n in LIMITS.items()}
    if not fields["name"] or not (fields["url"] or fields["about"]):
        return 400, {"error": "Give a company name, plus its website or a short description."}
    key = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    if key not in _answers:
        try:
            verdict, usage = check(fields["name"], fields["url"], fields["about"])
        except ValueError as e:  # a URL we won't fetch
            return 400, {"error": str(e)}
        except (urllib.error.URLError, TimeoutError):
            return 502, {"error": "Couldn't read that website. Paste a short description instead."}
        except Exception:
            return 502, {"error": "The check failed. Try again in a minute."}
        _answers[key] = {"name": fields["name"], "url": fields["url"], "verdict": verdict.model_dump(),
                         "unknown_citations": cited_ids_ok(verdict), "usage": usage}
    return 200, _answers[key]


class CheckHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path.split("?")[0] != "/api/check":
            return self.send_error(404)
        size = min(int(self.headers.get("Content-Length") or 0), 20_000)
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            body = {}
        status, payload = handle(body if isinstance(body, dict) else {})
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
