import React from 'react'
import { Layout, Menu, Button, Space, Typography, Avatar, Dropdown } from 'antd'
import {
  DashboardOutlined,
  BugOutlined,
  UnorderedListOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/spiders', icon: <BugOutlined />, label: '爬虫管理' },
  { key: '/tasks', icon: <UnorderedListOutlined />, label: '任务列表' },
  { key: '/schedules', icon: <ClockCircleOutlined />, label: '定时调度' },
  { key: '/items', icon: <DatabaseOutlined />, label: '数据浏览' },
]

const MainLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const userMenu = {
    items: [
      { key: 'profile', icon: <UserOutlined />, label: '个人设置', onClick: () => navigate('/settings') },
      { type: 'divider' as const },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
    ],
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        theme="light"
        width={220}
        style={{
          borderRight: '1px solid #f0f0f0',
          boxShadow: '2px 0 8px rgba(0,0,0,0.03)',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <Text strong style={{ fontSize: 18, letterSpacing: '-0.02em' }}>
            Open<span style={{ color: '#d97757' }}>Spider</span>
          </Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ border: 'none', paddingTop: 8 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            borderBottom: '1px solid #f0f0f0',
            height: 64,
          }}
        >
          <Space>
            <Text type="secondary" style={{ fontSize: 13 }}>
              {user?.display_name || user?.username}
            </Text>
            <Dropdown menu={userMenu} placement="bottomRight">
              <Avatar
                size={32}
                icon={<UserOutlined />}
                style={{ background: '#d97757', cursor: 'pointer' }}
              />
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24, background: '#f7f7f5', overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout
