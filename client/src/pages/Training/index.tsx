import { useState, useEffect, useRef, useCallback } from 'react'
import { Row, Col, message, Form, Empty } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { useAppStore } from '../../store/appStore'
import {
  getTrainingStatus,
  startTraining,
  stopTraining,
  subscribeTrainingProgress,
  startSwiftTraining,
} from '../../services/trainingApi'
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

const getErrorMessage = (error: any, fallback: string) =>
  error?.response?.data?.detail || error?.message || fallback

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
  const [memoryPreset, setMemoryPreset] = useState<'auto' | '6gb' | '8gb' | '12gb'>('auto')
  const [useFlashAttn, setUseFlashAttn] = useState(false)
  const [quantizationBit, setQuantizationBit] = useState<4 | 8 | 0>(4)
  const [gradientAccumulation, setGradientAccumulation] = useState<number>(16)

  const checkTrainingStatus = useCallback(async () => {
    try {
      const data = await getTrainingStatus()
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
    } catch (error) {
      console.error('Failed to check training status:', error)
    }
  }, [setIsTraining])

  useEffect(() => {
    const interval = setInterval(checkTrainingStatus, 3000)
    void checkTrainingStatus()
    return () => clearInterval(interval)
  }, [checkTrainingStatus])

  useEffect(() => {
    if (isTraining && backendStatus === 'connected') {
      setTrainingStatus('training')
      setChartData([])
      unsubscribeRef.current = subscribeTrainingProgress(
        (nextProgress: any) => {
          setProgress(nextProgress)
          if (nextProgress.loss !== undefined && nextProgress.step !== undefined) {
            setChartData((prev) => {
              const newData = [...prev, { step: nextProgress.step, loss: nextProgress.loss, lr: nextProgress.lr || 0 }]
              return newData.length > 500 ? newData.slice(newData.length - 500) : newData
            })
          }
          if (nextProgress.status === 'loading') setTrainingStatus('loading')
          else if (nextProgress.status === 'training' || nextProgress.status === 'running') setTrainingStatus('training')
          else if (nextProgress.status === 'completed') {
            setTrainingStatus('completed')
            setIsTraining(false)
            message.success('训练完成')
          } else if (nextProgress.status === 'failed' || nextProgress.status === 'stopped') {
            setTrainingStatus(nextProgress.status === 'failed' ? 'failed' : 'idle')
            setIsTraining(false)
            if (nextProgress.status === 'failed') {
              message.error(nextProgress.message || '训练失败')
            } else {
              message.warning('训练已停止')
            }
          }
        },
        (error: Error) => {
          console.error('SSE error:', error)
          setTrainingStatus('idle')
        },
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
        precision_preset: precisionPreset,
        memory_preset: memoryPreset,
        use_flash_attn: useFlashAttn,
        quantization: quantizationBit,
      }

      const result = useSwift && swiftAvailable
        ? await startSwiftTraining(config)
        : await startTraining(config)

      setIsTraining(true)
      addTrainingRecord(result)
      setCurrentTaskId(result.id)
      message.success('训练任务已提交')
    } catch (error: any) {
      setTrainingStatus('idle')
      message.error(getErrorMessage(error, '启动训练失败'))
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
      message.error(getErrorMessage(error, '停止训练失败'))
    }
  }

  return (
    <AnimatedLayout animationKey="training">
      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.titleIcon}><ThunderboltOutlined /></div>
          <div>
            <h1 className={styles.title}>模型训练</h1>
            <p className={styles.subtitle}>配置参数并开始微调你的模型。</p>
          </div>
        </div>

        {backendStatus !== 'connected' ? (
          <GlassCard intensity="high" style={{ padding: 'var(--space-12) 0', textAlign: 'center' }}>
            <Empty description="后端服务未连接，请先启动应用。" />
          </GlassCard>
        ) : (
          <Row gutter={[24, 24]}>
            <Col xs={24} xl={14}>
              <SwiftChecker onStatusChange={(status) => setSwiftAvailable(status.available)} />
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
                  memoryPreset={memoryPreset}
                  onMemoryChange={setMemoryPreset}
                  useFlashAttn={useFlashAttn}
                  onFlashAttnChange={setUseFlashAttn}
                  quantizationBit={quantizationBit}
                  onQuantizationChange={setQuantizationBit}
                  gradientAccumulation={gradientAccumulation}
                  onGradAccChange={setGradientAccumulation}
                  onApplyPreset={(preset) => {
                    const configs = {
                      low: { rank: 8, alpha: 16, batchSize: 1, gradientAccumulation: 16, maxSeqLength: 512 },
                      medium: { rank: 16, alpha: 32, batchSize: 2, gradientAccumulation: 8, maxSeqLength: 1024 },
                      high: { rank: 32, alpha: 64, batchSize: 4, gradientAccumulation: 4, maxSeqLength: 2048 },
                    }
                    form.setFieldsValue(configs[preset])
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
                    onReset={() => {
                      setTrainingStatus('idle')
                      setProgress(null)
                      setChartData([])
                    }}
                  />
                </GlassCard>

                {chartData.length > 0 && (
                  <GlassCard intensity="low" noHover>
                    <LossChart data={chartData} />
                  </GlassCard>
                )}

                {isTraining && currentTaskId && (
                  <GlassCard intensity="low" noHover>
                    <TrainingChart taskId={currentTaskId} autoConnect />
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
