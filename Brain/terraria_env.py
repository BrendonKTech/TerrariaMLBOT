import json
import socket
import time

import gymnasium as gym
import numpy as np
from gymnasium import spaces

HOST, PORT = "127.0.0.1", 5555
GRID_W, GRID_H = 15, 11
MAX_ENEMIES = 5
ENEMY_RANGE_PX = 60 * 16
MAX_EPISODE_STEPS = 3000

# Reward tuning
REWARD_PER_DAMAGE_DEALT = 0.01 # hitting things = good
REWARD_PER_KILL = 1.0          # finishing enemies off is good
PENALTY_DAMAGE_TAKEN = 2.0     # times the fraction of max HP lost
PENALTY_DEATH = 5.0            # death bad
REWARD_NEW_AREA = 0.05         # curiosity: first visit to each 8x8-tile area
REWARD_PER_ITEM = 0.1          # picking things up
AREA_SIZE = 8                  # tiles per side of an "area"

class TerrariaEnv(gym.Env):
    def __init__(self):
        super().__init__()
        self.action_space = spaces.MultiDiscrete([3,2,2,9,4])

        self.obs_size = 10 + MAX_ENEMIES * 4 + GRID_W * GRID_H * 2
        self.observation_space = spaces.Box(-1.0, 1.0, shape=(self.obs_size,), dtype=np.float32)

        self.sock = None
        self.reader = None
        self.last = None
        self.steps = 0
        self.visited = set()