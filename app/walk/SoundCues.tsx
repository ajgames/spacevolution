import { useFrame, useThree } from '@react-three/fiber'
import { useMemo } from 'react'
import { Vector3 } from 'three'
import type { Point } from '../demo/audio.ts'
import { liveCues } from './cues.ts'
import { gainAt, listener, transmissionTo } from './space.ts'

// Where sounds come from, drawn over the view. Each audible sound gets an arc
// on a ring around the crosshair, pointing the way it comes from (up the ring
// is ahead, down is behind) with its name beside it; the louder it reaches
// you, the brighter and wider. A source that's in view also gets a pulsing
// marker where it is. Sounds overhead or below say so with an arrow.

const SLOTS = 6
const COLOR = '#f0a040'
const NAMES: Record<string, string> = {
  pulse: 'PULSE',
  alarm: 'ALARM',
  door: 'DOOR',
  relay: 'RELAYS',
  fault: 'FAULT',
  seal: 'POD SEAL',
  monitor: 'MONITOR',
  screen: 'SCREEN',
  voice: 'STEWARD',
  droid: 'DROID',
}

// The overlay's elements, reached from the canvas's frame loop.
const layer = {
  svg: null as SVGSVGElement | null,
  arcs: [] as (SVGGElement | null)[],
  marks: [] as (SVGGElement | null)[],
}

// The DOM half, over the canvas.
export function SoundCues() {
  return (
    <svg
      ref={(svg) => {
        layer.svg = svg
      }}
      className="pointer-events-none absolute inset-0 size-full font-mono"
      aria-hidden
    >
      {Array.from({ length: SLOTS }, (_, i) => (
        <g
          key={`arc${i}`}
          ref={(g) => {
            layer.arcs[i] = g
          }}
          display="none"
        >
          <path fill="none" stroke={COLOR} strokeLinecap="round" />
          <text fill={COLOR} fontSize="10" letterSpacing="2" textAnchor="middle" dominantBaseline="middle" />
        </g>
      ))}
      {Array.from({ length: SLOTS }, (_, i) => (
        <g
          key={`mark${i}`}
          ref={(g) => {
            layer.marks[i] = g
          }}
          display="none"
        >
          <circle fill="none" stroke={COLOR} strokeWidth="1.5" />
          <circle fill="none" stroke={COLOR} strokeWidth="1" />
        </g>
      ))}
    </svg>
  )
}

type Heard = { label: string; point: Point; alpha: number }

// The canvas half: projects each cue through the camera and updates the DOM.
export function CueProjector() {
  const camera = useThree((state) => state.camera)
  const v = useMemo(() => new Vector3(), [])

  useFrame(({ clock }) => {
    const svg = layer.svg
    if (!svg) return
    const now = performance.now()
    const heard: Heard[] = []
    for (const { cue, age } of liveCues(now)) {
      // One-shots swell in fast and fade out; held cues stay near full.
      const fade = Math.min(1, age / 0.05) * (1 - age) ** 1.2
      const ranked = cue.points
        .map((point) => ({ point, gain: gainAt(point, cue.reach) * transmissionTo(point) }))
        .sort((a, b) => b.gain - a.gain)
      // The loudest source, and a second if it's nearly as loud (between two speakers).
      for (const { point, gain } of ranked.slice(0, 2)) {
        if (gain < ranked[0].gain * 0.6) break
        const alpha = Math.min(1, Math.sqrt(gain * cue.level) * 1.15) * fade
        if (alpha > 0.06) heard.push({ label: cue.label, point, alpha })
      }
    }
    heard.sort((a, b) => b.alpha - a.alpha)

    const W = svg.clientWidth
    const H = svg.clientHeight
    const cx = W / 2
    const cy = H / 2
    const R = Math.max(80, Math.min(150, Math.min(W, H) * 0.17))
    let arcs = 0
    let marks = 0
    const bearings: number[] = [] // of the arcs so far, so labels pointing the same way stack outward
    for (const { label, point, alpha } of heard) {
      const [x, y, z] = point
      // Right on top of you (a button you pressed): you know where it is.
      if (Math.hypot(x - listener.x, y - listener.y, z - listener.z) < 1) continue
      v.set(x, y, z).applyMatrix4(camera.matrixWorldInverse)
      const bearing = Math.atan2(v.x, -v.z) // 0 ahead, positive to the right
      const elevation = Math.atan2(v.y, Math.hypot(v.x, v.z))
      const ahead = v.z < -0.2
      v.set(x, y, z).project(camera)
      const inView = ahead && Math.abs(v.x) < 0.94 && Math.abs(v.y) < 0.9

      if (arcs < SLOTS) {
        const g = layer.arcs[arcs++]!
        const span = 0.16 + 0.14 * alpha
        const at = (a: number, r: number) => `${cx + Math.sin(a) * r} ${cy - Math.cos(a) * r}`
        const path = g.children[0] as SVGPathElement
        path.setAttribute('d', `M ${at(bearing - span, R)} A ${R} ${R} 0 0 1 ${at(bearing + span, R)}`)
        path.setAttribute('stroke-width', String(2 + 3 * alpha))
        const text = g.children[1] as SVGTextElement
        const crowd = bearings.filter((b) => Math.abs(Math.atan2(Math.sin(b - bearing), Math.cos(b - bearing))) < 0.4).length
        bearings.push(bearing)
        const [tx, ty] = at(bearing, R + 20 + crowd * 16).split(' ')
        text.setAttribute('x', tx)
        text.setAttribute('y', ty)
        const arrow = elevation > 0.6 ? '▲ ' : elevation < -0.6 ? '▼ ' : ''
        text.textContent = arrow + (NAMES[label] ?? label.toUpperCase())
        // Dimmer while the marker shows it in view.
        g.setAttribute('opacity', String(alpha * (inView ? 0.55 : 1)))
        g.setAttribute('display', 'inline')
      }
      if (inView && marks < SLOTS) {
        const g = layer.marks[marks++]!
        const sx = ((v.x + 1) / 2) * W
        const sy = ((1 - v.y) / 2) * H
        const r = 7 + 9 * alpha
        const ripple = (clock.elapsedTime * 1.4 + marks * 0.37) % 1
        const [ring, wave] = g.children as unknown as SVGCircleElement[]
        for (const c of [ring, wave]) {
          c.setAttribute('cx', String(sx))
          c.setAttribute('cy', String(sy))
        }
        ring.setAttribute('r', String(r))
        wave.setAttribute('r', String(r * (1 + ripple * 1.6)))
        wave.setAttribute('opacity', String(1 - ripple))
        g.setAttribute('opacity', String(alpha))
        g.setAttribute('display', 'inline')
      }
    }
    for (let i = arcs; i < SLOTS; i++) layer.arcs[i]?.setAttribute('display', 'none')
    for (let i = marks; i < SLOTS; i++) layer.marks[i]?.setAttribute('display', 'none')
  })

  return null
}
