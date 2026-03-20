/**
 * 记忆管理页面
 */
import { useState } from 'react'
import { Button, Space } from 'antd'
import { BulbOutlined, PlusOutlined } from '@ant-design/icons'

import MemoryManager from '../components/MemoryManager'

export default function MemoryPage() {
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false)

  return (
    <div style={{ padding: 24, height: '100%' }}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, marginBottom: 8 }}>
          <BulbOutlined style={{ marginRight: 8 }} />
          智能记忆系统
        </h2>
        <p style={{ color: 'var(--text-secondary)', margin: 0 }}>
          三级记忆架构：工作记忆、短期记忆、长期记忆，支持知识图谱和 MCP 协议
        </p>
      </div>

      <Space>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setMemoryManagerOpen(true)}
        >
          打开记忆管理
        </Button>
      </Space>

      <MemoryManager
        open={memoryManagerOpen}
        onClose={() => setMemoryManagerOpen(false)}
      />
    </div>
  )
}
