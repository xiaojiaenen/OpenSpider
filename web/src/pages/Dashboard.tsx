import React, { useEffect, useState, useCallback } from 'react'
import {
  Row,
  Col,
  Card,
  Table,
  Tag,
  Typography,
  Space,
  Button,
  message,
  Tooltip,
  Progress,
  Empty,
} from 'antd'
import {
  BugOutlined,
  ThunderboltOutlined,
  DatabaseOutlined,
  CheckCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RocketOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusOutlined,
} from '@ant-design/icons'
import { spiderApi, taskApi } from '../services/api'
import type { ColumnsType } from 'antd/es/table'

const { Title, Text } = Typography

const statusConfig: Record<
  string,
  { color: string; bg: string; label: string }
> = {
  running: { color: '#1677ff', bg: '#e6f4ff', label: '运行中' },
  completed: { color: '#52c41a', bg: '#f6ffed', label: '已完成' },
  failed: { color: '#ff4d4f', bg: '#fff2f0', label: '失败' },
  crashed: { color: '#ff4d4f', bg: '#fff2f0', label: '崩溃' },
  pending: { color: '#8c8c8c', bg: '#f5f5f5', label: '等待中' },
  paused: { color: '#faad14', bg: '#fffbe6', label: '已暂停' },
}

interface StatCardProps {
  title: string
  value: number | string
  icon: React.ReactNode
  gradient: string
  borderColor: string
  trend?: 'up' | 'down' | 'flat'
  trendValue?: string
  suffix?: string
}

const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  icon,
  gradient,
  borderColor,
  trend,
  trendValue,
  suffix,
}) => {
  const trendIcon =
    trend === 'up' ? (
      <ArrowUpOutlined style={{ color: '#52c41a', fontSize: 12 }} />
    ) : trend === 'down' ? (
      <ArrowDownOutlined style={{ color: '#ff4d4f', fontSize: 12 }} />
    ) : (
      <MinusOutlined style={{ color: '#8c8c8c', fontSize: 12 }} />
    )

  return (
    <Card
      styles={{
        body: { padding: 0 },
      }}
      style={{
        borderRadius: 12,
        overflow: 'hidden',
        border: 'none',
        boxShadow: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'stretch',
        }}
      >
        {/* Left color border */}
        <div
          style={{
            width: 4,
            background: `linear-gradient(180deg, ${borderColor}, ${borderColor}88)`,
            borderRadius: '12px 0 0 12px',
            flexShrink: 0,
          }}
        />
        {/* Content */}
        <div
          style={{
            flex: 1,
            padding: '20px 24px',
            background: gradient,
            position: 'relative',
          }}
        >
          {/* Background icon watermark */}
          <div
            style={{
              position: 'absolute',
              right: 16,
              top: '50%',
              transform: 'translateY(-50%)',
              opacity: 0.06,
              fontSize: 56,
              lineHeight: 1,
              color: borderColor,
            }}
          >
            {icon}
          </div>
          <div style={{ position: 'relative', zIndex: 1 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: `${borderColor}18`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 16,
                  color: borderColor,
                }}
              >
                {icon}
              </div>
              <Text
                style={{
                  color: '#666',
                  fontSize: 13,
                  fontWeight: 500,
                }}
              >
                {title}
              </Text>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
              <span
                style={{
                  fontSize: 32,
                  fontWeight: 700,
                  color: '#1a1a1a',
                  lineHeight: 1.1,
                  letterSpacing: '-0.02em',
                }}
              >
                {value}
              </span>
              {suffix && (
                <span style={{ fontSize: 14, color: '#999', marginLeft: 2 }}>
                  {suffix}
                </span>
              )}
            </div>
            {trend && trendValue && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  marginTop: 6,
                }}
              >
                {trendIcon}
                <Text style={{ fontSize: 12, color: '#999' }}>
                  {trendValue}
                </Text>
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  )
}

const DashboardPage: React.FC = () => {
  const [spiders, setSpiders] = useState<any[]>([])
  const [tasks, setTasks] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [startingSpiders, setStartingSpiders] = useState<Set<string>>(
    new Set()
  )

  const loadData = useCallback(async () => {
    try {
      const [spiderData, taskData] = await Promise.all([
        spiderApi.list(),
        taskApi.list({ limit: 10 }),
      ])
      setSpiders(spiderData.spiders || [])
      setTasks(taskData.tasks || [])
    } catch {
      // silently ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const activeSpiders = spiders.filter((s) => s.is_running).length
  const totalItems = spiders.reduce((sum, s) => sum + (s.items_scraped || 0), 0)
  const failedTasks = tasks.filter(
    (t) => t.status === 'failed' || t.status === 'crashed'
  ).length
  const completedTasks = tasks.filter((t) => t.status === 'completed').length

  const handleQuickStart = async (spiderId: number, spiderName: string) => {
    setStartingSpiders((prev) => new Set(prev).add(spiderName))
    try {
      await spiderApi.start(spiderId)
      message.success(`已启动: ${spiderName}`)
      await loadData()
    } catch {
      message.error(`启动失败: ${spiderName}`)
    } finally {
      setStartingSpiders((prev) => {
        const next = new Set(prev)
        next.delete(spiderName)
        return next
      })
    }
  }

  const taskColumns: ColumnsType<any> = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 72,
      render: (id: number) => (
        <Text strong style={{ fontFamily: 'monospace', fontSize: 13 }}>
          #{id}
        </Text>
      ),
    },
    {
      title: '爬虫',
      dataIndex: 'spider_name',
      render: (name: string) => (
        <Text strong style={{ fontSize: 13 }}>
          {name}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (s: string) => {
        const cfg = statusConfig[s] || statusConfig.pending
        return (
          <Tag
            color={cfg.color}
            style={{
              borderRadius: 6,
              padding: '2px 10px',
              fontSize: 12,
              fontWeight: 500,
              background: cfg.bg,
              border: `1px solid ${cfg.color}25`,
            }}
          >
            {cfg.label || s}
          </Tag>
        )
      },
    },
    {
      title: '数据量',
      dataIndex: 'items_scraped',
      width: 100,
      align: 'right',
      render: (v: number) => (
        <Text
          style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}
        >
          {(v || 0).toLocaleString()}
        </Text>
      ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 13 }}>
          {v ? new Date(v).toLocaleString('zh-CN') : '-'}
        </Text>
      ),
    },
  ]

  const quickStartSpiders = spiders.filter(
    (s) => !s.is_running && s.id != null
  )

  return (
    <div style={{ maxWidth: 1400 }}>
      {/* Header */}
      <div
        style={{
          marginBottom: 28,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <Title level={4} style={{ margin: 0, fontWeight: 600 }}>
            仪表盘
          </Title>
          <Text type="secondary" style={{ fontSize: 13, marginTop: 4, display: 'block' }}>
            总览系统运行状态与任务进展
          </Text>
        </div>
        <Tooltip title="刷新数据">
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={() => {
              setLoading(true)
              loadData()
            }}
            loading={loading}
          />
        </Tooltip>
      </div>

      {/* Stats Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="注册爬虫"
            value={spiders.length}
            icon={<BugOutlined />}
            gradient="linear-gradient(135deg, #fff7f3 0%, #ffffff 100%)"
            borderColor="#d97757"
            trend="up"
            trendValue={`活跃 ${activeSpiders}`}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="运行中"
            value={activeSpiders}
            icon={<ThunderboltOutlined />}
            gradient="linear-gradient(135deg, #f0faf0 0%, #ffffff 100%)"
            borderColor="#52c41a"
            trend={activeSpiders > 0 ? 'up' : 'flat'}
            trendValue={
              activeSpiders > 0
                ? `${((activeSpiders / Math.max(spiders.length, 1)) * 100).toFixed(0)}% 占用`
                : '无运行任务'
            }
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="总数据量"
            value={totalItems.toLocaleString()}
            icon={<DatabaseOutlined />}
            gradient="linear-gradient(135deg, #f0f5ff 0%, #ffffff 100%)"
            borderColor="#1677ff"
            trend="up"
            trendValue={`${tasks.length} 次任务`}
            suffix="条"
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard
            title="任务成功率"
            value={
              tasks.length > 0
                ? `${((completedTasks / tasks.length) * 100).toFixed(0)}`
                : '0'
            }
            icon={<CheckCircleOutlined />}
            gradient="linear-gradient(135deg, #fff7f7 0%, #ffffff 100%)"
            borderColor="#ff4d4f"
            trend={failedTasks > 0 ? 'down' : 'flat'}
            trendValue={
              failedTasks > 0
                ? `${failedTasks} 个失败`
                : '全部正常'
            }
            suffix="%"
          />
        </Col>
      </Row>

      {/* Main Content: Quick Actions + Recent Tasks */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Recent Tasks */}
        <Col xs={24} lg={16}>
          <Card
            title={
              <span style={{ fontWeight: 600, fontSize: 15 }}>最近任务</span>
            }
            styles={{ body: { padding: 0 } }}
            style={{
              borderRadius: 12,
              overflow: 'hidden',
            }}
          >
            <Table
              columns={taskColumns}
              dataSource={tasks}
              rowKey="id"
              loading={loading}
              pagination={false}
              size="middle"
              rowClassName={(_, index) =>
                index !== undefined && index % 2 === 1
                  ? 'dashboard-row-alt'
                  : ''
              }
              style={{ fontSize: 14 }}
            />
          </Card>
        </Col>

        {/* Quick Actions */}
        <Col xs={24} lg={8}>
          <Card
            title={
              <span style={{ fontWeight: 600, fontSize: 15 }}>快捷操作</span>
            }
            style={{
              borderRadius: 12,
              overflow: 'hidden',
            }}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={10}>
              {quickStartSpiders.length > 0 ? (
                quickStartSpiders.slice(0, 6).map((spider) => (
                  <div
                    key={spider.name}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 12px',
                      background: '#fafafa',
                      borderRadius: 8,
                      border: '1px solid #f0f0f0',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        minWidth: 0,
                        flex: 1,
                      }}
                    >
                      <div
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 6,
                          background: '#f0f5ff',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        <RocketOutlined
                          style={{ color: '#1677ff', fontSize: 13 }}
                        />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <Text
                          strong
                          ellipsis
                          style={{ fontSize: 13, display: 'block' }}
                        >
                          {spider.name}
                        </Text>
                        <Text
                          type="secondary"
                          style={{ fontSize: 11 }}
                        >
                          {spider.items_scraped || 0} 条数据
                        </Text>
                      </div>
                    </div>
                    <Button
                      type="primary"
                      size="small"
                      icon={<PlayCircleOutlined />}
                      loading={startingSpiders.has(spider.name)}
                      onClick={() => handleQuickStart(spider.id, spider.name)}
                      style={{
                        borderRadius: 6,
                        fontSize: 12,
                        flexShrink: 0,
                      }}
                    >
                      启动
                    </Button>
                  </div>
                ))
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="没有可启动的爬虫"
                  style={{ margin: '24px 0' }}
                />
              )}
            </Space>

            {quickStartSpiders.length > 6 && (
              <div style={{ marginTop: 12, textAlign: 'center' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  还有 {quickStartSpiders.length - 6} 个爬虫
                </Text>
              </div>
            )}
          </Card>

          {/* Spider Status Overview */}
          <Card
            title={
              <span style={{ fontWeight: 600, fontSize: 15 }}>
                爬虫状态概览
              </span>
            }
            style={{
              borderRadius: 12,
              overflow: 'hidden',
              marginTop: 16,
            }}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={14}>
              {spiders.length > 0 ? (
                spiders.slice(0, 5).map((spider) => {
                  const total = spider.items_scraped || 0
                  const errs = spider.errors_count || 0
                  const reqs = spider.requests_made || 0
                  const errRate = reqs > 0 ? (errs / reqs) * 100 : 0
                  return (
                    <div key={spider.name}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          marginBottom: 6,
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                          }}
                      >
                          {spider.is_running ? (
                            <div
                              style={{
                                width: 6,
                                height: 6,
                                borderRadius: '50%',
                                background: '#52c41a',
                                boxShadow: '0 0 4px #52c41a66',
                              }}
                            />
                          ) : (
                            <div
                              style={{
                                width: 6,
                                height: 6,
                                borderRadius: '50%',
                                background: '#d9d9d9',
                              }}
                            />
                          )}
                          <Text strong ellipsis style={{ fontSize: 13 }}>
                            {spider.name}
                          </Text>
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {total.toLocaleString()} 条
                        </Text>
                      </div>
                      <Progress
                        percent={
                          reqs > 0
                            ? Math.min(
                                ((reqs - errs) / reqs) * 100,
                                100
                              )
                            : 0
                        }
                        size="small"
                        strokeColor={
                          errRate > 10
                            ? '#ff4d4f'
                            : errRate > 5
                            ? '#faad14'
                            : '#52c41a'
                        }
                        showInfo={false}
                        style={{ marginBottom: 0 }}
                      />
                    </div>
                  )
                })
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无爬虫数据"
                  style={{ margin: '12px 0' }}
                />
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      {/* Inject subtle CSS for alternating rows */}
      <style>{`
        .dashboard-row-alt td {
          background-color: #fafbfc !important;
        }
        .dashboard-row-alt:hover td {
          background-color: #f0f5ff !important;
        }
        .ant-table-row:hover td {
          background-color: #f0f5ff !important;
        }
      `}</style>
    </div>
  )
}

export default DashboardPage
