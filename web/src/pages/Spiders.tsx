import React, { useEffect, useState } from 'react'
import {
  Table, Tag, Button, Space, Typography, message, Upload, Modal, Tooltip, Card, Switch,
} from 'antd'
import {
  PlayCircleOutlined, PauseOutlined, StopOutlined,
  DeleteOutlined, ReloadOutlined, CloudUploadOutlined, SyncOutlined,
  BugOutlined, GlobalOutlined, LockOutlined,
} from '@ant-design/icons'
import { spiderApi } from '../services/api'
import type { ColumnsType } from 'antd/es/table'

const { Title } = Typography

const statusMap: Record<string, { color: string; text: string }> = {
  idle: { color: 'default', text: '空闲' },
  running: { color: 'processing', text: '运行中' },
  paused: { color: 'warning', text: '已暂停' },
  failed: { color: 'error', text: '失败' },
  disabled: { color: 'default', text: '已禁用' },
}

const SpidersPage: React.FC = () => {
  const [spiders, setSpiders] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const data = await spiderApi.list()
      setSpiders(data.spiders || [])
    } catch {
      message.error('加载爬虫列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleAction = async (action: 'start' | 'stop' | 'pause' | 'resume' | 'remove', id: number) => {
    try {
      await spiderApi[action](id)
      message.success(`操作成功`)
      load()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    }
  }

  const handleDelete = (id: number, name: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除爬虫「${name}」吗？`,
      okText: '删除',
      okType: 'danger',
      onOk: async () => {
        await handleAction('remove', id)
      },
    })
  }

  const handleToggleVisibility = async (id: number, isPublic: boolean) => {
    try {
      await spiderApi.setVisibility(id, isPublic)
      message.success(isPublic ? '已设为公开' : '已设为私有')
      load()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    }
  }

  const columns: ColumnsType<any> = [
    {
      title: '名称',
      dataIndex: 'name',
      render: (name: string, record: any) => (
        <Space>
          <strong>{name}</strong>
          {record.is_public && (
            <Tooltip title="公开爬虫">
              <Tag color="blue" icon={<GlobalOutlined />} style={{ margin: 0 }}>公开</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => {
        const info = statusMap[s] || { color: 'default', text: s }
        const icon = s === 'running' ? <SyncOutlined spin /> : undefined
        return <Tag color={info.color} icon={icon}>{info.text}</Tag>
      },
    },
    { title: '数据量', dataIndex: 'items_scraped', width: 90 },
    { title: '请求', dataIndex: 'requests_made', width: 80 },
    { title: '错误', dataIndex: 'errors_count', width: 70, render: (v: number) =>
      v > 0 ? <Tag color="error">{v}</Tag> : v
    },
    {
      title: '可见性',
      width: 100,
      render: (_: any, record: any) => {
        const isMine = !!record.owner_user_id
        if (!isMine) {
          return record.is_public
            ? <Tag color="blue" icon={<GlobalOutlined />}>公开</Tag>
            : <Tag icon={<LockOutlined />}>私有</Tag>
        }
        return (
          <Switch
            checked={record.is_public}
            checkedChildren="公开"
            unCheckedChildren="私有"
            onChange={(checked) => handleToggleVisibility(record.id, checked)}
          />
        )
      },
    },
    {
      title: '操作',
      width: 200,
      render: (_: any, record: any) => {
        const running = record.is_running
        return (
          <Space size={4}>
            {running ? (
              <>
                <Tooltip title="暂停">
                  <Button size="small" icon={<PauseOutlined />}
                    onClick={() => handleAction('pause', record.id)} />
                </Tooltip>
                <Tooltip title="停止">
                  <Button size="small" danger icon={<StopOutlined />}
                    onClick={() => handleAction('stop', record.id)} />
                </Tooltip>
              </>
            ) : (
              <>
                <Tooltip title="启动">
                  <Button size="small" type="primary" icon={<PlayCircleOutlined />}
                    onClick={() => handleAction('start', record.id)} />
                </Tooltip>
                <Tooltip title="恢复">
                  <Button size="small" icon={<ReloadOutlined />}
                    onClick={() => handleAction('resume', record.id)} />
                </Tooltip>
              </>
            )}
            <Tooltip title="删除">
              <Button size="small" danger icon={<DeleteOutlined />}
                onClick={() => handleDelete(record.id, record.name)} />
            </Tooltip>
          </Space>
        )
      },
    },
  ]

  return (
    <Card style={{ borderRadius: 8 }} styles={{ body: { padding: 24 } }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Space align="center">
          <Title level={4} style={{ margin: 0 }}>
            <BugOutlined style={{ marginRight: 8 }} />
            爬虫管理
          </Title>
          <Tag>{spiders.length} 个</Tag>
        </Space>
        <Space>
          <Upload
            showUploadList={false}
            accept=".py"
            customRequest={async ({ file }) => {
              try {
                await spiderApi.upload(file as File)
                message.success('上传成功')
                load()
              } catch (err: any) {
                message.error(err.response?.data?.detail || '上传失败')
              }
            }}
          >
            <Button icon={<CloudUploadOutlined />}>上传爬虫</Button>
          </Upload>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </div>
      <Table columns={columns} dataSource={spiders} rowKey="id" loading={loading} size="middle" />
    </Card>
  )
}

export default SpidersPage
