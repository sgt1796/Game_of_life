#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.widgets as widgets
import matplotlib.animation as animation
from matplotlib.patches import Rectangle
from matplotlib.widgets import Slider, Button



# This is a python implementation of Conway's game of life
def _init_grid(n, ratio):
    # Initialize n x n matrix to simulate Conway's Game of Life
    ones = int(n ** 2 * ratio)
    vector = np.array([1] * ones + [0] * (n ** 2 - ones))
    np.random.shuffle(vector)
    return vector.reshape((n, n))


def next_gen(grid):
    # Apply Conway's Game of Life rules
    N = grid.shape[0]
    pad_grid = np.zeros((N + 2, N + 2))
    pad_grid[1:-1, 1:-1] = grid
    next_grid = grid.copy()

    for i in range(1, N + 1):
        for j in range(1, N + 1):
            state = grid[i - 1, j - 1]
            neighbors = np.sum(pad_grid[(i - 1): (i + 2), (j - 1): (j + 2)]) - state
            if state and (neighbors < 2 or neighbors > 3):
                next_grid[i - 1, j - 1] = 0
            elif state == 0 and neighbors == 3:
                next_grid[i - 1, j - 1] = 1

    return next_grid


def main():
    N = 120
    global current_grid, fade_grid, img, color, is_dragging, tail_color, is_running, ani, tail_fade_rate, selected_color
    current_grid = _init_grid(N, 0.1).astype(float)
    fade_grid = np.zeros_like(current_grid)

    is_dragging = False
    is_running = True
    tail_fade_rate = 0.33  # Default fading rate

    color = np.array([46, 204, 113]) / 255.0
    bg_color = np.array([34, 47, 62]) / 255.0
    tail_color = np.array([171, 235, 198]) / 255.0
    selected_color = color

    global fig, ax
    fig, ax = plt.subplots()
    ax.axis('off')
    plt.title('Conway\'s Game of Life', fontsize=24, color='mediumseagreen', fontweight='heavy', style='italic',
              family='fantasy', pad=20)
    fig.patch.set_facecolor(bg_color)
    img = ax.imshow(current_grid, interpolation='nearest')

    # Border for aesthetic
    border_color = 'grey'
    border = Rectangle((-0.5, -0.5), N, N, linewidth=2, edgecolor=border_color, facecolor='none', alpha=0.9)
    ax.add_patch(border)

    # Create a subplot for the slider
    axcolor = 'lightgoldenrodyellow'
    ax_fade_rate = plt.axes([0.25, 0.01, 0.65, 0.03], facecolor=axcolor)  # Adjust these values to position your slider
    s_fade_rate = widgets.Slider(ax_fade_rate, 'Fade Rate', 0.0, 1.0, valinit=tail_fade_rate)

    # Define the top-right corner for the slider placement
    top_right_x = 0.95  # x position for the rightmost edge of the sliders
    top_right_y = 0.80  # y position for the top edge of the sliders
    slider_height = 0.2  # the height of the sliders
    slider_width = 0.02  # the width of the sliders
    spacing = 0.01  # spacing between the sliders



    # Set the axes for the RGB sliders for the cell color
    axcolor_r = plt.axes(
        [top_right_x - 3 * (slider_width + spacing), top_right_y - slider_height, slider_width, slider_height],
        facecolor=axcolor)
    axcolor_g = plt.axes(
        [top_right_x - 2 * (slider_width + spacing), top_right_y - slider_height, slider_width, slider_height],
        facecolor=axcolor)
    axcolor_b = plt.axes(
        [top_right_x - (slider_width + spacing), top_right_y - slider_height, slider_width, slider_height],
        facecolor=axcolor)

    # Additional offset for the second set of sliders (tail color)
    additional_offset = slider_height + 2 * spacing + 0.1

    # Set the axes for the RGB sliders for the tail color
    axcolor_r_tail = plt.axes(
        [top_right_x - 3 * (slider_width + spacing), top_right_y - slider_height - additional_offset, slider_width,
         slider_height],
        facecolor=axcolor)
    axcolor_g_tail = plt.axes(
        [top_right_x - 2 * (slider_width + spacing), top_right_y - slider_height - additional_offset, slider_width,
         slider_height],
        facecolor=axcolor)
    axcolor_b_tail = plt.axes(
        [top_right_x - (slider_width + spacing), top_right_y - slider_height - additional_offset, slider_width,
         slider_height],
        facecolor=axcolor)

    # Create the vertical sliders for the cell color
    s_color_r = Slider(axcolor_r, 'R', 0.0, 1.0, valinit=color[0], orientation='vertical')
    s_color_g = Slider(axcolor_g, 'G', 0.0, 1.0, valinit=color[1], orientation='vertical')
    s_color_b = Slider(axcolor_b, 'B', 0.0, 1.0, valinit=color[2], orientation='vertical')

    # Hide the value display (valtext) for each slider
    s_color_r.valtext.set_visible(False)
    s_color_g.valtext.set_visible(False)
    s_color_b.valtext.set_visible(False)

    # Place a title horizontally above the cell color sliders
    fig.text(top_right_x - 1.5 * (slider_width + spacing), top_right_y + 0.045, 'Cell Color',
             va='bottom', ha='center', color='black', fontsize=10)

    # Create the vertical sliders for tail color
    s_color_r_tail = Slider(axcolor_r_tail, 'R', 0.0, 1.0, valinit=tail_color[0], orientation='vertical')
    s_color_g_tail = Slider(axcolor_g_tail, 'G', 0.0, 1.0, valinit=tail_color[1], orientation='vertical')
    s_color_b_tail = Slider(axcolor_b_tail, 'B', 0.0, 1.0, valinit=tail_color[2], orientation='vertical')

    # Hide the value display (valtext) for each slider
    s_color_r_tail.valtext.set_visible(False)
    s_color_g_tail.valtext.set_visible(False)
    s_color_b_tail.valtext.set_visible(False)

    # Place a title horizontally above the tail color sliders
    fig.text(top_right_x - 1.5 * (slider_width + spacing), top_right_y - slider_height - additional_offset + 0.25,
             'Tail Effect Color',
             va='bottom', ha='center', color='black', fontsize=10)

    # ... [rest of the previous code] ...

    # Update function for the slider
    def update_fade_rate(val):
        global tail_fade_rate
        tail_fade_rate = s_fade_rate.val
        update_plot()

    s_fade_rate.on_changed(update_fade_rate)

    # Function to update the alpha values for fading effect
    def update_alpha(grid, fade_grid, rate):
        fade_grid[grid == 1] = 1
        fade_grid[grid == 0] -= rate
        fade_grid[fade_grid < 0] = 0
        return fade_grid

    def update_rgba(current_grid, fade_grid, RGB_color, RGB_tail_color):
        rgba_array = np.zeros((current_grid.shape[0], current_grid.shape[1], 4))
        rgba_array[..., :3] = RGB_color
        rgba_array[current_grid == 1, :3] = RGB_color
        rgba_array[current_grid == 0, :3] = RGB_tail_color
        rgba_array[..., 3] = fade_grid
        return rgba_array

    def get_grid_coord(x, y, ax, grid_size):
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        x_grid = int(grid_size * (x - xlim[0]) / (xlim[1] - xlim[0]))
        y_grid = grid_size - 1 - int(grid_size * (y - ylim[0]) / (ylim[1] - ylim[0]))
        return x_grid, y_grid

    def on_click(event):
        if event.inaxes == ax and event.button == 1:
            global is_dragging
            is_dragging = True
            seed_grid(event)

    def on_motion(event):
        if is_dragging and event.inaxes == ax:
            seed_grid(event)

    def on_release(event):
        if event.button == 1:
            global is_dragging
            is_dragging = False

    # Function to handle key press events
    def on_key_press(event):
        global is_running, ani
        if event.key == ' ':
            # Toggle running state
            is_running = not is_running
            if is_running:
                ani.event_source.start()
            else:
                ani.event_source.stop()

    # Function to update the grid with a new seed based on the event coordinates
    def seed_grid(event):
        global current_grid, fade_grid, img
        x, y = event.xdata, event.ydata
        i, j = get_grid_coord(x, y, ax, N)
        if i >= 0 and i < N and j >= 0 and j < N:
            current_grid[j, i] = 1
            fade_grid[j, i] = 1
            update_plot()

    # Function to update the plot
    def update_plot():
        global current_grid, fade_grid, img, color, tail_color
        rgba_array = update_rgba(current_grid, fade_grid, color, tail_color)
        img.set_data(rgba_array)
        fig.canvas.draw_idle()

    # Use this function in your animation update step
    def update(*args):
        global current_grid, fade_grid, img, color, is_running
        if not is_running:
            return img,
        current_grid = next_gen(current_grid)
        fade_grid = update_alpha(current_grid, fade_grid, tail_fade_rate)
        rgba_array = update_rgba(current_grid, fade_grid, color, tail_color)
        img.set_data(rgba_array)
        return img,


    ax_ratio = plt.axes([0.25, 0.04, 0.65, 0.03], facecolor=axcolor)
    s_ratio = Slider(ax_ratio, 'Seeding Ratio', 0.0, 1.0, valinit=0.1)

    ax_reset = plt.axes([0.82, 0.08, 0.1, 0.04])
    b_reset = Button(ax_reset, 'Reset', color=axcolor, hovercolor='0.975')

    # Add a button to clear the grid
    ax_clear = plt.axes([0.82, 0.14, 0.1, 0.04])  # Set the position for the "Clear" button
    b_clear = Button(ax_clear, 'Clear', color=axcolor, hovercolor='0.975')

    # Callback function for the seeding ratio slider
    def update_seeding_ratio(val):
        global current_grid, fade_grid
        current_grid = _init_grid(N, s_ratio.val).astype(float)
        fade_grid = np.zeros_like(current_grid)
        update_plot()

    s_ratio.on_changed(update_seeding_ratio)

    # Callback function for the reset button
    def reset(event):
        global current_grid, fade_grid
        current_grid = _init_grid(N, s_ratio.val).astype(float)
        fade_grid = np.zeros_like(current_grid)
        update_plot()

    b_reset.on_clicked(reset)

    # Callback function for the clear button
    def clear_grid(event):
        global current_grid, fade_grid
        current_grid = np.zeros((N, N), dtype=float)
        fade_grid = np.zeros_like(current_grid)
        update_plot()

    b_clear.on_clicked(clear_grid)

    # Callback function to update the cell color
    def update_cell_color(val):
        global color
        color[0] = s_color_r.val
        color[1] = s_color_g.val
        color[2] = s_color_b.val
        update_plot()

    # Register the update function with each slider
    s_color_r.on_changed(update_cell_color)
    s_color_g.on_changed(update_cell_color)
    s_color_b.on_changed(update_cell_color)

    # Callback function to update the tail color
    def update_tail_color(val):
        global tail_color
        tail_color[0] = s_color_r_tail.val
        tail_color[1] = s_color_g_tail.val
        tail_color[2] = s_color_b_tail.val
        update_plot()

    # Register the update function with each slider
    s_color_r_tail.on_changed(update_tail_color)
    s_color_g_tail.on_changed(update_tail_color)
    s_color_b_tail.on_changed(update_tail_color)

    # Connect the event handlers to the figure
    fig.canvas.mpl_connect('button_press_event', on_click)
    fig.canvas.mpl_connect('motion_notify_event', on_motion)
    fig.canvas.mpl_connect('button_release_event', on_release)
    fig.canvas.mpl_connect('key_press_event', on_key_press)

    # Set up the animation
    ani = animation.FuncAnimation(fig, update, interval=25, save_count=50)


    # Display the animation
    plt.show()


if __name__ == "__main__":
    main()

