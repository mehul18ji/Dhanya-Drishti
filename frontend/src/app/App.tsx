import { Navigate, Route, Routes } from 'react-router-dom'

import { DashboardLayout } from '../components/layout/DashboardLayout'
import { AboutModelPage } from '../pages/AboutModelPage'
import { AnalyzePage } from '../pages/AnalyzePage'
import { HistoryPage } from '../pages/HistoryPage'

export default function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route index element={<AnalyzePage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="about" element={<AboutModelPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
