import { useEffect, useState } from 'react'
import type { LightingState } from '../scene/shipData.ts'
import { lightingFor, useDemo } from './store.ts'

// The phase picks the lighting; a breaker fault stutters it between emergency
// and blackout until the breakers have reset.
export function useLighting(): LightingState {
  const phase = useDemo((s) => s.phase)
  const stutter = useDemo((s) => s.stutter)
  const [flicker, setFlicker] = useState<LightingState>('blackout')
  useEffect(() => {
    if (!stutter) return
    let timer: ReturnType<typeof setTimeout>
    const step = () => {
      setFlicker((f) => (f === 'blackout' ? 'emergency' : 'blackout'))
      timer = setTimeout(step, 40 + Math.random() * 180)
    }
    step()
    return () => clearTimeout(timer)
  }, [stutter])
  return stutter ? flicker : lightingFor(phase)
}
