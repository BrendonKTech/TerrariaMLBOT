import argparse
import os

from stable_baselines3 import PPO

from terraria_env import WATCH_PORT, TerrariaEnv
from train import latest_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="path to a .zip brain (default: newest in models/, reloaded as training saves new ones)")
    parser.add_argument("--port", type=int, default=WATCH_PORT, help="port of the Terraria instance to play in (not the one training uses)")
    args = parser.parse_args()

    path = args.model or latest_model()
    if not path:
        raise SystemExit("No saved brain yet. Run train.py first.")
    print(f"Watching {path}")

    env = TerrariaEnv(port=args.port)
    model = PPO.load(path)
    loaded_mtime = os.path.getmtime(path)
    obs, _ = env.reset()
    total, kills, episode = 0.0, 0, 1
    try:
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            total += reward
            kills += info["kills"]
            if terminated or truncated:
                print(f"Episode {episode}: reward {total:.1f}, kills {kills}, {'died' if terminated else 'survived'}")

                # When following training, switch to the newest checkpoint between episodes
                newest = None if args.model else latest_model()
                if newest and os.path.getmtime(newest) > loaded_mtime:
                    try:
                        model = PPO.load(newest)
                        loaded_mtime = os.path.getmtime(newest)
                        print(f"Switched to {newest}")
                    except Exception as e:  # train.py may still be writing the file; try again next episode
                        print(f"Couldn't load {newest} yet: {e}")

                obs, _ = env.reset()
                total, kills, episode = 0.0, 0, episode + 1
    except (KeyboardInterrupt, ConnectionError):
        pass
    finally:
        env.close()


if __name__ == "__main__":
    main()
