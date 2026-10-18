================================================================================
 AEGIS PRIMORDIAL — SENTINEL OF THE NULL VEIL           (Locust Nullifier v1.0.0)
 Minecraft Bedrock 1.21.80+   |   identifier: aegis:primordial_sentinel
================================================================================

WHAT IT IS
  A tall, hooded, armored humanoid guardian that is friendly to players and
  hunts "The Locust" (Doctor Nowhere / T.O.E. ports, Evolution variants) —
  including versions that are immune to /kill, use damage_sensor "no", or a
  min-health lock. It does NOT fight them on their terms: it ERASES them.

INSTALL
  1. Open Aegis_Primordial.mcaddon (double-click / share to Minecraft).
  2. Add BOTH packs (behavior + resource) to your world.
  3. World settings -> Experiments: enable "Beta APIs" (required for
     @minecraft/server scripting). Cheats enabled recommended.

SUMMON
  /summon aegis:primordial_sentinel
  /function aegis/summon                     (spawns 2 blocks in front of you)
  /function aegis/give_core                  (gives an "Aegis Core" item;
                                             use it to summon the sentinel)
  Spawn egg: "Aegis Primordial Spawn Egg" in the creative inventory.
  Auto-deploy: the first time a Locust is detected near a player with no
  Aegis within 96 blocks, one is deployed automatically (60 s cooldown).

HOW THE NULL SEVER WORKS (why /kill fails but this works)
  Invulnerable Locust ports block the DAMAGE pipeline:
     minecraft:damage_sensor { deals_damage: "no" }   -> no hit ever lands
     minecraft:health { min == max }                  -> can never reach 0
  /kill, swords, TNT, /damage all go through that pipeline. The Aegis does not.
  Its script layer calls Entity.remove() from @minecraft/server, which is a
  world-level despawn: the entity is deleted outright without consulting its
  health or any damage component. Before that it also tries override-cause
  damage and forced despawn events, so it works even on ports that are only
  partially immune. All layers run at once:
     A  Melee strike  -> entityHitEntity / entityHurt -> remove()
     B  BP animation controller + events -> /scriptevent aegis:* -> remove()
     C  Proximity scan every 6 ticks (64-block awareness, contact erase)
     D  Null Sever ultimate: 1.4 s charge (hands forward, particle implosion,
        VO "Nullifying anomaly") -> shockwave -> every Locust within 16 blocks
        erased -> void-tear + confirm chime + VO "Locust signature erased."
        Cooldown 10 s.  Blink (void-step) keeps it in range of teleporting or
        flying Locusts.
     E  Family filters + tag override (/tag <e> add aegis_target)
     F  Fallback repeated remove()/kill() attempts if the first call throws.

DETECTION
  Matches by typeId substring ("locust", "doctor_nowhere", ...), type family
  (locust, the_locust, locust_evolution, nowhere, toe, anomaly, horror), name
  tag containing "locust", or the tag aegis_target. Players, items and other
  Aegis are never targeted. Edit CONFIG at the top of scripts/main.js to add
  more identifiers.

COMMAND MENU (NEW)
  Sneak + use the Aegis Core to open the command UI:
    Summon Sentinel | Recall all to me | Force Nullify (all dims)
    Mode cycle (guard / hunter / passive) | HUD toggle | Dismiss all
  Modes:  guard   = relay sentinels only to protect players (default)
          hunter  = relay to ANY Locust anywhere, even unobserved
          passive = no auto-deploy / relay; still erases on contact & hit

NULL VEIL RELAY (NEW)
  Every 2 s the script sweeps all dimensions. If a Locust threatens a player
  and no sentinel covers it, an idle sentinel void-steps there (cross-dimension)
  and lands between the player and the threat. Sentinels also interpose
  themselves whenever a Locust gets within 10 blocks of a player.

HUD + CINEMATICS (NEW)
  Actionbar for players within 40 blocks: state, Veil integrity %, Null Sever
  cooldown, threat count. Null Sever shows a title card, draws a particle beam
  from the sentinel's core to every erased target, and shakes the camera.
  Energy wings unfold on the model during Overdrive / Null Sever.

VEIL REGENERATION (NEW)
  Below 30% HP the sentinel void-steps away, gains Regeneration V +
  Resistance IV for 10 s and re-engages (30 s cooldown).

OPERATOR COMMANDS
  /scriptevent aegis:help          list all commands
  /scriptevent aegis:mode <guard|hunter|passive>
  /scriptevent aegis:hud <on|off>
  /scriptevent aegis:recall        bring every sentinel to you
  /function aegis/nullify_all      erase every Locust in all dimensions now
  /function aegis/status           tracked sentinels + total erased
  /function aegis/mark_target      tag the nearest mob as a target
  /scriptevent aegis:force_nullify <radius>
  Scoreboard "aegis_erased" tracks kills; dynamic property aegis:total_erased.

PROTECTION
  Every 6 s in guard mode: Resistance II + Regeneration II + Fire Resistance to
  players within 12 blocks; Slowness/Weakness to monsters. Immune to Locust /
  horror / player damage; 500 HP, full knockback resistance, fire & lava proof,
  breathes underwater. Dies only to the void (and fades gracefully).

STATES   spawning -> guard -> overdrive (Locust < 32 blocks, boss bar,
         brighter texture, faster) -> null_sever -> overdrive/guard -> fading

COMPATIBILITY
  Works alongside Locust add-ons; it does not alter their world effects, it
  only removes the entity. Script API version: @minecraft/server 2.0.0.

CREDITS  Sanycorp / CRVX — procedural assets built by tools/ in the repository.
