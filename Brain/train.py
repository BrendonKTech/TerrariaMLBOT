import argparse
import glob
import os

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.monitor import Monitor

from terraria_env import TerrariaEnv

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(HERE, "models")
LOGS_DIR = os.path.join(HERE, "logs")


def latest_model():
    files = glob.glob(os.path.join(MODELS_DIR, "*.zip"))
    return max(files, key=os.path.getmtime) if files else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=1_000_000, help="decisions to train for (15 per second of game time)")
    parser.add_argument("--fresh", action="store_true", help="ignore saved brains and start from scratch")
    args = parser.parse_args()

    # Monitor records each episode's total reward and length, which is what shows up in TensorBoard
    env = Monitor(TerrariaEnv())

    path = None if args.fresh else latest_model()
    if path:
        print(f"Resuming from {path}")
        model = PPO.load(path, env=env, tensorboard_log=LOGS_DIR)
    else:
        print("Starting a brand new brain")
        model = PPO(
            "MlpPolicy",       # a plain neural network (2 layers of 64), plenty for a list of 360 numbers
            env,
            n_steps=1024,      # play ~68s of game time, then pause to learn from it
            batch_size=64,
            n_epochs=10,       # how many times to study each batch of experience
            learning_rate=3e-4,
            gamma=0.99,        # how much it cares about the future: a reward 100 steps away still counts ~37%
            ent_coef=0.01,     # bonus for staying a bit random, so it keeps trying new things instead of locking in early
            verbose=1,
            tensorboard_log=LOGS_DIR,
        )

    checkpoints = CheckpointCallback(save_freq=10_000, save_path=MODELS_DIR, name_prefix="bot")
    try:
        model.learn(
            total_timesteps=args.steps,
            callback=checkpoints,
            reset_num_timesteps=False,  # keep counting from the old total so TensorBoard graphs continue, not restart
            tb_log_name="PPO",
        )
    except (KeyboardInterrupt, ConnectionError) as e:
        print(f"\nStopping: {e or 'Ctrl+C'}")
    finally:
        os.makedirs(MODELS_DIR, exist_ok=True)
        model.save(os.path.join(MODELS_DIR, "bot_latest"))
        print(f"Saved brain to {MODELS_DIR}")
        env.close()


if __name__ == "__main__":
    main()
