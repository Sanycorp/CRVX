/* =========================================================================
   AEGIS-PRIMORDIAL :: NULL VEIL SENTINEL
   Behavior script — the reason this pack exists.

   The Locust cannot be killed with /kill because its own behaviour pack
   cancels the damage (damage_sensor / min_health / invulnerable flags).
   Entity.remove() does not go through the damage pipeline at all, so it is
   the only reliable way to erase it. This script:

     * scans for any entity whose identifier / tag / name-tag looks like a
       Locust (case-insensitive, keyword driven so it works with every
       Locust add-on),
     * drives the sentinel's stance (guard / combat / overdrive) and its
       attack + Null Sever animations through synced entity properties,
     * force-removes the anomaly on Null Sever or after sustained melee
       pressure, with particles, sound and a chat report,
     * protects the player: guardian aura, Void Pulse, Void Step pursuit
       and an auto-deploy when an anomaly is first detected.

   Commands (works in any world, no experiments needed for the script):
     /scriptevent aegis:summon            spawn a sentinel at yourself
     /scriptevent aegis:summon 3          spawn three
     /scriptevent aegis:purge             erase every detected anomaly
     /scriptevent aegis:scan              list what it can see
     /scriptevent aegis:status            sentinel status
     /scriptevent aegis:config reload     re-read CONFIG at runtime
   ========================================================================= */

import { world, system } from "@minecraft/server";

/* ------------------------------------------------------------------ config */
const CONFIG = {
  // The sentinel itself
  entityType: "aegis:primordial_sentinel",

  // Case-insensitive substrings matched against identifier, tags and name tag.
  // Add your own Locust identifier here if it is not covered.
  locustKeywords: [
    "locust",
    "the_locust",
    "toe_locust",
    "doctor_nowhere",
    "nowhere",
    "hopal",
    "anomaly",
    "null_veiler_hostile",
  ],
  // Never ever remove these, whatever they are called.
  protectedKeywords: ["aegis", "player"],

  // Ranges (blocks)
  detectRadius: 96,      // how far around a player we look for anomalies
  overdriveRange: 32,    // Locust closer than this  -> Overdrive
  severRange: 14,        // Null Sever reach
  meleeRange: 4.2,       // counts as "landed a hit"
  auraRadius: 12,        // Guardian Aura radius
  pulseRadius: 8,        // Void Pulse radius
  stepMin: 16,           // Void Step engages further than this...
  stepMax: 72,           // ...and no further than this
  chatRadius: 32,        // who gets the report

  // Timing (ticks; 20 ticks = 1 second)
  scanInterval: 10,
  auraInterval: 80,      // every 4 s
  severCooldown: 240,    // 12 s
  pulseCooldown: 120,    // 6 s
  stepCooldown: 140,     // 7 s
  meleeCooldown: 18,
  severChargeTicks: 50,  // 2.5 s charge animation
  severHoldTicks: 30,    // 1.5 s release animation
  punchTicks: 18,
  slashTicks: 22,

  // Melee hits needed on an anomaly before it is force-erased
  hitsToErase: 2,

  // Abilities
  autoDeploy: true,      // summon a sentinel when an anomaly is first seen
  maxSentinels: 2,
  guardianAura: true,
  voidPulse: true,
  voidStep: true,

  // Effects handed to protected players (duration in ticks, 0 = level I)
  auraRegenTicks: 120,
  auraResistTicks: 120,
  auraAmplifier: 0,      // 0 = I, 1 = II

  debug: false
};

const PREFIX = "§b§l[Aegis]§r ";

/* --------------------------------------------------------------- utilities */
/** distance between two {x,y,z} */
function dist(a, b) {
  const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function msg(text, dimension, location, radius) {
  try {
    if (!dimension) { world.sendMessage(text); return; }
    const near = dimension.getPlayers({
      location: location,
      maxDistance: radius === undefined ? CONFIG.chatRadius : radius
    });
    if (near.length === 0) world.sendMessage(text);
    for (const p of near) p.sendMessage(text);
  } catch (_) {
    try { world.sendMessage(text); } catch (__) { /* ignore */ }
  }
}

function log(text) {
  if (CONFIG.debug) console.warn("[aegis] " + text);
}

/* --------------------------------------------------------------- scheduler */
/* A tiny tick scheduler built on system.run only, so it works on every
   @minecraft/server version (no dependency on runInterval/runTimeout). */
const jobs = [];
let clock = 0;

function schedule(delayTicks, fn) {
  jobs.push({ due: clock + Math.max(0, delayTicks | 0), fn });
}

function runScheduler() {
  for (let i = jobs.length - 1; i >= 0; i--) {
    if (clock >= jobs[i].due) {
      const job = jobs[i];
      jobs.splice(i, 1);
      try { job.fn(); } catch (e) { log("job failed: " + e); }
    }
  }
}

/* ------------------------------------------------------------ anomaly tests */
function matches(entity, keywords) {
  let id = "";
  try { id = (entity.typeId || "").toLowerCase(); } catch (_) { return false; }
  for (const k of keywords) if (id.indexOf(k) !== -1) return true;

  try {
    for (const tag of entity.getTags()) {
      const t = String(tag).toLowerCase();
      for (const k of keywords) if (t.indexOf(k) !== -1) return true;
    }
  } catch (_) { /* no tags */ }

  try {
    const n = (entity.nameTag || "").toLowerCase();
    if (n) for (const k of keywords) if (n.indexOf(k) !== -1) return true;
  } catch (_) { /* no name tag */ }

  return false;
}

function isLocust(entity) {
  if (!entity) return false;
  try { if (!entity.isValid()) return false; } catch (_) { return false; }
  if (matches(entity, CONFIG.protectedKeywords)) return false;   // safety first
  return matches(entity, CONFIG.locustKeywords);
}

function isSentinel(entity) {
  if (!entity) return false;
  try {
    if (!entity.isValid()) return false;
    return entity.typeId === CONFIG.entityType;
  } catch (_) { return false; }
}

/* --------------------------------------------------------- force erasure */
let erasedCount = 0;

function eraseAnomaly(entity, dimension, reason) {
  if (!entity) return false;
  try { if (!entity.isValid()) return false; } catch (_) { return false; }
  if (!isLocust(entity)) return false;

  let loc = null;
  try { loc = entity.location; } catch (_) { return false; }

  const name = (function () {
    try { return entity.nameTag || entity.typeId; } catch (_) { return "anomaly"; }
  })();

  // Pre-erasure flourishes (wrapped: never let cosmetics block the removal)
  try { if (dimension) dimension.spawnParticle("aegis:death_dissolve", loc); } catch (_) {}
  try { if (dimension) dimension.spawnParticle("aegis:null_sever_blast", loc); } catch (_) {}
  try {
    if (dimension) dimension.playSound("aegis.null_sever_release", loc, {
      volume: 1.0, pitch: 0.85
    });
  } catch (_) {}

  try { entity.addTag("aegis_nullified"); } catch (_) {}
  try { entity.triggerEvent("aegis:force_nullify_target"); } catch (_) {}

  // The actual erasure. kill() first (it runs death logic where it can),
  // then remove() which bypasses damage_sensor, min_health and invulnerability.
  let removed = false;
  try { entity.kill(); } catch (_) { /* older API, ignore */ }
  try { entity.remove(); removed = true; } catch (e) {
    log("remove() failed: " + e);
  }

  if (removed) {
    erasedCount++;
    msg(PREFIX + "§bNull Sever complete.§r Anomaly erased (§7" + name + "§r).",
      dimension, loc, CONFIG.chatRadius);
    log("erased " + name + " via " + reason);
  }
  return removed;
}

/* ------------------------------------------------------- sentinel registry */
const sentinels = new Map();   // id -> { id, mode, attack, readyAt:{} }

function registry(id) {
  let s = sentinels.get(id);
  if (!s) {
    s = {
      id: id,
      mode: -1,
      attack: -1,
      severAt: 0,
      pulseAt: 0,
      stepAt: 0,
      meleeAt: 0,
      auraAt: 0,
      busyUntil: 0,
      lastMove: 0
    };
    sentinels.set(id, s);
  }
  return s;
}

function setMode(entity, mode) {
  return setProp(entity, "aegis:mode", mode, "mode");
}
function setAttack(entity, attack) {
  return setProp(entity, "aegis:attack", attack, "attack");
}
function setProp(entity, prop, value, slot) {
  if (!entity) return false;
  const s = registry(entity.id);
  if (s[slot] === value) return true;             // already there
  const events = {
    mode: ["aegis:return_guard", "aegis:enter_combat", "aegis:overdrive_enter", "aegis:overdrive_hold"],
    attack: ["aegis:attack_clear", "aegis:attack_punch", "aegis:attack_slash", "aegis:null_sever_charge", "aegis:null_sever_release"]
  }[slot];
  const ev = events[value];
  try {
    if (ev) entity.triggerEvent(ev);
    s[slot] = value;
    return true;
  } catch (e) {
    log("triggerEvent " + ev + " failed: " + e);
    return false;
  }
}

/* ------------------------------------------------------------- melee cycle */
const hitCounts = new Map();   // locust id -> hits

function registerHit(entity, dimension) {
  if (!isLocust(entity)) return;
  const id = entity.id;
  const n = (hitCounts.get(id) || 0) + 1;
  hitCounts.set(id, n);
  log("hit " + n + "/" + CONFIG.hitsToErase + " on anomaly " + id);
  if (n >= CONFIG.hitsToErase) {
    hitCounts.delete(id);
    schedule(8, () => eraseAnomaly(entity, dimension, "melee pressure"));
  }
}

/* ------------------------------------------------------------- Void Pulse */
function voidPulse(sentinel, dimension, loc, targets) {
  const s = registry(sentinel.id);
  if (clock < s.pulseAt) return;
  s.pulseAt = clock + CONFIG.pulseCooldown;

  try { dimension.spawnParticle("aegis:overdrive_burst", loc); } catch (_) {}
  try { dimension.playSound("aegis.void_pulse", loc, { volume: 1.0, pitch: 1.0 }); } catch (_) {}

  for (const t of targets) {
    if (!isLocust(t)) continue;
    try {
      const tl = t.location;
      const dx = tl.x - loc.x, dy = tl.y - loc.y + 0.4, dz = tl.z - loc.z;
      const d = Math.max(0.4, Math.sqrt(dx * dx + dy * dy + dz * dz));
      const power = 1.9 * (1.0 - Math.min(1, d / CONFIG.pulseRadius)) + 0.35;
      t.applyImpulse({ x: dx / d * power, y: dy / d * power * 0.6 + 0.35, z: dz / d * power });
      t.applyDamage(18, { cause: "sonic_boom" });
      t.addEffect("weakness", 60, { amplifier: 1 });
    } catch (_) { /* target vanished */ }
  }
}

/* -------------------------------------------------------------- Void Step */
function voidStep(sentinel, dimension, from, to) {
  const s = registry(sentinel.id);
  if (clock < s.stepAt) return false;
  s.stepAt = clock + CONFIG.stepCooldown;

  const dx = from.x - to.x, dy = from.y - to.y, dz = from.z - to.z;
  const d = Math.max(0.001, Math.sqrt(dx * dx + dy * dy + dz * dz));
  // land 3 blocks short of the target, on the same ground level
  const dest = {
    x: to.x + (dx / d) * 3.0,
    y: to.y + 0.2,
    z: to.z + (dz / d) * 3.0
  };

  try { dimension.spawnParticle("aegis:void_step", from); } catch (_) {}
  try { dimension.playSound("aegis.void_step", from, { volume: 0.9, pitch: 1.0 }); } catch (_) {}
  try {
    sentinel.teleport(dest, { dimension: dimension, checkForBlocks: true });
    sentinel.triggerEvent("aegis:void_step");
  } catch (e) {
    try { sentinel.teleport(dest); } catch (_) { return false; }
  }
  schedule(4, () => {
    try { dimension.spawnParticle("aegis:void_step", dest); } catch (_) {}
  });
  return true;
}

/* ------------------------------------------------------------ Null Sever */
function beginNullSever(sentinel, dimension, target, loc) {
  const s = registry(sentinel.id);
  if (clock < s.severAt) return false;
  if (clock < s.busyUntil) return false;

  s.severAt = clock + CONFIG.severCooldown;
  s.busyUntil = clock + CONFIG.severChargeTicks + CONFIG.severHoldTicks;

  setAttack(sentinel, 3);                       // charge animation
  try { dimension.playSound("aegis.null_sever_charge", loc, { volume: 1.0 }); } catch (_) {}
  msg(PREFIX + "§bExecuting Null Sever.§r", dimension, loc, CONFIG.chatRadius);

  schedule(CONFIG.severChargeTicks, () => {
    try {
      if (!sentinel.isValid()) return;
      setAttack(sentinel, 4);                   // release animation
    } catch (_) { return; }

    // erase everything that still looks like an anomaly in range
    let erased = 0;
    try {
      const list = dimension.getEntities({
        location: sentinel.location,
        maxDistance: CONFIG.severRange + 6
      });
      for (const e of list) {
        if (isLocust(e)) {
          if (eraseAnomaly(e, dimension, "null sever")) erased++;
        }
      }
    } catch (_) { /* ignore */ }

    if (erased === 0) {
      msg(PREFIX + "§7Null Sever discharged. No anomaly in the beam.§r",
        dimension, sentinel.location, CONFIG.chatRadius);
    }

    schedule(CONFIG.severHoldTicks, () => {
      try { if (sentinel.isValid()) setAttack(sentinel, 0); } catch (_) {}
    });
  });
  return true;
}

/* --------------------------------------------------- per-sentinel update */
function updateSentinel(sentinel, anomalies) {
  const s = registry(sentinel.id);
  let loc, dimension;
  try {
    loc = sentinel.location;
    dimension = sentinel.dimension;
  } catch (_) { return; }

  // nearest anomaly
  let nearest = null, nd = Infinity;
  for (const a of anomalies) {
    try {
      if (!a.isValid()) continue;
      const d = dist(loc, a.location);
      if (d < nd) { nd = d; nearest = a; }
    } catch (_) {}
  }

  /* ---- stance -------------------------------------------------------- */
  if (!nearest) {
    if (s.mode !== 0 && clock >= s.busyUntil) setMode(sentinel, 0);
  } else if (nd <= CONFIG.overdriveRange) {
    if (s.mode !== 2 && s.mode !== 3 && clock >= s.busyUntil) {
      setMode(sentinel, 2);
      schedule(24, () => { try { if (sentinel.isValid()) setMode(sentinel, 3); } catch (_) {} });
    }
  } else {
    if (s.mode !== 1 && clock >= s.busyUntil) setMode(sentinel, 1);
  }

  /* ---- Guardian Aura -------------------------------------------------- */
  if (CONFIG.guardianAura && clock >= s.auraAt) {
    s.auraAt = clock + CONFIG.auraInterval;
    try {
      const players = dimension.getPlayers({ location: loc, maxDistance: CONFIG.auraRadius });
      for (const p of players) {
        try {
          p.addEffect("regeneration", CONFIG.auraRegenTicks, { amplifier: CONFIG.auraAmplifier });
          p.addEffect("resistance", CONFIG.auraResistTicks, { amplifier: CONFIG.auraAmplifier });
        } catch (_) {}
      }
      if (players.length > 0) {
        dimension.spawnParticle("aegis:aura_ring", loc);
        try { dimension.playSound("aegis.aura_pulse", loc, { volume: 0.5 }); } catch (_) {}
      }
    } catch (_) {}
  }

  if (!nearest) return;

  /* ---- Null Sever ----------------------------------------------------- */
  if (nd <= CONFIG.severRange && clock >= s.severAt && clock >= s.busyUntil) {
    beginNullSever(sentinel, dimension, nearest, loc);
    return;
  }

  /* ---- Void Pulse ----------------------------------------------------- */
  if (CONFIG.voidPulse && nd <= CONFIG.pulseRadius) {
    voidPulse(sentinel, dimension, loc, anomalies);
  }

  /* ---- Void Step pursuit ---------------------------------------------- */
  if (CONFIG.voidStep && clock >= s.stepAt && nd > CONFIG.stepMin && nd <= CONFIG.stepMax) {
    let tloc;
    try { tloc = nearest.location; } catch (_) { tloc = null; }
    if (tloc) voidStep(sentinel, dimension, loc, tloc);
    return;
  }

  /* ---- melee flourish -------------------------------------------------- */
  if (nd <= CONFIG.meleeRange && clock >= s.meleeAt && clock >= s.busyUntil) {
    s.meleeAt = clock + CONFIG.meleeCooldown;
    const usePunch = (Math.floor(clock / 20) % 2) === 0;
    setAttack(sentinel, usePunch ? 1 : 2);
    schedule(usePunch ? CONFIG.punchTicks : CONFIG.slashTicks, () => {
      try { if (sentinel.isValid() && registry(sentinel.id).busyUntil <= clock) setAttack(sentinel, 0); }
      catch (_) {}
    });
    registerHit(nearest, dimension);
  }
}

/* -------------------------------------------------------------- main scan */
function scan() {
  clock++;
  runScheduler();

  const allAnomalies = [];
  const seenSentinels = new Set();

  let players = [];
  try { players = world.getAllPlayers(); } catch (_) { players = []; }

  for (const p of players) {
    let dimension, ploc;
    try { dimension = p.dimension; ploc = p.location; } catch (_) { continue; }
    if (!dimension) continue;

    let list = [];
    try {
      list = dimension.getEntities({ location: ploc, maxDistance: CONFIG.detectRadius });
    } catch (_) { continue; }

    const anomalies = [];
    for (const e of list) {
      if (isSentinel(e)) {
        seenSentinels.add(e.id);
        try { sentinels.set(e.id, registry(e.id)); } catch (_) {}
      } else if (isLocust(e)) {
        anomalies.push(e);
      }
    }

    for (const e of list) {
      if (isSentinel(e)) {
        try { updateSentinel(e, anomalies); } catch (err) { log("update failed: " + err); }
      }
    }

    for (const a of anomalies) allAnomalies.push(a);

    /* auto deploy ------------------------------------------------------- */
    if (CONFIG.autoDeploy && anomalies.length > 0) {
      const nearbySentinel = list.some(isSentinel);
      if (!nearbySentinel && sentinels.size < CONFIG.maxSentinels) {
        spawnSentinel(dimension, ploc, anomalies[0]);
      }
    }
  }

  // forget stale records
  for (const id of Array.from(sentinels.keys())) {
    if (!seenSentinels.has(id)) sentinels.delete(id);
  }

  return allAnomalies;
}

/* ------------------------------------------------------------- spawning */
function spawnSentinel(dimension, near, target) {
  // try a few offsets so it does not land inside a wall
  const offsets = [
    { x: 2.0, y: 0.2, z: 0.0 },
    { x: -2.0, y: 0.2, z: 0.0 },
    { x: 0.0, y: 0.2, z: 2.0 },
    { x: 0.0, y: 0.2, z: -2.0 },
    { x: 3.0, y: 0.2, z: 3.0 },
    { x: 0.0, y: 1.2, z: 0.0 }
  ];
  for (const o of offsets) {
    const loc = { x: near.x + o.x, y: near.y + o.y, z: near.z + o.z };
    try {
      const e = dimension.spawnEntity(CONFIG.entityType, loc);
      try { e.triggerEvent("aegis:spawn"); } catch (_) {}
      try { dimension.spawnParticle("aegis:spawn_dissolve", loc); } catch (_) {}
      try { dimension.playSound("aegis.spawn", loc, { volume: 1.0 }); } catch (_) {}
      msg(PREFIX + "§bNull Veil Sentinel deployed.§r Anomaly signature detected.",
        dimension, loc, CONFIG.chatRadius);
      schedule(20, () => {
        try { if (e.isValid()) dimension.playSound("aegis.voice.locust_confirmed", e.location, { volume: 1.0 }); } catch (_) {}
      });
      return e;
    } catch (_) { /* try next offset */ }
  }
  return null;
}

/* -------------------------------------------------------- script commands */
function handleCommand(ev) {
  const id = String(ev.id || "").toLowerCase();
  if (id.indexOf("aegis:") !== 0) return;

  const sender = ev.sourceEntity;
  const cmd = id.substring("aegis:".length);
  const arg = (ev.message || "").trim();

  let dimension = null, loc = null;
  try { dimension = sender ? sender.dimension : world.getDimension("overworld"); } catch (_) {}
  try { loc = sender ? sender.location : { x: 0, y: 64, z: 0 }; } catch (_) {}
  if (!dimension) { try { dimension = world.getDimension("overworld"); } catch (_) {} }
  if (!loc) loc = { x: 0, y: 64, z: 0 };

  const tell = (t) => {
    try { if (sender && sender.sendMessage) sender.sendMessage(t); else world.sendMessage(t); }
    catch (_) { try { world.sendMessage(t); } catch (__) {} }
  };

  switch (cmd) {
    case "summon": {
      const n = Math.max(1, Math.min(8, parseInt(arg || "1", 10) || 1));
      let ok = 0;
      for (let i = 0; i < n; i++) if (spawnSentinel(dimension, loc, null)) ok++;
      tell(PREFIX + (ok > 0 ? "§b" + ok + "§r sentinel(s) deployed." : "§cDeployment failed."));
      break;
    }
    case "purge": {
      let erased = 0, seen = 0;
      for (const dimName of ["overworld", "nether", "the_end"]) {
        let dim;
        try { dim = world.getDimension(dimName); } catch (_) { dim = null; }
        if (!dim) continue;
        for (const p of world.getAllPlayers()) {
          let list = [];
          try {
            list = dim.getEntities({ location: p.location, maxDistance: 128 });
          } catch (_) { continue; }
          for (const e of list) {
            if (isLocust(e)) {
              seen++;
              if (eraseAnomaly(e, dim, "manual purge")) erased++;
            }
          }
        }
      }
      tell(PREFIX + "Purge complete. §b" + erased + "§r/" + seen + " anomaly signature(s) erased.");
      break;
    }
    case "scan": {
      const found = [];
      for (const p of world.getAllPlayers()) {
        let list = [];
        try { list = p.dimension.getEntities({ location: p.location, maxDistance: CONFIG.detectRadius }); }
        catch (_) { continue; }
        for (const e of list) {
          if (isLocust(e)) {
            let l = null;
            try { l = e.location; } catch (_) {}
            found.push("§7" + e.typeId + "§r @ " +
              (l ? Math.round(l.x) + "," + Math.round(l.y) + "," + Math.round(l.z) : "?"));
          }
        }
      }
      tell(PREFIX + (found.length
        ? "§b" + found.length + "§r anomaly signature(s): " + found.join(" | ")
        : "§7No anomaly signature detected.§r"));
      break;
    }
    case "status": {
      tell(PREFIX + "Sentinels active: §b" + sentinels.size +
        "§r | Anomalies erased this session: §b" + erasedCount + "§r");
      break;
    }
    case "config": {
      tell(PREFIX + "Keywords: " + CONFIG.locustKeywords.join(", ") +
        " | severRange " + CONFIG.severRange + " | hitsToErase " + CONFIG.hitsToErase +
        " | autoDeploy " + CONFIG.autoDeploy);
      break;
    }
    case "help":
    default: {
      tell(PREFIX + "Commands: §7aegis:summon§r, §7aegis:purge§r, §7aegis:scan§r, §7aegis:status§r, §7aegis:config§r");
      break;
    }
  }
}

/* ------------------------------------------------------------------- boot */
try {
  world.afterEvents.scriptEventReceive.subscribe(handleCommand);
} catch (e) { log("scriptEventReceive unavailable: " + e); }

// Melee confirmation: if the sentinel lands a hit on an anomaly, count it.
try {
  world.afterEvents.entityHurt.subscribe((ev) => {
    try {
      const src = ev.damageSource ? ev.damageSource.damagingEntity : undefined;
      if (!src || !isSentinel(src)) return;
      const victim = ev.hurtEntity;
      if (!isLocust(victim)) return;
      registerHit(victim, victim.dimension);
      try { victim.dimension.spawnParticle("aegis:impact_hit", victim.location); } catch (_) {}
    } catch (_) {}
  });
} catch (e) { log("entityHurt unavailable: " + e); }

// Anomaly that manages to delete a sentinel should not silently break things.
try {
  world.afterEvents.entityRemove && world.afterEvents.entityRemove.subscribe((ev) => {
    try {
      if (ev && ev.removedEntity && ev.removedEntity.id !== undefined) {
        sentinels.delete(ev.removedEntity.id);
        hitCounts.delete(ev.removedEntity.id);
      }
    } catch (_) {}
  });
} catch (_) { /* optional event */ }

system.run(function tick() {
  try { scan(); } catch (e) { log("scan failed: " + e); }
  system.run(tick);
});

try {
  world.afterEvents.worldLoad.subscribe(() => {
    world.sendMessage(PREFIX + "§bNull Veil Sentinel online.§r " +
      "§7/scriptevent aegis:help§r");
  });
} catch (_) { /* optional */ }

console.warn("[aegis] Null Veil Sentinel script loaded");
