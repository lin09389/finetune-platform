import React from 'react'
import { Form, Select, InputNumber, Button, Space, Divider, Switch, Row, Col } from 'antd'
import { 
  ThunderboltOutlined, 
  PlayCircleOutlined, 
  StopOutlined, 
  CheckCircleOutlined,
  InfoCircleOutlined
} from '@ant-design/icons'
import NeumorphicButton from '../../../components/shared/NeumorphicButton'
import styles from './ConfigForm.module.css'

interface ConfigFormProps {
  form: any
  onFinish: (values: any) => void
  isTraining: boolean
  starting: boolean
  onStop: () => void
  models: { id: string; name: string; quantized?: number }[]
  datasets: { id: string; name: string; samples: number }[]
  swiftAvailable: boolean
  useSwift: boolean
  onSwiftChange: (checked: boolean) => void
  precisionPreset: 'max' | 'balanced' | 'fast'
  onPrecisionChange: (preset: any) => void
  useDora: boolean
  onDoraChange: (checked: boolean) => void
  memoryPreset: 'auto' | '6gb' | '8gb' | '12gb'
  onMemoryChange: (preset: any) => void
  useFlashAttn: boolean
  onFlashAttnChange: (checked: boolean) => void
  quantizationBit: 0 | 4 | 8
  onQuantizationChange: (bit: any) => void
  gradientAccumulation: number
  onGradAccChange: (val: number) => void
  useLoraPlus: boolean
  onLoraPlusChange: (checked: boolean) => void
  loraPlusLrRatio: number
  onLoraPlusLrRatioChange: (val: number) => void
  useGalore: boolean
  onGaloreChange: (checked: boolean) => void
  galoreRank: number
  onGaloreRankChange: (val: number) => void
  onApplyPreset: (preset: 'low' | 'medium' | 'high') => void
}

const ConfigForm: React.FC<ConfigFormProps> = ({
  form,
  onFinish,
  isTraining,
  starting,
  onStop,
  models,
  datasets,
  swiftAvailable,
  useSwift,
  onSwiftChange,
  precisionPreset,
  onPrecisionChange,
  useDora,
  onDoraChange,
  memoryPreset,
  onMemoryChange,
  useFlashAttn,
  onFlashAttnChange,
  quantizationBit,
  onQuantizationChange,
  gradientAccumulation,
  onGradAccChange,
  onApplyPreset,
}) => {
  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={onFinish}
      disabled={isTraining}
      className={styles.form}
    >
      <Row gutter={24}>
        <Col span={12}>
          <Form.Item label="基础模型" name="modelId" rules={[{ required: true }]}>
            <Select
              placeholder="选择基础模型"
              options={models.map(m => ({ value: m.id, label: `${m.name} ${m.quantized ? `(INT${m.quantized})` : ''}` }))}
              showSearch
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="训练数据集" name="datasetId" rules={[{ required: true }]}>
            <Select
              placeholder="选择数据集"
              options={datasets.map(d => ({ value: d.id, label: `${d.name} (${d.samples}条)` }))}
              showSearch
            />
          </Form.Item>
        </Col>
      </Row>

      <Divider className={styles.divider}>加速与精度框架</Divider>
      
      <Row gutter={24}>
        <Col span={8}>
          <Form.Item
            label={<span className={styles.labelWithIcon}><ThunderboltOutlined /> SWIFT 框架</span>}
            tooltip="阿里 SWIFT 框架可提升训练速度 25%"
          >
            <Switch checked={useSwift} onChange={onSwiftChange} disabled={!swiftAvailable} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            label={<span className={styles.labelWithIcon}><CheckCircleOutlined /> 精度预设</span>}
          >
            <Select value={precisionPreset} onChange={onPrecisionChange}>
              <Select.Option value="max">🏆 最高 (Max)</Select.Option>
              <Select.Option value="balanced">⚖️ 平衡 (Balanced)</Select.Option>
              <Select.Option value="fast">⚡ 快速 (Fast)</Select.Option>
            </Select>
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            label={<span className={styles.labelWithIcon}><InfoCircleOutlined /> DoRA 微调</span>}
            tooltip="DoRA 分解权重为幅度和方向"
          >
            <Switch checked={useDora} onChange={onDoraChange} disabled={precisionPreset === 'fast'} />
          </Form.Item>
        </Col>
      </Row>

      <Divider className={styles.divider}>显存管理优化</Divider>

      <Row gutter={24}>
        <Col span={12}>
          <Form.Item label="显存优化预设">
            <Select value={memoryPreset} onChange={onMemoryChange}>
              <Select.Option value="auto">🤖 自动检测</Select.Option>
              <Select.Option value="6gb">💾 6GB (极致)</Select.Option>
              <Select.Option value="8gb">💾 8GB (平衡)</Select.Option>
              <Select.Option value="12gb">💾 12GB (DeepSpeed)</Select.Option>
            </Select>
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="量化策略">
            <Select value={quantizationBit} onChange={onQuantizationChange} disabled={memoryPreset !== 'auto'}>
              <Select.Option value={4}>4bit (省显存)</Select.Option>
              <Select.Option value={8}>8bit (平衡)</Select.Option>
              <Select.Option value={0}>无量化 (高精度)</Select.Option>
            </Select>
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={24}>
        <Col span={8}>
          <Form.Item label="梯度累积">
            <InputNumber min={1} max={128} value={gradientAccumulation} onChange={(v) => onGradAccChange(v || 16)} style={{ width: '100%' }} disabled={memoryPreset !== 'auto'} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="Flash Attention">
            <Switch checked={useFlashAttn} onChange={onFlashAttnChange} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <div className={styles.presetGroup}>
            <label className={styles.smallLabel}>参数快捷预设</label>
            <Space>
              <Button size="small" onClick={() => onApplyPreset('low')}>6GB</Button>
              <Button size="small" onClick={() => onApplyPreset('medium')}>8GB</Button>
              <Button size="small" onClick={() => onApplyPreset('high')}>12G+</Button>
            </Space>
          </div>
        </Col>
      </Row>

      <Divider className={styles.divider}>训练参数</Divider>

      <Row gutter={16}>
        <Col span={8}>
          <Form.Item label="训练轮数" name="epochs">
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="LoRA Rank" name="rank">
            <InputNumber min={4} max={128} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="LoRA Alpha" name="alpha">
            <InputNumber min={8} max={256} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item label="学习率" name="learningRate">
            <InputNumber min={1e-6} max={1e-3} step={1e-5} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="最大序列长度" name="maxSeqLength">
            <InputNumber min={128} max={4096} step={128} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <Form.Item style={{ marginTop: 'var(--space-6)', textAlign: 'right' }}>
        <Space size="large">
          {isTraining ? (
            <NeumorphicButton
              variant="danger"
              size="lg"
              onClick={onStop}
              icon={<StopOutlined />}
            >
              停止训练
            </NeumorphicButton>
          ) : (
            <NeumorphicButton
              variant="primary"
              size="lg"
              htmlType="submit"
              loading={starting}
              disabled={!models.length || !datasets.length}
              icon={<PlayCircleOutlined />}
            >
              开始训练
            </NeumorphicButton>
          )}
        </Space>
      </Form.Item>
    </Form>
  )
}

export default ConfigForm
