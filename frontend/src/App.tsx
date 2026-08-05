import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useAuth } from './context/AuthContext'
import { Spinner } from './components/ui'

import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import ResumePage from './pages/Resume'
import InterviewSetup from './pages/InterviewSetup'
import InterviewRoom from './pages/InterviewRoom'
import ReportPage from './pages/Report'
import RoadmapPage from './pages/Roadmap'
import Admin from './pages/Admin'
import type { ReactElement } from 'react'

function Protected({ children, adminOnly = false }: {
  children: ReactElement; adminOnly?: boolean
}) {
  const { user, loading } = useAuth()
  if (loading) return <Spinner label="Loading your session…" />
  if (!user) return <Navigate to="/login" replace />
  if (adminOnly && user.role !== 'admin') return <Navigate to="/dashboard" replace />
  return children
}

export default function App() {
  const { user, loading } = useAuth()

  return (
    <Routes>
      <Route path="/login"
             element={loading ? <Spinner /> : user ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/register"
             element={loading ? <Spinner /> : user ? <Navigate to="/dashboard" replace /> : <Register />} />

      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/resume" element={<ResumePage />} />
        <Route path="/interview" element={<InterviewSetup />} />
        <Route path="/interview/:interviewId" element={<InterviewRoom />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/report/:interviewId" element={<ReportPage />} />
        <Route path="/roadmap" element={<RoadmapPage />} />
        <Route path="/admin" element={<Protected adminOnly><Admin /></Protected>} />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
