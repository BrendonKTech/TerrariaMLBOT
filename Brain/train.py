import argparse
import glob
import os
from typing import Callable

import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

from terraria_env import TRAIN_PORT, TerrariaEnv

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(HERE, "models")
LOGS_DIR = os.path.join(HERE, "logs")


def latest_model():
    files = glob.glob(os.path.join(MODELS_DIR, "*.zip"))
    return max(files, key=os.path.getmtime) if files else None


class RewardPartsCallback(BaseCallback):
    """Graphs where each episode's reward came from (kills, exploration, ...) under "reward/" in TensorBoard,
    and what killed the bot under "deaths/" (deaths per round of learning, one line per cause)."""

    def __init__(self):
        super().__init__()
        self.deaths = {}

    def _on_step(self):
        for info in self.locals["infos"]:
            for name, value in info.get("reward_parts", {}).items():
                self.logger.record_mean(f"reward/{name}", value)
            if "death_cause" in info:
                cause = info["death_cause"][:40]
                self.deaths[cause] = self.deaths.get(cause, 0) + 1
        return True

    def _on_rollout_end(self):
        for cause, count in self.deaths.items():
            self.logger.record(f"deaths/{cause}", count)
        self.deaths = {}


def make_env(port) -> Callable[[], gym.Env]:
    # Monitor records each episode's total reward and length, which is what shows up in TensorBoard
    return lambda: Monitor(TerrariaEnv(port=port))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=1_000_000, help="decisions to train for (15 per second of game time, per game)")
    parser.add_argument("--fresh", action="store_true", help="ignore saved brains and start from scratch")
    parser.add_argument("--port", type=int, default=TRAIN_PORT, help="port of the first Terraria instance to train in")
    parser.add_argument("--envs", type=int, default=1, help="how many Terraria instances to train in at once (ports --port, --port+1, ...)")
    args = parser.parse_args()

    # Each game runs at a fixed speed, so more games at once is the way to learn faster. Every game gets its
    # own Python process, so one brain collects experience from all of them in parallel.
    env_fns = [make_env(args.port + i) for i in range(args.envs)]
    env = SubprocVecEnv(env_fns) if args.envs > 1 else DummyVecEnv(env_fns)

    path = None if args.fresh else latest_model()
    if path:
        print(f"Resuming from {path}")
        try:
            model = PPO.load(path, env=env, tensorboard_log=LOGS_DIR)
        except ValueError as e:  # the saved brain was built for different actions/observations than the env has now
            env.close()
            raise SystemExit(f"{path} doesn't fit the current bot ({e}).\n"
                             "Move the old .zip files out of models/ or run with --fresh.")
    else:
        print("Starting a brand new brain")
        model = PPO(
            "MlpPolicy",       # a plain neural network (2 layers of 64), plenty for a list of 360 numbers
            env,
            n_steps=1024,      # play ~68s of game time (in every game), then pause to learn from it
            batch_size=64 * args.envs,
            n_epochs=10,       # how many times to study each batch of experience
            learning_rate=3e-4,
            gamma=0.99,        # how much it cares about the future: a reward 100 steps away still counts ~37%
            ent_coef=0.01,     # bonus for staying a bit random, so it keeps trying new things instead of locking in early
            verbose=1,
            tensorboard_log=LOGS_DIR,
        )

    # save_freq counts rounds of steps, and each round is one step in every game
    checkpoints = CheckpointCallback(save_freq=max(10_000 // args.envs, 1), save_path=MODELS_DIR, name_prefix="bot")
    try:
        model.learn(
            total_timesteps=args.steps,
            callback=[checkpoints, RewardPartsCallback()],
            # Resuming keeps counting from the old total so TensorBoard graphs continue; a new brain gets its own graph (PPO_1, PPO_2...)
            reset_num_timesteps=path is None,
            tb_log_name="PPO",
        )
    except (KeyboardInterrupt, ConnectionError, EOFError) as e:  # EOFError = one of the game processes died
        print(f"\nStopping: {e or 'Ctrl+C'}")
    finally:
        os.makedirs(MODELS_DIR, exist_ok=True)
        model.save(os.path.join(MODELS_DIR, "bot_latest"))
        print(f"Saved brain to {MODELS_DIR}")
        try:
            env.close()
        except (ConnectionError, EOFError):
            pass


if __name__ == "__main__":
    main()
