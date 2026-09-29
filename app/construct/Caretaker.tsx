import { useAnimations, useGLTF } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { type Bone, type Group, MathUtils, type Mesh, type Object3D, Quaternion, Vector3 } from 'three'
import { type Mode, body, ground, useConstruct } from './store.ts'
import { mouthSignal } from './voice.ts'

// The caretaker (blender/export/characters/caretaker.glb, synced to public/).
// The clips are in place: this component moves him at the speed each clip was
// authored for (the rig's "clips" extra), so planted feet stay planted. The jaw,
// lip shapes, blinks and eyes are driven here; no clip keys them.

export const CARETAKER_URL = '/characters/caretaker.glb'
useGLTF.preload(CARETAKER_URL)

type Clips = Record<string, { seconds: number; loop: boolean; speed: number }>

const WALK_CIRCLE = 2.2 // the walk circles the middle of the room at this radius
const STRAFE_REACH = 1.3 // metres each side of where the strafe started
const FADE = 0.3
const CLIP: Record<Mode, string> = {
  idle: 'idle',
  walk: 'walk',
  jump: 'jump',
  talk: 'talk',
  strafe: 'strafe_left',
  crouch: 'crouch',
}

type Actions = ReturnType<typeof useAnimations>['actions']

// Per-frame state, reset when he mounts.
const playing = { clip: null as string | null }
const strafe = { dir: 1, travelled: 0 }
const face = { time: 0, level: 0, bright: 0.5, press: 0, blinkAt: 2, blink: -1, saccadeAt: 0 }
const look = new Vector3() // saccade offset added to the gaze target
const lookTo = new Vector3()

const X = new Vector3(1, 0, 0)
const FORWARD = new Vector3(0, 1, 0) // an eye bone's +Y points out of the pupil
const IDENTITY = new Quaternion()
const MAX_EYE = 0.44 // radians, about as far as the eyes turn before the head would
const q = new Quaternion()
const q2 = new Quaternion()
const parentQ = new Quaternion()
const v = new Vector3()
const v2 = new Vector3()

function crossfade(actions: Actions, clip: string) {
  if (playing.clip === clip) return
  const next = actions[clip]
  if (!next) {
    console.warn(`[caretaker] no "${clip}" clip yet`)
    return
  }
  next.reset().setEffectiveTimeScale(1).setEffectiveWeight(1).fadeIn(FADE).play()
  if (playing.clip) actions[playing.clip]?.fadeOut(FADE)
  playing.clip = clip
}

// Frame-rate independent approach of `from` towards `to` with time constant tau.
const approach = (from: number, to: number, dt: number, tau: number) => from + (to - from) * (1 - Math.exp(-dt / tau))

export default function Caretaker() {
  const group = useRef<Group>(null)
  const gltf = useGLTF(CARETAKER_URL)
  const { actions } = useAnimations(gltf.animations, group)
  const mode = useConstruct((s) => s.mode)

  const rig = useMemo(() => {
    const bone = (name: string) => gltf.scene.getObjectByName(name) as Bone
    const faces: Mesh[] = []
    gltf.scene.traverse((o: Object3D) => {
      const mesh = o as Mesh
      if (mesh.morphTargetDictionary && 'mouth_wide' in mesh.morphTargetDictionary) faces.push(mesh)
    })
    const jaw = bone('jaw')
    const eyes = [bone('eye_L'), bone('eye_R')]
    return {
      hips: bone('hips'),
      feet: [
        [bone('foot_L'), bone('toe_L')],
        [bone('foot_R'), bone('toe_R')],
      ] as const,
      jaw,
      jawRest: jaw.quaternion.clone(),
      eyes: eyes.map((eye) => ({ eye, rest: eye.quaternion.clone() })),
      faces, // the body is split per material; every part carries the morph targets
      clips: (gltf.scene.getObjectByName('RIG_caretaker')?.userData.clips ?? {}) as Clips,
    }
  }, [gltf])

  useLayoutEffect(() => {
    // Skinned meshes keep their bind-pose bounds; without this he vanishes mid-jump.
    gltf.scene.traverse((o: Object3D) => void (o.frustumCulled = false))
    playing.clip = null
    Object.assign(strafe, { dir: 1, travelled: 0 })
    Object.assign(face, { time: 0, level: 0, press: 0, blinkAt: 2, blink: -1, saccadeAt: 0 })
  }, [gltf])

  useEffect(() => {
    if (mode === 'strafe') Object.assign(strafe, { dir: 1, travelled: 0 })
    crossfade(actions, CLIP[mode])
  }, [mode, actions])

  useFrame((state, delta) => {
    const g = group.current
    if (!g) return
    const dt = Math.min(delta, 0.1)
    const speed = (clip: string) => rig.clips[clip]?.speed ?? 0
    const cam = state.camera.position

    // Locomotion. Forward is (sin yaw, cos yaw); his left is (cos yaw, -sin yaw).
    const turnTo = (want: number, rate: number) => {
      const diff = MathUtils.euclideanModulo(want - body.yaw + Math.PI, Math.PI * 2) - Math.PI
      body.yaw += MathUtils.clamp(diff, -rate * dt, rate * dt)
    }
    if (mode === 'walk') {
      // Steer onto a circle round the middle of the room, turning left: along the
      // tangent, leaning in or out by how far off the circle he is.
      const s = speed('walk')
      const r = Math.hypot(body.x, body.z)
      turnTo(Math.atan2(body.x, body.z) + Math.PI / 2 + MathUtils.clamp(1.2 * (r - WALK_CIRCLE), -0.8, 0.8), s / 1.1)
      body.x += Math.sin(body.yaw) * s * dt
      body.z += Math.cos(body.yaw) * s * dt
    } else {
      // Everything else plays to the camera: turn to face it.
      turnTo(Math.atan2(cam.x - body.x, cam.z - body.z), 2.2)
    }
    if (mode === 'strafe') {
      const step = speed('strafe_left') * strafe.dir * dt
      body.x += Math.cos(body.yaw) * step
      body.z -= Math.sin(body.yaw) * step
      strafe.travelled += step
      if (Math.abs(strafe.travelled) > STRAFE_REACH && Math.sign(strafe.travelled) === strafe.dir) {
        strafe.dir = -strafe.dir
        crossfade(actions, strafe.dir > 0 ? 'strafe_left' : 'strafe_right')
      }
    }
    g.position.set(body.x, 0, body.z)
    g.rotation.y = body.yaw
    g.updateWorldMatrix(false, true)
    rig.hips.getWorldPosition(ground.hips)
    rig.feet.forEach(([foot, toe], i) => {
      foot.getWorldPosition(ground.feet[i])
      ground.feet[i].lerp(toe.getWorldPosition(v), 0.5) // midfoot
    })
    ground.yaw = body.yaw

    // Mouth: loudness opens the jaw, brightness picks wide ("ee") or round ("oo").
    const talking = mode === 'talk'
    const t = (face.time += dt) // its own clock: R3F's restarts when the frameloop changes
    const sig = mouthSignal()
    face.level = approach(face.level, sig.level, dt, sig.level > face.level ? 0.035 : 0.09)
    face.bright = approach(face.bright, sig.bright, dt, 0.08)
    face.press = approach(face.press, talking && face.level < 0.05 ? 0.5 : 0, dt, 0.05) // lips meet between words
    const open = Math.min(1, face.level * 2.2)
    rig.jaw.quaternion.copy(rig.jawRest).multiply(q.setFromAxisAngle(X, MathUtils.degToRad(15 * face.level ** 0.8)))

    if (t > face.blinkAt) {
      face.blink = t
      face.blinkAt = t + 1.8 + Math.random() * 3.5
    }
    const blink = face.blink >= 0 && t - face.blink < 0.17 ? Math.sin(((t - face.blink) / 0.17) * Math.PI) : 0
    const weights: Record<string, number> = {
      mouth_wide: MathUtils.smoothstep(face.bright, 0.45, 0.75) * open,
      mouth_round: (1 - MathUtils.smoothstep(face.bright, 0.18, 0.42)) * open,
      lip_upper_up: MathUtils.smoothstep(face.bright, 0.7, 0.95) * 0.45 * open,
      mouth_press: face.press,
      mouth_smile: talking ? 0.12 : 0.06,
      blink_L: blink,
      blink_R: blink,
    }
    for (const mesh of rig.faces) {
      for (const [name, w] of Object.entries(weights)) {
        const i = mesh.morphTargetDictionary![name]
        if (i !== undefined) mesh.morphTargetInfluences![i] = w
      }
    }

    // Eyes: on the camera while he talks or stands, ahead otherwise; small saccades.
    if (t > face.saccadeAt) {
      face.saccadeAt = t + 0.6 + Math.random() * 2
      lookTo.set((Math.random() - 0.5) * 0.25, (Math.random() - 0.5) * 0.12, 0)
    }
    look.lerp(lookTo, 1 - Math.exp(-dt / 0.03))
    const atCamera = mode === 'talk' || mode === 'idle'
    for (const { eye, rest } of rig.eyes) {
      eye.quaternion.copy(rest)
      if (!atCamera) {
        eye.quaternion.multiply(q.setFromAxisAngle(X, look.y))
        continue
      }
      // Rotate the eye's world forward onto the camera, capped, then back into local space.
      eye.updateWorldMatrix(true, false)
      eye.getWorldPosition(v)
      v2.copy(cam).add(look).sub(v).normalize()
      eye.getWorldQuaternion(q)
      v.copy(FORWARD).applyQuaternion(q)
      q2.setFromUnitVectors(v, v2)
      const angle = 2 * Math.acos(MathUtils.clamp(q2.w, -1, 1))
      if (angle > MAX_EYE) q2.slerp(IDENTITY, 1 - MAX_EYE / angle)
      eye.parent!.getWorldQuaternion(parentQ)
      eye.quaternion.copy(parentQ.invert().multiply(q2).multiply(q))
    }
  })

  return (
    <group ref={group} dispose={null}>
      <primitive object={gltf.scene} />
    </group>
  )
}
