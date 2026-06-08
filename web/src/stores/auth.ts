import { create } from 'zustand'

interface UserInfo {
  id: number
  username: string
  email: string
  display_name: string
  role: string
  status: string
}

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: UserInfo | null
  isAuthenticated: boolean

  setTokens: (access: string, refresh: string) => void
  setUser: (user: UserInfo) => void
  logout: () => void
  loadFromStorage: () => void
}

// 初始化时直接从 localStorage 读取，避免首次渲染竞态
function _loadInitial(): Pick<AuthState, 'accessToken' | 'refreshToken' | 'user' | 'isAuthenticated'> {
  try {
    const access = localStorage.getItem('access_token')
    const refresh = localStorage.getItem('refresh_token')
    const userInfo = localStorage.getItem('user_info')
    if (access && refresh) {
      return {
        accessToken: access,
        refreshToken: refresh,
        user: userInfo ? JSON.parse(userInfo) : null,
        isAuthenticated: true,
      }
    }
  } catch {
    // localStorage 不可用时静默降级
  }
  return { accessToken: null, refreshToken: null, user: null, isAuthenticated: false }
}

export const useAuthStore = create<AuthState>((set) => ({
  ..._loadInitial(),

  setTokens: (access, refresh) => {
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
    set({ accessToken: access, refreshToken: refresh, isAuthenticated: true })
  },

  setUser: (user) => {
    localStorage.setItem('user_info', JSON.stringify(user))
    set({ user })
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
    set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false })
  },

  loadFromStorage: () => {
    const access = localStorage.getItem('access_token')
    const refresh = localStorage.getItem('refresh_token')
    const userInfo = localStorage.getItem('user_info')
    if (access && refresh) {
      const user = userInfo ? JSON.parse(userInfo) : null
      set({ accessToken: access, refreshToken: refresh, isAuthenticated: true, user })
    }
  },
}))
