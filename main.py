#!/usr/bin/env python3
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Rectangle


# This is a python implementation of Conway's game of life
def _init_grid(n, ratio):
    '''
    Initialize n x n matrix to simulate Conway's Game of Life
    :param n: size of the matrix
    :param ratio: the percentage of 1's out of total cells
    :return: numpy array representing the initialized grid
    '''

    # calculate needed 1's amount
    ones = int(n ** 2 * ratio)

    # create vector has that many 1's and 0's
    vector = np.array([1] * ones + [0] * (n ** 2 - ones))

    # shuffle the vector to randomize the 1, reshape it to a matrix
    np.random.shuffle(vector)

    # transform the 1D vector to 2D matrix, return the matrix
    return vector.reshape((n, n))


# Function to apply Conway's Game of Life rules
def next_gen(grid):
    '''
    This function takes a n x n matrix (grid) with 1s and 0s and apply Conway's GOL rule
    :param grid: The R2 space of the (t-1)-th generation
    :return: The R2 space of the t-th generation
    '''

    N = grid.shape[0]

    # Pad 0s around the grid for the ease of boundary conditions
    pad_grid = np.zeros((N+2, N+2))
    pad_grid[1:-1, 1:-1] = grid

    next_grid = grid.copy()

    for i in range(1,N+1):
        for j in range(1,N+1):
            # state is the current status (dead / alive) for the (i,j) cell
            state = grid[i-1, j-1]

            # count its neighboring 8 grids
            neighbors = np.sum(pad_grid[(i-1): (i+2), (j-1): (j+2)]) - state

            # if cell is alive, and <2 or >3 neighbor present, cell died (=0)
            #                 , if 2<= neighbor <= 3, cell keep alive (no change)
            if state and (neighbors < 2 or neighbors > 3):
                next_grid[i-1, j-1] = 0
            # if cell dead, exactly 3 neighbors around, it lives (=1)
            elif state == 0 and neighbors == 3:
                next_grid[i-1, j-1] = 1

    return next_grid


def main():
    # np.random.seed(123)
    N = 120  # Define the size of the grid.
    global current_grid, fade_grid, img, color, is_dragging, tail_color, is_running, ani
    current_grid = _init_grid(N, 0.1).astype(float)
    fade_grid = np.zeros_like(current_grid)  # Grid to track the fade levels

    # Global flag to track click-and-drag state
    is_dragging = False
    is_running = True

    # manual override -- for aesthetic improvement
    color = np.array([46, 204, 113]) / 255.0  # Emerald
    bg_color = np.array([34, 47, 62]) / 255.0  # Dark Slate Grey
    tail_color = np.array([171, 235, 198]) / 255.0  # Mint Cream

    # Set up the figure, adjusting aesthetics
    global fig, ax
    fig, ax = plt.subplots()
    ax.axis('off')  # Turn off the axis.
    plt.title('Conway\'s Game of Life', fontsize=24, color='mediumseagreen', fontweight='heavy', style='italic', family='fantasy', pad=20)


    fig.patch.set_facecolor(bg_color)  # Set the background color of the figure

    # Use imshow to display the initial grid with custom colors
    img = ax.imshow(current_grid, interpolation='nearest')

    # Glow boarder effect
    # Draw the border
    # Set the properties of the neon border
    border_color = 'grey'  # Color of the border
    border = Rectangle((-0.5, -0.5), N, N, linewidth=2, edgecolor=border_color, facecolor='none', alpha=0.9)
    ax.add_patch(border)

    # A rectangle with no glow effect
    border = Rectangle((-0.5, -0.5), N, N, linewidth=2, edgecolor=border_color, facecolor='none')
    ax.add_patch(border)


    # Function to update the alpha values for fading effect
    def update_alpha(grid, fade_grid, rate=0.33):
        # Alive cells are reset to maximum value
        fade_grid[grid == 1] = 1
        # Dead cells decay their alpha value
        fade_grid[grid == 0] -= rate
        # Ensure alpha value does not go below 0
        fade_grid[fade_grid < 0] = 0
        return fade_grid

    # Create an RGBA array based on the current grid and fade_grid
    def update_rgba(current_grid, fade_grid, RGB_color, RGB_tail_color):
        # Initialize the RGBA array: shape (N, N, 4) with all zeros
        rgba_array = np.zeros((current_grid.shape[0], current_grid.shape[1], 4))

        # Set RGB for purple color
        rgba_array[..., :3] = RGB_color  # RGB

        # Use current_grid to determine where to apply the color
        rgba_array[current_grid == 1, :3] = RGB_color  # RGB
        rgba_array[current_grid == 0, :3] = RGB_tail_color

        # Use the fade_grid as the alpha channel
        # Use the fade_grid as the alpha channel
        rgba_array[..., 3] = fade_grid

        return rgba_array

    # Use this function in your animation update step
    def update(*args):
        global current_grid, fade_grid, img, color, is_running
        if not is_running:
            return img,
        # Calculate the next generation
        current_grid = next_gen(current_grid)
        # Update the fade grid (this logic will depend on how you calculate fading)
        # For example, you might decrease the fade_grid values by some amount here for cells that are dead
        fade_grid = update_alpha(current_grid, fade_grid)
        # Update the RGBA data
        rgba_array = update_rgba(current_grid, fade_grid, color, tail_color)

        img.set_data(rgba_array)
        return img,

    def get_grid_coord(x, y, ax, grid_size):
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        x_grid = int(grid_size * (x - xlim[0]) / (xlim[1] - xlim[0]))
        # Invert the y-axis calculation to match the NumPy array indexing
        y_grid = grid_size - 1 - int(grid_size * (y - ylim[0]) / (ylim[1] - ylim[0]))
        return x_grid, y_grid

    # Function to handle the mouse click event
    def on_click(event):
        global current_grid, img, is_dragging
        if event.inaxes == ax and event.button == 1:
            is_dragging = True
            seed_grid(event)

    # Function to handle the mouse motion event
    def on_motion(event):
        global is_dragging
        if is_dragging and event.inaxes == ax:
            seed_grid(event)

    # Function to handle the mouse release event
    def on_release(event):
        global is_dragging
        if event.button == 1:
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
