"""Local API for the site in development. The Vite dev server proxies /api here.

Usage: .venv/bin/python -m gt.serve
"""
from http.server import ThreadingHTTPServer

from gt.api import CheckHandler

if __name__ == "__main__":
    print("Check API on http://127.0.0.1:8787/api/check")
    ThreadingHTTPServer(("127.0.0.1", 8787), CheckHandler).serve_forever()
