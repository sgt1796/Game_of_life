#!/usr/bin/env python3
"""Belousov-Zhabotinsky reaction cellular automaton visualizer."""

from collections import deque

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib import animation, colors
from matplotlib.widgets import Slider, Button, RadioButtons
from scipy.signal import convolve2d

# 3x3 kernel to average a cell with its eight neighbors.
NEIGHBOR_KERNEL = np.ones((3, 3), dtype=float)


def random_substrates(size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng()
    a = rng.random((size, size))
    b = rng.random((size, size))
    c = rng.random((size, size))
    return a, b, c


def step(
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    alpha: float,
    beta: float,
    gamma: float,
    boundary_mode: str,
    domain_mask: np.ndarray | None,
):
    def avg(field: np.ndarray) -> np.ndarray:
        boundary = "wrap" if boundary_mode == "wrap" else "fill"
        masked_field = field if domain_mask is None else field * domain_mask

        summed = convolve2d(masked_field, NEIGHBOR_KERNEL, mode="same", boundary=boundary, fillvalue=0.0)

        # Open and masked modes normalize by the number of valid neighbors to avoid edge dilution.
        needs_count_norm = boundary_mode == "open" or domain_mask is not None
        if needs_count_norm:
            mask_for_counts = np.ones_like(field) if domain_mask is None else domain_mask
            counts = convolve2d(mask_for_counts, NEIGHBOR_KERNEL, mode="same", boundary=boundary, fillvalue=0.0)
            counts = np.clip(counts, 1.0, None)
            return summed / counts

        return summed / 9.0

    avg_a = avg(a)
    avg_b = avg(b)
    avg_c = avg(c)

    a_next = np.clip(avg_a + avg_a * (alpha * avg_b - gamma * avg_c), 0.0, 1.0)
    b_next = np.clip(avg_b + avg_b * (beta * avg_c - alpha * avg_a), 0.0, 1.0)
    c_next = np.clip(avg_c + avg_c * (gamma * avg_a - beta * avg_b), 0.0, 1.0)
    if domain_mask is not None:
        a_next *= domain_mask
        b_next *= domain_mask
        c_next *= domain_mask
    return a_next, b_next, c_next


def soft_rgb(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    red = 0.25 + 0.75 * a
    green = 0.25 + 0.75 * c
    blue = 0.25 + 0.75 * b
    return np.stack([red, green, blue], axis=-1)


def main():
    size = 300
    alpha_init, beta_init, gamma_init = 1.0, 1.0, 1.0
    a, b, c = random_substrates(size)
    running = True
    history_length = 400
    step_index = 0
    rng = np.random.default_rng()
    disturb_radius = 8
    disturb_strength = 0.55
    mouse_down = False
    boundary_mode = "wrap"
    mask_mode = "full"
    yy, xx = np.ogrid[:size, :size]
    center = (size - 1) / 2.0
    round_radius = size * 0.48
    round_mask = ((xx - center) ** 2 + (yy - center) ** 2) <= round_radius ** 2

    # Color mappers for selectable looks.
    cmap_plasma = cm.get_cmap("plasma")
    cmap_turbo = cm.get_cmap("turbo")
    norm_relief = colors.PowerNorm(gamma=0.7)
    triad_palette = np.array([[29, 210, 168], [255, 120, 104], [250, 207, 90]], dtype=float) / 255.0

    def color_relief(a_sub, b_sub, c_sub):
        field = 0.55 * a_sub + 0.35 * b_sub + 0.10 * c_sub
        grad_y, grad_x = np.gradient(field)
        edge = np.sqrt(grad_x ** 2 + grad_y ** 2)
        height = np.clip(field + 0.45 * edge, 0.0, 1.0)
        return cmap_plasma(norm_relief(height))[..., :3]

    def color_hue(a_sub, b_sub, c_sub):
        total = a_sub + b_sub + c_sub + 1e-6
        hue = (np.arctan2(c_sub - b_sub, a_sub - 0.5 * (b_sub + c_sub)) / (2 * np.pi)) % 1.0
        sat = np.clip(np.std(np.stack([a_sub, b_sub, c_sub], axis=-1), axis=-1) * 1.6, 0.0, 1.0)
        val = np.clip(
            0.65 * total / 3.0 + 0.35 * np.max(np.stack([a_sub, b_sub, c_sub], axis=-1), axis=-1),
            0.0,
            1.0,
        )
        return colors.hsv_to_rgb(np.stack([hue, sat, val], axis=-1))

    def color_turbo(a_sub, b_sub, c_sub):
        level = np.clip(
            0.6 * (a_sub + b_sub + c_sub) / 3.0
            + 0.4 * np.std(np.stack([a_sub, b_sub, c_sub], axis=-1), axis=-1),
            0.0,
            1.0,
        )
        return cmap_turbo(level)[..., :3]

    def color_triad(a_sub, b_sub, c_sub):
        weights = np.stack([a_sub, b_sub, c_sub], axis=-1)
        weights /= weights.sum(axis=-1, keepdims=True) + 1e-6
        return np.einsum("...k,kc->...c", weights, triad_palette)

    color_options = [
        ("Relief (plasma)", color_relief),
        ("Hue wheel", color_hue),
        ("Turbo depth", color_turbo),
        ("Soft RGB", soft_rgb),
        ("Triad blend", color_triad),
    ]
    name_to_index = {name: idx for idx, (name, _) in enumerate(color_options)}
    active_color_index = 0
    boundary_options = [
        ("Wrap (toroidal)", "wrap"),
        ("Open (absorbing)", "open"),
        ("Clamp edges (fill)", "fill"),
    ]
    boundary_name_to_index = {name: idx for idx, (name, _) in enumerate(boundary_options)}
    boundary_mode_to_index = {mode: idx for idx, (_, mode) in enumerate(boundary_options)}
    mask_options = [("Full grid", "full"), ("Round mask", "round")]
    mask_name_to_index = {name: idx for idx, (name, _) in enumerate(mask_options)}

    def current_to_rgb():
        return color_options[active_color_index][1](a, b, c)

    time_values: deque[int] = deque(maxlen=history_length)
    a_levels: deque[float] = deque(maxlen=history_length)
    b_levels: deque[float] = deque(maxlen=history_length)
    c_levels: deque[float] = deque(maxlen=history_length)

    fig, (ax_pattern, ax_levels, ax_options) = plt.subplots(
        1,
        3,
        figsize=(14.5, 6.5),
        gridspec_kw={"width_ratios": [1.2, 1, 0.55]},
    )
    fig.subplots_adjust(bottom=0.2, top=0.9, wspace=0.25)
    fig.patch.set_facecolor("#101820")

    fig.suptitle(
        "Belousov-Zhabotinsky Cellular Automaton",
        fontsize=18,
        color="#89cff0",
        y=0.97,
    )

    ax_pattern.axis("off")
    img = ax_pattern.imshow(current_to_rgb(), interpolation="nearest")

    ax_levels.set_facecolor("#0f1b26")
    ax_levels.set_title("Average substrate levels", color="#d2e7ff", pad=10)
    ax_levels.set_ylim(0.0, 1.0)
    ax_levels.set_xlim(0, history_length)
    ax_levels.grid(alpha=0.2, linestyle="--", linewidth=0.6)
    ax_levels.tick_params(colors="#d2e7ff", labelsize=9)
    for spine in ax_levels.spines.values():
        spine.set_color("#395070")
    ax_levels.set_xlabel("Step", color="#d2e7ff")
    ax_levels.set_ylabel("Normalized concentration", color="#d2e7ff")

    (line_a,) = ax_levels.plot([], [], color="#ff5c5c", label="a (red channel)", linewidth=1.6)
    (line_b,) = ax_levels.plot([], [], color="#4db5ff", label="b (blue channel)", linewidth=1.2)
    (line_c,) = ax_levels.plot([], [], color="#7bd88f", label="c (green channel)", linewidth=1.2)
    legend = ax_levels.legend(loc="upper right", facecolor="#0f1b26", edgecolor="#395070")
    for text in legend.get_texts():
        text.set_color("#d2e7ff")

    ax_options.axis("off")
    ax_options.set_facecolor("#0f1b26")
    # Palette selector sits inside the dedicated options panel.
    ax_palette = ax_options.inset_axes([0.08, 0.55, 0.84, 0.35], facecolor="#0f1b26")
    palette_selector = RadioButtons(
        ax_palette,
        [name for name, _ in color_options],
        active=active_color_index,
    )
    for lbl in palette_selector.labels:
        lbl.set_color("#d2e7ff")
        lbl.set_fontsize(9)

    def on_palette(label: str):
        nonlocal active_color_index
        active_color_index = name_to_index[label]
        img.set_data(current_to_rgb())
        fig.canvas.draw_idle()

    palette_selector.on_clicked(on_palette)

    # Boundary selector to choose wrap, open/absorbing, or zero-fill edges.
    ax_boundary = ax_options.inset_axes([0.08, 0.30, 0.84, 0.20], facecolor="#0f1b26")
    boundary_selector = RadioButtons(
        ax_boundary,
        [name for name, _ in boundary_options],
        active=boundary_name_to_index["Wrap (toroidal)"],
    )
    def update_boundary_labels(disable_wrap: bool):
        for lbl, (_, mode) in zip(boundary_selector.labels, boundary_options):
            color = "#627386" if disable_wrap and mode == "wrap" else "#d2e7ff"
            lbl.set_color(color)
            lbl.set_fontsize(9)

    update_boundary_labels(disable_wrap=False)

    def on_boundary(label: str):
        nonlocal boundary_mode
        mode = dict(boundary_options)[label]
        if mask_mode == "round" and mode == "wrap":
            # Prevent selecting wrap when round mask is active.
            boundary_selector.set_active(boundary_mode_to_index[boundary_mode])
            return
        boundary_mode = mode
        img.set_data(current_to_rgb())
        fig.canvas.draw_idle()

    boundary_selector.on_clicked(on_boundary)

    # Mask selector to toggle between full grid and round mask domain.
    ax_mask = ax_options.inset_axes([0.08, 0.07, 0.84, 0.18], facecolor="#0f1b26")
    mask_selector = RadioButtons(
        ax_mask,
        [name for name, _ in mask_options],
        active=mask_name_to_index["Full grid"],
    )
    for lbl in mask_selector.labels:
        lbl.set_color("#d2e7ff")
        lbl.set_fontsize(9)

    def on_mask(label: str):
        nonlocal mask_mode, a, b, c, boundary_mode
        mask_mode = dict(mask_options)[label]
        current_mask = round_mask if mask_mode == "round" else None
        if mask_mode == "round" and boundary_mode == "wrap":
            boundary_mode = "open"
            boundary_selector.set_active(boundary_name_to_index["Open (absorbing)"])
        update_boundary_labels(disable_wrap=mask_mode == "round")
        if current_mask is not None:
            a *= current_mask
            b *= current_mask
            c *= current_mask
        img.set_data(current_to_rgb())
        fig.canvas.draw_idle()

    mask_selector.on_clicked(on_mask)

    def record_levels():
        nonlocal step_index
        time_values.append(step_index)
        a_levels.append(float(a.mean()))
        b_levels.append(float(b.mean()))
        c_levels.append(float(c.mean()))
        step_index += 1

    def update_traces():
        if not time_values:
            return
        x = np.fromiter(time_values, dtype=float)
        line_a.set_data(x, a_levels)
        line_b.set_data(x, b_levels)
        line_c.set_data(x, c_levels)
        x_max = x[-1] if len(x) else history_length
        x_min = max(0, x_max - (history_length - 1))
        if x_min == x_max:
            x_max += 1
        ax_levels.set_xlim(x_min, x_max)
        ax_levels.figure.canvas.draw_idle()

    record_levels()
    update_traces()

    # Slider layout
    slider_left = 0.16
    slider_width = 0.68
    slider_height = 0.02
    slider_spacing = 0.038
    ax_alpha = plt.axes([slider_left, 0.12, slider_width, slider_height], facecolor="lightgoldenrodyellow")
    ax_beta = plt.axes(
        [slider_left, 0.12 - slider_spacing, slider_width, slider_height],
        facecolor="lightgoldenrodyellow",
    )
    ax_gamma = plt.axes(
        [slider_left, 0.12 - 2 * slider_spacing, slider_width, slider_height],
        facecolor="lightgoldenrodyellow",
    )

    s_alpha = Slider(ax_alpha, "α (A←B)", 0.4, 1.6, valinit=alpha_init)
    s_beta = Slider(ax_beta, "β (B←C)", 0.4, 1.6, valinit=beta_init)
    s_gamma = Slider(ax_gamma, "γ (C←A)", 0.4, 1.6, valinit=gamma_init)

    # Reset seeds button
    ax_reset = plt.axes([0.86, 0.9, 0.1, 0.05])
    b_reset = Button(ax_reset, "Reseed", color="lightgray", hovercolor="white")

    def on_reset(event):
        nonlocal a, b, c, step_index
        a, b, c = random_substrates(size)
        if mask_mode == "round":
            a *= round_mask
            b *= round_mask
            c *= round_mask
        step_index = 0
        time_values.clear()
        a_levels.clear()
        b_levels.clear()
        c_levels.clear()
        img.set_data(current_to_rgb())
        record_levels()
        update_traces()

    b_reset.on_clicked(on_reset)

    def apply_disturbance(event):
        nonlocal a, b, c
        if event.inaxes != ax_pattern or event.xdata is None or event.ydata is None:
            return
        cx = int(round(event.ydata))
        cy = int(round(event.xdata))
        rel = np.arange(-disturb_radius, disturb_radius + 1)
        mask = (rel[:, None] ** 2 + rel[None, :] ** 2) <= disturb_radius ** 2
        noise = rng.uniform(-disturb_strength, disturb_strength, size=mask.shape) * mask
        if boundary_mode == "wrap":
            idx = np.ix_((cx + rel) % size, (cy + rel) % size)
            a[idx] = np.clip(a[idx] + 0.65 * noise, 0.0, 1.0)
            b[idx] = np.clip(b[idx] + 0.65 * noise, 0.0, 1.0)
            c[idx] = np.clip(c[idx] + 0.65 * noise, 0.0, 1.0)
        else:
            xs = cx + rel
            ys = cy + rel
            valid_x = (xs >= 0) & (xs < size)
            valid_y = (ys >= 0) & (ys < size)
            if not valid_x.any() or not valid_y.any():
                return
            idx = np.ix_(xs[valid_x], ys[valid_y])
            trimmed_noise = noise[np.ix_(valid_x, valid_y)]
            if mask_mode == "round":
                mask_region = round_mask[idx]
                trimmed_noise = trimmed_noise * mask_region
                if not mask_region.any():
                    return
            a[idx] = np.clip(a[idx] + 0.65 * trimmed_noise, 0.0, 1.0)
            b[idx] = np.clip(b[idx] + 0.65 * trimmed_noise, 0.0, 1.0)
            c[idx] = np.clip(c[idx] + 0.65 * trimmed_noise, 0.0, 1.0)
        img.set_data(current_to_rgb())
        fig.canvas.draw_idle()

    def on_press(event):
        nonlocal mouse_down
        mouse_down = True
        apply_disturbance(event)

    def on_release(event):
        nonlocal mouse_down
        mouse_down = False

    def on_move(event):
        if mouse_down:
            apply_disturbance(event)

    def animate(_):
        nonlocal a, b, c
        if not running:
            return img, line_a, line_b, line_c
        domain_mask = round_mask if mask_mode == "round" else None
        a, b, c = step(a, b, c, s_alpha.val, s_beta.val, s_gamma.val, boundary_mode, domain_mask)
        img.set_data(current_to_rgb())
        record_levels()
        update_traces()
        return img, line_a, line_b, line_c

    ani = animation.FuncAnimation(fig, animate, interval=25, blit=False)

    def on_key(event):
        nonlocal running, ani
        if event.key == " ":
            running = not running
            if running:
                ani.event_source.start()
            else:
                ani.event_source.stop()
        elif event.key == "r":
            on_reset(event)

    fig.canvas.mpl_connect("key_press_event", on_key)
    fig.canvas.mpl_connect("button_press_event", on_press)
    fig.canvas.mpl_connect("button_release_event", on_release)
    fig.canvas.mpl_connect("motion_notify_event", on_move)

    plt.show()


if __name__ == "__main__":
    main()
