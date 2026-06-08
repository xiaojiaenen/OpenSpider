import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import {
  Table, Tag, Button, Space, Typography, Upload, Modal, Tooltip, Card, Switch, App, Drawer,
} from 'antd'
import {
  PlayCircleOutlined, PauseOutlined, StopOutlined,
  DeleteOutlined, ReloadOutlined, CloudUploadOutlined, SyncOutlined,
  BugOutlined, GlobalOutlined, LockOutlined, CodeOutlined,
} from '@ant-design/icons'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import 'highlight.js/styles/github.css'
import { spiderApi } from '../services/api'
import type { ColumnsType } from 'antd/es/table'

hljs.registerLanguage('python', python)

const { Title, Text } = Typography

const statusMap: Record<string, { color: string; text: string }> = {
  idle: { color: 'default', text: '空闲' },
  running: { color: 'processing', text: '运行中' },
  paused: { color: 'warning', text: '已暂停' },
  failed: { color: 'error', text: '失败' },
  disabled: { color: 'default', text: '已禁用' },
}

const HighlightedCode: React.FC<{ code: string }> = React.memo(({ code }) => {
  const ref = useRef<HTMLPreElement>(null)
  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = hljs.highlight(code, { language: 'python' }).value
    }
  }, [code])
  return (
    <pre
      ref={ref}
      style={{
        background: '#f6f8fa',
        padding: 16,
        borderRadius: 8,
        fontSize: 13,
        lineHeight: 1.6,
        overflow: 'auto',
        maxHeight: 'calc(100vh - 160px)',
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        margin: 0,
        tabSize: 4,
      }}
    />
  )
})

const SpidersPage: React.FC = () => {
  const { message } = App.useApp()
  const [spiders, setSpiders] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  // 正在操作的爬虫 id 集合（防重复点击）
  const [actingIds, setActingIds] = useState<Set<number>>(new Set())
  // 正在切换可见性的 id
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set())
  // 代码查看抽屉
  const [codeDrawer, setCodeDrawer] = useState<{ open: boolean; name: string; source: string; loading: boolean }>({
    open: false, name: '', source: '', loading: false,
  })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await spiderApi.list()
      setSpiders(data.spiders || [])
    } catch {
      message.error('加载爬虫列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleAction = useCallback(async (action: 'start' | 'stop' | 'pause' | 'resume' | 'remove', id: number | null) => {
    if (!id) {
      message.warning('爬虫未同步，请刷新后重试')
      return
    }
    if (actingIds.has(id)) return
    setActingIds((prev) => new Set(prev).add(id))
    try {
      await spiderApi[action](id)
      message.success('操作成功')
      await load()
    } catch (err: any) {
      const detail = err.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '操作失败')
    } finally {
      setActingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }, [actingIds, load])

  const handleDelete = useCallback((id: number, name: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除爬虫「${name}」吗？`,
      okText: '删除',
      okType: 'danger',
      onOk: async () => {
        await handleAction('remove', id)
      },
    })
  }, [handleAction])

  const handleToggleVisibility = useCallback(async (id: number, isPublic: boolean) => {
    if (togglingIds.has(id)) return
    setTogglingIds((prev) => new Set(prev).add(id))
    try {
      await spiderApi.setVisibility(id, isPublic)
      message.success(isPublic ? '已设为公开' : '已设为私有')
      await load()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }, [togglingIds, load])

  const handleViewCode = useCallback(async (id: number, name: string) => {
    setCodeDrawer({ open: true, name, source: '', loading: true })
    try {
      const data = await spiderApi.getCode(id)
      setCodeDrawer({ open: true, name, source: data.source || '', loading: false })
    } catch (err: any) {
      message.error(err.response?.data?.detail || '获取代码失败')
      setCodeDrawer({ open: false, name: '', source: '', loading: false })
    }
  }, [])

  const columns: ColumnsType<any> = useMemo(() => [
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
            disabled={togglingIds.has(record.id)}
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
        const isPaused = record.status === 'paused'
        const acting = actingIds.has(record.id)
        return (
          <Space size={4}>
            {running ? (
              <>
                <Tooltip title="暂停">
                  <Button size="small" icon={<PauseOutlined />} loading={acting}
                    onClick={() => handleAction('pause', record.id)} />
                </Tooltip>
                <Tooltip title="停止">
                  <Button size="small" danger icon={<StopOutlined />} loading={acting}
                    onClick={() => handleAction('stop', record.id)} />
                </Tooltip>
              </>
            ) : (
              <>
                <Tooltip title="启动">
                  <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={acting}
                    onClick={() => handleAction('start', record.id)} />
                </Tooltip>
                {isPaused && (
                  <Tooltip title="恢复">
                    <Button size="small" icon={<ReloadOutlined />} loading={acting}
                      onClick={() => handleAction('resume', record.id)} />
                  </Tooltip>
                )}
              </>
            )}
            <Tooltip title="删除">
              <Button size="small" danger icon={<DeleteOutlined />} loading={acting}
                onClick={() => handleDelete(record.id, record.name)} />
            </Tooltip>
            {record.id && (
              <Tooltip title="查看代码">
                <Button size="small" icon={<CodeOutlined />}
                  onClick={() => handleViewCode(record.id, record.name)} />
              </Tooltip>
            )}
          </Space>
        )
      },
    },
  ], [actingIds, togglingIds, handleAction, handleDelete, handleToggleVisibility, handleViewCode])

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
      <Table columns={columns} dataSource={spiders} rowKey={(r: any) => r.id ?? r.name} loading={loading} size="middle" />

      <Drawer
        title={
          <Space>
            <CodeOutlined />
            <span>{codeDrawer.name}</span>
          </Space>
        }
        open={codeDrawer.open}
        onClose={() => setCodeDrawer({ open: false, name: '', source: '', loading: false })}
        width={720}
        destroyOnClose
      >
        {codeDrawer.loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>加载中...</div>
        ) : (
          <HighlightedCode code={codeDrawer.source} />
        )}
      </Drawer>
    </Card>
  )
}

export default SpidersPage
