import { useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import { CanvasTexture, MeshBasicMaterial, SRGBColorSpace } from 'three'
import { propMaterial } from './props.ts'
import { useWalk } from './store.ts'
import { voiceLevel } from './voice.ts'
import { SPEAKERS } from './world.ts'

// The PA's ceiling speakers: a round grille in a rim, with a small amber lamp
// that lights with the steward's voice, so you can see which way to look.

function grilleTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#6d726f'
  ctx.fillRect(0, 0, 128, 128)
  ctx.fillStyle = '#0b0c0c'
  for (let y = 6; y < 128; y += 9) {
    for (let x = (y / 9) % 2 ? 6 : 10.5; x < 128; x += 9) {
      ctx.beginPath()
      ctx.arc(x, y, 2.6, 0, Math.PI * 2)
      ctx.fill()
    }
  }
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

const grille = propMaterial({ map: grilleTexture(), roughness: 0.7, metalness: 0.5 })
const rim = propMaterial({ color: '#3b4240', roughness: 0.5, metalness: 0.7 })
const lamp = new MeshBasicMaterial({ color: '#000000', toneMapped: false })

export default function Speakers() {
  const level = useRef(0)
  useFrame((_, dt) => {
    const target = useWalk.getState().speaking ? 0.25 + voiceLevel() : 0
    level.current += (target - level.current) * Math.min(1, dt * 20)
    lamp.color.setRGB(1, 0.55, 0.16).multiplyScalar(0.05 + level.current * 3)
  })
  return (
    <>
      {SPEAKERS.map(({ name, at }) => (
        // Facing down out of the ceiling.
        <group key={name} position={at} rotation-x={Math.PI / 2}>
          <mesh material={rim} position-z={-0.002}>
            <ringGeometry args={[0.15, 0.175, 32]} />
          </mesh>
          <mesh material={grille}>
            <circleGeometry args={[0.15, 32]} />
          </mesh>
          <mesh material={lamp} position={[0.12, 0.12, 0.001]}>
            <circleGeometry args={[0.012, 12]} />
          </mesh>
        </group>
      ))}
    </>
  )
}
