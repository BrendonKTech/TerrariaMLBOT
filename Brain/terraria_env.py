import json
import socket
import time

import gymnasium as gym
import numpy as np
from gymnasium import spaces

HOST = "127.0.0.1"
TRAIN_PORT = 5555  # each Terraria instance listens on its own port, so train.py and watch.py can run side by side
WATCH_PORT = 5556
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
REWARD_NEW_ITEM_TYPE = 0.5     # first time holding each kind of item this episode (a stack count would be farmable)
AREA_SIZE = 8                  # tiles per side of an "area"

# How every episode starts (see BotPlayer.DoReset). These are the dials for training stages:
# time = "day" / "night" / "keep", spawns = enemy spawn multiplier (0 = none), loadout = 1 to restore the starting inventory.
# Enemy strength is the Journey difficulty slider, set once in-game (it's saved with the world).
DEFAULT_RESET = {"time": "day", "spawns": 1.0, "loadout": 1}

NOOP = [0, 0, 0, 0, 0, 2]

class TerrariaEnv(gym.Env):
    def __init__(self, port=TRAIN_PORT, reset_options=None):
        super().__init__()
        self.port = port
        self.reset_options = {**DEFAULT_RESET, **(reset_options or {})}
        # move, jump, use item, aim direction, hotbar slot, aim distance (near = mining/building, far = fighting)
        self.action_space = spaces.MultiDiscrete([3,2,2,9,4,3])

        self.obs_size = 10 + MAX_ENEMIES * 4 + GRID_W * GRID_H * 2
        self.observation_space = spaces.Box(-1.0, 1.0, shape=(self.obs_size,), dtype=np.float32)

        self.sock = None
        self.reader = None
        self.last = None
        self.steps = 0
        self.visited = set()

    # Connection
    def _connect(self):
        print(f"Connecting to Terraria on port {self.port} (load a world with BotBridge enabled)...")
        while True:
            try:
                self.sock = socket.create_connection((HOST, self.port))
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
        self._send_line(" ".join(str(int(a)) for a in action))

    def _send_line(self, line):
        if self.sock is None:
            raise ConnectionError("Not connected to Terraria")
        self.sock.sendall((line + "\n").encode("utf-8"))

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
        r += s["newItems"] * REWARD_NEW_ITEM_TYPE

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

        # The world can't be restarted, so the mod fakes it: back to spawn, healed, starting kit, enemies cleared.
        # Every episode starting the same way is what lets the bot tell good habits from lucky circumstances.
        opts = {**self.reset_options, **((options or {}).get("reset") or {})}
        self._send_line("RESET " + " ".join(f"{k}={v}" for k, v in opts.items()))
        self.last = self._read()
        while self.last["dead"] or self.last["resetting"]:
            self._send(NOOP)
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
