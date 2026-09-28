// What the scene needs to know about the Blender export in public/ship/ (see
// scripts/sync-ship.ts). Ported from blender/export/preview.html, which stays
// the reference for how rooms, lightmaps and emissive materials fit together.

export const SHIP_URL = `${import.meta.env.BASE_URL}ship/`

export const LIGHTING_STATES = ['normal', 'emergency', 'blackout'] as const
export type LightingState = (typeof LIGHTING_STATES)[number]

export type RoomInfo = {
  glb: string
  // A partial bake (bake_lightmaps.py --states) leaves some states out.
  lightmaps: Partial<Record<LightingState, { file: string; lightMapIntensity: number }>>
}
export type ShipManifest = { resolution: number; rooms: Record<string, RoomInfo> }

// Paths in the manifest are relative to it, so they resolve against SHIP_URL.
export const manifest: Promise<ShipManifest> = fetch(`${SHIP_URL}manifest.json`).then((res) => {
  if (!res.ok) throw new Error(`${res.url}: ${res.status}. Is public/ship/ synced? (npm run sync:ship)`)
  return res.json()
})

// Emissive materials by role, switched per lighting state like the bake does.
// "dynamic" is the engineering blink button, which the scene animates.
export const EMISSIVE_ROLES: Record<string, string> = {
  MAT_emit_warm: 'strip',
  MAT_emit_red: 'alarm',
  MAT_emit_amber: 'indicator',
  MAT_display: 'indicator',
  MAT_screen: 'screen',
  MAT_emit_blink: 'dynamic',
}
export const ROLES_ON: Record<LightingState, string[]> = {
  normal: ['strip', 'indicator', 'screen', 'dynamic'],
  emergency: ['alarm', 'indicator', 'screen', 'dynamic'],
  blackout: ['indicator', 'screen', 'dynamic'],
}

// Reflections are faint, only so metal edges read, and scaled per state so they
// never out-shine the bake.
export const ENV_INTENSITY: Record<LightingState, number> = { normal: 0.1, emergency: 0.012, blackout: 0.008 }

type Vec3 = [number, number, number]
// Blender is Z-up, three.js is Y-up: Blender (x, y, z) is three.js (x, z, -y).
const b2t = (x: number, y: number, z: number): Vec3 => [x, z, -y]

// Camera position and orbit target per view, at the 1.7 m player eye height.
export const VIEWS = {
  command: [b2t(-1.6, 5.45, 1.7), b2t(0.6, 9.6, 1.15)],
  cryo: [b2t(-5.45, 0.55, 1.7), b2t(-10.8, -0.4, 1.2)],
  engineering: [b2t(5.45, -0.9, 1.7), b2t(10.8, 1.0, 1.25)],
  corridor: [b2t(0, 4.4, 1.7), b2t(0, -1.8, 0.7)],
  arm: [b2t(2.9, -0.35, 1.7), b2t(-4.9, 0.25, 1.15)],
} satisfies Record<string, [Vec3, Vec3]>
export type View = keyof typeof VIEWS
