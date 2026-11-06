"""Local HTTP bridge between Luminous Life and the Python simulation core."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
import webbrowser

from Game_of_Life import UnboundedGameOfLife


ASSETS = Path(__file__).resolve().parent / "luminous-life" / "dist"


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    return value


def _coordinates(value, painting=False):
    if not isinstance(value, list) or len(value) > 100_000:
        raise ValueError("Provide a list of at most 100,000 cells.")
    result = []
    for cell in value:
        if not isinstance(cell, list) or len(cell) != (3 if painting else 2):
            raise ValueError("Each cell needs x, y coordinates" + (" and an alive flag." if painting else "."))
        x = _integer(cell[0], "x", -1_000_000, 1_000_000)
        y = _integer(cell[1], "y", -1_000_000, 1_000_000)
        if painting:
            if type(cell[2]) is not bool:
                raise ValueError("The alive flag must be true or false.")
            result.append((x, y, cell[2]))
        else:
            result.append((x, y))
    return result


class LifeWebServer(ThreadingHTTPServer):
    """Serve the frontend and serialize access to its simulation."""

    daemon_threads = True

    def __init__(self, address=("127.0.0.1", 8000), life_engine="auto"):
        self.simulation = UnboundedGameOfLife(life_engine=life_engine)
        self.simulation_lock = threading.Lock()
        super().__init__(address, partial(LifeRequestHandler, directory=str(ASSETS)))

    def snapshot(self):
        cells = self.simulation.living_cells()
        return {"cells": cells, "generation": self.simulation.generation,
                "population": len(cells), "engine": self.simulation.life_engine}


class LifeRequestHandler(SimpleHTTPRequestHandler):
    def _json(self, status, value):
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/state":
            with self.server.simulation_lock:
                self._json(200, self.server.snapshot())
        elif path.startswith("/api/"):
            self._json(404, {"error": "Unknown simulation endpoint."})
        else:
            super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/reset", "/api/step", "/api/paint"):
            self._json(404, {"error": "Unknown simulation endpoint."})
            return
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            self._json(403, {"error": "Use the local Luminous Life page to control this simulation."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4_000_000:
                raise ValueError("A JSON request of at most 4 MB is required.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("The request must be a JSON object.")
            with self.server.simulation_lock:
                simulation = self.server.simulation
                if path == "/api/reset":
                    cells = _coordinates(data.get("cells"))
                    warmup = _integer(data.get("warmup", 0), "warmup", 0, 12)
                    simulation.load_cells(cells)
                    for _ in range(warmup):
                        simulation.step()
                    simulation.generation = 0
                elif path == "/api/step":
                    steps = _integer(data.get("steps", 1), "steps", 1, 3)
                    for _ in range(steps):
                        simulation.step()
                else:
                    simulation.paint_cells(_coordinates(data.get("cells"), painting=True))
                self._json(200, self.server.snapshot())
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(400, {"error": str(exc)})

    def log_message(self, format, *args):
        # Animation requests are frequent; keep the console focused on errors.
        if len(args) < 2 or str(args[1]) not in ("200", "304"):
            super().log_message(format, *args)


def run_webui(life_engine="auto", port=8000, open_browser=True):
    if not (ASSETS / "index.html").is_file():
        raise SystemExit(f"Luminous Life assets are missing from {ASSETS}.")
    if not 1 <= port <= 65535:
        raise SystemExit("Use a web UI port between 1 and 65535.")
    try:
        server = LifeWebServer(("127.0.0.1", port), life_engine=life_engine)
    except OSError as exc:
        raise SystemExit(f"Could not start Luminous Life on port {port}: {exc}. Try --port 8001.") from exc
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Luminous Life: {url}\nPython Life engine: {life_engine}\nPress Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
