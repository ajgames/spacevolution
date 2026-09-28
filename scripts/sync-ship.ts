// Mirrors the files the game needs from blender/export/ into public/ship/.
//
// blender/export/lightmaps/manifest.json is the source of truth: it names every
// room GLB and baked lightmap, so preview.html and the optional lightmaps/exr/
// masters stay behind. The manifest lands at public/ship/manifest.json, where
// its paths (written relative to export/) resolve against it unchanged.
//
// Runs on `npm run sync:ship`, before every `vite build`, and inside the dev
// server, which re-syncs and reloads the page when Blender re-exports or re-bakes.
import { copyFile, mkdir, open, readFile, readdir, rm, stat, utimes } from 'node:fs/promises'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Logger, Plugin, ResolvedConfig } from 'vite'

const EXPORT_DIR = 'blender/export'
const SHIP_DIR = 'public/ship'

type Manifest = {
  rooms: Record<string, { glb: string; lightmaps: Record<string, { file: string }> }>
}

export type SyncResult = { copied: string[]; removed: string[]; unchanged: number; warnings: string[] }

export async function syncShip(root: string): Promise<SyncResult> {
  const exportDir = join(root, EXPORT_DIR)
  const shipDir = join(root, SHIP_DIR)
  const manifestPath = join(exportDir, 'lightmaps/manifest.json')

  let manifest: Manifest
  try {
    manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
  } catch (err) {
    throw new Error(`can't read ${relative(root, manifestPath)}: ${(err as Error).message}`)
  }

  // public/ship path -> blender/export path
  const wanted = new Map([['manifest.json', manifestPath]])
  for (const room of Object.values(manifest.rooms)) {
    wanted.set(room.glb, join(exportDir, room.glb))
    for (const lm of Object.values(room.lightmaps)) wanted.set(lm.file, join(exportDir, lm.file))
  }

  const files = new Map<string, { src: string; size: number; mtime: Date }>()
  const missing: string[] = []
  for (const [rel, src] of wanted) {
    const s = await stat(src).catch(() => null)
    if (s) files.set(rel, { src, size: s.size, mtime: s.mtime })
    else missing.push(relative(root, src))
  }
  if (missing.length) throw new Error(`missing from the export:\n  ${missing.join('\n  ')}`)

  const toCopy: string[] = []
  for (const [rel, { src, size, mtime }] of files) {
    const dest = await stat(join(shipDir, rel)).catch(() => null)
    if (dest && dest.size === size && dest.mtime.getTime() === mtime.getTime()) continue
    await assertComplete(src, size)
    toCopy.push(rel)
  }

  for (const rel of toCopy) {
    const { src, mtime } = files.get(rel)!
    const dest = join(shipDir, rel)
    await mkdir(dirname(dest), { recursive: true })
    await copyFile(src, dest)
    // Keeping the source mtime is what lets the next run skip unchanged files, so
    // Syncthing isn't handed 30+ MB of identical assets on every dev start.
    await utimes(dest, mtime, mtime)
  }

  const removed: string[] = []
  for (const entry of await readdir(shipDir, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) continue
    const path = join(entry.parentPath, entry.name)
    const rel = relative(shipDir, path).split(sep).join('/')
    if (files.has(rel)) continue
    await rm(path)
    removed.push(rel)
  }

  // The bake writes through the "lightmap" UV map, so a GLB exported after its
  // lightmaps may no longer line up with them. mtime is the only signal we have.
  const warnings: string[] = []
  for (const room of Object.values(manifest.rooms)) {
    const exported = files.get(room.glb)!.mtime.getTime()
    const baked = Math.min(...Object.values(room.lightmaps).map((lm) => files.get(lm.file)!.mtime.getTime()))
    if (exported > baked) {
      warnings.push(`${room.glb} was exported after its lightmaps were baked; re-bake if geometry or UVs changed`)
    }
  }

  return { copied: toCopy, removed, unchanged: files.size - toCopy.length, warnings }
}

// Blender writes exports in place, so a watcher can see a file half-written.
// GLB's header records the total length, and a PNG always ends in an IEND chunk.
async function assertComplete(path: string, size: number) {
  const isGlb = path.endsWith('.glb')
  if (!isGlb && !path.endsWith('.png')) return
  const buf = Buffer.alloc(12)
  const fh = await open(path)
  await fh.read(buf, 0, 12, isGlb ? 0 : Math.max(0, size - 12)).finally(() => fh.close())
  const ok = isGlb
    ? buf.toString('latin1', 0, 4) === 'glTF' && buf.readUInt32LE(8) === size
    : buf.toString('latin1', 4, 8) === 'IEND'
  if (!ok) throw new Error(`${path} looks incomplete; is Blender still writing it?`)
}

function report(logger: Logger, { copied, removed, unchanged, warnings }: SyncResult) {
  logger.info(`[ship] ${copied.length} copied, ${removed.length} removed, ${unchanged} unchanged`, { timestamp: true })
  for (const w of warnings) logger.warn(`[ship] ${w}`, { timestamp: true })
}

export function shipAssets(): Plugin {
  let config: ResolvedConfig
  return {
    name: 'ship-assets',
    configResolved(resolved) {
      config = resolved
    },
    // Runs before Vite copies public/ into dist/, and a broken export fails the build.
    async buildStart() {
      if (config.command === 'build') report(config.logger, await syncShip(config.root))
    },
    async configureServer(server) {
      const exportDir = join(config.root, EXPORT_DIR)
      let queue = Promise.resolve()
      let timer: ReturnType<typeof setTimeout> | undefined
      const sync = () => {
        queue = queue.then(async () => {
          try {
            const result = await syncShip(config.root)
            report(config.logger, result)
            if (result.copied.length || result.removed.length) server.ws.send({ type: 'full-reload' })
          } catch (err) {
            config.logger.error(`[ship] ${(err as Error).message}`, { timestamp: true })
          }
        })
      }
      // Vite waits for this before serving, so the first request never races the copy.
      sync()
      await queue
      // An export or bake writes several files in a row, so wait for Blender to go quiet.
      server.watcher.on('all', (_event, file) => {
        if (!file.startsWith(exportDir + sep)) return
        clearTimeout(timer)
        timer = setTimeout(sync, 1000)
      })
    },
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const { copied, removed, unchanged, warnings } = await syncShip(join(dirname(fileURLToPath(import.meta.url)), '..'))
    for (const rel of copied) console.log(`copied   ${rel}`)
    for (const rel of removed) console.log(`removed  ${rel}`)
    console.log(`${copied.length} copied, ${removed.length} removed, ${unchanged} unchanged`)
    for (const w of warnings) console.warn(`warning: ${w}`)
  } catch (err) {
    console.error((err as Error).message)
    process.exitCode = 1
  }
}
