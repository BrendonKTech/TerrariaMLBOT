import argparse

from stable_baselines3 import PPO

from terraria_env import TerrariaEnv
from train import latest_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="path to a .zip brain (default: newest in models/)")
    args = parser.parse_args()

    path = args.model or latest_model()
    if not path:
        raise SystemExit("No saved brain yet. Run train.py first.")
    print(f"Watching {path}")

    env = TerrariaEnv()
    model = PPO.load(path)
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
                obs, _ = env.reset()
                total, kills, episode = 0.0, 0, episode + 1
    except (KeyboardInterrupt, ConnectionError):
        pass
    finally:
        env.close()


if __name__ == "__main__":
    main()
