import axios from 'axios'
import { useAuthStore } from '../stores/auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：注入 JWT
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 自动刷新
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = useAuthStore.getState().refreshToken
      if (refreshToken) {
        try {
          const { data } = await axios.post('/auth/refresh', {
            refresh_token: refreshToken,
          })
          useAuthStore.getState().setTokens(data.access_token, data.refresh_token)
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
          return api(originalRequest)
        } catch {
          useAuthStore.getState().logout()
          window.location.href = '/login'
        }
      } else {
        useAuthStore.getState().logout()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api

// ── Auth API ─────────────────────────────────

export const authApi = {
  register: (data: { username: string; email: string; password: string; display_name?: string }) =>
    axios.post('/auth/register', data).then((r) => r.data),

  login: (username: string, password: string) =>
    axios.post('/auth/login/json', { username, password }).then((r) => r.data),

  refresh: (refresh_token: string) =>
    axios.post('/auth/refresh', { refresh_token }).then((r) => r.data),

  getMe: () => api.get('/auth/me').then((r) => r.data),

  updateProfile: (data: { display_name?: string; email?: string }) =>
    api.put('/auth/me', data).then((r) => r.data),

  changePassword: (data: { old_password: string; new_password: string }) =>
    api.put('/auth/me/password', data).then((r) => r.data),
}

// ── Spider API ───────────────────────────────

export const spiderApi = {
  list: () => api.get('/spiders').then((r) => r.data),
  get: (id: number) => api.get(`/spiders/${id}`).then((r) => r.data),
  start: (id: number, params?: Record<string, unknown>) =>
    api.post(`/spiders/${id}/start`, { params: params || {} }).then((r) => r.data),
  stop: (id: number) => api.post(`/spiders/${id}/stop`).then((r) => r.data),
  pause: (id: number) => api.post(`/spiders/${id}/pause`).then((r) => r.data),
  resume: (id: number) => api.post(`/spiders/${id}/resume`).then((r) => r.data),
  remove: (id: number) => api.delete(`/spiders/${id}`).then((r) => r.data),
  setVisibility: (id: number, isPublic: boolean) =>
    api.put(`/spiders/${id}/visibility`, { is_public: isPublic }).then((r) => r.data),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/spiders/upload', form).then((r) => r.data)
  },
}

// ── Task API ─────────────────────────────────

export const taskApi = {
  list: (params?: { spider?: string; status?: string; limit?: number; offset?: number }) =>
    api.get('/tasks', { params }).then((r) => r.data),
  get: (id: number) => api.get(`/tasks/${id}`).then((r) => r.data),
  logs: (id: number, limit?: number) =>
    api.get(`/tasks/${id}/logs`, { params: { limit } }).then((r) => r.data),
}

// ── Item API ─────────────────────────────────

export const itemApi = {
  list: (params?: { spider?: string; task_id?: number; page?: number; page_size?: number }) =>
    api.get('/items', { params }).then((r) => r.data),
  export: (spiderName: string, format = 'json') =>
    api.get(`/export/${spiderName}`, { params: { format } }).then((r) => r.data),
}

// ── Schedule API ─────────────────────────────

export const scheduleApi = {
  list: () => api.get('/schedules').then((r) => r.data),
  create: (data: { spider_name: string; cron: string; params?: Record<string, unknown> }) =>
    api.post('/schedules', data).then((r) => r.data),
  update: (id: number, data: { cron?: string; params?: Record<string, unknown> }) =>
    api.put(`/schedules/${id}`, data).then((r) => r.data),
  remove: (id: number) => api.delete(`/schedules/${id}`).then((r) => r.data),
  enable: (id: number) => api.post(`/schedules/${id}/enable`).then((r) => r.data),
  disable: (id: number) => api.post(`/schedules/${id}/disable`).then((r) => r.data),
  runs: (id: number) => api.get(`/schedules/${id}/runs`).then((r) => r.data),
}

// ── Health API ───────────────────────────────

export const healthApi = {
  check: () => axios.get('/health').then((r) => r.data),
}
