# Conway's Game of Life

This is a Python implementation of Conway's Game of Life. The Game of Life is a cellular automaton devised by the British mathematician John Horton Conway in 1970. It's a zero-player game, meaning that its evolution is determined by its initial state, requiring no further input. One interacts with the Game of Life by creating an initial configuration and observing how it evolves.

## Web demos (ready for GitHub Pages)

- A browser-native Game of Life and a Belousov–Zhabotinsky visualizer live in `docs/`. Open `docs/index.html` locally or point GitHub Pages at the `docs/` folder (Settings → Pages → Source: `main` / `/docs`) to publish.
- Direct entry points: `docs/game-of-life.html` and `docs/bz-visualization.html` (shared styling in `docs/style.css`).

## Rules

The universe of the Game of Life is a two-dimensional orthogonal grid of square cells, each of which is in one of two possible states, alive or dead. Every cell interacts with its eight neighbors, which are the cells that are horizontally, vertically, or diagonally adjacent.

At each step in time, the following transitions occur:

1. **Birth**: A dead cell with exactly three live neighbors becomes a live cell.
2. **Death by Isolation**: A live cell with fewer than two live neighbors dies.
3. **Death by Overcrowding**: A live cell with more than three live neighbors dies.
4. **Survival**: A live cell with two or three live neighbors continues to live.

The initial pattern constitutes the 'seed' of the system. The first generation is created by applying the above rules simultaneously to every cell in the seed—births and deaths occur simultaneously.

## Implementation

The implementation uses Python libraries NumPy for numerical operations and Matplotlib for visualization. The `next_gen` function uses convolution to apply the Game of Life rules efficiently. The program includes features like interactive grid color adjustments, real-time updates, and a fading effect to visualize cell lifespans.

## Usage

### Running the Game

1. **Python Source Code**:
   - To run the game, execute the `Game_of_Life.py` script using Python:
     ```sh
     python Game_of_Life.py
     ```
   - Or run it in any Python IDE.
   - The script initializes a 150x150 grid with a random distribution of live cells and starts the simulation. Use the interactive controls to adjust settings such as fade rate, cell colors, and seeding ratio.

2. **Executable Version**:
   - An executable version of the game is available for users who do not have a Python environment set up. Simply download and run the executable file.

3. **Webpage Version**:
   - The repository also includes a webpage version (`game_of_life.html`) that provides a comprehensive explanation of the Game of Life, converted from R Markdown files with implementation of Game of Life using R.
  
## Conclusion

This implementation of Conway's Game of Life provides a flexible and interactive way to explore cellular automata.    
