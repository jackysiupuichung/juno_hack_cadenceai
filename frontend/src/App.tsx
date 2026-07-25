import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import NewVisit from './pages/NewVisit'
import CheckIn from './pages/CheckIn'
import BriefPage from './pages/BriefPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/visit/new" element={<NewVisit />} />
      <Route path="/checkin" element={<CheckIn />} />
      <Route path="/brief" element={<BriefPage />} />
    </Routes>
  )
}
