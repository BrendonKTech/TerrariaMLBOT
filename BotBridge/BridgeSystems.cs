using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using Microsoft.Xna.Framework;
using Newtonsoft.Json;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace BotBridge
{
	// The bot's "eyes" and phone line. Every few ticks: send what the player sees to Python, wait for an action back.
	public class BridgeSystem : ModSystem
	{
		const int Port = 5555;
		// One decision every 4 ticks (15 per second). Deciding every single tick wastes effort, since one tick barely changes anything.
		const int FrameSkip = 4;
		const int MaxEnemies = 5;
		const float EnemyRange = 60 * 16f; // 60 tiles, in pixels
		public const int GridW = 15, GridH = 11;

		TcpListener listener;
		TcpClient client;
		StreamReader reader;
		StreamWriter writer;
		int tick;

		public override void OnWorldLoad() {
			if (Main.netMode != NetmodeID.SinglePlayer)
				return;
			listener = new TcpListener(IPAddress.Loopback, Port);
			listener.Start();
			Main.NewText("[BotBridge] Waiting for the Python brain on port " + Port + "...", Color.Yellow);
		}

		public override void OnWorldUnload() {
			Disconnect();
			listener?.Stop();
			listener = null;
		}

		public override void PostUpdateEverything() {
			if (listener == null)
				return;

			if (client == null) {
				// Pending() never blocks, so the game runs normally until Python connects
				if (!listener.Pending())
					return;
				Accept();
			}

			if (++tick % FrameSkip != 0)
				return;

			Player player = Main.LocalPlayer;
			BotPlayer bot = player.GetModPlayer<BotPlayer>();
			try {
				writer.WriteLine(BuildObservation(player, bot));
				writer.Flush();
				bot.ResetCounters();

				// Lockstep: the game waits here until Python answers. This freezes the game while Python trains; that's intended.
				string line = reader.ReadLine();
				if (line == null)
					throw new IOException("Python closed the connection");
				ApplyAction(bot, line);
			}
			catch (Exception e) {
				Main.NewText("[BotBridge] Disconnected: " + e.Message, Color.OrangeRed);
				Disconnect();
			}
		}

		void Accept() {
			client = listener.AcceptTcpClient();
			client.NoDelay = true;           // send small messages immediately instead of batching them
			client.ReceiveTimeout = 120000;  // give up if Python goes silent for 2 minutes
			NetworkStream stream = client.GetStream();
			reader = new StreamReader(stream, Encoding.UTF8);
			writer = new StreamWriter(stream, new UTF8Encoding(false));
			Main.LocalPlayer.GetModPlayer<BotPlayer>().BotActive = true;
			Main.NewText("[BotBridge] Brain connected. The bot has control.", Color.LightGreen);
		}

		void Disconnect() {
			if (Main.LocalPlayer?.active == true)
				Main.LocalPlayer.GetModPlayer<BotPlayer>().BotActive = false;
			reader?.Dispose();
			writer?.Dispose();
			client?.Close();
			reader = null;
			writer = null;
			client = null;
		}

		// Action format: "move jump use aim hotbar", e.g. "2 1 0 8 0" = run right, jump, aim at nearest enemy, slot 1
		static void ApplyAction(BotPlayer bot, string line) {
			int[] a = line.Split(' ').Select(int.Parse).ToArray();
			bot.Move = a[0];
			bot.Jump = a[1] == 1;
			bot.UseItem = a[2] == 1;
			bot.Aim = a[3];
			bot.Hotbar = a[4];
		}

		public static NPC NearestEnemy(Player player, float range) {
			NPC best = null;
			float bestDist = range;
			foreach (NPC npc in Main.npc) {
				if (!npc.CanBeChasedBy())
					continue;
				float d = Vector2.Distance(player.Center, npc.Center);
				if (d < bestDist) {
					bestDist = d;
					best = npc;
				}
			}
			return best;
		}

		static string BuildObservation(Player player, BotPlayer bot) {
			var enemies = Main.npc
				.Where(n => n.CanBeChasedBy() && Vector2.Distance(player.Center, n.Center) < EnemyRange)
				.OrderBy(n => Vector2.Distance(player.Center, n.Center))
				.Take(MaxEnemies)
				.Select(n => new[] { n.Center.X - player.Center.X, n.Center.Y - player.Center.Y, (float)n.life / n.lifeMax })
				.ToArray();

			// Tile grid around the player, one char per tile: 0 = air, 1 = solid, 2 = liquid
			var tiles = new StringBuilder(GridW * GridH);
			int px = (int)(player.Center.X / 16), py = (int)(player.Center.Y / 16);
			for (int y = py - GridH / 2; y <= py + GridH / 2; y++) {
				for (int x = px - GridW / 2; x <= px + GridW / 2; x++) {
					if (!WorldGen.InWorld(x, y)) {
						tiles.Append('1');
						continue;
					}
					Tile t = Main.tile[x, y];
					if (t.HasTile && !t.IsActuated && Main.tileSolid[t.TileType])
						tiles.Append('1');
					else if (t.LiquidAmount > 0)
						tiles.Append('2');
					else
						tiles.Append('0');
				}
			}

			int itemCount = 0;
			for (int i = 0; i < 50; i++) {
				if (!player.inventory[i].IsAir)
					itemCount += player.inventory[i].stack;
			}

			return JsonConvert.SerializeObject(new {
				life = player.statLife,
				lifeMax = player.statLifeMax2,
				mana = player.statMana,
				manaMax = player.statManaMax2,
				x = player.Center.X / 16f,
				y = player.Center.Y / 16f,
				vx = player.velocity.X,
				vy = player.velocity.Y,
				grounded = player.velocity.Y == 0f,
				dead = player.dead,
				day = Main.dayTime,
				hotbar = player.selectedItem,
				items = itemCount,
				enemies,
				tiles = tiles.ToString(),
				dealt = bot.DamageDealt,
				taken = bot.DamageTaken,
				kills = bot.Kills,
			});
		}
	}
}
