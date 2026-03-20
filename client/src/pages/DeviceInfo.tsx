import { Card, Row, Col, Progress, Descriptions, Tag, Spin, Alert, Button } from 'antd'
import { 
  ThunderboltOutlined, 
  AppleOutlined, 
  QuestionCircleOutlined,
  ReloadOutlined
} from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { useEffect, useState } from 'react'
import { getDeviceInfo } from '../services/api'

export default function DeviceInfo() {
  const { backendStatus, deviceInfo, setDeviceInfo } = useAppStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchInfo = async () => {
    if (backendStatus !== 'connected') {
      setError('后端服务未连接')
      return
    }
    
    setLoading(true)
    setError(null)
    try {
      const info = await getDeviceInfo()
      setDeviceInfo(info)
    } catch (err: any) {
      setError(err.message || '获取设备信息失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchInfo()
  }, [backendStatus])

  const getPlatformIcon = (platform: string) => {
    switch (platform) {
      case 'cuda':
        return <ThunderboltOutlined style={{ color: '#76b900' }} />
      case 'mac':
        return <AppleOutlined style={{ color: '#555' }} />
      default:
        return <QuestionCircleOutlined />
    }
  }

  const getPlatformName = (platform: string) => {
    switch (platform) {
      case 'cuda':
        return 'NVIDIA CUDA'
      case 'mac':
        return 'Apple Silicon (MLX)'
      default:
        return '未知平台'
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ padding: '0 24px' }}>
      <div className="page-container">
        <div className="page-title">
          设备信息
          <Button 
            icon={<ReloadOutlined />} 
            onClick={fetchInfo}
            loading={loading}
            style={{ marginLeft: 16 }}
            size="small"
          >
            刷新
          </Button>
        </div>

        {error && (
          <Alert 
            message="错误" 
            description={error} 
            type="error" 
            showIcon 
            style={{ marginBottom: 16 }} 
          />
        )}

        {deviceInfo && (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Card title="计算平台" variant="borderless" style={{ height: '100%' }}>
                  <div style={{ textAlign: 'center', padding: '20px 0' }}>
                    <div style={{ fontSize: 48, marginBottom: 16 }}>
                      {getPlatformIcon(deviceInfo.platform)}
                    </div>
                    <Tag color={deviceInfo.platform === 'cuda' ? 'success' : 'purple'} style={{ fontSize: 16, padding: '4px 16px' }}>
                      {getPlatformName(deviceInfo.platform)}
                    </Tag>
                    <div style={{ marginTop: 16, color: '#666' }}>
                      {deviceInfo.device_name}
                    </div>
                  </div>
                  <Descriptions column={1} style={{ marginTop: 16 }}>
                    <Descriptions.Item label="CUDA 可用">
                      {deviceInfo.cuda_available ? <Tag color="success">是</Tag> : <Tag>否</Tag>}
                    </Descriptions.Item>
                    {deviceInfo.platform === 'mac' && (
                      <Descriptions.Item label="MPS 可用">
                        {deviceInfo.mps_available ? <Tag color="success">是</Tag> : <Tag>否</Tag>}
                      </Descriptions.Item>
                    )}
                  </Descriptions>
                </Card>
              </Col>

              <Col xs={24} md={12}>
                <Card title="显存 (VRAM)" variant="borderless" style={{ height: '100%' }}>
                  <Progress
                    type="circle"
                    percent={deviceInfo.vram_total ? Math.round((deviceInfo.vram_used / deviceInfo.vram_total) * 100) : 0}
                    format={() => `${(deviceInfo.vram_used || 0).toFixed(1)} / ${(deviceInfo.vram_total || 0).toFixed(1)} GB`}
                    strokeColor={{
                      '0%': '#108ee9',
                      '100%': '#87d068'
                    }}
                  />
                  <Descriptions column={1} style={{ marginTop: 24 }}>
                    <Descriptions.Item label="总容量">{(deviceInfo.vram_total || 0).toFixed(1)} GB</Descriptions.Item>
                    <Descriptions.Item label="已使用">{(deviceInfo.vram_used || 0).toFixed(1)} GB</Descriptions.Item>
                    <Descriptions.Item label="剩余可用">{(deviceInfo.vram_free || 0).toFixed(1)} GB</Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>
            </Row>

            <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
              <Col xs={24} md={12}>
                <Card title="系统内存 (RAM)" variant="borderless">
                  <Progress
                    type="circle"
                    percent={Math.round(((deviceInfo.memory_used || 0) / (deviceInfo.memory_total || 1)) * 100)}
                    format={() => `${(deviceInfo.memory_used || 0).toFixed(1)} / ${(deviceInfo.memory_total || 0).toFixed(1)} GB`}
                    strokeColor={{
                      '0%': '#108ee9',
                      '100%': '#87d068'
                    }}
                  />
                  <Descriptions column={1} style={{ marginTop: 24 }}>
                    <Descriptions.Item label="总容量">{(deviceInfo.memory_total || 0).toFixed(1)} GB</Descriptions.Item>
                    <Descriptions.Item label="已使用">{(deviceInfo.memory_used || 0).toFixed(1)} GB</Descriptions.Item>
                    <Descriptions.Item label="剩余可用">{(deviceInfo.memory_free || 0).toFixed(1)} GB</Descriptions.Item>
                  </Descriptions>
                </Card>
              </Col>

              <Col xs={24} md={12}>
                <Card title="显存建议" variant="borderless">
                  <div style={{ padding: '20px 0' }}>
                    {(deviceInfo.vram_free || 0) < 6 && (
                      <Alert
                        message="显存不足"
                        description="当前显存小于 6GB，建议使用 INT4 量化 + QLoRA 进行微调。可选模型：Qwen2.5-0.5B, Phi-3-mini, TinyLlama-1.1B"
                        type="warning"
                        showIcon
                      />
                    )}
                    {(deviceInfo.vram_free || 0) >= 6 && (deviceInfo.vram_free || 0) < 10 && (
                      <Alert
                        message="显存适中"
                        description="6-10GB 显存可使用 INT4 量化微调 7B 模型，如 Qwen2.5-1.8B, Llama3-8B-Instruct, ChatGLM3-6B"
                        type="success"
                        showIcon
                      />
                    )}
                    {(deviceInfo.vram_free || 0) >= 10 && (deviceInfo.vram_free || 0) < 16 && (
                      <Alert
                        message="显存充裕"
                        description="10-16GB 显存可微调 7B 模型（INT4/INT8），或使用 QLoRA 微调 13B 模型"
                        type="success"
                        showIcon
                      />
                    )}
                    {deviceInfo.vram_free >= 16 && (
                      <Alert
                        message="显存充足"
                        description="16GB+ 显存可微调 13B 模型，或使用 LoRA 微调 30B+ 模型"
                        type="success"
                        showIcon
                      />
                    )}
                  </div>
                </Card>
              </Col>
            </Row>
          </>
        )}
      </div>
    </div>
  )
}
