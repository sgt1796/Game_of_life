#!/usr/bin/env python3
"""Simulation state and entry point for Conway's Game of Life."""

import argparse
from pathlib import Path

import numpy as np

from life_engines import QuickLifeEngine, next_generation


def _init_grid(n, ratio):
    """Create an n-by-n grid with the requested proportion of live cells."""
    ones = int(n ** 2 * ratio)
    vector = np.array([1] * ones + [0] * (n ** 2 - ones))
    np.random.shuffle(vector)
    return vector.reshape((n, n))


def next_gen(grid, boundary_mode, method="auto"):
    """Advance binary Life; select byte sums or packed bits by grid size.

    Explicit methods are "dense", "packed", "lookup", and "quicklife". All preserve the
    float64 matrix interface and wrap/open/fill boundary behavior.
    Use QuickLifeEngine directly to preserve its packed state across steps.
    """
    return next_generation(grid, boundary_mode, method)


class GameOfLife:
    """Control the grid and simulation independently of its user interface."""

    def __init__(self, size=150, seeding_ratio=0.1, life_engine="auto", boundary_mode="wrap"):
        self.size = size
        self.seeding_ratio = seeding_ratio
        self.life_engine = None
        self.boundary_mode = boundary_mode
        self.is_running = True
        self._engine = None
        self.reset()
        self.set_life_engine(life_engine)

    def set_life_engine(self, name):
        """Change implementation without changing the world or run state."""
        if name not in ("auto", "dense", "packed", "lookup", "quicklife"):
            raise ValueError(f"Unknown Life engine: {name}")
        if name == self.life_engine:
            return
        engine = QuickLifeEngine(self.grid, self.boundary_mode) if name == "quicklife" else None
        self._engine = engine
        self.life_engine = name

    def step(self):
        """Advance one generation while running, retaining QuickLife state."""
        if self.is_running:
            if self._engine is None:
                self.grid = next_gen(self.grid, self.boundary_mode, method=self.life_engine)
            else:
                self._engine.step()
                self.grid = self._engine.to_numpy()
        return self.grid

    def reset(self, seeding_ratio=None):
        """Reseed the board, optionally changing the proportion of live cells."""
        if seeding_ratio is not None:
            self.seeding_ratio = seeding_ratio
        self.grid = _init_grid(self.size, self.seeding_ratio).astype(float)
        if self._engine is not None:
            self._engine.load(self.grid)

    def clear(self):
        """Remove every live cell from the board."""
        self.grid = np.zeros((self.size, self.size), dtype=float)
        if self._engine is not None:
            self._engine.load(self.grid)

    def seed_cell(self, x, y):
        """Make a cell alive; return whether its coordinates are on the board."""
        return self.set_cell(x, y)

    def set_cell(self, x, y, alive=True):
        """Set or erase a cell, keeping the persistent engine in sync."""
        if not (0 <= x < self.grid.shape[1] and 0 <= y < self.grid.shape[0]):
            return False
        self.grid[y, x] = int(alive)
        if self._engine is not None:
            self._engine.set_cell(x, y, alive)
        return True

    def set_boundary_mode(self, mode):
        """Change the boundary behavior for subsequent generations."""
        self.boundary_mode = mode
        if self._engine is not None:
            self._engine.set_boundary(mode)

    def toggle_running(self):
        """Pause or resume the simulation and return its running state."""
        self.is_running = not self.is_running
        return self.is_running


class UnboundedGameOfLife(GameOfLife):
    """Use the same Life engines on a growing board with world coordinates.

    Empty padding is added before live cells reach an edge, so patterns never
    wrap or get clipped. QuickLife retains its packed state between expansions.
    """

    MARGIN = 32
    MAX_AREA = 16_777_216

    def __init__(self, life_engine="auto"):
        super().__init__(size=64, seeding_ratio=0, life_engine=life_engine, boundary_mode="open")
        self.origin = (-32, -32)
        self.generation = 0

    def _load_world(self, grid, origin):
        self.grid = grid
        self.origin = origin
        if self._engine is not None:
            self._engine.load(grid)

    @classmethod
    def _check_area(cls, rows, cols):
        if rows * cols > cls.MAX_AREA:
            raise ValueError("The populated area is too large; reset or draw closer to the current field.")

    def load_cells(self, cells):
        """Replace the world with live (x, y) coordinates and reset its counter."""
        coordinates = np.asarray(cells, dtype=np.int64).reshape(-1, 2)
        if not len(coordinates):
            self._load_world(np.zeros((64, 64), dtype=float), (-32, -32))
        else:
            low = coordinates.min(axis=0) - self.MARGIN
            high = coordinates.max(axis=0) + self.MARGIN + 1
            cols, rows = map(int, high - low)
            self._check_area(rows, cols)
            grid = np.zeros((rows, cols), dtype=float)
            local = coordinates - low
            grid[local[:, 1], local[:, 0]] = 1
            self._load_world(grid, tuple(map(int, low)))
        self.generation = 0

    def clear(self):
        self.load_cells([])

    def _grow(self, left=0, top=0, right=0, bottom=0):
        if not any((left, top, right, bottom)):
            return
        rows, cols = self.grid.shape
        self._check_area(rows + top + bottom, cols + left + right)
        grid = np.pad(self.grid, ((top, bottom), (left, right)))
        self._load_world(grid, (self.origin[0] - left, self.origin[1] - top))

    def paint_cells(self, changes):
        """Apply a batch of (world x, world y, alive) edits."""
        if not changes:
            return
        xs, ys, _ = zip(*changes)
        x, y = self.origin
        rows, cols = self.grid.shape
        self._grow(
            left=max(0, x - min(xs) + self.MARGIN) if min(xs) < x else 0,
            top=max(0, y - min(ys) + self.MARGIN) if min(ys) < y else 0,
            right=max(xs) - (x + cols) + self.MARGIN + 1 if max(xs) >= x + cols else 0,
            bottom=max(ys) - (y + rows) + self.MARGIN + 1 if max(ys) >= y + rows else 0)
        for world_x, world_y, alive in changes:
            self.set_cell(world_x - self.origin[0], world_y - self.origin[1], alive)

    def step(self):
        if self.is_running:
            self._grow(
                left=self.MARGIN if self.grid[:, 0].any() else 0,
                top=self.MARGIN if self.grid[0].any() else 0,
                right=self.MARGIN if self.grid[:, -1].any() else 0,
                bottom=self.MARGIN if self.grid[-1].any() else 0)
            super().step()
            self.generation += 1
        return self.grid

    def living_cells(self):
        """Return live cells as world (x, y) pairs for a renderer."""
        rows, cols = np.nonzero(self.grid)
        return np.column_stack((cols + self.origin[0], rows + self.origin[1])).tolist()


def build_parser():
    """Keep shared simulation options and each interface's options together."""
    from life_stream import STYLES

    parser = argparse.ArgumentParser(
        description="Conway's Life with terminal, desktop, web, and diffusion views.",
        epilog="Run '%(prog)s COMMAND --help' for that interface's options.")
    commands = parser.add_subparsers(dest="command", required=True, title="interfaces")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--life-engine", choices=["auto", "dense", "packed", "lookup", "quicklife"], default="auto",
                        help="Life engine; quicklife combines persistent packed slices, lookup and dirty tiles.")

    commands.add_parser("run", parents=[common],
                        help="Open the Matplotlib desktop UI.",
                        description="Run the interactive Matplotlib desktop view.")

    terminal = commands.add_parser("cli", parents=[common],
                                   help="Animate Life in the terminal using filled squares.",
                                   description="Show live cells as ■ and dead cells as spaces. Stop with Ctrl+C.")
    terminal.add_argument("--grid-size", type=int, default=None,
                          help="Cells per side (default: fit the terminal, up to 24).")
    terminal.add_argument("--fps", type=float, default=8, help="Generations per second (default: 8).")
    terminal.add_argument("--density", type=float, default=0.2, help="Initial live fraction (default: 0.2).")
    terminal.add_argument("--boundary", choices=["wrap", "open", "fill"], default="wrap")
    terminal.add_argument("--seed", type=int, help="Random seed for a repeatable starting grid.")
    terminal.add_argument("--frames", type=int, default=0,
                          help="Frames to display, including the initial grid; 0 runs until Ctrl+C.")

    webui = commands.add_parser("webui", parents=[common],
                                help="Open the Luminous Life web UI.",
                                description="Serve Luminous Life, powered by the Python core.")
    webui.add_argument("--port", type=int, default=8000, help="Local web UI port (default: 8000).")
    webui.add_argument("--no-browser", action="store_true", help="Start the web UI without opening a browser.")

    diffusion = commands.add_parser("streamdiffusion", parents=[common],
                                    help="Render the matrix with StreamDiffusion.",
                                    description="Render the Life matrix with StreamDiffusion, live or to PNG files.")
    diffusion.add_argument("--stream-root", type=Path,
                           default=Path(__file__).resolve().parent.parent / "StreamDiffusion")
    diffusion.add_argument("--model", default="KBlueLeaf/kohaku-v2.1")
    diffusion.add_argument("--style", choices=list(STYLES), default="Bioluminescent")
    diffusion.add_argument("--prompt", help="Override the selected style's prompt.")
    diffusion.add_argument("--grid-size", type=int, default=64, help="Cells per side in diffusion mode.")
    diffusion.add_argument("--size", type=int, default=512, help="Output pixels per side; a multiple of 64.")
    diffusion.add_argument("--fps", type=float, default=8, help="Life generations per second, independent of GPU speed.")
    diffusion.add_argument("--density", type=float, default=0.20)
    diffusion.add_argument("--fade", type=float, default=0.12, help="Trail opacity lost per generation.")
    diffusion.add_argument("--boundary", choices=["wrap", "open", "fill"], default="wrap")
    diffusion.add_argument("--seed", type=int, default=2)
    diffusion.add_argument("--acceleration", choices=["none", "xformers", "tensorrt"], default="none")
    diffusion.add_argument("--t-indices", type=int, nargs="+", default=[28, 40],
                           help="Ascending indices in a 50-step schedule; higher indices retain more input detail.")
    diffusion.add_argument("--allow-download", action="store_true", help="Allow uncached model downloads.")
    diffusion.add_argument("--render-frames", type=int, default=0, help="Save this many frames without opening a UI.")
    diffusion.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "renders" / "life")
    return parser


def main(life_engine="auto"):
    """Launch the interactive view with the simulation controller."""
    from Game_of_Life_UI import GameOfLifeUI

    simulation = GameOfLife(life_engine=life_engine)
    ui = GameOfLifeUI(simulation)
    ui.show()


def cli(argv=None):
    """Parse an interface subcommand and launch its view."""
    parser = build_parser()
    options = parser.parse_args(argv)
    if options.command == "cli":
        from Game_of_Life_CLI import run_cli, validate_options

        try:
            validate_options(options)
        except ValueError as error:
            parser.error(str(error))
        run_cli(options, GameOfLife)
    elif options.command == "webui":
        from Game_of_Life_Web import run_webui

        run_webui(life_engine=options.life_engine, port=options.port, open_browser=not options.no_browser)
    elif options.command == "streamdiffusion":
        from life_stream import run

        run(options, lambda grid, boundary: next_gen(grid, boundary, method=options.life_engine))
    else:
        main(life_engine=options.life_engine)


if __name__ == "__main__":
    cli()
