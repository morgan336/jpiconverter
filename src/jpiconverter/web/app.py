"""Tiny Flask app: GET / shows an upload form, POST /convert returns a CSV.

Designed to be runnable both locally (`flask --app jpiconverter.web.app run`)
and on a hosted Python platform (Render/Fly/Railway) with a single
`gunicorn jpiconverter.web.app:app` command.

State-free: the uploaded .JPI lives in memory for one request and is discarded.
"""

from __future__ import annotations

import zipfile
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
        files = [f for f in request.files.getlist("jpi") if f and f.filename]
        if not files:
            return render_template("index.html",
                                   error="Please choose at least one .JPI file to upload.",
                                   warning=None), 400

        csvs: dict[str, bytes] = {}     # out_name -> CSV bytes
        failures: dict[str, str] = {}   # input filename -> error message

        for f in files:
            raw = f.read()
            if not raw:
                failures[f.filename] = "empty file"
                continue
            try:
                flights, _ = decode(raw, source_name=f.filename)
            except Exception as e:
                failures[f.filename] = str(e)
                continue
            csvs[Path(f.filename).stem + ".csv"] = to_flysto_csv(flights)

        # Nothing decoded successfully — render an inline error page.
        if not csvs:
            msg = "; ".join(f"{n}: {e}" for n, e in failures.items())
            return render_template("index.html",
                                   error=f"Could not decode any uploaded file. {msg}",
                                   warning=None), 400

        # Single successful file, no failures → return the CSV directly.
        if len(csvs) == 1 and not failures:
            out_name, csv_bytes = next(iter(csvs.items()))
            return send_file(
                BytesIO(csv_bytes),
                mimetype="text/csv",
                as_attachment=True,
                download_name=out_name,
            )

        # Multiple successes (or partial success) → bundle as ZIP.
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in csvs.items():
                z.writestr(name, data)
            if failures:
                report = "Files that failed to convert:\n\n" + "\n".join(
                    f"  {n}: {e}" for n, e in failures.items()
                ) + "\n"
                z.writestr("WARNINGS.txt", report)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name="jpiconverter_batch.zip",
        )

    return app


# Module-level `app` for `flask --app jpiconverter.web.app` and gunicorn.
app = create_app()
