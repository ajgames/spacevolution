import { lazy, type ReactNode, Suspense } from 'react'
import { Route, Routes } from 'react-router'
import Landing from './routes/landing.tsx'

// The 3D routes load on demand, so the landing page doesn't wait for three.js.
const Fly = lazy(() => import('./routes/fly.tsx'))
const Demo = lazy(() => import('./routes/demo.tsx'))

export default function App() {
  return (
    <Routes>
      <Route index element={<Landing />} />
      <Route path="fly" element={<Scene3d route={<Fly />} />} />
      <Route path="demo" element={<Scene3d route={<Demo />} />} />
    </Routes>
  )
}

function Scene3d({ route }: { route: ReactNode }) {
  return <Suspense fallback={<main className="h-dvh bg-black" />}>{route}</Suspense>
}
