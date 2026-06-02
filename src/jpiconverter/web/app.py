"""Tiny Flask app: GET / shows an upload form, POST /convert returns a CSV.

Designed to be runnable both locally (`flask --app jpiconverter.web.app run`)
and on a hosted Python platform (Render/Fly/Railway) with a single
`gunicorn jpiconverter.web.app:app` command.

State-free: the uploaded .JPI lives in memory for one request and is discarded.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from flask import Flask, render_template, request, send_file

from ..decode import decode
from ..flysto import to_flysto_csv


def create_app() -> Flask:
    app = Flask(__name__)
    # 4 MB cap — fits Vercel's hobby-tier 4.5 MB body limit with a small
    # margin. Real JPI downloads observed so far top out around 2 MB.
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

    @app.get("/")
    def index():
        return render_template("index.html", error=None, warning=None)

    @app.post("/convert")
    def convert():
        f = request.files.get("jpi")
        if not f or not f.filename:
            return render_template("index.html",
                                   error="Please choose a .JPI file to upload.",
                                   warning=None), 400

        raw = f.read()
        if not raw:
            return render_template("index.html",
                                   error="The uploaded file was empty.",
                                   warning=None), 400

        try:
            flights, _ = decode(raw, source_name=f.filename)
        except Exception as e:
            return render_template("index.html",
                                   error=f"Could not decode {f.filename}: {e}",
                                   warning=None), 400

        csv_bytes = to_flysto_csv(flights)
        out_name = Path(f.filename).stem + ".csv"

        return send_file(
            BytesIO(csv_bytes),
            mimetype="text/csv",
            as_attachment=True,
            download_name=out_name,
        )

    return app


# Module-level `app` for `flask --app jpiconverter.web.app` and gunicorn.
app = create_app()
