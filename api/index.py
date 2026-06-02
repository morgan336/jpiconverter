"""Vercel serverless entry point.

Vercel's @vercel/python builder runs this module and expects a WSGI-compatible
`app` symbol. We shim sys.path so the `jpiconverter` package under src/ is
importable, then re-export the Flask app.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"),
)

from jpiconverter.web.app import app  # noqa: E402,F401
