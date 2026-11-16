import { lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { prefetchAfterLogin, prefetchBeforeLogin } from './lib/prefetch'
import { useStore } from './state/store'
import { Login } from './ui/Login'
import { Shell } from './ui/Shell'

// One download per page, fetched ahead of time by `lib/prefetch.ts` while the browser is idle.
const LiveMap = lazy(() => import('./pages/LiveMap').then((module) => ({ default: module.LiveMap })))
const Tasks = lazy(() => import('./pages/Tasks').then((module) => ({ default: module.Tasks })))
const Zones = lazy(() => import('./pages/Zones').then((module) => ({ default: module.Zones })))
const Clinics = lazy(() => import('./pages/Clinics').then((module) => ({ default: module.Clinics })))
const Building = lazy(() => import('./pages/Building').then((module) => ({ default: module.Building })))
const Stock = lazy(() => import('./pages/Stock').then((module) => ({ default: module.Stock })))
const Night = lazy(() => import('./pages/Night').then((module) => ({ default: module.Night })))
const Audit = lazy(() => import('./pages/Audit').then((module) => ({ default: module.Audit })))
const Incidents = lazy(() => import('./pages/Incidents').then((module) => ({ default: module.Incidents })))
const Monitor = lazy(() => import('./pages/Monitor').then((module) => ({ default: module.Monitor })))
const System = lazy(() => import('./pages/System').then((module) => ({ default: module.System })))
const Patients = lazy(() => import('./pages/Patients').then((module) => ({ default: module.Patients })))

function PageLoading() {
  return <div className="page-loading" role="status">Loading…</div>
}

export default function App() {
  const session = useStore((state) => state.session)
  const theme = useStore((state) => state.theme)
  useEffect(() => { document.documentElement.dataset.theme = theme }, [theme])
  // While the operator types, fetch the map; once signed in, every other page.
  useEffect(() => { if (session) prefetchAfterLogin(); else prefetchBeforeLogin() }, [session])
  useEffect(() => {
    const expire = (): void => { useStore.getState().signOut() }
    window.addEventListener('clinic-pilot:session-expired', expire)
    return () => window.removeEventListener('clinic-pilot:session-expired', expire)
  }, [])

  if (!session) return <Login />
  return (
    <Shell>
      <Suspense fallback={<PageLoading />}>
        <Routes>
          <Route path="/" element={<LiveMap />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/zones" element={<Zones />} />
          <Route path="/clinics" element={<Clinics />} />
          <Route path="/building" element={<Building />} />
          <Route path="/stock" element={<Stock />} />
          <Route path="/night" element={<Night />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/monitor" element={<Monitor />} />
          <Route path="/patients" element={<Patients />} />
          <Route path="/system" element={<System />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Shell>
  )
}
