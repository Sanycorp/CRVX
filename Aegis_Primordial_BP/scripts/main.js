// ============================================================================
//  AEGIS PRIMORDIAL — SENTINEL OF THE NULL VEIL
//  Script API core (@minecraft/server 2.0.0, Minecraft Bedrock 1.21.80+)
//
//  This module is the authoritative "kill-immunity bypass".  Behaviour-pack
//  JSON handles pathing / animation / targeting; this script guarantees that
//  any Locust variant is ERASED regardless of damage_sensor, min-health lock
//  or /kill immunity, by using Entity.remove() — which is a world-level
//  despawn that never consults the entity's health or damage components.
//
//  Layers (all active simultaneously):
//    A. Melee / Null Sever hits (entityHitEntity) -> immediate nullify
//    B. BP animation-controller & events -> /scriptevent aegis:* -> nullify
//    C. Periodic proximity scan around every Aegis -> nullify within radius
//    D. Null Sever cinematic (charge -> release -> erase in 16-block radius)
//    E. World-wide first-detection auto-spawn of an Aegis near the player
//    F. Continuous fallback: override-cause damage + forced event + remove()
// ============================================================================

import {
  world,
  system,
  EntityDamageCause,
  EquipmentSlot,
  ItemStack,
  GameMode,
} from "@minecraft/server";

// ----------------------------------------------------------------------------
//  CONFIGURATION
// ----------------------------------------------------------------------------
export const CONFIG = Object.freeze({
  AEGIS_ID: "aegis:primordial_sentinel",
  CORE_ITEM_ID: "aegis:aegis_core",

  // Exact identifiers of known Locust ports (lower-cased). Substring matching
  // below covers unknown ports, so this list only needs to be "best effort".
  LOCUST_TYPE_IDS: [
    "locust:locust",
    "locust:the_locust",
    "the_locust:locust",
    "the_locust:the_locust",
    "doctor_nowhere:locust",
    "doctor_nowhere:the_locust",
    "doctornowhere:locust",
    "dn:locust",
    "nowhere:locust",
    "toe:locust",
    "toe:the_locust",
    "theory_of_everything:locust",
    "locust_evolution:locust",
    "evolution:locust",
    "horror:locust",
    "sm:locust",
    "mc:locust",
  ],

  // Substrings searched inside typeId, nameTag, and family list.
  LOCUST_SUBSTRINGS: ["locust", "the_locust", "doctor_nowhere", "doctornowhere", "t.o.e", "toe_locust"],

  // Type families that mark an entity as a valid nullification target.
  LOCUST_FAMILIES: ["locust", "the_locust", "locust_evolution", "nowhere", "doctor_nowhere", "toe", "anomaly"],

  // Manual override: /tag <entity> add aegis_target
  TARGET_TAG: "aegis_target",

  // Never touch these.
  PROTECTED_TYPES: ["minecraft:player", "aegis:primordial_sentinel", "minecraft:item", "minecraft:xp_orb"],
  PROTECTED_FAMILIES: ["aegis", "player", "player_protector"],

  SCAN_INTERVAL_TICKS: 6, // ~3x per second
  DETECTION_RADIUS: 64, // blocks — script-side awareness
  OVERDRIVE_RADIUS: 32, // enter overdrive when a Locust is this close
  BLINK_RADIUS: 18, // blink (short-range void teleport) toward target if further than this
  NULL_SEVER_TRIGGER_RADIUS: 12, // begin Null Sever when target within this range
  NULL_SEVER_ERASE_RADIUS: 16, // every Locust inside this radius at release is erased
  NULL_SEVER_COOLDOWN_TICKS: 200, // 10 s
  NULL_SEVER_RELEASE_DELAY_TICKS: 28, // cinematic delay (matches 1.4 s charge animation)
  PROXIMITY_ERASE_RADIUS: 4.5, // touching a Locust is enough — it is erased on contact
  AURA_INTERVAL_TICKS: 120, // 6 s
  AURA_RADIUS: 12,
  AUTO_SPAWN_ON_FIRST_DETECTION: true,
  AUTO_SPAWN_COOLDOWN_TICKS: 1200, // 60 s
  CHAT_PREFIX: "§b[Aegis]§r ",
});

// ----------------------------------------------------------------------------
//  STATE
// ----------------------------------------------------------------------------
/** @type {Map<string, {lastSever:number, severing:boolean, lastAura:number, lastBlink:number}>} */
const aegisState = new Map();
let lastAutoSpawnTick = -999999;
let totalErased = 0;

// ----------------------------------------------------------------------------
//  UTILITIES
// ----------------------------------------------------------------------------
function safe(fn, fallback = undefined) {
  try {
    return fn();
  } catch {
    return fallback;
  }
}

function isValid(entity) {
  return !!entity && safe(() => entity.isValid, false) === true;
}

function dist(a, b) {
  const dx = a.x - b.x,
    dy = a.y - b.y,
    dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function broadcast(msg, near = null, radius = 48) {
  const text = CONFIG.CHAT_PREFIX + msg;
  try {
    if (near) {
      for (const p of near.dimension.getPlayers({ location: near.location, maxDistance: radius })) {
        p.sendMessage(text);
      }
    } else {
      world.sendMessage(text);
    }
  } catch {}
}

function getObjective() {
  let obj = world.scoreboard.getObjective("aegis_erased");
  if (!obj) obj = world.scoreboard.addObjective("aegis_erased", "§bLocusts Erased by Aegis");
  return obj;
}

function recordErase(aegis, target) {
  totalErased++;
  world.setDynamicProperty("aegis:total_erased", totalErased);
  safe(() => {
    const obj = getObjective();
    obj.setScore("§bTotal", (safe(() => obj.getScore("§bTotal"), 0) ?? 0) + 1);
    if (isValid(aegis)) obj.setScore(aegis, (safe(() => obj.getScore(aegis), 0) ?? 0) + 1);
  });
  if (isValid(aegis)) {
    safe(() => aegis.setProperty("aegis:erased", (aegis.getProperty("aegis:erased") ?? 0) + 1));
  }
}

// ----------------------------------------------------------------------------
//  LOCUST CLASSIFICATION
// ----------------------------------------------------------------------------
function isProtected(entity) {
  const typeId = safe(() => entity.typeId, "") ?? "";
  if (CONFIG.PROTECTED_TYPES.includes(typeId)) return true;
  const fams = safe(() => entity.getComponent("minecraft:type_family")?.getTypeFamilies(), []) ?? [];
  return fams.some((f) => CONFIG.PROTECTED_FAMILIES.includes(f));
}

export function isLocust(entity) {
  if (!isValid(entity) || isProtected(entity)) return false;

  const typeId = (safe(() => entity.typeId, "") ?? "").toLowerCase();
  if (CONFIG.LOCUST_TYPE_IDS.includes(typeId)) return true;
  if (CONFIG.LOCUST_SUBSTRINGS.some((s) => typeId.includes(s))) return true;

  if (safe(() => entity.hasTag(CONFIG.TARGET_TAG), false)) return true;
  if (safe(() => entity.hasTag("locust"), false)) return true;

  const nameTag = (safe(() => entity.nameTag, "") ?? "").toLowerCase();
  if (nameTag && CONFIG.LOCUST_SUBSTRINGS.some((s) => nameTag.includes(s))) return true;

  const fams = safe(() => entity.getComponent("minecraft:type_family")?.getTypeFamilies(), []) ?? [];
  for (const f of fams) {
    const lf = f.toLowerCase();
    if (CONFIG.LOCUST_FAMILIES.includes(lf)) return true;
    if (lf.includes("locust")) return true;
  }
  return false;
}

function findLocusts(center, dimension, radius) {
  const out = [];
  let ents = [];
  try {
    ents = dimension.getEntities({ location: center, maxDistance: radius });
  } catch {
    return out;
  }
  for (const e of ents) if (isLocust(e)) out.push(e);
  return out;
}

// ----------------------------------------------------------------------------
//  THE NULLIFY ROUTINE — ERASES ANY LOCUST REGARDLESS OF INVULNERABILITY
// ----------------------------------------------------------------------------
export function nullify(target, aegis, reason = "null_sever") {
  if (!isValid(target) || isProtected(target)) return false;

  const typeId = safe(() => target.typeId, "unknown");
  const loc = safe(() => ({ ...target.location }), null);
  const dim = safe(() => target.dimension, null);

  // Layer F-1: override-cause damage (bypasses most damage_sensor filters).
  safe(() => target.applyDamage(1_000_000, { cause: EntityDamageCause.override, damagingEntity: aegis }));
  safe(() => target.applyDamage(1_000_000, { cause: EntityDamageCause.selfDestruct }));

  // Layer F-2: forced despawn events many ports expose.
  for (const ev of ["aegis:force_nullify", "minecraft:despawn", "despawn", "minecraft:entity_despawn", "instant_despawn"]) {
    safe(() => target.triggerEvent(ev));
  }

  // Layer F-3: THE GUARANTEE. Entity.remove() is a world-level removal that
  // does not consult health, damage_sensor, min-health locks or /kill rules.
  let removed = false;
  try {
    target.remove();
    removed = true;
  } catch {
    // Some entities throw if already being removed; re-check validity.
    removed = !isValid(target);
  }
  if (!removed) {
    // Last resort: schedule repeated removal attempts.
    let attempts = 0;
    const id = system.runInterval(() => {
      attempts++;
      if (!isValid(target) || attempts > 20) {
        system.clearRun(id);
        return;
      }
      safe(() => target.kill());
      safe(() => target.remove());
    }, 2);
  }

  // FX + feedback
  if (dim && loc) {
    safe(() => dim.spawnParticle("aegis:void_tear", { x: loc.x, y: loc.y + 1, z: loc.z }));
    safe(() => dim.spawnParticle("aegis:erase_burst", { x: loc.x, y: loc.y + 1, z: loc.z }));
    safe(() => dim.playSound("aegis.null_sever.tear", loc, { volume: 1.2, pitch: 1.0 }));
    safe(() => dim.playSound("aegis.null_sever.confirm", loc, { volume: 1.0, pitch: 1.0 }));
    safe(() => dim.playSound("aegis.vo.erased", loc, { volume: 1.0, pitch: 1.0 }));
  }
  recordErase(aegis, target);
  broadcast(`Null Sever executed. Target erased. §8(${typeId}, via ${reason})`, isValid(aegis) ? aegis : null);
  return true;
}

// ----------------------------------------------------------------------------
//  NULL SEVER CINEMATIC
// ----------------------------------------------------------------------------
function beginNullSever(aegis, st) {
  if (st.severing) return;
  st.severing = true;
  st.lastSever = system.currentTick;

  // Put the entity into the null_sever component group (locks movement, plays
  // RP animation through the synced property, fires queue_command FX).
  safe(() => aegis.triggerEvent("aegis:activate_null_sever"));
  // In case the BP event filter rejected it (e.g. no JSON target yet), force state.
  safe(() => aegis.setProperty("aegis:state", "null_sever"));
  safe(() => aegis.setProperty("aegis:glow", 1.0));

  const dim = aegis.dimension;
  const origin = { ...aegis.location };

  // Charge-up ring of particles for the duration of the delay.
  let t = 0;
  const chargeId = system.runInterval(() => {
    t += 4;
    if (!isValid(aegis) || t > CONFIG.NULL_SEVER_RELEASE_DELAY_TICKS) {
      system.clearRun(chargeId);
      return;
    }
    const l = aegis.location;
    safe(() => dim.spawnParticle("aegis:null_sever_charge", { x: l.x, y: l.y + 1.3, z: l.z }));
  }, 4);

  system.runTimeout(() => {
    st.severing = false;
    if (!isValid(aegis)) return;
    releaseNullSever(aegis, origin);
  }, CONFIG.NULL_SEVER_RELEASE_DELAY_TICKS);
}

function releaseNullSever(aegis, origin) {
  const dim = aegis.dimension;
  const loc = aegis.location;

  safe(() => dim.spawnParticle("aegis:null_sever_shockwave", { x: loc.x, y: loc.y + 0.1, z: loc.z }));
  safe(() => dim.spawnParticle("aegis:null_sever_slash", { x: loc.x, y: loc.y + 1.3, z: loc.z }));
  safe(() => dim.playSound("aegis.null_sever.release", loc, { volume: 1.3, pitch: 1.0 }));
  safe(() => aegis.runCommand("camerashake add @a[r=24] 0.45 0.7 positional"));

  const targets = findLocusts(loc, dim, CONFIG.NULL_SEVER_ERASE_RADIUS);
  let count = 0;
  for (const tgt of targets) if (nullify(tgt, aegis, "Null Sever")) count++;

  // Restore state
  safe(() => aegis.triggerEvent("aegis:null_sever_complete"));
  if (count > 0) {
    system.runTimeout(() => {
      if (!isValid(aegis)) return;
      const remaining = findLocusts(aegis.location, aegis.dimension, CONFIG.DETECTION_RADIUS);
      if (remaining.length === 0) {
        safe(() => aegis.triggerEvent("aegis:return_to_guard"));
        safe(() => dim.playSound("aegis.vo.secured", aegis.location, { volume: 1.0, pitch: 1.0 }));
        broadcast("Area secured. §8No remaining Locust signatures within 64 blocks.", aegis);
      }
    }, 40);
  } else {
    safe(() => aegis.triggerEvent("aegis:return_to_guard"));
  }
}

// ----------------------------------------------------------------------------
//  BLINK — void step toward a distant target (keeps hunting reliable even when
//  Locust ports teleport or noclip)
// ----------------------------------------------------------------------------
function blinkToward(aegis, target, st) {
  if (system.currentTick - st.lastBlink < 40) return;
  st.lastBlink = system.currentTick;
  const a = aegis.location,
    b = target.location;
  const d = dist(a, b);
  const landing = CONFIG.NULL_SEVER_TRIGGER_RADIUS - 4; // land inside Null Sever range, outside contact range
  if (d <= landing) return;
  const f = (d - landing) / d;
  const dest = { x: a.x + (b.x - a.x) * f, y: b.y, z: a.z + (b.z - a.z) * f };
  const dim = aegis.dimension;
  safe(() => dim.spawnParticle("aegis:blink_out", { x: a.x, y: a.y + 1, z: a.z }));
  safe(() => dim.playSound("aegis.blink", a, { volume: 0.9, pitch: 1.0 }));
  safe(() => aegis.teleport(dest, { dimension: dim, facingLocation: b, keepVelocity: false }));
  safe(() => dim.spawnParticle("aegis:blink_in", { x: dest.x, y: dest.y + 1, z: dest.z }));
}

// ----------------------------------------------------------------------------
//  PROTECTIVE AURA
// ----------------------------------------------------------------------------
function pulseAura(aegis, st) {
  st.lastAura = system.currentTick;
  const dim = aegis.dimension;
  const loc = aegis.location;
  for (const p of dim.getPlayers({ location: loc, maxDistance: CONFIG.AURA_RADIUS })) {
    safe(() => p.addEffect("resistance", 200, { amplifier: 1, showParticles: false }));
    safe(() => p.addEffect("regeneration", 160, { amplifier: 1, showParticles: false }));
    safe(() => p.addEffect("fire_resistance", 200, { amplifier: 0, showParticles: false }));
  }
  // Weaken hostile horrors nearby (non-Locust; Locusts are simply erased).
  for (const e of dim.getEntities({ location: loc, maxDistance: CONFIG.AURA_RADIUS, families: ["monster"] })) {
    safe(() => e.addEffect("slowness", 120, { amplifier: 2, showParticles: false }));
    safe(() => e.addEffect("weakness", 120, { amplifier: 2, showParticles: false }));
  }
  safe(() => aegis.triggerEvent("aegis:cast_aura"));
  safe(() => dim.spawnParticle("aegis:aura_ring", { x: loc.x, y: loc.y + 0.1, z: loc.z }));
}

// ----------------------------------------------------------------------------
//  AUTO-SPAWN ON FIRST DETECTION
// ----------------------------------------------------------------------------
function maybeAutoSpawn(locust) {
  if (!CONFIG.AUTO_SPAWN_ON_FIRST_DETECTION) return;
  if (system.currentTick - lastAutoSpawnTick < CONFIG.AUTO_SPAWN_COOLDOWN_TICKS) return;
  const dim = locust.dimension;
  const existing = dim.getEntities({ type: CONFIG.AEGIS_ID, location: locust.location, maxDistance: 96 });
  if (existing.length > 0) return;
  const players = dim.getPlayers({ location: locust.location, maxDistance: 96 });
  if (players.length === 0) return;
  const p = players[0];
  const view = p.getViewDirection();
  const pos = { x: p.location.x - view.x * 2, y: p.location.y, z: p.location.z - view.z * 2 };
  lastAutoSpawnTick = system.currentTick;
  const aegis = safe(() => dim.spawnEntity(CONFIG.AEGIS_ID, pos), null);
  if (aegis) {
    broadcast("§eLocust anomaly detected. Emergency deployment authorised.", p);
  }
}

// ----------------------------------------------------------------------------
//  MAIN TICK — proximity scan around every Aegis
// ----------------------------------------------------------------------------
function tickAegis(aegis) {
  const id = aegis.id;
  let st = aegisState.get(id);
  if (!st) {
    st = { lastSever: -99999, severing: false, lastAura: system.currentTick, lastBlink: -99999 };
    aegisState.set(id, st);
  }
  const state = safe(() => aegis.getProperty("aegis:state"), "guard");
  if (state === "spawning" || state === "fading") return;

  const dim = aegis.dimension;
  const loc = aegis.location;
  const locusts = findLocusts(loc, dim, CONFIG.DETECTION_RADIUS);

  if (locusts.length === 0) {
    if (state === "overdrive") safe(() => aegis.triggerEvent("aegis:return_to_guard"));
    if (system.currentTick - st.lastAura >= CONFIG.AURA_INTERVAL_TICKS && state === "guard") pulseAura(aegis, st);
    return;
  }

  // Nearest first
  locusts.sort((a, b) => dist(a.location, loc) - dist(b.location, loc));
  const nearest = locusts[0];
  const d = dist(nearest.location, loc);

  // Layer C: contact erase
  for (const l of locusts) {
    if (dist(l.location, loc) <= CONFIG.PROXIMITY_ERASE_RADIUS) nullify(l, aegis, "proximity");
  }
  if (!isValid(nearest)) return;

  if (d <= CONFIG.OVERDRIVE_RADIUS && state === "guard") {
    safe(() => aegis.triggerEvent("aegis:enter_overdrive"));
  }

  // Continuous soft tracking: face the target, blink if it is far.
  if (!st.severing) {
    safe(() => aegis.lookAt(nearest.location));
    // Blink immediately if far; if merely out of Null Sever range, give BP
    // pathfinding ~4 s to close in, then blink anyway (stall-proof against
    // flying / noclipping / teleporting Locust ports).
    if (d > CONFIG.BLINK_RADIUS || (d > CONFIG.NULL_SEVER_TRIGGER_RADIUS && system.currentTick - st.lastBlink >= 80)) {
      blinkToward(aegis, nearest, st);
    }
  }

  // Layer D: Null Sever when in range and off cooldown.
  if (
    !st.severing &&
    d <= CONFIG.NULL_SEVER_TRIGGER_RADIUS &&
    system.currentTick - st.lastSever >= CONFIG.NULL_SEVER_COOLDOWN_TICKS
  ) {
    beginNullSever(aegis, st);
  }
}

system.runInterval(() => {
  for (const dimId of ["overworld", "nether", "the_end"]) {
    let dim;
    try {
      dim = world.getDimension(dimId);
    } catch {
      continue;
    }
    let aegisList = [];
    try {
      aegisList = dim.getEntities({ type: CONFIG.AEGIS_ID });
    } catch {
      continue;
    }
    for (const a of aegisList) {
      try {
        tickAegis(a);
      } catch (err) {
        console.warn(`[Aegis] tick error: ${err}`);
      }
    }
  }
  // Housekeeping
  if (system.currentTick % 200 === 0) {
    for (const [id] of aegisState) {
      if (!isValid(safe(() => world.getEntity(id), null))) aegisState.delete(id);
    }
  }
}, CONFIG.SCAN_INTERVAL_TICKS);

// ----------------------------------------------------------------------------
//  EVENTS
// ----------------------------------------------------------------------------

// Layer A: any Aegis hit on a Locust = instant erase.
world.afterEvents.entityHitEntity.subscribe((ev) => {
  const { damagingEntity, hitEntity } = ev;
  if (!isValid(damagingEntity) || damagingEntity.typeId !== CONFIG.AEGIS_ID) return;
  if (isLocust(hitEntity)) nullify(hitEntity, damagingEntity, "melee strike");
});

// Also cover damage routed through BP attack component.
world.afterEvents.entityHurt.subscribe((ev) => {
  const src = ev.damageSource?.damagingEntity;
  if (!isValid(src) || src.typeId !== CONFIG.AEGIS_ID) return;
  if (isLocust(ev.hurtEntity)) nullify(ev.hurtEntity, src, "strike");
});

// Protect the Aegis: if something tries to make it die, we handle graceful fade.
world.afterEvents.entityDie.subscribe((ev) => {
  const e = ev.deadEntity;
  if (!isValid(e)) return;
  if (isLocust(e)) recordErase(null, e);
});

// Layer E: detect Locust spawns (auto-deploy an Aegis).
world.afterEvents.entitySpawn.subscribe((ev) => {
  const e = ev.entity;
  if (!isValid(e)) return;
  if (e.typeId === CONFIG.AEGIS_ID) {
    aegisState.set(e.id, { lastSever: -99999, severing: false, lastAura: system.currentTick, lastBlink: -99999 });
    system.runTimeout(() => {
      if (isValid(e)) safe(() => e.dimension.playSound("aegis.vo.online", e.location, { volume: 1.0, pitch: 1.0 }));
    }, 30);
    return;
  }
  if (isLocust(e)) {
    broadcast("§cLocust signature detected.§r §8" + e.typeId);
    maybeAutoSpawn(e);
  }
});

// Layer B: script events from BP animation controllers / events / commands.
system.afterEvents.scriptEventReceive.subscribe(
  (ev) => {
    const { id, message, sourceEntity } = ev;
    switch (id) {
      case "aegis:null_sever": {
        if (!isValid(sourceEntity) || sourceEntity.typeId !== CONFIG.AEGIS_ID) return;
        const st = aegisState.get(sourceEntity.id);
        if (message === "release") {
          // Controller-driven release path (works even if script timer drifted)
          const targets = findLocusts(sourceEntity.location, sourceEntity.dimension, CONFIG.NULL_SEVER_ERASE_RADIUS);
          for (const t of targets) nullify(t, sourceEntity, "Null Sever (controller)");
        } else if (message === "begin" && st) {
          beginNullSever(sourceEntity, st);
        }
        break;
      }
      case "aegis:melee_hit": {
        if (!isValid(sourceEntity)) return;
        const targets = findLocusts(sourceEntity.location, sourceEntity.dimension, 5);
        for (const t of targets) nullify(t, sourceEntity, "melee");
        break;
      }
      case "aegis:force_nullify": {
        // /scriptevent aegis:force_nullify [radius]   (usable by operators)
        const radius = Number(message) > 0 ? Number(message) : 64;
        const center = isValid(sourceEntity) ? sourceEntity : null;
        let n = 0;
        if (center) {
          for (const t of findLocusts(center.location, center.dimension, radius)) if (nullify(t, center, "force_nullify")) n++;
        } else {
          for (const dimId of ["overworld", "nether", "the_end"]) {
            const dim = safe(() => world.getDimension(dimId), null);
            if (!dim) continue;
            for (const t of dim.getEntities()) if (isLocust(t) && nullify(t, null, "force_nullify")) n++;
          }
        }
        broadcast(`Force nullify complete. §8${n} target(s) erased.`);
        break;
      }
      case "aegis:aura": {
        if (!isValid(sourceEntity)) return;
        const st = aegisState.get(sourceEntity.id);
        if (st) pulseAura(sourceEntity, st);
        break;
      }
      case "aegis:status": {
        const total = world.getDynamicProperty("aegis:total_erased") ?? 0;
        broadcast(`Status: §f${aegisState.size}§7 sentinel(s) tracked, §f${total}§7 Locust(s) erased this world.`);
        break;
      }
      case "aegis:register":
      case "aegis:overdrive":
      default:
        break;
    }
  },
  { namespaces: ["aegis"] }
);

// ----------------------------------------------------------------------------
//  CUSTOM ITEM COMPONENT — "Aegis Core" summons the sentinel on use
// ----------------------------------------------------------------------------
system.beforeEvents.startup.subscribe((ev) => {
  ev.itemComponentRegistry.registerCustomComponent("aegis:summon_core", {
    onUse(e) {
      const player = e.source;
      if (!isValid(player)) return;
      const dim = player.dimension;
      const view = player.getViewDirection();
      const pos = {
        x: player.location.x + view.x * 2.5,
        y: player.location.y,
        z: player.location.z + view.z * 2.5,
      };
      const existing = dim.getEntities({ type: CONFIG.AEGIS_ID, location: pos, maxDistance: 6 });
      if (existing.length > 0) {
        player.sendMessage(CONFIG.CHAT_PREFIX + "§7A sentinel already stands here.");
        return;
      }
      const aegis = safe(() => dim.spawnEntity(CONFIG.AEGIS_ID, pos), null);
      if (!aegis) return;
      safe(() => aegis.lookAt(player.location));
      safe(() => player.playSound("aegis.core_activate", { volume: 1.0, pitch: 1.0 }));
      // Consume one core (not in creative)
      if (safe(() => player.getGameMode(), GameMode.Creative) !== GameMode.Creative) {
        const inv = player.getComponent("minecraft:equippable");
        const stack = inv?.getEquipment(EquipmentSlot.Mainhand);
        if (stack && stack.typeId === CONFIG.CORE_ITEM_ID) {
          const next = stack.amount > 1 ? new ItemStack(stack.typeId, stack.amount - 1) : undefined;
          inv.setEquipment(EquipmentSlot.Mainhand, next);
        }
      }
    },
  });
});

world.afterEvents.worldLoad.subscribe(() => {
  totalErased = world.getDynamicProperty("aegis:total_erased") ?? 0;
  console.log("[Aegis Primordial] Null Veil protocol loaded. Erased so far: " + totalErased);
});
