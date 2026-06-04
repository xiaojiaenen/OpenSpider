import React, { useEffect, useState } from 'react'
import {
  Table, Tag, Button, Space, Typography, message, Modal, Form, Input, Switch, Card,
  Select, Tooltip, Empty,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, ClockCircleOutlined, CheckCircleOutlined,
  PauseCircleOutlined, DeleteOutlined, EditOutlined, BugOutlined,
} from '@ant-design/icons'
import { scheduleApi, spiderApi } from '../services/api'
import type { ColumnsType } from 'antd/es/table'

const { Title, Text } = Typography

/* ── Cron 预设 ──────────────────────────────── */

interface CronPreset {
  label: string
  value: string
}

const CRON_PRESETS: CronPreset[] = [
  { label: '每小时', value: '0 * * * *' },
  { label: '每 2 小时', value: '0 */2 * * *' },
  { label: '每 6 小时', value: '0 */6 * * *' },
  { label: '每天 8:00', value: '0 8 * * *' },
  { label: '每天 12:00', value: '0 12 * * *' },
  { label: '每天 20:00', value: '0 20 * * *' },
  { label: '每周一 8:00', value: '0 8 * * 1' },
  { label: '每周五 18:00', value: '0 18 * * 5' },
  { label: '自定义 cron', value: '__custom__' },
]

const CRON_LABEL_MAP: Record<string, string> = Object.fromEntries(
  CRON_PRESETS.map((p) => [p.value, p.label]),
)

function cronToPreset(cron: string): string {
  return CRON_LABEL_MAP[cron] ? cron : '__custom__'
}

/* ── Spider 信息 ────────────────────────────── */

interface SpiderInfo {
  name: string
  description?: string
}

/* ── 组件 ───────────────────────────────────── */

const SchedulesPage: React.FC = () => {
  const [schedules, setSchedules] = useState<any[]>([])
  const [spiders, setSpiders] = useState<SpiderInfo[]>([])
  const [spiderMap, setSpiderMap] = useState<Record<string, SpiderInfo>>({})
  const [loading, setLoading] = useState(true)
  const [spidersLoading, setSpidersLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const cronPreset = Form.useWatch('cronPreset', form)

  /* ── 数据加载 ───────────────────────────── */

  const loadSchedules = async () => {
    setLoading(true)
    try {
      const data = await scheduleApi.list()
      setSchedules(data.schedules || [])
    } catch {
      // 静默
    } finally {
      setLoading(false)
    }
  }

  const loadSpiders = async () => {
    setSpidersLoading(true)
    try {
      const data = await spiderApi.list()
      const list: SpiderInfo[] = data.spiders || data || []
      setSpiders(list)
      const map: Record<string, SpiderInfo> = {}
      list.forEach((s) => { map[s.name] = s })
      setSpiderMap(map)
    } catch {
      // 静默
    } finally {
      setSpidersLoading(false)
    }
  }

  useEffect(() => {
    loadSchedules()
    loadSpiders()
  }, [])

  /* ── 操作 ────────────────────────────────── */

  const handleToggle = async (record: any) => {
    try {
      if (record.status === 'enabled') {
        await scheduleApi.disable(record.id)
      } else {
        await scheduleApi.enable(record.id)
      }
      message.success('操作成功')
      loadSchedules()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    }
  }

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: '确认删除此调度？',
      content: '删除后不可恢复，请谨慎操作。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await scheduleApi.remove(id)
        message.success('已删除')
        loadSchedules()
      },
    })
  }

  const handleCreate = async (values: any) => {
    const cron = values.cronPreset === '__custom__'
      ? values.customCron
      : values.cronPreset

    if (!cron) {
      message.warning('请选择或输入 Cron 表达式')
      return
    }

    try {
      await scheduleApi.create({
        spider_name: values.spider_name,
        cron,
      })
      message.success('调度已创建')
      setModalOpen(false)
      form.resetFields()
      loadSchedules()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '创建失败')
    }
  }

  /* ── 表格列定义 ──────────────────────────── */

  const columns: ColumnsType<any> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 64,
      align: 'center',
    },
    {
      title: '爬虫',
      dataIndex: 'spider_name',
      render: (name: string) => {
        const spider = spiderMap[name]
        return (
          <Space direction="vertical" size={0}>
            <Text strong>
              <BugOutlined style={{ marginRight: 4, color: '#1677ff' }} />
              {name}
            </Text>
            {spider?.description && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {spider.description}
              </Text>
            )}
          </Space>
        )
      },
    },
    {
      title: '调度规则',
      dataIndex: 'cron',
      width: 160,
      render: (cron: string) => {
        const label = CRON_LABEL_MAP[cron]
        return (
          <Tooltip title={cron}>
            <Tag icon={<ClockCircleOutlined />} color="blue">
              {label || cron}
            </Tag>
          </Tooltip>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      align: 'center',
      render: (s: string) => {
        const enabled = s === 'enabled'
        return (
          <Tag
            icon={enabled ? <CheckCircleOutlined /> : <PauseCircleOutlined />}
            color={enabled ? 'success' : 'default'}
          >
            {enabled ? '运行中' : '已暂停'}
          </Tag>
        )
      },
    },
    {
      title: '下次运行',
      dataIndex: 'next_run',
      width: 180,
      render: (v: string) => (
        <Text type={v ? undefined : 'secondary'}>
          {v ? new Date(v).toLocaleString('zh-CN') : '-'}
        </Text>
      ),
    },
    {
      title: '执行次数',
      dataIndex: 'run_count',
      width: 90,
      align: 'center',
      render: (count: number) => (
        <Text strong>{count ?? 0}</Text>
      ),
    },
    {
      title: '操作',
      width: 140,
      align: 'center',
      render: (_: any, record: any) => (
        <Space size="small">
          <Tooltip title={record.status === 'enabled' ? '暂停' : '启用'}>
            <Switch
              checked={record.status === 'enabled'}
              onChange={() => handleToggle(record)}
              size="small"
              checkedChildren="启"
              unCheckedChildren="停"
            />
          </Tooltip>
          <Tooltip title="删除">
            <Button
              type="text"
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record.id)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  /* ── 渲染 ─────────────────────────────────── */

  return (
    <Card
      style={{ margin: 0, borderRadius: 8 }}
      styles={{ body: { padding: 24 } }}
    >
      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 20,
        }}
      >
        <Space align="center">
          <Title level={4} style={{ margin: 0 }}>
            <ClockCircleOutlined style={{ marginRight: 8 }} />
            定时调度
          </Title>
          <Tag color="blue">{schedules.length} 个任务</Tag>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadSchedules}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModalOpen(true)}
          >
            创建调度
          </Button>
        </Space>
      </div>

      {/* 表格 */}
      <Table
        columns={columns}
        dataSource={schedules}
        rowKey="id"
        loading={loading}
        pagination={schedules.length > 10 ? { pageSize: 10, showTotal: (t) => `共 ${t} 条` } : false}
        locale={{
          emptyText: (
            <Empty
              description="暂无调度任务"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ),
        }}
        size="middle"
        style={{ borderRadius: 8 }}
      />

      {/* 创建调度 Modal */}
      <Modal
        title={
          <Space>
            <PlusOutlined />
            创建调度
          </Space>
        }
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false)
          form.resetFields()
        }}
        onOk={() => form.submit()}
        okText="创建"
        cancelText="取消"
        destroyOnClose
        width={480}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
          style={{ marginTop: 16 }}
        >
          <Form.Item
            name="spider_name"
            label="爬虫"
            rules={[{ required: true, message: '请选择爬虫' }]}
          >
            <Select
              placeholder="选择要调度的爬虫"
              loading={spidersLoading}
              showSearch
              optionFilterProp="label"
              options={spiders.map((s) => ({
                value: s.name,
                label: s.description ? `${s.name} - ${s.description}` : s.name,
              }))}
            />
          </Form.Item>

          <Form.Item
            name="cronPreset"
            label="调度频率"
            rules={[{ required: true, message: '请选择调度频率' }]}
            initialValue="0 */6 * * *"
          >
            <Select
              placeholder="选择调度频率"
              options={CRON_PRESETS.map((p) => ({
                value: p.value,
                label: p.label,
              }))}
            />
          </Form.Item>

          {cronPreset === '__custom__' && (
            <Form.Item
              name="customCron"
              label="Cron 表达式"
              rules={[{ required: true, message: '请输入 Cron 表达式' }]}
              extra="格式: 分 时 日 月 周 (例: 0 8 * * *)"
            >
              <Input
                placeholder="0 */6 * * *"
                style={{ fontFamily: 'monospace' }}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </Card>
  )
}

export default SchedulesPage
