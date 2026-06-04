import React, { useEffect, useState } from 'react'
import { Table, Tag, Select, Typography, Space, Drawer, Card } from 'antd'
import { taskApi } from '../services/api'
import type { ColumnsType } from 'antd/es/table'

const { Title, Text } = Typography

const statusConfig: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  pending: { color: 'default', label: '等待中' },
  paused: { color: 'warning', label: '已暂停' },
  crashed: { color: 'error', label: '崩溃' },
}

const TasksPage: React.FC = () => {
  const [tasks, setTasks] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [page, setPage] = useState(1)
  const [logs, setLogs] = useState<any[]>([])
  const [logDrawer, setLogDrawer] = useState<{ open: boolean; taskId: number | null }>({
    open: false,
    taskId: null,
  })

  const load = async () => {
    setLoading(true)
    try {
      const data = await taskApi.list({
        status: statusFilter,
        limit: 20,
        offset: (page - 1) * 20,
      })
      setTasks(data.tasks || [])
      setTotal(data.total || 0)
    } catch {
      // 静默
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [statusFilter, page])

  const openLogs = async (taskId: number) => {
    setLogDrawer({ open: true, taskId })
    try {
      const data = await taskApi.logs(taskId, 200)
      setLogs(data.logs || [])
    } catch {
      setLogs([])
    }
  }

  const columns: ColumnsType<any> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '爬虫', dataIndex: 'spider_name' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => {
        const cfg = statusConfig[s] || { color: 'default', label: s }
        return <Tag color={cfg.color}>{cfg.label}</Tag>
      },
    },
    { title: '数据', dataIndex: 'items_scraped', width: 80 },
    { title: '请求', dataIndex: 'requests_made', width: 80 },
    { title: '错误', dataIndex: 'errors_count', width: 70 },
    {
      title: '开始时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
    },
    {
      title: '操作',
      width: 80,
      render: (_: any, record: any) => (
        <a onClick={() => openLogs(record.id)}>日志</a>
      ),
    },
  ]

  const logLevelMap: Record<string, { color: string; label: string }> = {
    error: { color: 'error', label: '错误' },
    warning: { color: 'warning', label: '警告' },
    info: { color: 'processing', label: '信息' },
    debug: { color: 'default', label: '调试' },
  }

  return (
    <Card style={{ borderRadius: 8 }} styles={{ body: { padding: 24 } }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={4} style={{ margin: 0 }}>任务列表</Title>
        <Select
          placeholder="全部状态"
          allowClear
          style={{ width: 140 }}
          onChange={(v) => { setStatusFilter(v); setPage(1) }}
          options={[
            { value: 'running', label: '运行中' },
            { value: 'completed', label: '已完成' },
            { value: 'failed', label: '失败' },
            { value: 'paused', label: '已暂停' },
            { value: 'crashed', label: '已崩溃' },
          ]}
        />
      </div>
      <Table
        columns={columns}
        dataSource={tasks}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: setPage,
          showTotal: (t) => `共 ${t} 条`,
        }}
      />
      <Drawer
        title={`任务 #${logDrawer.taskId} 日志`}
        open={logDrawer.open}
        onClose={() => setLogDrawer({ open: false, taskId: null })}
        width={600}
      >
        {logs.length === 0 ? (
          <Text type="secondary">暂无日志</Text>
        ) : (
          <div style={{ fontFamily: 'monospace', fontSize: 13, lineHeight: 1.8 }}>
            {logs.map((log: any) => {
              const levelCfg = logLevelMap[log.level] || { color: 'default', label: log.level }
              return (
                <div key={log.id} style={{ padding: '2px 0' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    [{new Date(log.created_at).toLocaleTimeString()}]
                  </Text>{' '}
                  <Tag color={levelCfg.color} style={{ fontSize: 11 }}>
                    {levelCfg.label}
                  </Tag>{' '}
                  {log.message}
                </div>
              )
            })}
          </div>
        )}
      </Drawer>
    </Card>
  )
}

export default TasksPage
