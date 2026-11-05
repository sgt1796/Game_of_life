"""Compare all Life engines with float64 matrix output every generation.

Run from the repository root. SciPy is optional; --scipy-path can point at an
already extracted cached wheel without installing anything into the runtime.
Fixed-input steps include initialization and all conversions. Optional evolving
workloads retain QuickLife state and record setup separately for every engine.
"""

import argparse
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from life_engines import QuickLifeEngine, step_dense, step_lookup, step_packed, step_quicklife


def numpy_float(grid, boundary):
    padded = np.pad(grid.astype(float), 1, mode="wrap" if boundary == "wrap" else "constant")
    rows, cols = grid.shape
    count = sum(padded[y:y + rows, x:x + cols] for y in range(3) for x in range(3)
                if (y, x) != (1, 1))
    birth = (count == 3) & (grid == 0)
    survival = ((count == 2) | (count == 3)) & (grid == 1)
    return np.where(birth | survival, 1, 0).astype(float)


def scipy_engines():
    try:
        import scipy
        from scipy.signal import convolve2d
        from scipy.ndimage import convolve
    except ImportError:
        return {}, None

    def signal_float(grid, boundary):
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        count = convolve2d(grid, kernel, mode="same", boundary="wrap" if boundary == "wrap" else "fill",
                           fillvalue=0.0)
        birth = (count == 3) & (grid == 0)
        survival = ((count == 2) | (count == 3)) & (grid == 1)
        return np.where(birth | survival, 1, 0).astype(float)

    def signal_bytes(grid, boundary):
        cells = grid.astype(np.uint8)
        count = convolve2d(cells, np.ones((3, 3), dtype=np.uint8), mode="same",
                           boundary="wrap" if boundary == "wrap" else "fill")
        return ((count == 3) | ((count == 4) & (cells == 1))).astype(float)

    def ndimage_bytes(grid, boundary):
        cells = grid.astype(np.uint8)
        count = convolve(cells, np.ones((3, 3), dtype=np.uint8),
                         mode="wrap" if boundary == "wrap" else "constant", cval=0)
        return ((count == 3) | ((count == 4) & (cells == 1))).astype(float)

    return {"scipy_signal_float": signal_float, "scipy_signal_uint8": signal_bytes,
            "scipy_ndimage_uint8": ndimage_bytes}, scipy.__version__


def measure(function, grid, boundary, repeats, target):
    function(grid, boundary)  # Exclude lazy lookup construction and cold imports.
    start = time.perf_counter()
    function(grid, boundary)
    estimate = time.perf_counter() - start
    calls = max(1, min(200, int(target / max(estimate, 1e-9))))
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(calls):
            function(grid, boundary)
        samples.append((time.perf_counter() - start) * 1000 / calls)
    return {"median_ms": statistics.median(samples), "min_ms": min(samples),
            "samples_ms": samples, "calls_per_sample": calls}


def initial_grid(size, pattern, density):
    if pattern == "random":
        return (np.random.default_rng(2).random((size, size)) < density).astype(float)
    grid = np.zeros((size, size), dtype=float)
    center = (size - 3) // 2
    if pattern == "glider":
        grid[center:center + 3, center:center + 3] = [[0, 1, 0], [0, 0, 1], [1, 1, 1]]
    elif pattern == "block":
        grid[center:center + 2, center:center + 2] = 1
    return grid


def measure_evolving(function, grid, boundary, generations, repeats, expected):
    """Use identical evolving inputs and dense-output scope for every engine."""
    samples, setups = [], []
    final_stats = None
    packed_bytes = None
    for _ in range(repeats):
        gc.collect()
        setup_start = time.perf_counter()
        engine = QuickLifeEngine(grid, boundary) if function is step_quicklife else None
        cells = grid.copy() if engine is None else None
        for _ in range(2):
            if engine is None:
                cells = function(cells, boundary)
            else:
                engine.step()
                cells = engine.to_numpy()
        setups.append((time.perf_counter() - setup_start) * 1000)
        start = time.perf_counter()
        for _ in range(generations):
            if engine is None:
                cells = function(cells, boundary)
            else:
                engine.step()
                cells = engine.to_numpy()
        samples.append((time.perf_counter() - start) * 1000 / generations)
        np.testing.assert_array_equal(cells, expected)
        if engine is not None:
            final_stats = dict(engine.last_stats)
            packed_bytes = engine.packed_state_bytes
    return {"median_ms": statistics.median(samples), "min_ms": min(samples),
            "samples_ms": samples, "calls_per_sample": generations,
            "setup_and_two_generations_ms": statistics.median(setups),
            "last_update": final_stats, "packed_state_bytes": packed_bytes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[64, 150, 512, 1024, 2048, 4096])
    parser.add_argument("--boundaries", nargs="+", default=["wrap", "open"], choices=["wrap", "open"])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--target-seconds", type=float, default=0.08)
    parser.add_argument("--density", type=float, default=0.2)
    parser.add_argument("--evolving-sizes", type=int, nargs="+", default=[],
                        help="Also compare all engines on evolving boards at these sizes.")
    parser.add_argument("--patterns", nargs="+", choices=["random", "glider", "block"],
                        default=["random", "glider", "block"])
    parser.add_argument("--generations", type=int, default=24,
                        help="Timed generations per evolving sample, after two warmup steps.")
    parser.add_argument("--scipy-path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results.json"))
    parser.add_argument("--resume", action="store_true", help="Keep completed rows from a compatible interrupted run.")
    args = parser.parse_args()
    if any(n < 1 for n in args.sizes) or args.repeats < 1 or args.target_seconds <= 0:
        parser.error("Sizes, repeats, and target-seconds must be positive.")
    if not 0 <= args.density <= 1:
        parser.error("Density must be between 0 and 1.")
    if any(n < 3 for n in args.evolving_sizes) or args.generations < 1:
        parser.error("Evolving sizes must be >= 3 and generations must be positive.")
    if args.scipy_path:
        sys.path.insert(0, str(args.scipy_path))
    methods, scipy_version = scipy_engines()
    methods = {"numpy_float": numpy_float, **methods, "numpy_uint8_separable": step_dense,
               "lookup_4x4": step_lookup, "packed_uint64": step_packed,
               "quicklife": step_quicklife}
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "processor": platform.processor(), "numpy": np.__version__, "scipy": scipy_version,
              "measured_at_utc": datetime.now(timezone.utc).isoformat(),
              "density": args.density, "dtype": "float64", "repeats": args.repeats,
              "target_seconds": args.target_seconds, "seed": 2,
              "fixed_sizes": args.sizes, "boundaries": args.boundaries,
              "evolving_sizes": args.evolving_sizes, "patterns": args.patterns,
              "scope": {
                  "fixed": "one CPU generation from the same input; includes engine initialization, packing, unpacking, allocation and float64 output",
                  "evolving": "successive CPU generations with float64 output each step; QuickLife retains packed state; setup and two warmup generations recorded separately",
                  "excluded": "one-time lookup construction, GUI drawing, trails and diffusion/GPU inference"},
              "evolving_generations_per_sample": args.generations,
              "evolving_warmup_generations": 2,
              "results": []}
    if args.resume and args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        for key in ("python", "platform", "processor", "numpy", "scipy", "density", "dtype",
                    "repeats", "target_seconds", "seed", "scope",
                    "fixed_sizes", "boundaries", "evolving_sizes", "patterns",
                    "evolving_generations_per_sample", "evolving_warmup_generations"):
            if previous.get(key) != report[key]:
                parser.error(f"Cannot resume: {key} differs from the saved run.")
        report = previous
    completed = {(row["size"], row["boundary"], row["workload"], row["pattern"], row["engine"])
                 for row in report["results"]}
    rng = np.random.default_rng(2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for n in args.sizes:
        grid = (rng.random((n, n)) < args.density).astype(float)
        for boundary in args.boundaries:
            expected = numpy_float(grid, boundary)
            for name, function in methods.items():
                if (n, boundary, "fixed", "random", name) in completed:
                    continue
                actual = function(grid, boundary)
                np.testing.assert_array_equal(actual, expected)
                del actual
                gc.collect()
                timing = measure(function, grid, boundary, args.repeats, args.target_seconds)
                row = {"size": n, "boundary": boundary, "workload": "fixed",
                       "pattern": "random", "engine": name, **timing}
                report["results"].append(row)
                print(f"{n:5} {boundary:4} {name:24} {timing['median_ms']:10.3f} ms", flush=True)
                args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            del expected
        del grid
    for n in args.evolving_sizes:
        for pattern in args.patterns:
            grid = initial_grid(n, pattern, args.density)
            for boundary in args.boundaries:
                expected = grid.copy()
                for _ in range(args.generations + 2):
                    expected = step_dense(expected, boundary)
                for name, function in methods.items():
                    if (n, boundary, "evolving", pattern, name) in completed:
                        continue
                    timing = measure_evolving(function, grid, boundary, args.generations,
                                              args.repeats, expected)
                    row = {"size": n, "boundary": boundary, "workload": "evolving",
                           "pattern": pattern, "engine": name, **timing}
                    report["results"].append(row)
                    print(f"{n:5} {boundary:4} {pattern:6} {name:24} {timing['median_ms']:10.3f} ms", flush=True)
                    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
