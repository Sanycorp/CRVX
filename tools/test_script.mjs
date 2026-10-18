// Mock-runtime test for Aegis_Primordial_BP/scripts/main.js
// Simulates an invulnerable Locust (damage_sensor "no", min-health lock, /kill immune)
// and asserts the script still erases it through Entity.remove().
import { mkdtempSync, writeFileSync, readFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const mainSrc = readFileSync(join(here, "../Aegis_Primordial_BP/scripts/main.js"), "utf8");

// ---------------- mock world ----------------
let tick = 0;
const timers = [];
const log = [];
const entities = new Set();

class Entity {
  constructor(typeId, loc, { families = [], invulnerable = false, nameTag = "" } = {}) {
    this.typeId = typeId; this.location = loc; this.id = String(Math.random());
    this.families = families; this.invulnerable = invulnerable; this.nameTag = nameTag;
    this.isValid = true; this.tags = new Set(); this.props = { "aegis:state": "guard", "aegis:glow": 0.35, "aegis:erased": 0 };
    this.dimension = dim; this.health = 1000; this.events = []; this.effects = [];
    entities.add(this);
  }
  getComponent(id) {
    if (id === "minecraft:type_family") return { getTypeFamilies: () => this.families };
    return undefined;
  }
  hasTag(t) { return this.tags.has(t); }
  getProperty(k) { return this.props[k]; }
  setProperty(k, v) { this.props[k] = v; }
  triggerEvent(e) {
    this.events.push(e);
    const map = { "aegis:enter_overdrive": "overdrive", "aegis:activate_null_sever": "null_sever", "aegis:null_sever_complete": "overdrive", "aegis:return_to_guard": "guard" };
    if (map[e]) this.props["aegis:state"] = map[e];
  }
  sendMessage(m) { log.push(`MSG ${m}`); }
  applyDamage() { if (this.invulnerable) return false; this.health -= 1; return true; }
  kill() { if (this.invulnerable) return false; this.remove(); return true; }
  remove() { this.isValid = false; entities.delete(this); log.push(`REMOVED ${this.typeId}`); }
  lookAt() {}
  teleport(loc) { this.location = loc; log.push(`BLINK ${this.typeId}`); }
  runCommand(c) { log.push(`CMD ${c}`); return { successCount: 1 }; }
  addEffect(e) { this.effects.push(e); }
  getViewDirection() { return { x: 0, y: 0, z: 1 }; }
}
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
const dim = {
  id: "overworld",
  getEntities(q = {}) {
    return [...entities].filter((e) => {
      if (q.type && e.typeId !== q.type) return false;
      if (q.location && q.maxDistance != null && dist(q.location, e.location) > q.maxDistance) return false;
      if (q.families && !q.families.some((f) => e.families.includes(f))) return false;
      return true;
    });
  },
  getPlayers(q) { return this.getEntities({ ...q, type: "minecraft:player" }); },
  spawnEntity(t, loc) { const e = new Entity(t, loc, { families: t.startsWith("aegis") ? ["aegis"] : [] }); fireSpawn(e); return e; },
  spawnParticle(id) { log.push(`FX ${id}`); },
  playSound(id) { log.push(`SND ${id}`); },
};
const signal = () => { const subs = []; return { subscribe: (f) => subs.push(f), fire: (ev) => subs.forEach((f) => f(ev)) }; };
const afterEvents = { entityHitEntity: signal(), entityHurt: signal(), entityDie: signal(), entitySpawn: signal(), worldLoad: signal() };
const fireSpawn = (e) => afterEvents.entitySpawn.fire({ entity: e });
const dynProps = {};
const scores = new Map();
const world = {
  afterEvents,
  getDimension: () => dim,
  getEntity: (id) => [...entities].find((e) => e.id === id),
  sendMessage: (m) => log.push(`MSG ${m}`),
  getDynamicProperty: (k) => dynProps[k],
  setDynamicProperty: (k, v) => (dynProps[k] = v),
  scoreboard: {
    getObjective: (n) => scores.get(n),
    addObjective: (n) => { const o = { s: new Map(), getScore: (k) => o.s.get(typeof k === "string" ? k : k.id), setScore: (k, v) => o.s.set(typeof k === "string" ? k : k.id, v) }; scores.set(n, o); return o; },
  },
};
const scriptEventSubs = [];
const startupSubs = [];
const system = {
  get currentTick() { return tick; },
  runInterval: (fn, n) => { const id = timers.length; timers.push({ fn, n, next: tick + n, repeat: true }); return id; },
  runTimeout: (fn, n) => { const id = timers.length; timers.push({ fn, n, next: tick + n, repeat: false }); return id; },
  clearRun: (id) => { if (timers[id]) timers[id].dead = true; },
  afterEvents: { scriptEventReceive: { subscribe: (f) => scriptEventSubs.push(f) } },
  beforeEvents: { startup: { subscribe: (f) => startupSubs.push(f) } },
};
function advance(n) {
  for (let i = 0; i < n; i++) {
    tick++;
    for (const t of timers) {
      if (t.dead || tick < t.next) continue;
      t.fn();
      if (t.repeat) t.next = tick + t.n; else t.dead = true;
    }
  }
}
globalThis.console.warn = (m) => log.push("WARN " + m);

// ---------------- load script with mock module ----------------
const dir = mkdtempSync(join(tmpdir(), "aegis-"));
mkdirSync(join(dir, "node_modules/@minecraft/server"), { recursive: true });
writeFileSync(join(dir, "node_modules/@minecraft/server/package.json"), JSON.stringify({ name: "@minecraft/server", type: "module", main: "index.js" }));
writeFileSync(join(dir, "node_modules/@minecraft/server/index.js"),
  `export const world = globalThis.__world; export const system = globalThis.__system;
   export const EntityDamageCause = { override: "override", selfDestruct: "selfDestruct" };
   export const EquipmentSlot = { Mainhand: "Mainhand" }; export class ItemStack {}; export const GameMode = { Creative: "Creative" };`);
writeFileSync(join(dir, "main.js"), mainSrc);
globalThis.__world = world; globalThis.__system = system;
const mod = await import(pathToFileURL(join(dir, "main.js")).href);

// ---------------- scenario ----------------
let pass = 0, fail = 0;
const assert = (c, m) => { if (c) { pass++; console.log("  ✔", m); } else { fail++; console.log("  ✘", m); } };

const player = new Entity("minecraft:player", { x: 0, y: 64, z: 0 }, { families: ["player"] });
const registry = { registerCustomComponent: (n, c) => (registry[n] = c) };
startupSubs.forEach((f) => f({ itemComponentRegistry: registry }));
assert(registry["aegis:summon_core"], "custom item component aegis:summon_core registered");

console.log("\n[1] Classification");
const locustA = new Entity("doctor_nowhere:locust", { x: 0, y: 64, z: 40 }, { families: ["monster"], invulnerable: true });
const locustB = new Entity("weirdport:ancient_horror_v2", { x: 10, y: 64, z: 10 }, { families: ["the_locust", "monster"], invulnerable: true });
const locustC = new Entity("custom:boss", { x: -10, y: 64, z: 5 }, { families: ["monster"], invulnerable: true, nameTag: "THE LOCUST (Evolution)" });
const cow = new Entity("minecraft:cow", { x: 3, y: 64, z: 3 }, { families: ["cow", "mob"] });
assert(mod.isLocust(locustA), "typeId substring match");
assert(mod.isLocust(locustB), "family match (unknown typeId)");
assert(mod.isLocust(locustC), "nameTag match");
assert(!mod.isLocust(cow), "cow is NOT a target");
assert(!mod.isLocust(player), "player is NOT a target");

console.log("\n[2] Invulnerability is real: /kill & damage fail on the Locust");
assert(locustA.kill() === false && locustA.isValid, "kill() fails (min-health lock)");
assert(locustA.applyDamage(1e6) === false && locustA.health === 1000, "applyDamage fails (damage_sensor no)");

console.log("\n[3] Auto-deploy on first detection");
fireSpawn(locustA);
const aegisList = dim.getEntities({ type: "aegis:primordial_sentinel" });
assert(aegisList.length === 1, "an Aegis auto-spawned near the player");
const aegis = aegisList[0];
aegis.families = ["aegis", "player_protector"];

console.log("\n[4] Hunting loop: overdrive, blink, Null Sever erases invulnerable Locust");
advance(12);
assert(aegis.events.includes("aegis:enter_overdrive"), "entered overdrive (Locust within 32)");
assert(log.some((l) => l.startsWith("BLINK")), "blinked toward distant target");
advance(700); // three spread-out targets => up to 3 Null Severs at 10 s cooldown
assert(aegis.events.includes("aegis:activate_null_sever"), "Null Sever activated");
assert(log.some((l) => l.includes("FX aegis:null_sever_shockwave")), "shockwave FX fired");
assert(!locustA.isValid && !locustB.isValid && !locustC.isValid, "ALL three Locust variants erased via remove()");
assert(cow.isValid && player.isValid && aegis.isValid, "cow, player and Aegis untouched");
assert(log.some((l) => l.includes("Null Sever executed. Target erased.")), "chat confirmation sent");
assert(world.getDynamicProperty("aegis:total_erased") === 3, "erase counter == 3");
assert(aegis.getProperty("aegis:erased") === 3, "entity property aegis:erased == 3");

console.log("\n[5] Melee contact path (entityHitEntity)");
const locustD = new Entity("toe:the_locust", { x: aegis.location.x + 1, y: 64, z: aegis.location.z }, { families: ["locust"], invulnerable: true });
afterEvents.entityHitEntity.fire({ damagingEntity: aegis, hitEntity: locustD });
assert(!locustD.isValid, "melee hit erased invulnerable Locust instantly");

console.log("\n[6] Operator scriptevent + tag override");
const mystery = new Entity("unknown:thing", { x: 2, y: 64, z: 2 }, { families: ["monster"], invulnerable: true });
mystery.tags.add("aegis_target");
scriptEventSubs.forEach((f) => f({ id: "aegis:force_nullify", message: "0", sourceEntity: undefined }));
assert(!mystery.isValid, "tagged entity erased by /scriptevent aegis:force_nullify");

console.log("\n[7] Protective aura");
player.location = { ...aegis.location };
advance(130);
assert(player.effects.includes("resistance") && player.effects.includes("regeneration"), "player received resistance + regeneration");
assert(aegis.events.includes("aegis:return_to_guard"), "returned to guard after area secured");

console.log(`\n${pass} passed, ${fail} failed`);
console.log(log.slice(0,40).join("\n"));
if (log.some((l) => l.startsWith("WARN"))) console.log(log.filter((l) => l.startsWith("WARN")).join("\n"));
process.exit(fail ? 1 : 0);
