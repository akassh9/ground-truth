"""Vercel Python function for the live Check. Same handler as the local dev server (gt/serve.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gt.api import CheckHandler  # noqa: E402


class handler(CheckHandler):  # Vercel looks for a class named `handler`
    pass
