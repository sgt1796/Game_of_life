"""Plot saved Life timings and starting patterns without rerunning benchmarks."""

import argparse
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
PATTERNS = ("random", "glider", "block")
METHODS = {
    "numpy_float": ("NumPy shifted sums (float64)", "#77818f", "o", "--"),
    "scipy_signal_float": ("SciPy signal convolution (float64)", "#d86c36", "s", "-"),
    "scipy_signal_uint8": ("SciPy signal convolution (uint8)", "#aa8b20", "v", "--"),
    "scipy_ndimage_uint8": ("SciPy ndimage convolution (uint8)", "#8254b7", "^", "-"),
    "numpy_uint8_separable": ("NumPy separable sums (uint8)", "#287db4", "D", "-"),
    "lookup_4x4": ("Block lookup (4×4 → 2×2)", "#ba638b", "P", "-"),
    "packed_uint64": ("Bit-parallel Life (uint64)", "#09856d", "X", "-"),
    "quicklife": ("QuickLife-inspired tiled lookup", "#da394e", "*", "-"),
}


def load_measurements(args, pattern, parser):
    measurements = {}
    metadata = {key: set() for key in ("samples", "densities", "generations", "seeds")}
    for path in args.results:
        report = json.loads(path.read_text(encoding="utf-8"))
        for row in report["results"]:
            if (row["boundary"] != args.boundary or row["engine"] not in METHODS
                    or row.get("workload", "fixed") != args.workload
                    or row.get("pattern", "random") != pattern):
                continue
            measurements[row["engine"], row["size"]] = row["median_ms"]
            metadata["samples"].add(report["repeats"])
            metadata["densities"].add(report["density"])
            metadata["seeds"].add(report.get("seed", 2))
            if args.workload == "evolving":
                metadata["generations"].add(report["evolving_generations_per_sample"])
    methods = {method: style for method, style in METHODS.items()
               if any(engine == method for engine, size in measurements)}
    if not methods:
        parser.error(f"No {args.workload} measurements for {pattern} with {args.boundary} boundaries.")
    sizes = sorted(set.intersection(*[
        {size for engine, size in measurements if engine == method} for method in methods
    ]))
    if not sizes:
        parser.error(f"No matching sizes for all available methods on {pattern}.")
    if len(metadata["densities"]) != 1 or len(metadata["seeds"]) != 1:
        parser.error("Use results with the same starting density and random seed for an accurate preview.")
    return measurements, methods, sizes, metadata


def comparison_limits(args):
    """Keep time and speedup scales identical across patterns in one workload."""
    groups = {}
    for path in args.results:
        report = json.loads(path.read_text(encoding="utf-8"))
        for row in report["results"]:
            if (row["boundary"] == args.boundary and row["engine"] in METHODS
                    and row.get("workload", "fixed") == args.workload):
                key = row.get("pattern", "random"), row["size"]
                groups.setdefault(key, {})[row["engine"]] = row["median_ms"]
    times = [value for group in groups.values() for value in group.values()]
    speedups = []
    for group in groups.values():
        baseline = group.get("scipy_signal_float", group.get("numpy_float"))
        if baseline is not None:
            speedups.extend(baseline / value for value in group.values())
    return (min(times) * .75, max(times) * 1.3), (0, max(speedups, default=1) * 1.25)


def pattern_preview(axis, pattern, size, metadata):
    """Draw the actual benchmark seed; crop sparse boards around their pattern."""
    import numpy as np
    from matplotlib.colors import ListedColormap
    from benchmarks.benchmark_life import initial_grid

    density = next(iter(metadata["densities"]))
    seed = next(iter(metadata["seeds"]))
    if pattern == "random":
        grid = (np.random.default_rng(seed).random((size, size)) < density).astype(float)
        caption = f"Initial {size} × {size} board"
    else:
        grid = initial_grid(size, pattern, density)
        # The canonical benchmark seeds are centered at this position.
        center = (size - 3) // 2
        start, stop = max(0, center - 4), min(size, center + 7)
        grid = grid[start:stop, start:stop]
        caption = f"Initial {grid.shape[0]} × {grid.shape[1]} detail"
    axis.imshow(grid, cmap=ListedColormap(["#edf1f5", "#09856d"]),
                vmin=0, vmax=1, interpolation="nearest")
    axis.set_xticks([])
    axis.set_yticks([])
    if pattern != "random":
        axis.set_xticks(np.arange(-.5, grid.shape[1], 1), minor=True)
        axis.set_yticks(np.arange(-.5, grid.shape[0], 1), minor=True)
        axis.grid(which="minor", color="white", linewidth=.6)
        axis.tick_params(which="minor", length=0)
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color("#d0d5dd")
    return caption


def line_options(method, style):
    label, color, marker, linestyle = style
    return dict(label=label, color=color, marker=marker, linestyle=linestyle,
                linewidth=2.7 if method in ("packed_uint64", "quicklife") else 1.9,
                markersize=5.5)


def configure_axis(axis, sizes, null_locator):
    axis.set_xscale("log", base=2)
    axis.set_xticks(sizes, [f"{size:,}" for size in sizes])
    axis.xaxis.set_minor_locator(null_locator())
    axis.grid(axis="y", which="major", color="#e4e7ec", linewidth=.8)
    axis.grid(axis="x", which="major", color="#f0f2f5", linewidth=.7)
    axis.set_axisbelow(True)
    axis.tick_params(length=0, pad=8)


def save_figure(fig, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".png", ".svg"):
        path = output.with_suffix(suffix)
        fig.savefig(path, dpi=200, facecolor="white")
        print(path)


def plot_patterns(args, parser, plt, formatter, null_locator):
    """Show milliseconds per generation on shared axes for all three patterns."""
    datasets = {pattern: load_measurements(args, pattern, parser) for pattern in PATTERNS}
    first_methods = datasets["random"][1]
    if any(set(data[1]) != set(first_methods) for data in datasets.values()):
        parser.error("The three patterns must contain the same methods.")
    sizes = sorted(set.intersection(*(set(data[2]) for data in datasets.values())))
    if not sizes:
        parser.error("The three patterns have no complete grid sizes in common.")
    metadata = datasets["random"][3]
    if any(data[3] != metadata for data in datasets.values()):
        parser.error("Use matching sample counts, generations, density and seed for all patterns.")

    fig = plt.figure(figsize=(18, 9))
    fig.patch.set_facecolor("white")
    layout = fig.add_gridspec(2, 3, left=.065, right=.98, top=.77, bottom=.18,
                             height_ratios=[1, 3.9], hspace=.22, wspace=.10)
    fig.suptitle("Game of Life: update time by starting pattern", x=.065, y=.97,
                 ha="left", fontsize=24, fontweight="bold")
    fig.text(.065, .921,
             f"Evolving boards  |  {args.boundary.capitalize()} boundaries  |  Lower time is better",
             fontsize=12, color="#667085")
    density = next(iter(metadata["densities"]))
    descriptions = {
        "random": ("Random", f"Initially {density:.0%} live cells"),
        "glider": ("Glider", "5 live cells · moving pattern"),
        "block": ("Block", "4 live cells · stable pattern"),
    }
    axes = []
    for column, pattern in enumerate(PATTERNS):
        measurements, methods, _, pattern_metadata = datasets[pattern]
        header = fig.add_subplot(layout[0, column])
        header.set_axis_off()
        title, description = descriptions[pattern]
        header.text(0, .78, title, fontsize=17, fontweight="bold", va="center")
        header.text(0, .44, description, fontsize=10, color="#667085", va="center")
        preview = header.inset_axes([.72, .05, .26, .93])
        caption = pattern_preview(preview, pattern, sizes[0], pattern_metadata)
        header.text(0, .12, caption, fontsize=9, color="#667085", va="center")

        axis = fig.add_subplot(layout[1, column], sharey=axes[0] if axes else None)
        axes.append(axis)
        for method, style in methods.items():
            times = [measurements[method, size] for size in sizes]
            axis.plot(sizes, times, **line_options(method, style))
        axis.set_yscale("log")
        axis.yaxis.set_major_formatter(formatter(lambda value, position: f"{value:g}"))
        configure_axis(axis, sizes, null_locator)
        if column:
            axis.tick_params(labelleft=False)
    axes[0].set_ylabel("Milliseconds / generation (log scale)", labelpad=12)
    time_limits, _ = comparison_limits(args)
    axes[0].set_ylim(time_limits)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(.06, .887),
               ncol=4, frameon=False, fontsize=10, columnspacing=2.0, labelspacing=.9)
    fig.text(.52, .105, "Grid side length N (each board contains N × N cells; log scale)",
             ha="center", fontsize=12)
    generations = "/".join(str(n) for n in sorted(metadata["generations"]))
    samples = "/".join(str(n) for n in sorted(metadata["samples"]))
    fig.text(.065, .056,
             f"Float64 output every generation · {samples} samples · {generations} timed generations per sample · Setup and two warmup generations excluded",
             fontsize=10, color="#667085")
    fig.text(.065, .029,
             "Previews show the benchmark's initial seeds; sparse patterns are enlarged. Timings exclude GUI drawing, trails and diffusion inference.",
             fontsize=10, color="#667085")
    save_figure(fig, args.output)
    plt.close(fig)


def plot_single(args, parser, plt, formatter, null_locator):
    measurements, methods, sizes, metadata = load_measurements(args, args.pattern, parser)
    baseline_method = "scipy_signal_float" if "scipy_signal_float" in methods else "numpy_float"
    if baseline_method not in methods:
        parser.error("A SciPy signal convolution or NumPy shifted-sum baseline is required.")
    baseline_label = ("SciPy signal (float64)" if baseline_method == "scipy_signal_float"
                      else "NumPy shifted sums (float64)")
    fig, (time_ax, speed_ax) = plt.subplots(
        2, 1, figsize=(12, 9), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(left=.095, right=.97, bottom=.15, top=.84, hspace=.24)
    fig.suptitle("Game of Life: update performance", x=.095, y=.97,
                 ha="left", fontsize=21, fontweight="bold")
    fig.text(.095, .925,
             f"{args.workload.capitalize()} input / {args.pattern} pattern  |  {args.boundary.capitalize()} boundaries",
             fontsize=11, color="#667085")
    fig.text(.095, .895, "Float64 output every generation", fontsize=10, color="#667085")
    preview = fig.add_axes([.855, .884, .10, .10])
    caption = pattern_preview(preview, args.pattern, sizes[0], metadata)
    fig.text(.905, .86, caption, ha="center", fontsize=8, color="#667085")

    baseline = [measurements[baseline_method, size] for size in sizes]
    for method, style in methods.items():
        times = [measurements[method, size] for size in sizes]
        options = line_options(method, style)
        time_ax.plot(sizes, times, **options)
        speed_ax.plot(sizes, [original / current for original, current in zip(baseline, times)], **options)
    time_ax.set_yscale("log")
    time_limits, speedup_limits = comparison_limits(args)
    time_ax.set_ylim(time_limits)
    time_ax.set_ylabel("Milliseconds / generation (log scale)", labelpad=12)
    time_ax.yaxis.set_major_formatter(formatter(lambda value, position: f"{value:g}"))
    time_ax.legend(loc="upper left", frameon=False, fontsize=9, labelspacing=.65)
    speed_ax.set_ylabel(f"Speedup vs. {baseline_label}", labelpad=12)
    speed_ax.set_xlabel("Grid side length N (each board contains N × N cells; log scale)", labelpad=12)
    speed_ax.axhline(1, color="#98a2b3", linewidth=1, linestyle=":", zorder=0)
    speed_ax.set_ylim(speedup_limits)
    speed_ax.yaxis.set_major_formatter(formatter(lambda value, position: f"{value:g}×"))
    for axis in (time_ax, speed_ax):
        configure_axis(axis, sizes, null_locator)
    largest = sizes[-1]
    annotations = [(baseline[-1] / measurements[method, largest], method, label)
                   for method, label in (("packed_uint64", "Bit-parallel"),
                                         ("quicklife", "QuickLife-inspired")) if method in methods]
    for index, (speedup, method, label) in enumerate(sorted(annotations)):
        speed_ax.annotate(f"{label}: {speedup:.1f}×", xy=(largest, speedup),
                          xytext=(-12, -18 if index == 0 else 15), textcoords="offset points",
                          ha="right", color=methods[method][1], fontweight="bold", fontsize=9)
    density = next(iter(metadata["densities"]))
    scope = ("Includes initialization, packing, unpacking and allocation" if args.workload == "fixed"
             else "Includes dense export; setup and two warmup generations excluded")
    fig.text(.095, .065,
             f"Initially {density:.0%} live cells · {scope}" if args.pattern == "random"
             else f"{args.pattern.capitalize()} pattern · {scope}", color="#667085", fontsize=9)
    samples = "/".join(str(count) for count in sorted(metadata["samples"]))
    generations = "/".join(str(n) for n in sorted(metadata["generations"]))
    batch = f" · {generations} generations per sample" if args.workload == "evolving" else ""
    fig.text(.095, .041,
             f"Excludes lookup construction, GUI drawing and diffusion inference. {samples} samples per method{batch}.",
             color="#667085", fontsize=9)
    save_figure(fig, args.output)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, nargs="+",
                        default=[HERE / "results.json", HERE / "large-results.json"])
    parser.add_argument("--boundary", choices=["wrap", "open"], default="wrap")
    parser.add_argument("--workload", choices=["fixed", "evolving"], default="fixed")
    parser.add_argument("--pattern", choices=[*PATTERNS, "all"], default="random",
                        help="Use all with --workload evolving for a three-pattern timing comparison.")
    parser.add_argument("--output", type=Path,
                        help="Output stem; defaults to a name for the workload and pattern.")
    parser.add_argument("--package-path", "--matplotlib-path", type=Path, nargs="+", default=[],
                        help="Optional directories containing existing plotting packages.")
    args = parser.parse_args()
    if args.pattern == "all" and args.workload != "evolving":
        parser.error("The all-pattern comparison requires --workload evolving.")
    if args.output is None:
        if args.pattern == "all":
            stem = "results"
        elif args.workload == "evolving":
            stem = f"result_{args.pattern}"
        else:
            stem = "methods-vs-size"
        args.output = HERE / stem
    sys.path.insert(0, str(HERE.parent))
    sys.path[:0] = [str(path) for path in args.package_path]
    os.environ.setdefault("MPLCONFIGDIR", str(HERE.parent / "renders" / "matplotlib"))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, NullLocator

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.labelcolor": "#344054", "text.color": "#182230",
        "xtick.color": "#475467", "ytick.color": "#475467",
        "axes.edgecolor": "#d0d5dd", "svg.fonttype": "none",
    })
    if args.pattern == "all":
        plot_patterns(args, parser, plt, FuncFormatter, NullLocator)
    else:
        plot_single(args, parser, plt, FuncFormatter, NullLocator)


if __name__ == "__main__":
    main()
