"""Transport-independent commands shared by native HTTP and browser Python."""

import json
import math

import numpy as np

from Game_of_Life import GameOfLife, UnboundedGameOfLife


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    return value


def coordinates(value, painting=False):
    if not isinstance(value, list) or len(value) > 100_000:
        raise ValueError("Provide a list of at most 100,000 cells.")
    result = []
    for cell in value:
        if not isinstance(cell, list) or len(cell) != (3 if painting else 2):
            raise ValueError("Each cell needs x, y coordinates" + (" and an alive flag." if painting else "."))
        x = integer(cell[0], "x", -1_000_000, 1_000_000)
        y = integer(cell[1], "y", -1_000_000, 1_000_000)
        if painting:
            if type(cell[2]) is not bool:
                raise ValueError("The alive flag must be true or false.")
            result.append((x, y, cell[2]))
        else:
            result.append((x, y))
    return result


class LifeSession:
    """One persistent simulation; never imports desktop or server dependencies."""

    def __init__(self, mode="unbounded", engine="auto"):
        if mode not in ("bounded", "unbounded"):
            raise ValueError("Mode must be bounded or unbounded.")
        self.mode = mode
        self.simulation = (UnboundedGameOfLife(life_engine=engine) if mode == "unbounded"
                           else GameOfLife(size=140, seeding_ratio=0, life_engine=engine))
        self.generation = 0

    def snapshot(self):
        sim = self.simulation
        if self.mode == "unbounded":
            cells = sim.living_cells()
        else:
            y, x = np.nonzero(sim.grid)
            cells = np.column_stack((x, y)).tolist()
        generation = sim.generation if self.mode == "unbounded" else self.generation
        return {"cells": cells, "generation": generation,
                "population": len(cells), "engine": sim.life_engine,
                "shape": list(sim.grid.shape)}

    def command(self, action, data):
        if not isinstance(data, dict):
            raise ValueError("The request must be a JSON object.")
        sim = self.simulation
        if action == "reset":
            warmup = integer(data.get("warmup", 0), "warmup", 0, 12)
            if self.mode == "unbounded":
                sim.load_cells(coordinates(data.get("cells")))
            else:
                size = integer(data.get("size", sim.size), "size", 3, 1024)
                density = data.get("density", sim.seeding_ratio)
                if (type(density) not in (int, float) or not math.isfinite(density)
                        or not 0 <= density <= 1):
                    raise ValueError("Density must be between zero and one.")
                cells = coordinates(data["cells"]) if "cells" in data else None
                if cells is not None and any(not (0 <= x < size and 0 <= y < size) for x, y in cells):
                    raise ValueError("Cell coordinates are outside the board.")
                sim.size = size
                sim.reset(density if cells is None else 0)
                if cells is not None:
                    for x, y in cells:
                        sim.set_cell(x, y)
            for _ in range(warmup):
                sim.step()
            self.generation = 0
            if self.mode == "unbounded":
                sim.generation = 0
        elif action == "step":
            steps = integer(data.get("steps", 1), "steps", 1, 3)
            for _ in range(steps):
                sim.step()
            self.generation += steps
        elif action == "paint":
            changes = coordinates(data.get("cells"), painting=True)
            if self.mode == "unbounded":
                sim.paint_cells(changes)
            else:
                if any(not (0 <= x < sim.size and 0 <= y < sim.size) for x, y, _ in changes):
                    raise ValueError("Cell coordinates are outside the board.")
                for x, y, alive in changes:
                    sim.set_cell(x, y, alive)
        elif action == "engine":
            sim.set_life_engine(data.get("engine"))
        elif action != "state":
            raise ValueError("Unknown simulation command.")
        return self.snapshot()

    def command_json(self, action, data):
        """Use strings at the JS boundary so no Python proxies escape a call."""
        return json.dumps(self.command(action, json.loads(data)), separators=(",", ":"))
