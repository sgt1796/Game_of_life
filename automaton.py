from Game_of_Life import GameOfLife
from numpy.random import seed

seed(67)
gol = GameOfLife(size = 10,
                 seeding_ratio = 0.3,
                 life_engine = 'auto')

print(gol.grid, end = '\r')

while True:
    
    print(gol.step(), end = '\r')