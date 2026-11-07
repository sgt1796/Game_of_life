"""Terminal view of the shared Life simulation; requires only NumPy."""

from contextlib import contextmanager
import math
import os
import shutil
import sys
import time

import numpy as np


def validate_options(options):
    for name in ("alive", "dead"):
        character = getattr(options, name)
        if len(character) != 1 or not character.isprintable():
            raise ValueError(f"--{name} must be one printable character (including a space).")
    if options.grid_size is not None and options.grid_size < 1:
        raise ValueError("--grid-size must be positive.")
    if not math.isfinite(options.fps) or options.fps <= 0:
        raise ValueError("--fps must be finite and positive.")
    if not 0 <= options.density <= 1:
        raise ValueError("--density must be between 0 and 1.")
    if options.frames < 0:
        raise ValueError("--frames must be nonnegative.")
    if options.seed is not None and not 0 <= options.seed < 2**32:
        raise ValueError("--seed must be between 0 and 4294967295.")


@contextmanager
def terminal_display():
    """Enable ANSI drawing on Windows and restore the cursor on exit."""
    interactive = sys.stdout.isatty()
    console = None
    if interactive and os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        console = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdout.fileno()))
        mode = wintypes.DWORD()
        if not console.GetConsoleMode(handle, ctypes.byref(mode)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not console.SetConsoleMode(handle, mode.value | 0x0004):
            raise ctypes.WinError(ctypes.get_last_error())
    try:
        if interactive:
            sys.stdout.write("\x1b[2J\x1b[H\x1b[?25l")
        yield interactive
    finally:
        if interactive:
            try:
                sys.stdout.write("\x1b[?25h\n")
                sys.stdout.flush()
            finally:
                if console is not None:
                    console.SetConsoleMode(handle, mode.value)


def render_frame(grid, generation, alive="■", dead=" "):
    rows = [" ".join(alive if cell else dead for cell in row) for row in grid]
    return f"Generation: {generation} | Alive: {int(grid.sum())}\n" + "\n".join(rows) + "\n"


def run_cli(options, simulation_class):
    columns, lines = shutil.get_terminal_size()
    size = options.grid_size if options.grid_size is not None else max(1, min(24, columns // 2, lines - 3))
    if options.seed is not None:
        np.random.seed(options.seed)
    simulation = simulation_class(size=size, seeding_ratio=options.density,
                                  life_engine=options.life_engine, boundary_mode=options.boundary)
    # Redirected output on Windows also needs to preserve the filled-square glyph.
    sys.stdout.reconfigure(encoding="utf-8")
    generation = 0
    try:
        with terminal_display() as interactive:
            while True:
                started = time.monotonic()
                frame = render_frame(simulation.grid, generation, options.alive, options.dead)
                if interactive:
                    sys.stdout.write("\x1b[H" + frame + "Ctrl+C to stop\x1b[J")
                else:
                    sys.stdout.write(frame + "\n")
                sys.stdout.flush()
                if options.frames and generation + 1 >= options.frames:
                    break
                simulation.step()
                generation += 1
                time.sleep(max(0, 1 / options.fps - (time.monotonic() - started)))
    except KeyboardInterrupt:
        pass
