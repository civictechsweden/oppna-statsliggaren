import argparse
import csv
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parent
SAMPLES_INDEX = ROOT / "build" / "xhtml-samples" / "index.csv"
REMOTE_BASE_URL = "https://www.statskontoret.se/Statsliggaren/Regleringsbrev?rbid="


def load_samples() -> list[dict[str, str]]:
    if not SAMPLES_INDEX.exists():
        return []

    with SAMPLES_INDEX.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        row["raw_html_rel"] = str(Path(row["raw_html"]).resolve().relative_to(ROOT))
        row["parsed_xhtml_rel"] = str(
            Path(row["parsed_xhtml"]).resolve().relative_to(ROOT)
        )

    return rows


class PreviewHandler(BaseHTTPRequestHandler):
    samples = load_samples()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self._send_html(self._render_index())
            return

        if parsed.path == "/compare":
            query = parse_qs(parsed.query)
            raw_path = query.get("raw", [""])[0]
            parsed_path = query.get("parsed", [""])[0]
            self._send_html(self._render_compare(raw_path, parsed_path))
            return

        if parsed.path.startswith("/files/"):
            requested = unquote(parsed.path.removeprefix("/files/"))
            self._send_file(requested)
            return

        self.send_error(404, "Not found")

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, relative_path: str) -> None:
        path = (ROOT / relative_path).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            self.send_error(403, "Forbidden")
            return

        if not path.exists() or not path.is_file():
            self.send_error(404, "File not found")
            return

        if path.suffix.lower() in {".html", ".xhtml"}:
            content_type = "text/html; charset=utf-8"
        elif path.suffix.lower() == ".css":
            content_type = "text/css; charset=utf-8"
        else:
            content_type = "text/plain; charset=utf-8"

        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _render_index(self) -> str:
        rows = []
        for sample in self.samples:
            compare_url = (
                "/compare?rbid="
                + quote(sample["rbid"])
                + "&raw="
                + quote(sample["raw_html_rel"])
                + "&parsed="
                + quote(sample["parsed_xhtml_rel"])
            )
            rows.append(
                "<tr>"
                f"<td>{html.escape(sample['variant'])}</td>"
                f"<td>{html.escape(sample['sample_slot'])}</td>"
                f"<td>{html.escape(sample['rbid'])}</td>"
                f"<td>{html.escape(sample['date'])}</td>"
                f"<td>{html.escape(sample['type'])}</td>"
                f"<td><a href=\"{compare_url}\">compare</a></td>"
                f"<td><a href=\"/files/{quote(sample['raw_html_rel'])}\">html</a></td>"
                f"<td><a href=\"/files/{quote(sample['parsed_xhtml_rel'])}\">xhtml</a></td>"
                "</tr>"
            )

        table_rows = "\n".join(rows) or (
            "<tr><td colspan=\"8\">No sample index found at build/xhtml-samples/index.csv</td></tr>"
        )

        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>XHTML Preview</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f4f1ea;
        --panel: #fffdf8;
        --line: #d8d1c2;
        --text: #1f1b16;
        --muted: #6a6256;
        --accent: #005a7a;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Georgia, "Times New Roman", serif;
        color: var(--text);
        background:
          radial-gradient(circle at top left, #fffaf0 0, transparent 35%),
          linear-gradient(180deg, #efe8db 0, var(--bg) 30%, #ece5d9 100%);
      }}
      main {{
        max-width: 1200px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }}
      h1 {{
        margin: 0 0 8px;
        font-size: 2rem;
      }}
      p {{
        margin: 0 0 20px;
        color: var(--muted);
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        background: var(--panel);
        border: 1px solid var(--line);
      }}
      th, td {{
        padding: 10px 12px;
        border-top: 1px solid var(--line);
        text-align: left;
        vertical-align: top;
      }}
      thead th {{
        border-top: 0;
        font-size: 0.9rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }}
      a {{
        color: var(--accent);
        text-decoration: none;
      }}
      a:hover {{
        text-decoration: underline;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>XHTML Sample Preview</h1>
      <p>Compare the original HTML with CSS against the cleaned intermediate XHTML.</p>
      <table>
        <thead>
          <tr>
            <th>Variant</th>
            <th>Slot</th>
            <th>RBID</th>
            <th>Date</th>
            <th>Type</th>
            <th>Compare</th>
            <th>Original</th>
            <th>Parsed</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </main>
  </body>
</html>
"""

    def _render_compare(self, raw_path: str, parsed_path: str) -> str:
        raw_rel = self._validated_relative_path(raw_path)
        parsed_rel = self._validated_relative_path(parsed_path)

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        rbid = query.get("rbid", [""])[0]
        remote_url = self._remote_letter_url(rbid)

        if remote_url is None or parsed_rel is None:
            return "<!doctype html><html><body><p>Invalid file path.</p></body></html>"

        raw_label = raw_rel or ""
        parsed_url = "/files/" + quote(parsed_rel)

        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Compare XHTML</title>
    <style>
      :root {{
        --bg: #f3efe7;
        --panel: #fffdf9;
        --line: #d7cfbf;
        --text: #1f1b16;
        --muted: #6a6256;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family: Georgia, "Times New Roman", serif;
      }}
      header {{
        padding: 16px 20px;
        border-bottom: 1px solid var(--line);
        background: rgba(255, 253, 249, 0.92);
        position: sticky;
        top: 0;
        z-index: 1;
        backdrop-filter: blur(8px);
      }}
      h1 {{
        margin: 0 0 6px;
        font-size: 1.2rem;
      }}
      p {{
        margin: 0;
        color: var(--muted);
        font-size: 0.95rem;
      }}
      main {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        padding: 12px;
        height: calc(100vh - 88px);
      }}
      section {{
        display: flex;
        flex-direction: column;
        min-height: 0;
        background: var(--panel);
        border: 1px solid var(--line);
      }}
      h2 {{
        margin: 0;
        padding: 10px 12px;
        font-size: 0.95rem;
        border-bottom: 1px solid var(--line);
      }}
      iframe {{
        width: 100%;
        height: 100%;
        border: 0;
        background: white;
      }}
      a {{ color: inherit; }}
      @media (max-width: 900px) {{
        main {{
          grid-template-columns: 1fr;
          height: auto;
        }}
        section {{
          min-height: 70vh;
        }}
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>Compare live HTML and parsed XHTML</h1>
      <p>
        <a href="/">Back to sample index</a>
        |
        <a href="{html.escape(remote_url)}" target="_blank" rel="noreferrer">open live page</a>
        |
        {html.escape(raw_label)}
        |
        {html.escape(parsed_rel)}
      </p>
    </header>
    <main>
      <section>
        <h2>Live Statskontoret page</h2>
        <iframe src="{html.escape(remote_url)}" title="Live Statskontoret page"></iframe>
      </section>
      <section>
        <h2>Parsed XHTML</h2>
        <iframe src="{parsed_url}" title="Parsed XHTML"></iframe>
      </section>
    </main>
  </body>
</html>
"""

    @staticmethod
    def _remote_letter_url(rbid: str) -> str | None:
        if not rbid or not rbid.isdigit():
            return None

        return f"{REMOTE_BASE_URL}{rbid}"

    @staticmethod
    def _validated_relative_path(value: str) -> str | None:
        if not value:
            return None

        path = (ROOT / value).resolve()
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return None

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview original HTML and parsed XHTML side by side."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    print(f"Serving preview on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
