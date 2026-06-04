import React, { useEffect, useState, useMemo, useCallback } from 'react'
import {
  Card,
  Table,
  Typography,
  Space,
  Tag,
  Button,
  Select,
  Drawer,
  Badge,
  Row,
  Col,
  Descriptions,
  Empty,
} from 'antd'
import {
  ReloadOutlined,
  DatabaseOutlined,
  CodeOutlined,
  GlobalOutlined,
  ClockCircleOutlined,
  GroupOutlined,
} from '@ant-design/icons'
import { itemApi } from '../services/api'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'

const { Title, Text, Paragraph } = Typography

/* ── Types ───────────────────────────────────── */

interface Item {
  id: number
  spider_name: string
  task_id: number
  data: Record<string, unknown>
  url: string
  crawled_at: string
}

interface TaskGroup {
  task_id: number
  spider_name: string
  crawled_at: string
  items: Item[]
  earliest: string
  latest: string
}

/* ── Component ───────────────────────────────── */

const ItemsPage: React.FC = () => {
  const [items, setItems] = useState<Item[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [selectedItem, setSelectedItem] = useState<Item | null>(null)
  const [spiderFilter, setSpiderFilter] = useState<string | undefined>(undefined)
  const [spiderOptions, setSpiderOptions] = useState<{ value: string; label: string }[]>([])

  const pageSize = 20

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await itemApi.list({
        spider: spiderFilter,
        page,
        page_size: pageSize,
      })
      const fetched: Item[] = data.items || []
      setItems(fetched)
      setTotal(data.total || 0)

      // Collect unique spider names for the filter
      if (!spiderFilter) {
        const names = Array.from(new Set(fetched.map((i) => i.spider_name)))
        setSpiderOptions((prev) => {
          const existing = new Set(prev.map((o) => o.value))
          const merged = [...prev]
          names.forEach((n) => {
            if (!existing.has(n)) merged.push({ value: n, label: n })
          })
          return merged
        })
      }
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [page, spiderFilter])

  useEffect(() => {
    load()
  }, [load])

  /* ── Group items by task_id ───────────────── */

  const taskGroups = useMemo<TaskGroup[]>(() => {
    const map = new Map<number, TaskGroup>()
    for (const item of items) {
      const tid = item.task_id
      if (!map.has(tid)) {
        map.set(tid, {
          task_id: tid,
          spider_name: item.spider_name,
          crawled_at: item.crawled_at,
          items: [],
          earliest: item.crawled_at,
          latest: item.crawled_at,
        })
      }
      const group = map.get(tid)!
      group.items.push(item)
      if (item.crawled_at < group.earliest) group.earliest = item.crawled_at
      if (item.crawled_at > group.latest) group.latest = item.crawled_at
    }
    return Array.from(map.values())
  }, [items])

  /* ── Data preview (key-value pairs) ────────── */

  const renderDataPreview = (data: Record<string, unknown>) => {
    const keys = Object.keys(data)
    if (keys.length === 0) return <Text type="secondary">-</Text>
    const previewKeys = keys.slice(0, 4)
    return (
      <div style={{ lineHeight: 1.7, fontSize: 12 }}>
        {previewKeys.map((k) => {
          const val = data[k]
          const display =
            typeof val === 'object' && val !== null
              ? JSON.stringify(val).slice(0, 35) + '...'
              : String(val).slice(0, 40)
          return (
            <div key={k} style={{ display: 'flex', gap: 4 }}>
              <Text
                strong
                style={{
                  color: '#1677ff',
                  fontSize: 11,
                  fontFamily: 'monospace',
                  whiteSpace: 'nowrap',
                }}
              >
                {k}
              </Text>
              <Text
                type="secondary"
                ellipsis
                style={{ fontSize: 11, fontFamily: 'monospace' }}
              >
                {display}
              </Text>
            </div>
          )
        })}
        {keys.length > 4 && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            ...还有 {keys.length - 4} 个字段
          </Text>
        )}
      </div>
    )
  }

  /* ── Expanded row: items within a task group ── */

  const expandedRowRender = (record: TaskGroup) => {
    const innerColumns: ColumnsType<Item> = [
      { title: 'ID', dataIndex: 'id', width: 70 },
      {
        title: 'URL',
        dataIndex: 'url',
        ellipsis: true,
        width: 260,
        render: (v: string) => (
          <Text
            copyable
            ellipsis
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          >
            {v || '-'}
          </Text>
        ),
      },
      {
        title: '数据预览',
        width: 320,
        render: (_: unknown, record: Item) => renderDataPreview(record.data || {}),
      },
      {
        title: '抓取时间',
        dataIndex: 'crawled_at',
        width: 170,
        render: (v: string) => (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {v ? new Date(v).toLocaleString('zh-CN') : '-'}
          </Text>
        ),
      },
      {
        title: '操作',
        width: 60,
        render: (_: unknown, record: Item) => (
          <a onClick={() => setSelectedItem(record)}>详情</a>
        ),
      },
    ]

    return (
      <Table
        columns={innerColumns}
        dataSource={record.items}
        rowKey="id"
        pagination={false}
        size="small"
        style={{ margin: '0 16px' }}
      />
    )
  }

  /* ── Group-level columns ────────────────────── */

  const groupColumns: ColumnsType<TaskGroup> = [
    {
      title: '任务ID',
      dataIndex: 'task_id',
      width: 100,
      render: (v: number) => (
        <Tag color="blue" style={{ fontFamily: 'monospace' }}>
          #{v}
        </Tag>
      ),
    },
    {
      title: '爬虫',
      dataIndex: 'spider_name',
      width: 160,
      render: (v: string) => (
        <Space size={4}>
          <DatabaseOutlined style={{ color: '#1677ff' }} />
          <Text strong>{v}</Text>
        </Space>
      ),
    },
    {
      title: '数据条数',
      width: 100,
      render: (_: unknown, record: TaskGroup) => (
        <Badge
          count={record.items.length}
          showZero
          overflowCount={9999}
          style={{
            backgroundColor: record.items.length > 0 ? '#52c41a' : '#d9d9d9',
          }}
        />
      ),
    },
    {
      title: '抓取时间',
      width: 180,
      render: (_: unknown, record: TaskGroup) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {record.crawled_at
            ? new Date(record.crawled_at).toLocaleString('zh-CN')
            : '-'}
        </Text>
      ),
    },
  ]

  /* ── Drawer: syntax-highlighted data block ──── */

  const renderHighlightedData = (data: Record<string, unknown>) => {
    const entries = Object.entries(data)
    if (entries.length === 0) return <Empty description="暂无数据" />
    return (
      <div
        style={{
          borderRadius: 8,
          overflow: 'hidden',
          border: '1px solid #f0f0f0',
        }}
      >
        <div
          style={{
            background: '#1e1e1e',
            padding: '8px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <CodeOutlined style={{ color: '#fff', fontSize: 13 }} />
          <Text style={{ color: '#fff', fontSize: 12 }}>JSON</Text>
        </div>
        <pre
          style={{
            margin: 0,
            padding: 0,
            background: '#fafafa',
            overflow: 'auto',
            maxHeight: 'calc(100vh - 320px)',
            fontSize: 13,
            lineHeight: 0,
          }}
        >
          <code>
            {entries.map(([key, value], idx) => {
              const isEven = idx % 2 === 0
              const bg = isEven ? '#fafafa' : '#f5f5f5'
              const valStr =
                typeof value === 'object' && value !== null
                  ? JSON.stringify(value, null, 2)
                  : String(value)
              return (
                <div
                  key={key}
                  style={{
                    background: bg,
                    padding: '8px 16px',
                    display: 'flex',
                    gap: 12,
                    borderBottom: '1px solid #f0f0f0',
                    lineHeight: 1.6,
                    minHeight: 32,
                  }}
                >
                  <span
                    style={{
                      color: '#0958d9',
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                      minWidth: 120,
                    }}
                  >
                    "{key}"
                  </span>
                  <span style={{ color: '#333', wordBreak: 'break-all' }}>
                    {valStr}
                  </span>
                </div>
              )
            })}
          </code>
        </pre>
      </div>
    )
  }

  /* ── JSX ────────────────────────────────────── */

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* Header & filters */}
      <Card
        size="small"
        style={{ borderRadius: 12 }}
      >
        <Row justify="space-between" align="middle">
          <Col>
            <Space size={8} align="center">
              <DatabaseOutlined style={{ fontSize: 20, color: '#1677ff' }} />
              <Title level={4} style={{ margin: 0 }}>
                数据浏览
              </Title>
              <Tag color="default">{total} 条</Tag>
            </Space>
          </Col>
          <Col>
            <Space size={8}>
              <Select
                placeholder="按爬虫筛选"
                allowClear
                showSearch
                style={{ width: 200 }}
                value={spiderFilter}
                onChange={(v) => {
                  setSpiderFilter(v)
                  setPage(1)
                }}
                options={spiderOptions}
                filterOption={(input, option) =>
                  (option?.label ?? '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
              />
              <Button
                icon={<ReloadOutlined />}
                onClick={load}
                loading={loading}
              >
                刷新
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Grouped table */}
      <Card
        title={
          <Space>
            <GroupOutlined />
            <span>按任务分组</span>
          </Space>
        }
        style={{ borderRadius: 12 }}
        styles={{ body: { padding: 0 } }}
      >
        <Table<TaskGroup>
          columns={groupColumns}
          dataSource={taskGroups}
          rowKey="task_id"
          loading={loading}
          expandable={{
            expandedRowRender,
            rowExpandable: (record) => record.items.length > 0,
          }}
          pagination={{
            current: page,
            total,
            pageSize,
            onChange: setPage,
            showTotal: (t) => `共 ${t} 条，${taskGroups.length} 个任务`,
            showSizeChanger: false,
          }}
          size="middle"
        />
      </Card>

      {/* Detail Drawer */}
      <Drawer
        title={
          selectedItem ? (
            <Space>
              <DatabaseOutlined style={{ color: '#1677ff' }} />
              <span>
                数据项 #{selectedItem.id}
              </span>
              <Tag color="blue">{selectedItem.spider_name}</Tag>
            </Space>
          ) : (
            '数据详情'
          )
        }
        open={!!selectedItem}
        onClose={() => setSelectedItem(null)}
        width={640}
        destroyOnClose
      >
        {selectedItem && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {/* Metadata */}
            <Descriptions
              column={1}
              size="small"
              bordered
              style={{ borderRadius: 8, overflow: 'hidden' }}
            >
              <Descriptions.Item label="ID">{selectedItem.id}</Descriptions.Item>
              <Descriptions.Item label="任务ID">
                <Tag color="blue">#{selectedItem.task_id}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="爬虫">
                <Space size={4}>
                  <DatabaseOutlined />
                  {selectedItem.spider_name}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="URL">
                <Space size={4}>
                  <GlobalOutlined style={{ color: '#8c8c8c' }} />
                  <Text
                    copyable
                    ellipsis
                    style={{ fontFamily: 'monospace', fontSize: 12 }}
                  >
                    {selectedItem.url || '-'}
                  </Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="抓取时间">
                <Space size={4}>
                  <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
                  {selectedItem.crawled_at
                    ? new Date(selectedItem.crawled_at).toLocaleString('zh-CN')
                    : '-'}
                </Space>
              </Descriptions.Item>
            </Descriptions>

            {/* Data block */}
            <div>
              <Text strong style={{ fontSize: 14, marginBottom: 8, display: 'block' }}>
                <CodeOutlined style={{ marginRight: 4 }} />
                数据内容
              </Text>
              {renderHighlightedData(selectedItem.data || {})}
            </div>
          </Space>
        )}
      </Drawer>
    </Space>
  )
}

export default ItemsPage
