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

    # Connection
    def _connect(self):
        print(f"Connecting to Terraria on port {PORT} (load a world with BotBridge enabled)...")
        while True:
            try: 
                self.sock = socket.create_connection((HOST, PORT))
                break
            except OSError:
                time.sleep(2)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.reader = self.sock.makefile("r", encoding="utf-8")
        print("Connected. The bot has control.")
        self.last = self._read()

    def _read(self):
            if self.reader is None:
                raise ConnectionError("Not connected to Terraria")

            line = self.reader.readline()
            if not line:
                raise ConnectionError(
                    "Terraria closed the connection"
                )
            return json.loads(line)

    def _send(self, action):
        if self.sock is None:
            raise ConnectionError("Not connected to Terraria")

        message = " ".join(str(int(a)) for a in action) + "\n"
        self.sock.sendall(message.encode("utf-8"))

    def _encode(self, s):
        hotbar = np.zeros(4, dtype=np.float32)
        if s["hotbar"] < 4:
            hotbar[s["hotbar"]] = 1.0
        player = [
            s["life"] / max(s["lifeMax"], 1),
            s["mana"] / max(s["manaMax"], 1),
            np.clip(s["vx"] / 10, -1, 1),
            np.clip(s["vy"] / 10, -1, 1),
            float(s["grounded"]),
            float(s["day"]),
        ]

        # Fixed-size enemy slots. The network needs the same input size every time, so missing
        # enemies are zeros with a "present" flag of 0 rather than just being left out.
        enemies = np.zeros((MAX_ENEMIES, 4), dtype=np.float32)
        for i, (dx, dy, hp) in enumerate(s["enemies"][:MAX_ENEMIES]):
            enemies[i] = [dx / ENEMY_RANGE_PX, dy / ENEMY_RANGE_PX, hp, 1.0]

        # Two "planes" for the tile grid (solid, liquid) instead of values 0/1/2. Encoding liquid as
        # "2" would wrongly suggest water is "more solid than solid" to the network.
        tiles = np.frombuffer(s["tiles"].encode(), dtype=np.uint8) - ord("0")
        solid = (tiles == 1).astype(np.float32)
        liquid = (tiles == 2).astype(np.float32)

        return np.concatenate([player, hotbar, enemies.ravel(), solid, liquid]).astype(np.float32)

    def _reward(self, prev, s):
        r = 0.0
        r += s["dealt"] * REWARD_PER_DAMAGE_DEALT
        r += s["kills"] * REWARD_PER_KILL
        r -= PENALTY_DAMAGE_TAKEN * s["taken"] / max(s["lifeMax"], 1)
        r += max(s["items"] - prev["items"], 0) * REWARD_PER_ITEM

        area = (int(s["x"]) // AREA_SIZE, int(s["y"]) // AREA_SIZE)
        if area not in self.visited:
            self.visited.add(area)
            r += REWARD_NEW_AREA

        if s["dead"] and not prev["dead"]:
            r -= PENALTY_DEATH
        return r

    # Gymnasium interface 
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)

        if self.sock is None:
            self._connect()

        # The world can't be "restarted" like a simple game, so an episode starts wherever the player
        # is now. If they're dead, press nothing until they respawn.
        while self.last is not None and self.last["dead"]:
            self._send([0, 0, 0, 0, 0])
            self.last = self._read()

        self.steps = 0
        self.visited = set()

        return self._encode(self.last), {}

    def step(self, action):
        self._send(action)
        s = self._read()
        reward = self._reward(self.last, s)
        self.last = s
        self.steps += 1

        terminated = s["dead"]
        truncated = self.steps >= MAX_EPISODE_STEPS    # just a time limit
        info = {"kills": s["kills"], "dealt": s["dealt"]}
        return self._encode(s), reward, terminated, truncated, info

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
            self.reader = None
