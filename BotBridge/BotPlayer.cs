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
		public int Move;      // 0 = none, 1 = left, 2 = right
		public bool Jump;
		public bool UseItem;
		public int Aim;       // 0-7 = compass direction, 8 = auto-aim at nearest enemy
		public int Hotbar;    // 0-3 = hotbar slots 1-4

		// Event counters since the last observation was sent. Python turns these into rewards.
		public int DamageDealt;
		public int DamageTaken;
		public int Kills;

		static readonly Vector2[] AimDirections =
		{
			new Vector2(1, 0), new Vector2(1, -1), new Vector2(0, -1), new Vector2(-1, -1),
			new Vector2(-1, 0), new Vector2(-1, 1), new Vector2(0, 1), new Vector2(1, 1),
		};

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
			Vector2 target = Player.Center + new Vector2(Player.direction * 100f, 0);
			if (Aim < 8) {
				target = Player.Center + Vector2.Normalize(AimDirections[Aim]) * 100f;
			}
			else {
				NPC nearest = BridgeSystem.NearestEnemy(Player, 1000f);
				if (nearest != null)
					target = nearest.Center;
			}
			Main.mouseX = (int)(target.X - Main.screenPosition.X);
			Main.mouseY = (int)(target.Y - Main.screenPosition.Y);
		}

		// Called for every hit this player lands, whether from a held item or a projectile
		public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone) {
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
	}
}
