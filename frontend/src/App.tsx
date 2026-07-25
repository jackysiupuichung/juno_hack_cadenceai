import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Onboarding from './pages/Onboarding'
import Consent from './pages/Consent'
import Home from './pages/Home'
import ConditionDetail from './pages/ConditionDetail'
import VisitDetail from './pages/VisitDetail'
import NewVisit from './pages/NewVisit'
import CheckIn from './pages/CheckIn'
import BriefPage from './pages/BriefPage'
import Settings from './pages/Settings'
import { getConsent, getProfile } from './localGate'

function Gate({ children }: { children: ReactNode }) {
  if (!getProfile()) return <Navigate to="/onboarding" replace />
  if (!getConsent()) return <Navigate to="/consent" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/onboarding" element={<Onboarding />} />
      <Route path="/consent" element={<Consent />} />
      <Route
        path="/"
        element={
          <Gate>
            <Home />
          </Gate>
        }
      />
      <Route
        path="/settings"
        element={
          <Gate>
            <Settings />
          </Gate>
        }
      />
      <Route
        path="/conditions/:conditionId"
        element={
          <Gate>
            <ConditionDetail />
          </Gate>
        }
      />
      <Route
        path="/conditions/:conditionId/visit/new"
        element={
          <Gate>
            <NewVisit />
          </Gate>
        }
      />
      <Route
        path="/conditions/:conditionId/visits/:visitId"
        element={
          <Gate>
            <VisitDetail />
          </Gate>
        }
      />
      <Route
        path="/conditions/:conditionId/checkin"
        element={
          <Gate>
            <CheckIn />
          </Gate>
        }
      />
      <Route
        path="/conditions/:conditionId/brief"
        element={
          <Gate>
            <BriefPage />
          </Gate>
        }
      />
    </Routes>
  )
}
