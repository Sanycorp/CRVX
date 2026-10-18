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
import { ActionFormData, MessageFormData } from "@minecraft/server-ui";

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
  MELEE_BONUS_DAMAGE: 20, // extra script damage on top of the 30 BP attack vs ordinary hostiles
  AURA_INTERVAL_TICKS: 120, // 6 s
  AURA_RADIUS: 12,
  AUTO_SPAWN_ON_FIRST_DETECTION: true,
  RELAY_SCAN_TICKS: 40, // Null Veil Relay: world-wide threat sweep every 2 s
  RELAY_PLAYER_RADIUS: 48, // a Locust within this range of a player counts as a threat
  THREAT_RADIUS: 10, // Locust this close to a player => Aegis interposes itself
  HUD_TICKS: 10,
  HUD_RADIUS: 40,
  REGEN_THRESHOLD: 0.3, // Veil Regeneration below 30% HP
  REGEN_COOLDOWN_TICKS: 600,
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

// Persisted world settings ----------------------------------------------------
//  mode:  "guard"   -> relay only to protect players (default)
//         "hunter"  -> relay to ANY Locust anywhere, auto-deploy aggressively
//         "passive" -> no auto-deploy, no relay; still erases on contact/hit
const MODES = ["guard", "hunter", "passive"];
function getMode() {
  const m = world.getDynamicProperty("aegis:mode");
  return MODES.includes(m) ? m : "guard";
}
function setMode(m) {
  if (MODES.includes(m)) world.setDynamicProperty("aegis:mode", m);
}
function hudEnabled() {
  return world.getDynamicProperty("aegis:hud") !== false;
}
function allDimensions() {
  const out = [];
  for (const id of ["overworld", "nether", "the_end"]) {
    const d = safe(() => world.getDimension(id), null);
    if (d) out.push(d);
  }
  return out;
}
function allAegis() {
  const out = [];
  for (const d of allDimensions()) for (const a of safe(() => d.getEntities({ type: CONFIG.AEGIS_ID }), [])) out.push(a);
  return out;
}
function allLocusts() {
  const out = [];
  for (const d of allDimensions()) for (const e of safe(() => d.getEntities(), [])) if (isLocust(e)) out.push(e);
  return out;
}

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
  for (const tgt of targets) {
    traceBeam(dim, { x: loc.x, y: loc.y + 1.3, z: loc.z }, { x: tgt.location.x, y: tgt.location.y + 1, z: tgt.location.z });
    if (nullify(tgt, aegis, "Null Sever")) count++;
  }
  for (const p of dim.getPlayers({ location: loc, maxDistance: 32 })) {
    safe(() => p.onScreenDisplay.setTitle("§b◈ NULL SEVER", { fadeInDuration: 2, stayDuration: 18, fadeOutDuration: 10, subtitle: count > 0 ? `§7${count} signature(s) erased` : "§7no signature in range" }));
  }

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

function traceBeam(dim, from, to) {
  const d = dist(from, to);
  const steps = Math.max(2, Math.min(80, Math.floor(d / 0.6)));
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const pos = { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t, z: from.z + (to.z - from.z) * t };
    safe(() => dim.spawnParticle("aegis:beam_trace", pos));
  }
}

// ----------------------------------------------------------------------------
//  BLINK — void step toward a distant target (keeps hunting reliable even when
//  Locust ports teleport or noclip)
// ----------------------------------------------------------------------------
function blinkTo(aegis, dest, face, st) {
  if (st) st.lastBlink = system.currentTick;
  const dim = aegis.dimension;
  const a = aegis.location;
  safe(() => dim.spawnParticle("aegis:blink_out", { x: a.x, y: a.y + 1, z: a.z }));
  safe(() => dim.playSound("aegis.blink", a, { volume: 0.9, pitch: 1.0 }));
  safe(() => aegis.teleport(dest, { dimension: dest.dimension ?? dim, facingLocation: face, keepVelocity: false }));
  const d2 = dest.dimension ?? dim;
  safe(() => d2.spawnParticle("aegis:blink_in", { x: dest.x, y: dest.y + 1, z: dest.z }));
}

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
  if (!CONFIG.AUTO_SPAWN_ON_FIRST_DETECTION || getMode() === "passive") return;
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

  // Veil Regeneration: emergency disengage + heal when badly hurt.
  const hp = safe(() => aegis.getComponent("minecraft:health"), null);
  if (hp && hp.currentValue / hp.effectiveMax < CONFIG.REGEN_THRESHOLD && system.currentTick - (st.lastRegen ?? -99999) > CONFIG.REGEN_COOLDOWN_TICKS) {
    st.lastRegen = system.currentTick;
    const ang = Math.random() * Math.PI * 2;
    blinkTo(aegis, { x: loc.x + Math.cos(ang) * 10, y: loc.y, z: loc.z + Math.sin(ang) * 10 }, loc, st);
    safe(() => aegis.addEffect("regeneration", 200, { amplifier: 4, showParticles: false }));
    safe(() => aegis.addEffect("resistance", 200, { amplifier: 3, showParticles: false }));
    safe(() => aegis.triggerEvent("aegis:cast_aura"));
    safe(() => dim.spawnParticle("aegis:aura_motes", { x: aegis.location.x, y: aegis.location.y + 1, z: aegis.location.z }));
    broadcast("§eVeil integrity critical — regenerating.", aegis);
  }

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

  // Interpose: if a Locust is close to a player and the Aegis is not between
  // them, blink to the player's side facing the threat.
  if (!st.severing && system.currentTick - st.lastBlink >= 40) {
    for (const p of dim.getPlayers({ location: nearest.location, maxDistance: CONFIG.THREAT_RADIUS })) {
      if (dist(p.location, loc) > 4) {
        const dx = nearest.location.x - p.location.x, dz = nearest.location.z - p.location.z;
        const n = Math.max(0.01, Math.hypot(dx, dz));
        blinkTo(aegis, { x: p.location.x + (dx / n) * 2, y: p.location.y, z: p.location.z + (dz / n) * 2 }, nearest.location, st);
        broadcast("§7Stay behind me.", p, 8);
      }
      break;
    }
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
//  NULL VEIL RELAY — world-wide threat sweep; moves an idle Aegis to wherever a
//  Locust threatens a player (or anywhere, in hunter mode), across dimensions.
// ----------------------------------------------------------------------------
system.runInterval(() => {
  const mode = getMode();
  if (mode === "passive") return;
  const sentinels = allAegis().filter((a) => {
    const st = aegisState.get(a.id);
    return !(st && st.severing) && safe(() => a.getProperty("aegis:state"), "guard") !== "fading";
  });
  if (sentinels.length === 0) return;
  for (const locust of allLocusts()) {
    const ldim = locust.dimension;
    const covered = sentinels.some((a) => a.dimension.id === ldim.id && dist(a.location, locust.location) <= CONFIG.DETECTION_RADIUS);
    if (covered) continue;
    const players = ldim.getPlayers({ location: locust.location, maxDistance: CONFIG.RELAY_PLAYER_RADIUS });
    if (players.length === 0 && mode !== "hunter") continue;
    // pick the sentinel that is least busy (no Locust near it), prefer same dimension
    const idle = sentinels.filter((a) => findLocusts(a.location, a.dimension, CONFIG.DETECTION_RADIUS).length === 0);
    const pool = idle.length ? idle : sentinels;
    pool.sort((a, b) => (a.dimension.id === ldim.id ? 0 : 1) - (b.dimension.id === ldim.id ? 0 : 1));
    const aegis = pool[0];
    const st = aegisState.get(aegis.id) ?? { lastSever: -99999, severing: false, lastAura: 0, lastBlink: -99999 };
    aegisState.set(aegis.id, st);
    const anchor = players[0] ? players[0].location : locust.location;
    const dx = locust.location.x - anchor.x, dz = locust.location.z - anchor.z;
    const n = Math.max(0.01, Math.hypot(dx, dz));
    const dest = { x: anchor.x + (dx / n) * 3, y: anchor.y, z: anchor.z + (dz / n) * 3, dimension: ldim };
    blinkTo(aegis, dest, locust.location, st);
    safe(() => aegis.triggerEvent("aegis:enter_overdrive"));
    broadcast("§eNull Veil Relay: sentinel redeployed to threat.", players[0] ?? null);
    break; // one relay per sweep
  }
}, CONFIG.RELAY_SCAN_TICKS);

// ----------------------------------------------------------------------------
//  HUD — actionbar for players near a sentinel
// ----------------------------------------------------------------------------
system.runInterval(() => {
  if (!hudEnabled()) return;
  for (const aegis of allAegis()) {
    const st = aegisState.get(aegis.id);
    const hp = safe(() => aegis.getComponent("minecraft:health"), null);
    const veil = hp ? Math.round((hp.currentValue / hp.effectiveMax) * 100) : 100;
    const threats = findLocusts(aegis.location, aegis.dimension, CONFIG.DETECTION_RADIUS).length;
    const cdTicks = st ? Math.max(0, CONFIG.NULL_SEVER_COOLDOWN_TICKS - (system.currentTick - st.lastSever)) : 0;
    const cd = st && st.severing ? "§dCHARGING" : cdTicks > 0 ? `§e${(cdTicks / 20).toFixed(1)}s` : "§aREADY";
    const state = safe(() => aegis.getProperty("aegis:state"), "guard");
    const stateTxt = state === "overdrive" ? "§cOVERDRIVE" : state === "null_sever" ? "§dNULL SEVER" : "§bGUARD";
    const threatTxt = threats > 0 ? `§c${threats} threat${threats > 1 ? "s" : ""}` : "§7clear";
    const text = `§b◈ AEGIS §8| ${stateTxt} §8| §7Veil §f${veil}% §8| §7Null Sever ${cd} §8| ${threatTxt}`;
    for (const p of aegis.dimension.getPlayers({ location: aegis.location, maxDistance: CONFIG.HUD_RADIUS })) {
      safe(() => p.onScreenDisplay.setActionBar(text));
    }
  }
}, CONFIG.HUD_TICKS);

// ----------------------------------------------------------------------------
//  COMMAND MENU (Aegis Core while sneaking)
// ----------------------------------------------------------------------------
function openMenu(player) {
  const total = world.getDynamicProperty("aegis:total_erased") ?? 0;
  const count = allAegis().length;
  const form = new ActionFormData()
    .title("§b◈ Aegis Primordial — Command")
    .body(`§7Sentinels active: §f${count}\n§7Locusts erased: §f${total}\n§7Mode: §f${getMode()}  §7HUD: §f${hudEnabled() ? "on" : "off"}`)
    .button("§bSummon Sentinel", "textures/items/aegis_core")
    .button("§eRecall all sentinels to me")
    .button("§cForce Nullify (all dimensions)")
    .button(`§dMode: ${getMode()}  §7(cycle)`)
    .button(`§7HUD: ${hudEnabled() ? "on" : "off"}  §7(toggle)`)
    .button("§8Dismiss all sentinels");
  form.show(player).then((r) => {
    if (r.canceled || r.selection === undefined) return;
    switch (r.selection) {
      case 0:
        summonFor(player);
        break;
      case 1: {
        let n = 0;
        for (const a of allAegis()) {
          const st = aegisState.get(a.id);
          blinkTo(a, { x: player.location.x + (Math.random() - 0.5) * 4, y: player.location.y, z: player.location.z + (Math.random() - 0.5) * 4, dimension: player.dimension }, player.location, st);
          n++;
        }
        player.sendMessage(CONFIG.CHAT_PREFIX + `§7Recalled ${n} sentinel(s).`);
        break;
      }
      case 2:
        new MessageFormData().title("§cForce Nullify").body("Erase every Locust signature in all dimensions right now?").button1("§cErase").button2("Cancel").show(player).then((m) => {
          if (m.selection === 0) {
            let n = 0;
            for (const t of allLocusts()) if (nullify(t, null, "force_nullify")) n++;
            player.sendMessage(CONFIG.CHAT_PREFIX + `§7Force nullify complete: §f${n}§7 erased.`);
          }
        });
        break;
      case 3: {
        const next = MODES[(MODES.indexOf(getMode()) + 1) % MODES.length];
        setMode(next);
        player.sendMessage(CONFIG.CHAT_PREFIX + `§7Mode set to §f${next}§7.`);
        break;
      }
      case 4:
        world.setDynamicProperty("aegis:hud", !hudEnabled());
        player.sendMessage(CONFIG.CHAT_PREFIX + `§7HUD ${hudEnabled() ? "enabled" : "disabled"}.`);
        break;
      case 5:
        for (const a of allAegis()) safe(() => a.triggerEvent("aegis:begin_fade"));
        player.sendMessage(CONFIG.CHAT_PREFIX + "§7All sentinels dismissed.");
        break;
    }
  });
}

function summonFor(player) {
  const dim = player.dimension;
  const view = player.getViewDirection();
  const pos = { x: player.location.x + view.x * 2.5, y: player.location.y, z: player.location.z + view.z * 2.5 };
  const existing = dim.getEntities({ type: CONFIG.AEGIS_ID, location: pos, maxDistance: 6 });
  if (existing.length > 0) {
    player.sendMessage(CONFIG.CHAT_PREFIX + "§7A sentinel already stands here.");
    return null;
  }
  const aegis = safe(() => dim.spawnEntity(CONFIG.AEGIS_ID, pos), null);
  if (!aegis) return null;
  safe(() => aegis.lookAt(player.location));
  safe(() => player.playSound("aegis.core_activate", { volume: 1.0, pitch: 1.0 }));
  return aegis;
}

// ----------------------------------------------------------------------------
//  EVENTS
// ----------------------------------------------------------------------------

// Layer A: any Aegis hit on a Locust = instant erase.
world.afterEvents.entityHitEntity.subscribe((ev) => {
  const { damagingEntity, hitEntity } = ev;
  if (!isValid(damagingEntity) || damagingEntity.typeId !== CONFIG.AEGIS_ID) return;
  if (isLocust(hitEntity)) {
    nullify(hitEntity, damagingEntity, "melee strike");
  } else if (isValid(hitEntity) && !isProtected(hitEntity)) {
    // Ordinary hostiles: guaranteed heavy strike + knock-up, bypassing armor quirks.
    safe(() => hitEntity.applyDamage(CONFIG.MELEE_BONUS_DAMAGE, { cause: EntityDamageCause.entityAttack, damagingEntity }));
    safe(() => hitEntity.applyKnockback({ x: hitEntity.location.x - damagingEntity.location.x, z: hitEntity.location.z - damagingEntity.location.z }, 0.45));
    safe(() => damagingEntity.dimension.spawnParticle("aegis:melee_impact", { x: hitEntity.location.x, y: hitEntity.location.y + 1, z: hitEntity.location.z }));
  }
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
      case "aegis:mode": {
        if (MODES.includes(message)) {
          setMode(message);
          broadcast(`Mode set to §f${message}§7.`);
        } else broadcast(`§cUnknown mode. Use: ${MODES.join(" | ")}`);
        break;
      }
      case "aegis:hud":
        world.setDynamicProperty("aegis:hud", message !== "off");
        broadcast(`HUD ${hudEnabled() ? "enabled" : "disabled"}.`);
        break;
      case "aegis:recall": {
        const p = isValid(sourceEntity) ? sourceEntity : null;
        if (!p) break;
        for (const a of allAegis()) blinkTo(a, { x: p.location.x, y: p.location.y, z: p.location.z, dimension: p.dimension }, p.location, aegisState.get(a.id));
        break;
      }
      case "aegis:help":
        broadcast(
          "§7Commands:\n§f/scriptevent aegis:status§7 — overview\n§f/scriptevent aegis:force_nullify <radius|0>§7 — erase Locusts\n§f/scriptevent aegis:mode guard|hunter|passive§7\n§f/scriptevent aegis:hud on|off§7\n§f/scriptevent aegis:recall§7 — bring sentinels to you\n§7Sneak + use Aegis Core opens the command menu."
        );
        break;
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
      if (player.isSneaking) {
        system.run(() => openMenu(player));
        return;
      }
      const aegis = summonFor(player);
      if (!aegis) return;
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
