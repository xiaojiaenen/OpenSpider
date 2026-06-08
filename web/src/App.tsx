import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/auth'
import { authApi } from './services/api'
import MainLayout from './layouts/MainLayout'
import LoginPage from './pages/Login'
import RegisterPage from './pages/Register'
import DashboardPage from './pages/Dashboard'
import SpidersPage from './pages/Spiders'
import TasksPage from './pages/Tasks'
import SchedulesPage from './pages/Schedules'
import ItemsPage from './pages/Items'
import SettingsPage from './pages/Settings'

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

const App: React.FC = () => {
  const { isAuthenticated, user, setUser } = useAuthStore()

  // 仅当已登录但没有用户信息时才拉取（store 初始化时已从 localStorage 恢复）
  useEffect(() => {
    if (isAuthenticated && !user) {
      authApi.getMe().then(setUser).catch((err) => {
        if (err?.response?.status === 401) {
          useAuthStore.getState().logout()
        }
      })
    }
  }, [isAuthenticated, user, setUser])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="spiders" element={<SpidersPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="schedules" element={<SchedulesPage />} />
          <Route path="items" element={<ItemsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
