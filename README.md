# TerrariaBot

A reinforcement-learning bot that plays (modded) Terraria and improves as it plays.

Terraria + tModLoader
BridgeSystem = eyes   -- state -->  terraria_env.py 
                                    turns state into numbers 
BotPlayer    = hands  <--action --  train.py (PPO) = brain

## Setup (once)
1. **Mod:** `cd BotBridge` then `dotnet build`. That packages the mod into tModLoader's mod folder.
    In-game: **Workshop -> Manage Mods -> Enabe Bot Bridge -> Reload**
2. **Python:** already set up in `brain\.venv`. If you ever need to redo it: 
    ```
    cd brain
    py -3.13 -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
    ```

## Train