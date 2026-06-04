import React, { useEffect } from 'react'
import { Form, Input, Button, Typography, message, Card, Space, Divider } from 'antd'
import { useAuthStore } from '../stores/auth'
import { authApi } from '../services/api'

const { Title, Text } = Typography

const SettingsPage: React.FC = () => {
  const { user, setUser } = useAuthStore()
  const [profileForm] = Form.useForm()
  const [passwordForm] = Form.useForm()

  useEffect(() => {
    if (user) {
      profileForm.setFieldsValue({
        display_name: user.display_name,
        email: user.email,
      })
    }
  }, [user])

  const handleUpdateProfile = async (values: { display_name: string; email: string }) => {
    try {
      const updated = await authApi.updateProfile(values)
      setUser(updated)
      message.success('个人资料已更新')
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新失败')
    }
  }

  const handleChangePassword = async (values: {
    old_password: string
    new_password: string
  }) => {
    try {
      await authApi.changePassword(values)
      message.success('密码已更新')
      passwordForm.resetFields()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新失败')
    }
  }

  return (
    <Space direction="vertical" size={24} style={{ width: '100%', maxWidth: 600 }}>
      <Title level={4} style={{ margin: 0 }}>个人设置</Title>

      <Card title="个人资料">
        <Form form={profileForm} layout="vertical" onFinish={handleUpdateProfile}>
          <Form.Item label="用户名">
            <Input value={user?.username} disabled />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email' }]}>
            <Input />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">保存</Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="修改密码">
        <Form form={passwordForm} layout="vertical" onFinish={handleChangePassword}>
          <Form.Item
            name="old_password"
            label="旧密码"
            rules={[{ required: true, message: '请输入旧密码' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[{ required: true, min: 6, message: '至少 6 个字符' }]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">修改密码</Button>
          </Form.Item>
        </Form>
      </Card>
    </Space>
  )
}

export default SettingsPage
