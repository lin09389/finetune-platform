import React from 'react'
import { Alert, Space, Button } from 'antd'
import { 
  LoadingOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined, 
  ThunderboltFilled 
} from '@ant-design/icons'
import { motion, AnimatePresence } from 'framer-motion'
import styles from './AgentStatus.module.css'

interface AgentExecution {
  status: 'pending' | 'executing' | 'confirming' | 'completed' | 'failed'
  description?: string
  error?: string
}

interface AgentStatusProps {
  agentExecution: AgentExecution | null
  onConfirm: () => void
  onCancel: () => void
}

const AgentStatus: React.FC<AgentStatusProps> = ({
  agentExecution,
  onConfirm,
  onCancel
}) => {
  return (
    <AnimatePresence>
      {agentExecution && (
        <motion.div
          initial={{ opacity: 0, y: -20, height: 0 }}
          animate={{ opacity: 1, y: 0, height: 'auto' }}
          exit={{ opacity: 0, y: -20, height: 0 }}
          transition={{ type: 'spring', damping: 20, stiffness: 300 }}
          className={styles.statusBanner}
        >
          <div className={styles.container}>
            <Alert
              className={styles.alert}
              message={
                <Space size="middle">
                  <div className={styles.iconBox}>
                    {agentExecution.status === 'executing' && <LoadingOutlined spin />}
                    {agentExecution.status === 'completed' && <CheckCircleOutlined style={{ color: 'var(--success)' }} />}
                    {agentExecution.status === 'failed' && <CloseCircleOutlined style={{ color: 'var(--error)' }} />}
                    {agentExecution.status === 'confirming' && <ThunderboltFilled style={{ color: 'var(--warning)' }} />}
                  </div>
                  <div className={styles.textBox}>
                    <div className={styles.statusTitle}>
                      {agentExecution.status === 'executing' && '正在执行智能任务...'}
                      {agentExecution.status === 'completed' && '任务执行成功'}
                      {agentExecution.status === 'failed' && '任务执行失败'}
                      {agentExecution.status === 'confirming' && '需要您的确认'}
                    </div>
                    <div className={styles.statusDesc}>
                      {agentExecution.status === 'failed' ? agentExecution.error : agentExecution.description || '智能助手正在处理您的请求'}
                    </div>
                  </div>
                </Space>
              }
              type={
                agentExecution.status === 'failed' ? 'error' :
                agentExecution.status === 'completed' ? 'success' :
                agentExecution.status === 'confirming' ? 'warning' : 'info'
              }
              action={
                agentExecution.status === 'confirming' && (
                  <Space>
                    <Button size="small" onClick={onCancel} className={styles.btn}>
                      拒绝
                    </Button>
                    <Button size="small" type="primary" danger onClick={onConfirm} className={styles.btnPrimary}>
                      确认执行
                    </Button>
                  </Space>
                )
              }
            />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default AgentStatus
