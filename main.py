#!/usr/bin/env python3
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation


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


# Load the JSON file into a Python dictionary
def load_color_dict(json_filename):
    with open(json_filename, 'r') as file:
        color_dict = json.load(file)
    return color_dict


# Function to select colors
def select_color(color_dict, color_name):
    if color_name in color_dict:
        # Get the RGB values for the given color name
        color_rgb = color_dict[color_name]
        # Normalize the RGB values for matplotlib
        normalized_color_rgb = [value / 255 for value in color_rgb]
        return normalized_color_rgb
    else:
        # Raise an error if the color name is not found in the dictionary
        raise ValueError(f"Color '{color_name}' not found in the dictionary.")


def main():
    # np.random.seed(123)
    N = 120  # Define the size of the grid.
    global current_grid, fade_grid, img, color
    current_grid = _init_grid(N, 0.3).astype(float)
    fade_grid = np.zeros_like(current_grid)  # Grid to track the fade levels

    # Load color selections
    color_name = 'grey'  # user-selected foreground color (cell color)
    bg_color_name = 'white'  # user-selected background color
    tail_color_name = 'lime'  # user-selected tail color


    color_dict = load_color_dict('colors.json')
    # Use the select_colors function to get the normalized RGB values
    color = select_color(color_dict, color_name)
    bg_color = select_color(color_dict, bg_color_name)
    tail_color = select_color(color_dict, tail_color_name)


    # manual override -- for aesthetic improvement
    color = np.array([46, 204, 113]) / 255.0  # Emerald
    bg_color = np.array([34, 47, 62]) / 255.0  # Dark Slate Grey
    tail_color = np.array([171, 235, 198]) / 255.0  # Mint Cream

    # Set up the figure, adjusting aesthetics
    fig, ax = plt.subplots()
    ax.axis('off')  # Turn off the axis.
    plt.title('Conway\'s Game of Life', fontsize=24, color='mediumseagreen', fontweight='heavy', style='italic', family='fantasy', pad=20)


    fig.patch.set_facecolor(bg_color)  # Set the background color of the figure

    # Use imshow to display the initial grid with custom colors
    img = ax.imshow(current_grid, interpolation='nearest')

    # Function to update the alpha values for fading effect
    def update_alpha(grid, fade_grid, rate=0.1):
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
        global current_grid, fade_grid, img, color
        # Calculate the next generation
        current_grid = next_gen(current_grid)
        # Update the fade grid (this logic will depend on how you calculate fading)
        # For example, you might decrease the fade_grid values by some amount here for cells that are dead
        fade_grid = update_alpha(current_grid, fade_grid)
        # Update the RGBA data
        rgba_array = update_rgba(current_grid, fade_grid, color, tail_color)

        img.set_data(rgba_array)
        return img,

    # Set up the animation
    ani = animation.FuncAnimation(fig, update, interval=25, save_count=50)

    # Display the animation
    plt.show()


if __name__ == "__main__":
    main()
