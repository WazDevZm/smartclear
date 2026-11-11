import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import { session } from './api'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Shell from './components/Shell'
import Dashboard from './pages/Dashboard'
import Queue from './pages/Queue'
import CaseDetail from './pages/CaseDetail'
import Upload from './pages/Upload'
import Batch from './pages/Batch'
import Records from './pages/Records'
import Performance from './pages/Performance'
import Audit from './pages/Audit'

function Private({ children }) {
  return session()?.token ? children : <Navigate to="/login" replace />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/app" element={<Private><Shell /></Private>}>
          <Route index element={<Dashboard />} />
          <Route path="queue" element={<Queue />} />
          <Route path="cases/:id" element={<CaseDetail />} />
          <Route path="verify" element={<Upload />} />
          <Route path="batch" element={<Batch />} />
          <Route path="records" element={<Records />} />
          <Route path="performance" element={<Performance />} />
          <Route path="audit" element={<Audit />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
