"""Direct NumPy-matrix to StreamDiffusion rendering for Game_of_Life.py.

The model receives an RGB conditioning image, never a screen capture. Only the
Life update function changes the numerical grid; generated pixels are display
output. Heavy model imports happen in the rendering worker, outside the UI.
"""

import argparse
from pathlib import Path
from queue import Empty, Full, Queue
import os
import sys
import threading
import time

import numpy as np


STYLES = {
    "Bioluminescent": {
        "background": (5, 12, 23), "live": (91, 246, 207), "trail": (90, 65, 160),
        "prompt": (
            "bioluminescent microbial colonies viewed through a microscope, "
            "luminous turquoise cell membranes, violet filaments, deep navy water, "
            "organic branching networks, intricate translucent textures, macro photography"
        ),
    },
    "Botanical": {
        "background": (12, 23, 22), "live": (189, 225, 131), "trail": (55, 126, 106),
        "prompt": (
            "delicate moss islands and tiny fern gardens, emerald and pale gold, "
            "branching botanical networks, dew drops, dark forest floor, "
            "intricate organic miniature landscape, macro photography"
        ),
    },
    "Cosmic": {
        "background": (9, 7, 26), "live": (247, 185, 114), "trail": (118, 67, 181),
        "prompt": (
            "luminous cosmic filaments and clustered stars, amber plasma, violet nebulae, "
            "deep indigo space, intricate branching constellations, ethereal astronomical art"
        ),
    },
}
NEGATIVE_PROMPT = "text, letters, watermark, people, faces, blurry, low quality"


def build_parser():
    parser = argparse.ArgumentParser(description="Conway's Life with optional live diffusion rendering.")
    parser.add_argument("--streamdiffusion", action="store_true", help="Render the matrix with StreamDiffusion.")
    parser.add_argument("--stream-root", type=Path,
                        default=Path(__file__).resolve().parent.parent / "StreamDiffusion")
    parser.add_argument("--model", default="KBlueLeaf/kohaku-v2.1")
    parser.add_argument("--style", choices=list(STYLES), default="Bioluminescent")
    parser.add_argument("--prompt", help="Override the selected style's prompt.")
    parser.add_argument("--grid-size", type=int, default=64, help="Cells per side in diffusion mode.")
    parser.add_argument("--size", type=int, default=512, help="Output pixels per side; a multiple of 64.")
    parser.add_argument("--fps", type=float, default=8, help="Life generations per second, independent of GPU speed.")
    parser.add_argument("--density", type=float, default=0.20)
    parser.add_argument("--fade", type=float, default=0.12, help="Trail opacity lost per generation.")
    parser.add_argument("--boundary", choices=["wrap", "open", "fill"], default="wrap")
    parser.add_argument("--life-engine", choices=["auto", "dense", "packed", "lookup", "quicklife"], default="auto",
                        help="Life engine; quicklife combines persistent packed slices, lookup and dirty tiles.")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--acceleration", choices=["none", "xformers", "tensorrt"], default="none")
    parser.add_argument("--t-indices", type=int, nargs="+", default=[28, 40],
                        help="Ascending indices in a 50-step schedule; higher indices retain more input detail.")
    parser.add_argument("--allow-download", action="store_true", help="Allow uncached model downloads.")
    parser.add_argument("--render-frames", type=int, default=0, help="Save this many frames without opening a UI.")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "renders" / "life")
    return parser


def validate_options(args):
    if args.grid_size < 3 or args.size < 64 or args.size % 64:
        raise ValueError("Use --grid-size >= 3 and a --size that is a positive multiple of 64.")
    if not np.isfinite(args.fps) or not 0 < args.fps <= 60:
        raise ValueError("--fps must be between 0 (exclusive) and 60.")
    if not 0 <= args.density <= 1 or not 0 <= args.fade <= 1:
        raise ValueError("--density and --fade must be between 0 and 1.")
    if args.render_frames < 0 or args.seed < 0:
        raise ValueError("--render-frames and --seed must be nonnegative.")
    if not args.t_indices or args.t_indices != sorted(set(args.t_indices)):
        raise ValueError("--t-indices must be unique and ascending.")
    if not all(0 <= i < 50 for i in args.t_indices):
        raise ValueError("Each --t-indices value must be between 0 and 49.")


class LifeState:
    def __init__(self, args, step):
        self.args = args
        self.step = step
        self.rng = np.random.default_rng(args.seed)
        self.engine = None
        self.reset()

    def reset(self, clear=False):
        n = self.args.grid_size
        self.grid = np.zeros((n, n), dtype=float)
        if not clear:
            indices = self.rng.choice(n * n, int(n * n * self.args.density), replace=False)
            self.grid.flat[indices] = 1
        self.trails = self.grid.copy()
        self.generation = 0
        if self.args.life_engine == "quicklife":
            from life_engines import QuickLifeEngine
            if self.engine is None:
                self.engine = QuickLifeEngine(self.grid, self.args.boundary)
            else:
                self.engine.set_boundary(self.args.boundary)
                self.engine.load(self.grid)

    def advance(self):
        if self.engine is None:
            self.grid = self.step(self.grid, self.args.boundary)
        else:
            self.engine.set_boundary(self.args.boundary)
            self.engine.step()
            self.grid = self.engine.to_numpy()
        self.trails = np.where(self.grid == 1, 1, np.maximum(0, self.trails - self.args.fade))
        self.generation += 1

    def paint(self, x, y, alive=True):
        if 0 <= y < self.grid.shape[0] and 0 <= x < self.grid.shape[1]:
            self.grid[y, x] = int(alive)
            self.trails[y, x] = int(alive)
            if self.engine is not None:
                self.engine.set_cell(x, y, alive)


def matrix_to_image(grid, trails, style="Bioluminescent", size=512):
    """Map numeric state and decaying history into deterministic RGB + soft bloom."""
    from PIL import Image, ImageChops, ImageFilter

    palette = STYLES[style]
    background = np.asarray(palette["background"], dtype=float)
    foreground = np.where((grid == 1)[..., None], palette["live"], palette["trail"])
    opacity = np.where(grid == 1, 1, np.clip(trails, 0, 1))[..., None]
    pixels = background + (foreground - background) * opacity
    image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    image = image.resize((size, size), Image.Resampling.NEAREST)
    glow = image.filter(ImageFilter.GaussianBlur(max(1, size / 180)))
    glow = Image.blend(Image.new("RGB", image.size), glow, 0.35)
    return ImageChops.screen(image, glow)


class StreamRenderer:
    def __init__(self, args):
        root = args.stream_root.resolve()
        if not (root / "utils" / "wrapper.py").is_file():
            raise RuntimeError(f"StreamDiffusion not found at {root}. Set --stream-root.")
        if not args.allow_download:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        sys.path.insert(0, str(root / "src"))
        sys.path.insert(0, str(root))

        import torch
        from huggingface_hub import snapshot_download
        from utils.wrapper import StreamDiffusionWrapper

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. Run with StreamDiffusion's .venv Python and a CUDA-enabled torch.")
        self.args = args
        self.prompt = None
        self.revision = None
        # This version's LoRA loader consults Hub metadata even when its weights
        # are cached. Supply local snapshots so offline mode really stays offline.
        local_assets = {}
        if not args.allow_download:
            local_assets["vae_id"] = snapshot_download("madebyollin/taesd", local_files_only=True)
            if "turbo" not in args.model:
                local_assets["lcm_lora_id"] = snapshot_download(
                    "latent-consistency/lcm-lora-sdv1-5", local_files_only=True)
        self.stream = StreamDiffusionWrapper(
            model_id_or_path=args.model, t_index_list=args.t_indices,
            mode="img2img", output_type="pil", width=args.size, height=args.size,
            frame_buffer_size=1, acceleration=args.acceleration,
            do_add_noise=False, enable_similar_image_filter=False,
            use_denoising_batch=True, cfg_type="self", seed=args.seed,
            engine_dir=str(Path(__file__).resolve().parent / "renders" / "engines"),
            **local_assets,
        )

    def render(self, image, prompt, revision=0, settle=False):
        changed = prompt != self.prompt or revision != self.revision
        if changed:
            # Call the underlying prepare to preserve the requested seed, too.
            self.stream.stream.prepare(
                prompt, NEGATIVE_PROMPT, num_inference_steps=50,
                guidance_scale=1.4, delta=0.5, seed=self.args.seed,
            )
            self.prompt, self.revision = prompt, revision
        # Prime the denoising stages after resets; headless saves settle on this
        # particular input. Live calls otherwise retain StreamDiffusion's pipeline.
        passes = len(self.args.t_indices) if changed or settle else 1
        for _ in range(passes):
            result = self.stream(image)
        return result


def put_latest(queue, value):
    """Bound latency: replace a pending frame instead of accumulating a backlog."""
    try:
        queue.put_nowait(value)
    except Full:
        try:
            queue.get_nowait()
        except Empty:
            pass
        queue.put_nowait(value)


class RenderWorker:
    def __init__(self, args, factory=StreamRenderer):
        self.requests = Queue(maxsize=1)
        self.results = Queue(maxsize=1)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(args, factory), daemon=True)

    def start(self):
        self.thread.start()

    def _run(self, args, factory):
        try:
            renderer = factory(args)
            while not self.stopped.is_set():
                try:
                    image, prompt, revision = self.requests.get(timeout=0.1)
                except Empty:
                    continue
                start = time.perf_counter()
                result = renderer.render(image, prompt, revision)
                put_latest(self.results, ("image", result, revision, time.perf_counter() - start))
        except (Exception, SystemExit) as exc:
            message = f"{type(exc).__name__}: {exc}"
            put_latest(self.results, ("error", message, None, None))


def run_headless(args, state):
    from PIL import Image

    args.output_dir.mkdir(parents=True, exist_ok=True)
    renderer = StreamRenderer(args)
    prompt = args.prompt or STYLES[args.style]["prompt"]
    for index in range(args.render_frames):
        source = matrix_to_image(state.grid, state.trails, args.style, args.size)
        start = time.perf_counter()
        result = renderer.render(source, prompt, settle=True)
        source.save(args.output_dir / f"{index:04d}-input.png")
        result.save(args.output_dir / f"{index:04d}-render.png")
        pair = Image.new("RGB", (args.size * 2, args.size))
        pair.paste(source, (0, 0))
        pair.paste(result, (args.size, 0))
        pair.save(args.output_dir / f"{index:04d}-comparison.png")
        print(f"Generation {state.generation}: {time.perf_counter() - start:.2f}s -> {args.output_dir}", flush=True)
        state.advance()


def configure_tk_libraries():
    # Relocatable Windows Python builds can fail to locate their bundled Tcl/Tk
    # scripts through an absolute path. Relative library paths work for these
    # builds as well as standard installs, without changing the installation.
    if sys.platform == "win32":
        base = Path(sys.base_prefix).resolve() / "tcl"
        for variable, pattern, script in [("TCL_LIBRARY", "tcl[0-9]*", "init.tcl"),
                                          ("TK_LIBRARY", "tk[0-9]*", "tk.tcl")]:
            for library in sorted(base.glob(pattern), reverse=True):
                if (library / script).is_file():
                    try:
                        os.environ.setdefault(variable, os.path.relpath(library))
                    except ValueError:  # The working directory may be on another drive.
                        os.environ.setdefault(variable, str(library))
                    break


def run_ui(args, state):
    configure_tk_libraries()
    import tkinter as tk
    from tkinter import ttk
    from PIL import ImageTk

    root = tk.Tk()
    root.title("Living Canvas | Game of Life + StreamDiffusion")
    root.configure(bg="#090f1c")
    root.resizable(False, False)
    theme = ttk.Style(root)
    theme.theme_use("clam")
    theme.configure("TFrame", background="#090f1c")
    theme.configure("TLabel", background="#090f1c", foreground="#d9e8ee")
    theme.configure("TButton", padding=(10, 7))
    body = ttk.Frame(root, padding=18)
    body.pack()
    ttk.Label(body, text="LIVING CANVAS", font=("Segoe UI", 21, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(body, text="A cellular world, painted by diffusion", font=("Segoe UI", 11)).grid(
        row=0, column=1, sticky="e")
    ttk.Label(body, text="LIFE / MATRIX INPUT", padding=(0, 14, 0, 8)).grid(row=1, column=0, sticky="w")
    ttk.Label(body, text="DIFFUSION / LIVE OUTPUT", padding=(16, 14, 0, 8)).grid(row=1, column=1, sticky="w")
    source_canvas = tk.Canvas(body, width=args.size, height=args.size, highlightthickness=0, bg="#050c17")
    source_canvas.grid(row=2, column=0)
    output_canvas = tk.Canvas(body, width=args.size, height=args.size, highlightthickness=0, bg="#050c17")
    output_canvas.grid(row=2, column=1, padx=(16, 0))
    source_item = source_canvas.create_image(0, 0, anchor="nw")
    output_item = output_canvas.create_image(0, 0, anchor="nw")
    loading_item = output_canvas.create_text(args.size // 2, args.size // 2,
                                            text="Loading the local model...", fill="#9aafc2",
                                            font=("Segoe UI", 13))
    controls = ttk.Frame(body, padding=(0, 14))
    controls.grid(row=3, column=0, columnspan=2, sticky="ew")
    running = tk.BooleanVar(value=True)
    style = tk.StringVar(value=args.style)
    fps = tk.DoubleVar(value=args.fps)
    prompt = tk.StringVar(value=args.prompt or STYLES[args.style]["prompt"])
    applied_prompt = prompt.get()
    boundary = tk.StringVar(value=args.boundary)
    status = tk.StringVar(value="Loading cached model. First rendering takes longer.")
    generation = tk.StringVar()
    revision = 0
    latest_output = None
    worker_failed = False
    worker = RenderWorker(args)

    def refresh():
        image = matrix_to_image(state.grid, state.trails, style.get(), args.size)
        photo = ImageTk.PhotoImage(image)
        source_canvas.itemconfigure(source_item, image=photo)
        source_canvas.photo = photo
        generation.set(f"Generation {state.generation:,}  |  Living {state.grid.mean():.1%}")
        if not worker_failed:
            put_latest(worker.requests, (image, applied_prompt, revision))

    def pause():
        running.set(not running.get())
        pause_button.configure(text="Pause" if running.get() else "Resume")

    def reset(clear=False):
        nonlocal revision
        revision += 1
        state.reset(clear=clear)
        refresh()

    def apply_prompt():
        nonlocal revision, applied_prompt
        applied_prompt = prompt.get()
        revision += 1
        refresh()

    def choose_style(event=None):
        prompt.set(STYLES[style.get()]["prompt"])
        apply_prompt()

    def draw(event, alive=True):
        state.paint(int(event.x * args.grid_size / args.size),
                    int(event.y * args.grid_size / args.size), alive)
        refresh()

    def save():
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()
        source = matrix_to_image(state.grid, state.trails, style.get(), args.size)
        source.save(args.output_dir / f"{stamp}-input.png")
        if latest_output is not None:
            latest_output.save(args.output_dir / f"{stamp}-render.png")
        status.set(f"Saved to {args.output_dir}")

    pause_button = ttk.Button(controls, text="Pause", command=pause)
    pause_button.pack(side="left")
    ttk.Button(controls, text="Reseed", command=reset).pack(side="left", padx=5)
    ttk.Button(controls, text="Clear", command=lambda: reset(True)).pack(side="left")
    ttk.Button(controls, text="Save images", command=save).pack(side="left", padx=5)
    style_box = ttk.Combobox(controls, textvariable=style, values=list(STYLES), state="readonly", width=17)
    style_box.pack(side="left", padx=(18, 5))
    style_box.bind("<<ComboboxSelected>>", choose_style)
    boundary_box = ttk.Combobox(controls, textvariable=boundary, values=["wrap", "open", "fill"],
                                state="readonly", width=6)
    boundary_box.pack(side="left", padx=5)
    ttk.Label(controls, text="Life steps/s").pack(side="left", padx=(10, 0))
    ttk.Scale(controls, from_=1, to=30, variable=fps, length=120).pack(side="left")
    prompt_row = ttk.Frame(body)
    prompt_row.grid(row=4, column=0, columnspan=2, sticky="ew")
    prompt_entry = ttk.Entry(prompt_row, textvariable=prompt, width=100)
    prompt_entry.pack(side="left", fill="x", expand=True)
    prompt_entry.bind("<Return>", lambda event: apply_prompt())
    ttk.Button(prompt_row, text="Apply prompt", command=apply_prompt).pack(side="left", padx=(8, 0))
    ttk.Label(body, textvariable=generation, padding=(0, 12, 0, 0)).grid(row=5, column=0, sticky="w")
    ttk.Label(body, text="Draw on input: left = grow / right = erase", padding=(0, 12, 0, 0)).grid(
        row=5, column=1, sticky="e")
    ttk.Label(body, textvariable=status, wraplength=args.size * 2, padding=(0, 8, 0, 0)).grid(
        row=6, column=0, columnspan=2, sticky="w")
    for sequence in ("<Button-1>", "<B1-Motion>"):
        source_canvas.bind(sequence, draw)
    for sequence in ("<Button-3>", "<B3-Motion>"):
        source_canvas.bind(sequence, lambda event: draw(event, False))

    def poll():
        nonlocal latest_output, worker_failed
        try:
            kind, result, result_revision, seconds = worker.results.get_nowait()
            if kind == "error":
                worker_failed = True
                output_canvas.itemconfigure(loading_item, text="Renderer could not start. See status below.")
                status.set(result + " | Use the StreamDiffusion .venv Python; see README.md for setup.")
            elif result_revision == revision:
                latest_output = result
                photo = ImageTk.PhotoImage(result)
                output_canvas.itemconfigure(output_item, image=photo)
                output_canvas.photo = photo
                output_canvas.itemconfigure(loading_item, text="")
                status.set(f"GPU render {seconds * 1000:.0f} ms | Latest frames only | Output may lag the input slightly")
        except Empty:
            pass
        root.after(30, poll)

    def tick():
        if running.get():
            args.boundary = boundary.get()
            state.advance()
            refresh()
        root.after(max(1, round(1000 / fps.get())), tick)

    def close():
        worker.stopped.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    refresh()
    worker.start()
    root.after(30, poll)
    root.after(round(1000 / args.fps), tick)
    root.mainloop()


def run(args, step):
    try:
        validate_options(args)
        state = LifeState(args, step)
        if args.render_frames:
            run_headless(args, state)
        else:
            run_ui(args, state)
    except (Exception, SystemExit) as exc:
        raise SystemExit(f"StreamDiffusion renderer: {exc}") from exc
