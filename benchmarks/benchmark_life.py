"""Compare complete matrix-in/matrix-out Life steps, including conversions.

Run from the repository root. SciPy is optional; --scipy-path can point at an
already extracted cached wheel without installing anything into the runtime.
"""

import argparse
import gc
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from life_engines import step_dense, step_lookup, step_packed


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[64, 150, 512, 1024, 2048, 4096])
    parser.add_argument("--boundaries", nargs="+", default=["wrap", "open"], choices=["wrap", "open"])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--target-seconds", type=float, default=0.08)
    parser.add_argument("--density", type=float, default=0.2)
    parser.add_argument("--scipy-path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results.json"))
    args = parser.parse_args()
    if any(n < 1 for n in args.sizes) or args.repeats < 1 or args.target_seconds <= 0:
        parser.error("Sizes, repeats, and target-seconds must be positive.")
    if not 0 <= args.density <= 1:
        parser.error("Density must be between 0 and 1.")
    if args.scipy_path:
        sys.path.insert(0, str(args.scipy_path))
    methods, scipy_version = scipy_engines()
    methods = {"numpy_float": numpy_float, **methods, "numpy_uint8_separable": step_dense,
               "lookup_4x4": step_lookup, "packed_uint64": step_packed}
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "processor": platform.processor(), "numpy": np.__version__, "scipy": scipy_version,
              "density": args.density, "dtype": "float64", "repeats": args.repeats,
              "scope": "one CPU generation; includes all packing, unpacking, allocation and float64 output; excludes GUI/GPU",
              "results": []}
    rng = np.random.default_rng(2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for n in args.sizes:
        grid = (rng.random((n, n)) < args.density).astype(float)
        for boundary in args.boundaries:
            expected = numpy_float(grid, boundary)
            for name, function in methods.items():
                actual = function(grid, boundary)
                np.testing.assert_array_equal(actual, expected)
                del actual
                gc.collect()
                timing = measure(function, grid, boundary, args.repeats, args.target_seconds)
                row = {"size": n, "boundary": boundary, "engine": name, **timing}
                report["results"].append(row)
                print(f"{n:5} {boundary:4} {name:24} {timing['median_ms']:10.3f} ms", flush=True)
                args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            del expected
        del grid
    print(f"Saved {args.output}", flush=True)


if __name__ == "__main__":
    main()
