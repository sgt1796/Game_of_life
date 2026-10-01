from dataclasses import dataclass
from itertools import product
import numpy as np

class automaton:
    def __init__(self, 
                 shape: tuple[int, int], 
                 state: np.ndarray, 
                 state_space: set = None,
                 rule: callable = None
                 ):
        '''
        Initialize the automaton with a given shape and state.

        :param shape: A tuple representing the dimensions of the automaton (e.g., (rows, columns)).
        :param state: A 2D numpy array representing the initial state of the automaton.
        :param state_space: An optional set representing the unique states in the automaton. If not provided, it will be inferred from the initial state.
        :param rule: An optional callable representing the update rule for the automaton. If not provided, a default rule will be used.
                     A rule is a function that takes 
        '''
        self.shape = shape
        self.state = state
        self.rule = rule
        # count unique states in self.state if state_space is not provided
        self.state_space = state_space if state_space is not None else set([a for row in state for a in row])

    def step(self, by: int = 1):
        '''
        Update the state of the automaton by applying the rule for a given number of steps.

        :param by: The number of steps to update the state. Default by 1.
        '''
        pass

@dataclass
class Neighborhood:
    '''
    A neighborhood is a collection of cells surrounding a central cell in a cellular automaton. 
    Providing a 2D array of states and the index of the center cell, by default the center cell is the first element of the array.
    '''
    center_index: int = 0
    states: np.ndarray = None
    

class Rule:
    def __init__(self, mapping: dict):
        '''
        Initialize the rule with a given mapping. The mapping is a dictionary that defines the next state for each possible combination of states in the local neighborhood.
        Rule class is acting directly on the current state of a cell and all its neighbors, called the local (Local Configuration) of the CA. 
        
        The **local** is an instance of the Neighborhood class, or in tuples or lists like (center, neighbor1, neighbor2,...).

        :param mapping: A dictionary representing the mapping of states to their next states.
        '''
        self.mapping = mapping

    def lookup(self, local):
        '''Lookup the next state for a given local neighborhood of states.'''
        return self.mapping[local]
    
    def __call__(self, local):
        '''Rules acting on a local neighborhood of states to determine the next state.'''
        return self.mapping[self.lookup(local)]

class DeterministicRule(Rule):
    '''
    A deterministic rule is a general rule that maps every possible state sequence individually to its next state
    For a cell with n neighbors (including center), there are s^n possible combination of states

    :param mapping: A dictionary representing the mapping of states to their next states. If not provided, it will be generated from the provided maps_to list and num_states.
    '''
    def __init__(self, 
                 mapping: dict = None,
                 num_states: int = None,
                 maps_to: list = None):
        if mapping is None:
            # len(maps_to) = num_states ** neighborhood_size
            remaining = len(maps_to)
            neighborhood_size = 0
            while remaining > 1:
                remaining, remainder = divmod(remaining, num_states)
                neighborhood_size += 1

                if remainder != 0:
                    raise ValueError("The length of maps_to must be a power of num_states.")

            # create a list of permutation of all possible states for the given neighborhood size
            all_states = [i for i in np.ndindex(*(num_states,) * neighborhood_size)]
            mapping = {local: maps_to[i] for i, local in enumerate(all_states)}
        super().__init__(mapping)
        

    def __call__(self, state, neighbor):
        pass

class TotalisticRule(Rule):
    '''
    A totalistic rule is a general rule that maps every possible sum of states to its next state (including the center cell)
    '''
    def __init__(self, mapping: dict):
        pass
    def __call__(self, state, neighbor):
        pass

class OuterTotalisticRule(Rule):
    '''
    An outer totalistic rule is a general rule that maps every possible sum of states to its next state (excluding the center cell)
    '''
    def __init__(self, mapping: dict):
        pass
    def __call__(self, state, neighbor):
        pass



         

initial_state = np.array([[0, 0, 0, 0, 0],
                          [0, 1, 1, 1, 0],
                          [0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0]])

gol = automaton((5, 5), initial_state)
# Each local configuration is (center, neighbor1, ..., neighbor8).
# np.ndindex matches the configuration ordering used by DeterministicRule.
gol_maps_to = [
    int(sum(local[1:]) == 3 or (local[0] == 1 and sum(local[1:]) == 2))
    for local in np.ndindex(*(2,) * 9)
]
gol_maps_to = [
    int(
        sum(local[1:]) == 3
        or (local[0] == 1 and sum(local[1:]) == 2)
    )
    for local in np.ndindex(*(2,) * 9)
]

rule = DeterministicRule(num_states=2, maps_to=gol_maps_to)

print(rule.mapping) 
