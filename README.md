# Conway's Game of Life

This is a Python implementation of Conway's Game of Life. The Game of Life is a cellular automaton devised by the British mathematician John Horton Conway in 1970. It's a zero-player game, meaning that its evolution is determined by its initial state, requiring no further input. One interacts with the Game of Life by creating an initial configuration and observing how it evolves.

## Rules

The universe of the Game of Life is a two-dimensional orthogonal grid of square cells, each of which is in one of two possible states, alive or dead. Every cell interacts with its eight neighbors, which are the cells that are horizontally, vertically, or diagonally adjacent.

At each step in time, the following transitions occur:

1. **Birth**: A dead cell with exactly three live neighbors becomes a live cell.
2. **Death by Isolation**: A live cell with fewer than two live neighbors dies.
3. **Death by Overcrowding**: A live cell with more than three live neighbors dies.
4. **Survival**: A live cell with two or three live neighbors continues to live.

The initial pattern constitutes the 'seed' of the system. The first generation is created by applying the above rules simultaneously to every cell in the seed—births and deaths occur simultaneously.

## Implementation


## Usage


## Examples


## Conclusion

