import { useState, useEffect, useRef } from 'react'
import { Card, Row, Col, Form, Select, InputNumber, Button, Space, Progress, Tag, message, Divider, Alert, Steps, Switch } from 'antd'
import { PlayCircleOutlined, StopOutlined, ThunderboltOutlined, CheckCircleOutlined, ClockCircleOutlined, LineChartOutlined } from '@ant-design/icons'
import { useAppStore } from '../store/appStore'
import { startTraining, stopTraining, subscribeTrainingProgress, startSwiftTraining, API_BASE_URL } from '../services/api'
import type { TrainingProgress as TrainingProgressType } from '../types'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import TrainingChart from '../components/TrainingChart'
import SwiftChecker from '../components/SwiftChecker'

interface ChartDataPoint {
  step: number
  loss: number
  lr: number
}

export default function Training() {
  const { models, datasets, backendStatus, isTraining, setIsTraining, deviceInfo, addTrainingRecord } = useAppStore()
  const [form] = Form.useForm()
  const [progress, setProgress] = useState<TrainingProgressType | null>(null)
  const [starting, setStarting] = useState(false)
  const [trainingStatus, setTrainingStatus] = useState<'idle' | 'loading' | 'training' | 'completed' | 'failed'>('idle')
  const unsubscribeRef = useRef<(() => void) | null>(null)
  const buttonClickedRef = useRef(false)
  const [chartData, setChartData] = useState<ChartDataPoint[]>([])
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)
  const [backendTraining, setBackendTraining] = useState(false) // 后端实际训练状态
  
  // P2-2: SWIFT 框架选项
  const [useSwift, setUseSwift] = useState(false)
  const [swiftAvailable, setSwiftAvailable] = useState(false)
  
  // P2-3: 高精度微调选项
  const [precisionPreset, setPrecisionPreset] = useState<'max' | 'balanced' | 'fast'>('balanced')
  const [useDora, setUseDora] = useState(false)
  
  // P2-4: 低显存优化选项
  const [memoryPreset, setMemoryPreset] = useState<'auto' | '6gb' | '8gb' | '12gb'>('auto')
  const [useFlashAttn, setUseFlashAttn] = useState(false)
  const [quantizationBit, setQuantizationBit] = useState<4 | 8 | 0>(4)
  const [gradientAccumulation, setGradientAccumulation] = useState<number>(16)

  // P2-5: LoRA+ 和 GaLore 选项
  const [useLoraPlus, setUseLoraPlus] = useState(false)
  const [loraPlusLrRatio, setLoraPlusLrRatio] = useState(16)
  const [useGalore, setUseGalore] = useState(false)
  const [galoreRank, setGaloreRank] = useState(128)

  const recommendedConfigs = {
    low: { rank: 8, alpha: 16, batchSize: 1, gradientAccumulation: 16, maxSeqLength: 512 },
    medium: { rank: 16, alpha: 32, batchSize: 2, gradientAccumulation: 8, maxSeqLength: 1024 },
    high: { rank: 32, alpha: 64, batchSize: 4, gradientAccumulation: 4, maxSeqLength: 2048 }
  }

  const applyPreset = (preset: 'low' | 'medium' | 'high') => {
    const config = recommendedConfigs[preset]
    form.setFieldsValue(config)
  }

  // 定期检查后端训练状态
  useEffect(() => {
    const checkTrainingStatus = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/training/status`)
        const data = await response.json()
        setBackendTraining(data.is_training)
        if (data.is_training && data.progress) {
          setProgress(data.progress)
          if (data.progress.status === 'failed') {
            setTrainingStatus('failed')
            setIsTraining(false)
            message.error(data.progress.message || '训练失败')
          } else if (data.progress.status === 'completed') {
            setTrainingStatus('completed')
            setIsTraining(false)
          }
        }
      } catch (e) {
        console.error('检查训练状态失败:', e)
      }
    }

    // 每 3 秒检查一次
    const interval = setInterval(checkTrainingStatus, 3000)
    checkTrainingStatus() // 立即检查一次

    return () => clearInterval(interval)
  }, [setIsTraining])

  useEffect(() => {
    if (isTraining && backendStatus === 'connected') {
      setTrainingStatus('training')
      setChartData([])
      unsubscribeRef.current = subscribeTrainingProgress(
        (p: any) => {
          setProgress(p)
          
          // 更新图表数据
          if (p.loss !== undefined && p.step !== undefined) {
            setChartData(prev => {
              const newData = [...prev, {
                step: p.step,
                loss: p.loss,
                lr: p.lr || 0
              }]
              // 保持最多 500 个点，避免性能问题
              if (newData.length > 500) {
                return newData.slice(newData.length - 500)
              }
              return newData
            })
          }

          if (p.status === 'loading') {
            setTrainingStatus('loading')
          } else if (p.status === 'training' || p.status === 'running') {
            setTrainingStatus('training')
          } else if (p.status === 'completed') {
            setTrainingStatus('completed')
            setIsTraining(false)
            message.success('训练完成!')
          } else if (p.status === 'failed' || p.status === 'stopped') {
            setTrainingStatus(p.status === 'failed' ? 'failed' : 'idle')
            setIsTraining(false)
            if (p.status === 'failed') {
              message.error(p.message || '训练失败')
            } else {
              message.warning('训练已停止')
            }
          }
        },
        (error: Error) => {
          console.error('SSE error:', error)
          setTrainingStatus('idle')
        }
      )
    }

    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current()
        unsubscribeRef.current = null
      }
    }
  }, [isTraining, backendStatus])

  const handleStart = async (values: any) => {
    if (buttonClickedRef.current) return
    buttonClickedRef.current = true

    if (!values['modelId'] || !values['datasetId']) {
      message.error('请选择模型和数据集')
      buttonClickedRef.current = false
      return
    }

    setStarting(true)
    setTrainingStatus('loading')
    setChartData([])
    
    try {
      // 使用 snake_case 字段名匹配后端 Pydantic 模型
      const config = {
        model_id: values['modelId'] as string,
        dataset_id: values['datasetId'] as string,
        method: (values['method'] as 'lora' | 'qlora' | 'full' | 'dora') || 'qlora',
        rank: (values['rank'] as number) || 8,
        alpha: (values['alpha'] as number) || 16,
        learning_rate: (values['learningRate'] as number) || 5e-5,
        epochs: (values['epochs'] as number) || 3,
        batch_size: (values['batchSize'] as number) || 1,
        gradient_accumulation: gradientAccumulation,
        max_seq_length: (values['maxSeqLength'] as number) || 512,
        warmup_steps: (values['warmupSteps'] as number) || 100,
        save_steps: (values['saveSteps'] as number) || 500,
        logging_steps: (values['loggingSteps'] as number) || 10,
        // P2-3: 高精度选项
        use_dora: useDora,
        precision_preset: precisionPreset,
        lr_scheduler: 'cosine',
        warmup_ratio: 0.1,
        weight_decay: 0.01,
        label_smoothing: precisionPreset === 'max' ? 0.1 : 0.0,
        gradient_checkpointing: true,
        bf16: true,
        eval_steps: 100,
        load_best_model: true,
        target_modules: 'all',
        lora_dropout: 0.05,
        max_grad_norm: 1.0,
        // P2-4: 低显存优化选项
        memory_preset: memoryPreset,
        use_flash_attn: useFlashAttn,
        deepspeed_stage: memoryPreset === '12gb' ? 2 : 0,
        offload_optimizer: memoryPreset === '12gb',
        quantization: quantizationBit as 0 | 4 | 8,

        // P2-5: LoRA+ 配置
        use_lora_plus: useLoraPlus,
        lora_plus_lr_ratio: loraPlusLrRatio,

        // P2-5: GaLore 配置
        use_galore: useGalore,
        galore_rank: galoreRank,
        galore_update_proj_gap: 50
      }

      console.log('发送训练配置:', JSON.stringify(config, null, 2))

      // P2-2: 使用 SWIFT 框架
      if (useSwift && swiftAvailable) {
        console.log('使用 SWIFT 框架训练...')
        const result = await startSwiftTraining(config)
        setIsTraining(true)
        addTrainingRecord(result)
        setCurrentTaskId(result.id)
        message.success('SWIFT 训练开始')
      } else {
        console.log('使用标准训练...')
        const result = await startTraining(config)
        console.log('训练结果:', result)
        setIsTraining(true)
        addTrainingRecord(result)
        setCurrentTaskId(result.id)
        message.success('训练开始')
      }
    } catch (error: unknown) {
      setTrainingStatus('idle')
      console.error('训练启动错误:', error)
      let errorMsg = '启动训练失败'
      if (error instanceof Error) {
        errorMsg = error.message
      } else if (typeof error === 'object' && error !== null && 'response' in error) {
        const axiosError = error as any
        if (axiosError.response?.data?.detail) {
          errorMsg = axiosError.response.data.detail
        }
      }
      message.error(errorMsg)
    } finally {
      setStarting(false)
      setTimeout(() => { buttonClickedRef.current = false }, 1000)
    }
  }

  const handleStop = async () => {
    try {
      await stopTraining()
      setIsTraining(false)
      setBackendTraining(false)
      setTrainingStatus('idle')
      setProgress(null)
      message.success('训练已停止')
    } catch (error) {
      message.error('停止训练失败')
    }
  }

  const getStepsCurrent = (status: string): number => {
    if (status === 'completed' || status === 'failed') return 2
    if (status === 'training' || status === 'loading') return 1
    return 0
  }

  const modelOptions = models.map(m => ({
    value: m.id,
    label: `${m.name} ${m.quantized ? `(INT${m.quantized})` : ''}`
  }))

  const datasetOptions = datasets.map(d => ({
    value: d.id,
    label: `${d.name} (${d.samples}条)`
  }))

  const getVramSuggestion = () => {
    if (!deviceInfo) return null
    if (deviceInfo.vram_free < 6) {
      return { preset: 'low', text: '6GB 以下显存' }
    } else if (deviceInfo.vram_free < 10) {
      return { preset: 'medium', text: '8GB 显存' }
    }
    return { preset: 'high', text: '12GB+ 显存' }
  }

  const suggestion = getVramSuggestion()

  const renderProgressContent = () => {
    if (trainingStatus === 'completed') {
      return (
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a', marginBottom: 16 }} />
          <div style={{ fontSize: 18, fontWeight: 'bold', color: '#52c41a', marginBottom: 16 }}>
            训练已完成
          </div>
          <Space direction="vertical" style={{ width: '100%' }}>
            {progress && (
              <>
                <div>最终 Loss: <Tag color="blue">{progress.loss?.toFixed(4)}</Tag></div>
                <div>总步数：<Tag>{progress.step}</Tag></div>
                <div>训练时长：<Tag>{Math.floor((progress.elapsedTime || 0) / 60)} 分钟</Tag></div>
              </>
            )}
            <Button type="primary" onClick={() => { setTrainingStatus('idle'); setProgress(null); setChartData([]) }}>
              开始新训练
            </Button>
          </Space>
        </div>
      )
    }

    if (trainingStatus === 'failed') {
      return (
        <div style={{ padding: '16px 0' }}>
          <Alert
            type="error"
            message="训练失败"
            description={progress?.message || '请检查模型和数据后重试'}
            showIcon
          />
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <Button onClick={() => { setTrainingStatus('idle'); setProgress(null); setChartData([]) }}>
              重新配置
            </Button>
          </div>
        </div>
      )
    }

    if (trainingStatus === 'loading' || trainingStatus === 'training') {
      return (
        <div>
          <div style={{ textAlign: 'center', padding: '20px 0', marginBottom: 16 }}>
            <Progress
              type="circle"
              percent={progress ? Math.round((progress.step / (progress.totalSteps || 1)) * 100) : 0}
              format={(percent) => `${percent}%`}
            />
            <div style={{ marginTop: 16, color: 'var(--text-secondary)' }}>
              {progress?.message || '正在加载模型和数据...'}
            </div>
          </div>
          <Steps
            current={getStepsCurrent(trainingStatus)}
            style={{ marginBottom: 16 }}
            items={[
              { title: '加载', icon: <ClockCircleOutlined /> },
              { title: '训练中', icon: <ThunderboltOutlined /> },
              { title: '完成', icon: <CheckCircleOutlined /> },
            ]}
          />
        </div>
      )
    }

    if (isTraining && progress) {
      return (
        <div>
          <Progress
            percent={Math.round((progress.step / (progress.totalSteps || 1)) * 100)}
            status="active"
            strokeColor={{
              '0%': '#108ee9',
              '100%': '#87d068'
            }}
          />
          <div style={{ marginTop: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }} size="small">
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <span><Tag color="blue">Epoch: {progress.epoch}</Tag></span>
                <span><Tag>Step: {progress.step} / {progress.totalSteps}</Tag></span>
                <span><Tag color="green">Loss: {progress.loss?.toFixed(4) || '--'}</Tag></span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <span><Tag color="purple">LR: {progress.lr?.toExponential(2) || '--'}</Tag></span>
                <span><Tag>显存：{progress.vramUsed?.toFixed(1) || 0} GB</Tag></span>
                <span><Tag>时间：{Math.floor((progress.elapsedTime || 0) / 60)}分钟</Tag></span>
              </div>
            </Space>
          </div>
        </div>
      )
    }

    return (
      <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-secondary)' }}>
        <ThunderboltOutlined style={{ fontSize: 48, marginBottom: 16 }} />
        <div>选择模型和数据集后开始训练</div>
        <div style={{ marginTop: 8, fontSize: 12 }}>
          建议：先在模型管理下载模型，数据集管理上传数据
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '0 24px' }}>
      <div className="page-container">
        <div className="page-title">
          <ThunderboltOutlined style={{ marginRight: 8 }} />
          模型训练
        </div>

        {backendStatus !== 'connected' ? (
          <Alert
            type="warning"
            message="后端服务未连接"
            description="请先启动应用后刷新页面"
            showIcon
          />
        ) : models.length === 0 || datasets.length === 0 ? (
          <Alert
            type="info"
            message="请先准备模型和数据集"
            description={
              <div>
                {models.length === 0 && <div>• 请在模型管理中下载模型</div>}
                {datasets.length === 0 && <div>• 请在数据集管理中上传数据</div>}
              </div>
            }
            showIcon
          />
        ) : (
          <Row gutter={24}>
            <Col xs={24} xl={14}>
              {/* P2-2: SWIFT 框架状态检查 */}
              <SwiftChecker onStatusChange={(status) => setSwiftAvailable(status.available)} />
              
              <Card title="训练配置" variant="borderless">
                <Form
                  form={form}
                  layout="vertical"
                  onFinish={handleStart}
                  initialValues={{
                    method: 'qlora',
                    rank: 8,
                    alpha: 16,
                    learningRate: 5e-5,
                    epochs: 3,
                    batchSize: 1,
                    gradientAccumulation: 16,
                    maxSeqLength: 512,
                    warmupSteps: 100,
                    saveSteps: 500,
                    loggingSteps: 10
                  }}
                  disabled={isTraining}
                >
                  <Form.Item label="选择模型" name="modelId" rules={[{ required: true, message: '请选择模型' }]}>
                    <Select
                      placeholder="选择要微调的模型"
                      options={modelOptions}
                      disabled={isTraining}
                      showSearch
                      filterOption={(input, option) =>
                        (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                    />
                  </Form.Item>

                  <Form.Item label="选择数据集" name="datasetId" rules={[{ required: true, message: '请选择数据集' }]}>
                    <Select
                      placeholder="选择训练数据集"
                      options={datasetOptions}
                      disabled={isTraining}
                      showSearch
                    />
                  </Form.Item>

                  {/* P2-2: SWIFT 框架开关 */}
                  <Form.Item
                    label={
                      <span>
                        <ThunderboltOutlined style={{ marginRight: 4, color: '#1677ff' }} />
                        使用 SWIFT 框架
                      </span>
                    }
                    name="useSwift"
                    valuePropName="checked"
                    initialValue={false}
                    tooltip="阿里 SWIFT 框架可提升训练速度 25%，降低显存占用 20%"
                  >
                    <Switch
                      checked={useSwift}
                      onChange={setUseSwift}
                      disabled={!swiftAvailable || isTraining}
                      checkedChildren="开启"
                      unCheckedChildren="关闭"
                    />
                  </Form.Item>

                  {/* P2-3: 精度预设选择 */}
                  <Form.Item
                    label={
                      <span>
                        <CheckCircleOutlined style={{ marginRight: 4, color: '#52c41a' }} />
                        精度预设
                      </span>
                    }
                    tooltip="最高精度：全参数/DoRA + 余弦退火；平衡：高秩 LoRA；快速：QLoRA"
                  >
                    <Select
                      value={precisionPreset}
                      onChange={setPrecisionPreset}
                      disabled={isTraining}
                    >
                      <Select.Option value="max">🏆 最高精度 (Max)</Select.Option>
                      <Select.Option value="balanced">⚖️ 平衡精度 (Balanced)</Select.Option>
                      <Select.Option value="fast">⚡ 快速训练 (Fast)</Select.Option>
                    </Select>
                  </Form.Item>

                  {/* P2-3: DoRA 开关 */}
                  <Form.Item
                    label={
                      <span>
                        <ThunderboltOutlined style={{ marginRight: 4, color: '#722ed1' }} />
                        DoRA 微调
                      </span>
                    }
                    tooltip="DoRA 分解权重为幅度和方向，精度接近全参数微调"
                    valuePropName="checked"
                  >
                    <Switch
                      checked={useDora}
                      onChange={setUseDora}
                      disabled={isTraining || precisionPreset === 'fast'}
                      checkedChildren="开启"
                      unCheckedChildren="关闭"
                    />
                  </Form.Item>

                  {/* P2-4: 显存优化预设 */}
                  <Divider>显存优化</Divider>

                  <Form.Item
                    label={
                      <span>
                        <ThunderboltOutlined style={{ marginRight: 4, color: '#fa8c16' }} />
                        显存优化预设
                      </span>
                    }
                    tooltip="根据 GPU 显存自动优化配置，在保证精度的情况下减少显存占用"
                  >
                    <Select
                      value={memoryPreset}
                      onChange={setMemoryPreset}
                      disabled={isTraining}
                    >
                      <Select.Option value="auto">🤖 自动检测</Select.Option>
                      <Select.Option value="6gb">💾 6GB 显存 (极致压缩)</Select.Option>
                      <Select.Option value="8gb">💾 8GB 显存 (平衡优化)</Select.Option>
                      <Select.Option value="12gb">💾 12GB 显存 (DeepSpeed)</Select.Option>
                    </Select>
                  </Form.Item>

                  <Row gutter={16}>
                    <Col span={8}>
                      <Form.Item label="梯度累积" name="gradientAccumulation">
                        <InputNumber
                          min={1}
                          max={128}
                          value={gradientAccumulation}
                          onChange={(value) => setGradientAccumulation(value || 16)}
                          style={{ width: '100%' }}
                          disabled={isTraining || memoryPreset !== 'auto'}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="量化位数" name="quantization">
                        <Select
                          value={quantizationBit}
                          onChange={setQuantizationBit}
                          disabled={isTraining || memoryPreset !== 'auto'}
                        >
                          <Select.Option value={4}>4bit (省显存)</Select.Option>
                          <Select.Option value={8}>8bit (平衡)</Select.Option>
                          <Select.Option value={0}>无量化 (高精度)</Select.Option>
                        </Select>
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="Flash Attn">
                        <Switch
                          checked={useFlashAttn}
                          onChange={setUseFlashAttn}
                          disabled={isTraining}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                        />
                      </Form.Item>
                    </Col>
                  </Row>

                  {/* P2-5: LoRA+ 和 GaLore 高级优化 */}
                  <Divider>高级优化技术</Divider>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        label={
                          <span>
                            <span style={{ marginRight: 4 }}>🔧</span>
                            LoRA+ (论文)
                          </span>
                        }
                        tooltip="LoRA+: 为 LoRA 的 A/B 矩阵设置不同学习率，收敛更快效果更好"
                        valuePropName="checked"
                      >
                        <Switch
                          checked={useLoraPlus}
                          onChange={setUseLoraPlus}
                          disabled={isTraining || precisionPreset === 'fast'}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      {useLoraPlus && (
                        <Form.Item label="学习率比值">
                          <InputNumber
                            min={1}
                            max={32}
                            value={loraPlusLrRatio}
                            onChange={(value) => setLoraPlusLrRatio(value || 16)}
                            style={{ width: '100%' }}
                            disabled={isTraining}
                          />
                        </Form.Item>
                      )}
                    </Col>
                  </Row>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        label={
                          <span>
                            <span style={{ marginRight: 4 }}>📉</span>
                            GaLore (论文)
                          </span>
                        }
                        tooltip="GaLore: 梯度低秩投影，4GB 显存训练 7B 模型 (需要安装 galore-torch)"
                        valuePropName="checked"
                      >
                        <Switch
                          checked={useGalore}
                          onChange={setUseGalore}
                          disabled={isTraining}
                          checkedChildren="开启"
                          unCheckedChildren="关闭"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      {useGalore && (
                        <Form.Item label="投影秩">
                          <InputNumber
                            min={16}
                            max={1024}
                            value={galoreRank}
                            onChange={(value) => setGaloreRank(value || 128)}
                            style={{ width: '100%' }}
                            disabled={isTraining}
                          />
                        </Form.Item>
                      )}
                    </Col>
                  </Row>

                  {!useGalore && (
                    <Alert
                      message="提示"
                      description="GaLore 需要安装: pip install galore-torch 或 pip install git+https://github.com/jiaweizzhao/GaLore.git"
                      type="info"
                      showIcon
                      style={{ marginBottom: 16 }}
                    />
                  )}

                  <Divider>训练参数预设</Divider>

                  <Space style={{ marginBottom: 16 }}>
                    <Button onClick={() => applyPreset('low')}>低显存 (6GB)</Button>
                    <Button onClick={() => applyPreset('medium')}>中等 (8GB)</Button>
                    <Button onClick={() => applyPreset('high')}>高性能 (12GB+)</Button>
                  </Space>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item label="训练方法" name="method">
                        <Select>
                          <Select.Option value="lora">LoRA</Select.Option>
                          <Select.Option value="qlora">QLoRA (推荐)</Select.Option>
                        </Select>
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="训练轮数 (Epochs)" name="epochs">
                        <InputNumber min={1} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item label="LoRA Rank (秩)" name="rank">
                        <InputNumber min={4} max={128} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="LoRA Alpha" name="alpha">
                        <InputNumber min={8} max={256} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item label="学习率" name="learningRate">
                        <InputNumber
                          min={1e-6}
                          max={1e-3}
                          step={1e-5}
                          style={{ width: '100%' }}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="最大序列长度" name="maxSeqLength">
                        <InputNumber min={128} max={4096} step={128} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item label="批次大小" name="batchSize">
                        <InputNumber min={1} max={32} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item label="梯度累积" name="gradientAccumulation">
                        <InputNumber min={1} max={128} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Divider>高级设置</Divider>

                  <Row gutter={16}>
                    <Col span={8}>
                      <Form.Item label="预热步数" name="warmupSteps">
                        <InputNumber min={0} max={1000} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="保存间隔" name="saveSteps">
                        <InputNumber min={100} max={5000} step={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item label="日志间隔" name="loggingSteps">
                        <InputNumber min={1} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Form.Item>
                    <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                      {(isTraining || backendTraining) ? (
                        <Button
                          type="primary"
                          danger
                          icon={<StopOutlined />}
                          onClick={handleStop}
                          size="large"
                        >
                          停止训练
                        </Button>
                      ) : (
                        <Button
                          type="primary"
                          icon={<PlayCircleOutlined />}
                          htmlType="submit"
                          loading={starting}
                          size="large"
                          disabled={!models.length || !datasets.length}
                        >
                          开始训练
                        </Button>
                      )}
                    </Space>
                  </Form.Item>
                </Form>
              </Card>
            </Col>

            <Col xs={24} xl={10}>
              <Card title="训练进度" variant="borderless">
                {renderProgressContent()}
              </Card>

              {chartData.length > 0 && (
                <Card
                  title={
                    <span>
                      <LineChartOutlined style={{ marginRight: 8, color: '#1677ff' }} />
                      Loss 曲线
                    </span>
                  }
                  variant="borderless"
                  style={{ marginTop: 16 }}
                >
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                      <XAxis
                        dataKey="step"
                        label={{ value: 'Step', position: 'insideBottom', offset: -5 }}
                        stroke="var(--text-secondary)"
                      />
                      <YAxis
                        label={{ value: 'Loss', angle: -90, position: 'insideLeft' }}
                        stroke="var(--text-secondary)"
                      />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--bg-elevated)',
                          border: '1px solid var(--border-color)',
                          borderRadius: 'var(--radius-lg)'
                        }}
                        labelStyle={{ color: 'var(--text-primary)' }}
                      />
                      <ReferenceLine y={0} stroke="var(--text-tertiary)" />
                      <Line
                        type="monotone"
                        dataKey="loss"
                        stroke="var(--accent-primary)"
                        strokeWidth={2}
                        dot={false}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Card>
              )}

              {/* P2-1: 训练可视化组件 - 实时图表 */}
              {isTraining && currentTaskId && (
                <div style={{ marginTop: 24 }}>
                  <TrainingChart taskId={currentTaskId} autoConnect={true} />
                </div>
              )}

              <Card title="显存建议" variant="borderless" style={{ marginTop: 16 }}>
                {suggestion && (
                  <div>
                    <Tag color={suggestion.preset === 'low' ? 'orange' : suggestion.preset === 'medium' ? 'blue' : 'green'}>
                      {suggestion.text}
                    </Tag>
                    <ul style={{ marginTop: 12, paddingLeft: 20, color: 'var(--text-secondary)' }}>
                      <li>INT4 + QLoRA: 6GB 显存可微调 7B 模型</li>
                      <li>INT4: 8GB 显存可微调 7B 模型</li>
                      <li>INT8: 12GB 显存可微调 7B 模型</li>
                      <li>FP16: 16GB 显存可微调 13B 模型</li>
                    </ul>
                  </div>
                )}
              </Card>
            </Col>
          </Row>
        )}
      </div>
    </div>
  )
}
