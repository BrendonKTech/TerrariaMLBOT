using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ModLoader;

namespace BotBridge
{
	// The bot's "hands". Python sends an action, BridgeSystem stores it here, and SetControls presses the buttons every tick.
	public class BotPlayer : ModPlayer
	{
		// Last action received from Python. Kept until a new one arrives, like holding a key down.
		public bool BotActive;
		public int Move;        // 0 = none, 1 = left, 2 = right
		public bool Jump;
		public bool UseItem;
		public int Aim;         // 0-7 = compass direction, 8 = auto-aim at nearest enemy
		public int Hotbar;      // 0-3 = hotbar slots 1-4
		public int AimDistance; // 0 = touching the player, 1 = a few tiles out, 2 = far. Ignored by auto-aim.

		// Event counters since the last observation was sent. Python turns these into rewards.
		public int DamageDealt;
		public int DamageTaken;
		public int Kills;

		// Episode reset, requested by Python. Settings stick until the next reset changes them.
		public bool PendingReset;
		public string ResetTime = "day";   // "day", "night" or "keep"
		public bool ResetLoadout = true;   // give back the inventory the player had when Python connected
		public float SpawnRateMultiplier = 1f; // read by BotSpawnRate. 0 = no enemies at all

		Item[] loadout;
		readonly HashSet<int> seenItemTypes = new();

		static readonly Vector2[] AimDirections =
		{
			new Vector2(1, 0), new Vector2(1, -1), new Vector2(0, -1), new Vector2(-1, -1),
			new Vector2(-1, 0), new Vector2(-1, 1), new Vector2(0, 1), new Vector2(1, 1),
		};
		// Pickaxes and blocks only reach ~4 tiles past the player, so the near/mid distances have to land inside that.
		// 24px = the tile right next to the player (or under the feet), 56px = 3.5 tiles out, 100px = far, for weapons.
		static readonly float[] AimDistances = { 24f, 56f, 100f };

		public override void SetControls() {
			if (!BotActive || Player.whoAmI != Main.myPlayer)
				return;

			Player.controlLeft = Move == 1;
			Player.controlRight = Move == 2;
			Player.controlJump = Jump;
			Player.controlUseItem = UseItem;
			// Block the other controls so your real keyboard can't fight the bot
			Player.controlUp = false;
			Player.controlDown = false;
			Player.controlHook = false;
			Player.controlThrow = false;

			// Switching items mid-swing cancels the swing, so only switch between uses
			if (Player.itemAnimation == 0)
				Player.selectedItem = Hotbar;

			// Items aim at the mouse, so the bot "moves the mouse" to wherever it wants to aim
			// Auto-aim (8) is a shortcut: aiming precisely is hard to learn, so we hand the bot a "look at the closest enemy" button
			float distance = AimDistances[Math.Clamp(AimDistance, 0, AimDistances.Length - 1)];
			Vector2 target = Player.Center + new Vector2(Player.direction * distance, 0);
			if (Aim < 8) {
				target = Player.Center + Vector2.Normalize(AimDirections[Aim]) * distance;
			}
			else {
				NPC nearest = BridgeSystem.NearestEnemy(Player, 1000f);
				if (nearest != null)
					target = nearest.Center;
			}
			Main.mouseX = (int)(target.X - Main.screenPosition.X);
			Main.mouseY = (int)(target.Y - Main.screenPosition.Y);
			// Pickaxes and block placement use the tile under the mouse. Set it directly too, in case it was already worked out this tick.
			Player.tileTargetX = (int)(target.X / 16f);
			Player.tileTargetY = (int)(target.Y / 16f);
		}

		// Called for every hit this player lands, whether from a held item or a projectile
		public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone) {
			// Only real enemies count. Otherwise the bot learns to farm bunnies, statue spawns, or a target dummy (which never dies)
			if (target.immortal || target.friendly || target.CountsAsACritter || target.SpawnedFromStatue)
				return;
			DamageDealt += damageDone;
			if (target.life <= 0)
				Kills++;
		}

		public override void OnHurt(Player.HurtInfo info) {
			DamageTaken += info.Damage;
		}

		public void ResetCounters() {
			DamageDealt = 0;
			DamageTaken = 0;
			Kills = 0;
		}

		// The inventory the bot gets back on every reset, so every episode starts with the same kit
		public void SaveLoadout() {
			loadout = Player.inventory.Take(Main.InventorySlotsTotal).Select(i => i.Clone()).ToArray();
			RememberCurrentItems();
		}

		// Item types the bot hasn't held yet this episode. Rewarding new types (not stack counts) means
		// placing a block and mining it back, or dropping and picking up torches, earns nothing.
		public int CountNewItemTypes() {
			int count = 0;
			for (int i = 0; i < Main.InventorySlotsTotal; i++) {
				Item item = Player.inventory[i];
				if (!item.IsAir && seenItemTypes.Add(item.type))
					count++;
			}
			return count;
		}

		void RememberCurrentItems() {
			seenItemTypes.Clear();
			CountNewItemTypes();
		}

		// Reset message format: "RESET key=value ...", e.g. "RESET time=day spawns=0.5 loadout=1". Missing keys keep their last value.
		public void RequestReset(string line) {
			foreach (string part in line.Split(' ').Skip(1)) {
				string[] kv = part.Split('=');
				if (kv.Length != 2)
					continue;
				switch (kv[0]) {
					case "time":
						ResetTime = kv[1];
						break;
					case "spawns":
						SpawnRateMultiplier = float.Parse(kv[1], CultureInfo.InvariantCulture);
						break;
					case "loadout":
						ResetLoadout = kv[1] == "1";
						break;
				}
			}
			// Let go of everything while the reset happens
			Move = 0;
			Jump = false;
			UseItem = false;
			PendingReset = true;
		}

		// Put the player back in the same starting situation: at spawn, full health, starting kit, chosen time, no enemies around
		public void DoReset() {
			PendingReset = false;

			Player.Spawn(PlayerSpawnContext.RecallFromItem);
			Player.velocity = Vector2.Zero;
			Player.fallStart = (int)(Player.position.Y / 16f);
			Player.statLife = Player.statLifeMax2;
			Player.statMana = Player.statManaMax2;
			for (int i = Player.buffType.Length - 1; i >= 0; i--) {
				if (Player.buffType[i] > 0 && Main.debuff[Player.buffType[i]])
					Player.DelBuff(i);
			}

			if (ResetLoadout && loadout != null) {
				for (int i = 0; i < loadout.Length; i++)
					Player.inventory[i] = loadout[i].Clone();
			}
			RememberCurrentItems();

			if (ResetTime == "day") {
				Main.dayTime = true;
				Main.time = 0; // dawn
			}
			else if (ResetTime == "night") {
				Main.dayTime = false;
				Main.time = 0; // dusk
			}

			// Clear out leftover enemies, but never during a boss fight (removing boss parts would break the fight)
			if (!Main.npc.Any(n => n.active && n.boss)) {
				foreach (NPC npc in Main.npc) {
					if (npc.active && !npc.friendly && !npc.townNPC && !npc.CountsAsACritter)
						npc.active = false;
				}
			}
			foreach (Projectile proj in Main.projectile) {
				if (proj.active && proj.hostile)
					proj.Kill();
			}
			ResetCounters();
		}
	}

	// Lets Python turn enemy spawns up or down per episode (a difficulty dial for training stages)
	public class BotSpawnRate : GlobalNPC
	{
		public override void EditSpawnRate(Player player, ref int spawnRate, ref int maxSpawns) {
			BotPlayer bot = player.GetModPlayer<BotPlayer>();
			if (!bot.BotActive || bot.SpawnRateMultiplier == 1f)
				return;
			if (bot.SpawnRateMultiplier <= 0f) {
				maxSpawns = 0;
				return;
			}
			// spawnRate is "1 in N chance per tick", so a smaller N means more spawns
			spawnRate = Math.Max(1, (int)(spawnRate / bot.SpawnRateMultiplier));
			maxSpawns = Math.Max(1, (int)(maxSpawns * bot.SpawnRateMultiplier));
		}
	}
}
