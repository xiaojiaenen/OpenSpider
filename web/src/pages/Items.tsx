import React, { useEffect, useState, useCallback } from 'react'
import {
  Card,
  Table,
  Typography,
  Space,
  Button,
  Select,
  Row,
  Col,
  Tag,
  Empty,
  message,
} from 'antd'
import {
  ReloadOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  CodeOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import { spiderApi, dataApi } from '../services/api'

const { Title, Text } = Typography

/* ── Component ───────────────────────────────── */

const ItemsPage: React.FC = () => {
  /* ── Spider selector ──────────────────────── */
  const [spiderOptions, setSpiderOptions] = useState<{ value: number; label: string }[]>([])
  const [selectedSpiderId, setSelectedSpiderId] = useState<number | null>(null)
  const [spidersLoading, setSpidersLoading] = useState(false)

  /* ── Fields & data ────────────────────────── */
  const [columns, setColumns] = useState<string[]>([])
  const [fieldMap, setFieldMap] = useState<Record<string, { label: string; type?: string }>>({})
  const [items, setItems] = useState<Record<string, unknown>[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)

  const standardColumns = ['user_id', 'task_id', 'url', 'crawled_at']

  /* ── Load spider list ─────────────────────── */

  const loadSpiders = useCallback(async () => {
    setSpidersLoading(true)
    try {
      const data = await spiderApi.list()
      const list = data.spiders || data || []
      setSpiderOptions(
        list.map((s: { id: number; name: string }) => ({
          value: s.id,
          label: s.name,
        })),
      )
    } catch {
      // silent
    } finally {
      setSpidersLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSpiders()
  }, [loadSpiders])

  /* ── Load fields for selected spider ──────── */

  const loadFields = useCallback(async (spiderId: number) => {
    try {
      const data = await dataApi.fields(spiderId)
      const flds: { name: string; label?: string; type?: string }[] = data.fields || []
      const map: Record<string, { label: string; type?: string }> = {}
      for (const f of flds) {
        map[f.name] = { label: f.label || f.name, type: f.type }
      }
      setFieldMap(map)

      // Merge: standard columns first, then spider-specific fields (excluding standard)
      const spiderFields = flds.filter((f) => !standardColumns.includes(f.name)).map((f) => f.name)
      setColumns([...standardColumns, ...spiderFields])
    } catch {
      setColumns([...standardColumns])
      setFieldMap({})
    }
  }, [])

  /* ── Load data for selected spider ────────── */

  const loadData = useCallback(
    async (spiderId: number, p: number, ps: number) => {
      setLoading(true)
      try {
        const data = await dataApi.list(spiderId, { page: p, page_size: ps })
        setItems(data.items || [])
        setTotal(data.total || 0)
      } catch {
        setItems([])
        setTotal(0)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  /* ── Spider selection change ──────────────── */

  const handleSpiderChange = useCallback(
    (spiderId: number) => {
      setSelectedSpiderId(spiderId)
      setPage(1)
      loadFields(spiderId)
      loadData(spiderId, 1, pageSize)
    },
    [loadFields, loadData, pageSize],
  )

  /* ── Reload ───────────────────────────────── */

  const handleReload = useCallback(() => {
    if (selectedSpiderId) {
      loadData(selectedSpiderId, page, pageSize)
    }
  }, [selectedSpiderId, page, pageSize, loadData])

  /* ── Pagination change ────────────────────── */

  const handlePageChange = useCallback(
    (p: number, ps: number) => {
      setPage(p)
      setPageSize(ps)
      if (selectedSpiderId) {
        loadData(selectedSpiderId, p, ps)
      }
    },
    [selectedSpiderId, loadData],
  )

  /* ── Export ───────────────────────────────── */

  const handleExport = useCallback(
    async (format: 'json' | 'csv') => {
      if (!selectedSpiderId) return
      try {
        const data = await dataApi.export(selectedSpiderId, format)
        if (format === 'json') {
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `spider_${selectedSpiderId}_data.json`
          a.click()
          URL.revokeObjectURL(url)
        } else {
          // CSV export: flatten items into rows
          const itemsArr = data.items || data
          if (!Array.isArray(itemsArr) || itemsArr.length === 0) {
            message.warning('没有可导出的数据')
            return
          }
          const headers = columns
          const csvRows = [headers.join(',')]
          for (const row of itemsArr) {
            const vals = headers.map((h) => {
              const v = row[h]
              const str = v === null || v === undefined ? '' : String(v)
              // Escape CSV: wrap in quotes if contains comma/newline/quote
              if (str.includes(',') || str.includes('\n') || str.includes('"')) {
                return `"${str.replace(/"/g, '""')}"`
              }
              return str
            })
            csvRows.push(vals.join(','))
          }
          const blob = new Blob(['﻿' + csvRows.join('\n')], {
            type: 'text/csv;charset=utf-8',
          })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `spider_${selectedSpiderId}_data.csv`
          a.click()
          URL.revokeObjectURL(url)
        }
        message.success(`${format.toUpperCase()} 导出成功`)
      } catch {
        message.error('导出失败')
      }
    },
    [selectedSpiderId, columns],
  )

  /* ── Table columns ────────────────────────── */

  const tableColumns = columns.map((col) => {
    const meta = fieldMap[col]
    const label = meta?.label || col
    const isTime = col === 'crawled_at' || meta?.type === 'datetime'
    return {
      title: label,
      dataIndex: col,
      key: col,
      ellipsis: true,
      width: col === 'url' ? 280 : col === 'crawled_at' ? 170 : col === 'task_id' ? 90 : col === 'user_id' ? 100 : 150,
      render: (value: unknown) => {
        if (value === null || value === undefined) return <Text type="secondary">-</Text>
        if (isTime) {
          return (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {new Date(String(value)).toLocaleString('zh-CN')}
            </Text>
          )
        }
        if (col === 'task_id') {
          return <Tag color="blue" style={{ fontFamily: 'monospace' }}>#{String(value)}</Tag>
        }
        if (typeof value === 'object') {
          return (
            <Text ellipsis style={{ fontFamily: 'monospace', fontSize: 12 }}>
              {JSON.stringify(value).slice(0, 60)}
            </Text>
          )
        }
        return <Text ellipsis style={{ fontSize: 13 }}>{String(value)}</Text>
      },
    }
  })

  /* ── JSX ────────────────────────────────────── */

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* Header & controls */}
      <Card size="small" style={{ borderRadius: 12 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space size={8} align="center">
              <DatabaseOutlined style={{ fontSize: 20, color: '#1677ff' }} />
              <Title level={4} style={{ margin: 0 }}>
                数据浏览
              </Title>
              {selectedSpiderId && (
                <Tag color="default">{total} 条</Tag>
              )}
            </Space>
          </Col>
          <Col>
            <Space size={8}>
              <Select
                placeholder="选择爬虫"
                showSearch
                style={{ width: 220 }}
                loading={spidersLoading}
                value={selectedSpiderId}
                onChange={handleSpiderChange}
                options={spiderOptions}
                filterOption={(input, option) =>
                  (option?.label ?? '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
              />
              {selectedSpiderId && (
                <>
                  <Button
                    icon={<CodeOutlined />}
                    onClick={() => handleExport('json')}
                  >
                    JSON
                  </Button>
                  <Button
                    icon={<FileTextOutlined />}
                    onClick={() => handleExport('csv')}
                  >
                    CSV
                  </Button>
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={handleReload}
                    loading={loading}
                  >
                    刷新
                  </Button>
                </>
              )}
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Data table */}
      <Card style={{ borderRadius: 12 }} styles={{ body: { padding: 0 } }}>
        {!selectedSpiderId ? (
          <div style={{ padding: 64, textAlign: 'center' }}>
            <Empty description="请先选择一个爬虫" />
          </div>
        ) : (
          <Table
            columns={tableColumns}
            dataSource={items}
            rowKey={(_, idx) => String(idx)}
            loading={loading}
            pagination={{
              current: page,
              total,
              pageSize,
              onChange: handlePageChange,
              showTotal: (t) => `共 ${t} 条`,
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50', '100'],
            }}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>
    </Space>
  )
}

export default ItemsPage
