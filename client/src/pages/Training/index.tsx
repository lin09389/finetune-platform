import { useState, useEffect, useRef, useCallback } from 'react'
import { Row, Col, message, Form, Empty } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { useAppStore } from '../../store/appStore'
import { startTraining, stopTraining, subscribeTrainingProgress, startSwiftTraining, API_BASE_URL } from '../../services/api'
import type { TrainingProgress as TrainingProgressType } from '../../types'
import GlassCard from '../../components/shared/GlassCard'
import AnimatedLayout from '../../components/shared/AnimatedLayout'
import ConfigForm from './components/ConfigForm'
import ProgressPanel from './components/ProgressPanel'
import LossChart from './components/LossChart'
import SwiftChecker from '../../components/SwiftChecker'
import TrainingChart from '../../components/TrainingChart'
import styles from './Training.module.css'

interface ChartDataPoint {
  step: number
  loss: number
  lr: number
}

const TrainingPage: React.FC = () => {
  const { models, datasets, backendStatus, isTraining, setIsTraining, addTrainingRecord } = useAppStore()
  const [form] = Form.useForm()
  const [progress, setProgress] = useState<TrainingProgressType | null>(null)
  const [starting, setStarting] = useState(false)
  const [trainingStatus, setTrainingStatus] = useState<'idle' | 'loading' | 'training' | 'completed' | 'failed'>('idle')
  const unsubscribeRef = useRef<(() => void) | null>(null)
  const [chartData, setChartData] = useState<ChartDataPoint[]>([])
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)
  const [backendTraining, setBackendTraining] = useState(false)
  
  const [useSwift, setUseSwift] = useState(false)
  const [swiftAvailable, setSwiftAvailable] = useState(false)
  const [precisionPreset, setPrecisionPreset] = useState<'max' | 'balanced' | 'fast'>('balanced')
  const [useDora, setUseDora] = useState(false)
  const [memoryPreset, setMemoryPreset] = useState<'auto' | '6gb' | '8gb' | '12gb'>('auto')
  const [useFlashAttn, setUseFlashAttn] = useState(false)
  const [quantizationBit, setQuantizationBit] = useState<4 | 8 | 0>(4)
  const [gradientAccumulation, setGradientAccumulation] = useState<number>(16)
  const [useLoraPlus, setUseLoraPlus] = useState(false)
  const [loraPlusLrRatio, setLoraPlusLrRatio] = useState(16)
  const [useGalore, setUseGalore] = useState(false)
  const [galoreRank, setGaloreRank] = useState(128)

  const checkTrainingStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/training/status`)
      const data = await response.json()
      setBackendTraining(data.is_training)
      if (data.is_training && data.progress) {
        setProgress(data.progress)
        if (data.progress.status === 'failed') {
          setTrainingStatus('failed')
          setIsTraining(false)
        } else if (data.progress.status === 'completed') {
          setTrainingStatus('completed')
          setIsTraining(false)
        }
      }
    } catch (e) {
      console.error('检查训练状态失败:', e)
    }
  }, [setIsTraining])

  useEffect(() => {
    const interval = setInterval(checkTrainingStatus, 3000)
    checkTrainingStatus()
    return () => clearInterval(interval)
  }, [checkTrainingStatus])

  useEffect(() => {
    if (isTraining && backendStatus === 'connected') {
      setTrainingStatus('training')
      setChartData([])
      unsubscribeRef.current = subscribeTrainingProgress(
        (p: any) => {
          setProgress(p)
          if (p.loss !== undefined && p.step !== undefined) {
            setChartData(prev => {
              const newData = [...prev, { step: p.step, loss: p.loss, lr: p.lr || 0 }]
              return newData.length > 500 ? newData.slice(newData.length - 500) : newData
            })
          }
          if (p.status === 'loading') setTrainingStatus('loading')
          else if (p.status === 'training' || p.status === 'running') setTrainingStatus('training')
          else if (p.status === 'completed') {
            setTrainingStatus('completed')
            setIsTraining(false)
            message.success('训练完成!')
          } else if (p.status === 'failed' || p.status === 'stopped') {
            setTrainingStatus(p.status === 'failed' ? 'failed' : 'idle')
            setIsTraining(false)
            if (p.status === 'failed') message.error(p.message || '训练失败')
            else message.warning('训练已停止')
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
  }, [isTraining, backendStatus, setIsTraining])

  const handleStart = async (values: any) => {
    if (starting || isTraining) return
    setStarting(true)
    setTrainingStatus('loading')
    setChartData([])
    
    try {
      const config = {
        model_id: values.modelId,
        dataset_id: values.datasetId,
        method: values.method || 'qlora',
        rank: values.rank || 8,
        alpha: values.alpha || 16,
        learning_rate: values.learningRate || 5e-5,
        epochs: values.epochs || 3,
        batch_size: values.batchSize || 1,
        gradient_accumulation: gradientAccumulation,
        max_seq_length: values.maxSeqLength || 512,
        warmup_steps: values.warmupSteps || 100,
        save_steps: values.saveSteps || 500,
        logging_steps: values.loggingSteps || 10,
        use_dora: useDora,
        precision_preset: precisionPreset,
        memory_preset: memoryPreset,
        use_flash_attn: useFlashAttn,
        quantization: quantizationBit,
        use_lora_plus: useLoraPlus,
        lora_plus_lr_ratio: loraPlusLrRatio,
        use_galore: useGalore,
        galore_rank: galoreRank,
      }

      let result
      if (useSwift && swiftAvailable) {
        result = await startSwiftTraining(config)
      } else {
        result = await startTraining(config)
      }
      setIsTraining(true)
      addTrainingRecord(result)
      setCurrentTaskId(result.id)
      message.success('训练任务已提交')
    } catch (error: any) {
      setTrainingStatus('idle')
      message.error(error.response?.data?.detail || '启动训练失败')
    } finally {
      setStarting(false)
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

  return (
    <AnimatedLayout animationKey="training">
      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.titleIcon}><ThunderboltOutlined /></div>
          <div>
            <h1 className={styles.title}>模型训练</h1>
            <p className={styles.subtitle}>配置参数并开始微调您的模型</p>
          </div>
        </div>

        {backendStatus !== 'connected' ? (
          <GlassCard intensity="high" style={{ padding: 'var(--space-12) 0', textAlign: 'center' }}>
            <Empty description="后端服务未连接，请先启动应用" />
          </GlassCard>
        ) : (
          <Row gutter={[24, 24]}>
            <Col xs={24} xl={14}>
              <SwiftChecker onStatusChange={(s) => setSwiftAvailable(s.available)} />
              <GlassCard intensity="medium" noHover>
                <ConfigForm
                  form={form}
                  onFinish={handleStart}
                  isTraining={isTraining || backendTraining}
                  starting={starting}
                  onStop={handleStop}
                  models={models}
                  datasets={datasets}
                  swiftAvailable={swiftAvailable}
                  useSwift={useSwift}
                  onSwiftChange={setUseSwift}
                  precisionPreset={precisionPreset}
                  onPrecisionChange={setPrecisionPreset}
                  useDora={useDora}
                  onDoraChange={setUseDora}
                  memoryPreset={memoryPreset}
                  onMemoryChange={setMemoryPreset}
                  useFlashAttn={useFlashAttn}
                  onFlashAttnChange={setUseFlashAttn}
                  quantizationBit={quantizationBit}
                  onQuantizationChange={setQuantizationBit}
                  gradientAccumulation={gradientAccumulation}
                  onGradAccChange={setGradientAccumulation}
                  useLoraPlus={useLoraPlus}
                  onLoraPlusChange={setUseLoraPlus}
                  loraPlusLrRatio={loraPlusLrRatio}
                  onLoraPlusLrRatioChange={setLoraPlusLrRatio}
                  useGalore={useGalore}
                  onGaloreChange={setUseGalore}
                  galoreRank={galoreRank}
                  onGaloreRankChange={setGaloreRank}
                  onApplyPreset={(p) => {
                    const configs = {
                      low: { rank: 8, alpha: 16, batchSize: 1, gradientAccumulation: 16, maxSeqLength: 512 },
                      medium: { rank: 16, alpha: 32, batchSize: 2, gradientAccumulation: 8, maxSeqLength: 1024 },
                      high: { rank: 32, alpha: 64, batchSize: 4, gradientAccumulation: 4, maxSeqLength: 2048 }
                    }
                    form.setFieldsValue(configs[p])
                  }}
                />
              </GlassCard>
            </Col>
            <Col xs={24} xl={10}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
                <GlassCard intensity="medium" noHover>
                  <ProgressPanel
                    status={trainingStatus}
                    progress={progress}
                    onReset={() => { setTrainingStatus('idle'); setProgress(null); setChartData([]) }}
                  />
                </GlassCard>

                {chartData.length > 0 && (
                  <GlassCard intensity="low" noHover>
                    <LossChart data={chartData} />
                  </GlassCard>
                )}

                {isTraining && currentTaskId && (
                  <GlassCard intensity="low" noHover>
                    <TrainingChart taskId={currentTaskId} autoConnect={true} />
                  </GlassCard>
                )}
              </div>
            </Col>
          </Row>
        )}
      </div>
    </AnimatedLayout>
  )
}

export default TrainingPage
