import { useState, useEffect, useRef, useCallback } from 'react'
import { Row, Col, Form, Empty, Button, Space, Modal, Select } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { useAppStore } from '../../store/appStore'
import {
  checkTrainingResources,
  getTrainingFailureAnalytics,
  getTrainingStatus,
  getTrainingHistory,
  getTrainingCheckpoints,
  getTrainingRecoveryOptions,
  resumeTraining,
  startTraining,
  stopTraining,
  subscribeTrainingProgress,
  startSwiftTraining,
} from '../../services/trainingApi'
import type { TrainingProgress as TrainingProgressType, Checkpoint, TrainingRecord } from '../../types'
import GlassCard from '../../components/shared/GlassCard'
import AnimatedLayout from '../../components/shared/AnimatedLayout'
import InsightPanel from '../../components/shared/InsightPanel'
import ConfigForm from './components/ConfigForm'
import ProgressPanel from './components/ProgressPanel'
import LossChart from './components/LossChart'
import SwiftChecker from '../../components/SwiftChecker'
import TrainingChart from '../../components/TrainingChart'
import RuntimeContextPanel from '../../components/runtime/RuntimeContextPanel'
import { useRuntimeContext } from '../../runtime/RuntimeContext'
import { notify } from '../../utils/notify'
import {
  buildTrainingFailureAnalytics,
  buildTrainingPreflightFingerprint,
  buildResumeConfigDiff,
  diagnoseTrainingFailure,
  type TrainingFailureAnalytics,
  type TrainingFailureDiagnosis,
} from './trainingInsights'
import styles from './Training.module.css'

interface ChartDataPoint {
  step: number
  loss: number
  lr: number
}

interface PreflightResult {
  passed: boolean
  available_vram: number
  required_vram: number
  suggestions: string[]
  warnings: string[]
  recommended_config: Record<string, any>
  device_name?: string
}

interface ResumeOption {
  taskId: string
  status: 'failed' | 'stopped'
  modelName: string
  datasetName: string
  startTime: string
  checkpoints: Checkpoint[]
  latestCheckpointName: string
  config: Record<string, any>
  reason?: string
}

const getErrorMessage = (error: any, fallback: string) =>
  error?.response?.data?.detail?.message
  || error?.response?.data?.detail
  || error?.message
  || fallback

const TrainingPage: React.FC = () => {
  const { models, datasets, backendStatus, isTraining, setIsTraining, addTrainingRecord } = useAppStore()
  const { actions, derived } = useRuntimeContext()
  const { setTrainingSelection, syncInferenceSelection } = actions
  const [form] = Form.useForm()
  const [progress, setProgress] = useState<TrainingProgressType | null>(null)
  const [starting, setStarting] = useState(false)
  const [trainingStatus, setTrainingStatus] = useState<'idle' | 'loading' | 'training' | 'stopping' | 'completed' | 'failed'>('idle')
  const unsubscribeRef = useRef<(() => void) | null>(null)
  const [chartData, setChartData] = useState<ChartDataPoint[]>([])
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)
  const [backendTraining, setBackendTraining] = useState(false)
  const [preflightResult, setPreflightResult] = useState<PreflightResult | null>(null)
  const [preflightChecking, setPreflightChecking] = useState(false)
  const [preflightFingerprint, setPreflightFingerprint] = useState<string | null>(null)
  const [resumeOptions, setResumeOptions] = useState<ResumeOption[]>([])
  const [selectedResumeTaskId, setSelectedResumeTaskId] = useState<string | null>(null)
  const [selectedResumeCheckpointName, setSelectedResumeCheckpointName] = useState<string | null>(null)
  const [resumeLoading, setResumeLoading] = useState(false)
  const [resumeStarting, setResumeStarting] = useState(false)
  const [failureDiagnosis, setFailureDiagnosis] = useState<TrainingFailureDiagnosis | null>(null)
  const [failureAnalytics, setFailureAnalytics] = useState<TrainingFailureAnalytics | null>(null)

  const [useSwift, setUseSwift] = useState(false)
  const [swiftAvailable, setSwiftAvailable] = useState(false)
  const [precisionPreset, setPrecisionPreset] = useState<'max' | 'balanced' | 'fast'>('balanced')
  const [memoryPreset, setMemoryPreset] = useState<'auto' | '6gb' | '8gb' | '12gb'>('auto')
  const [useFlashAttn, setUseFlashAttn] = useState(false)
  const [quantizationBit, setQuantizationBit] = useState<4 | 8 | 0>(4)
  const [gradientAccumulation, setGradientAccumulation] = useState<number>(16)
  const watchedModelId = Form.useWatch('modelId', form)
  const watchedDatasetId = Form.useWatch('datasetId', form)
  const watchedMethod = Form.useWatch('method', form)
  const watchedBatchSize = Form.useWatch('batchSize', form)
  const watchedMaxSeqLength = Form.useWatch('maxSeqLength', form)

  useEffect(() => {
    setTrainingSelection({
      modelId: watchedModelId,
      datasetId: watchedDatasetId,
    })
  }, [setTrainingSelection, watchedDatasetId, watchedModelId])

  const getCurrentPreflightFingerprint = useCallback(() => {
    const values = form.getFieldsValue()
    return buildTrainingPreflightFingerprint(values, {
      gradientAccumulation,
      precisionPreset,
      memoryPreset,
      useFlashAttn,
      quantizationBit,
      useSwift,
    })
  }, [form, gradientAccumulation, memoryPreset, precisionPreset, quantizationBit, useFlashAttn, useSwift])

  const resolveTrainingRecoveryState = useCallback(async () => {
    if (backendStatus !== 'connected') {
      setResumeOptions([])
      setSelectedResumeTaskId(null)
      setSelectedResumeCheckpointName(null)
      setFailureAnalytics(null)
      return
    }

    setResumeLoading(true)
    try {
      const [recoveryPayload, analyticsPayload] = await Promise.all([
        getTrainingRecoveryOptions(6).catch(() => null),
        getTrainingFailureAnalytics().catch(() => null),
      ])

      if (analyticsPayload) {
        setFailureAnalytics(analyticsPayload)
      } else {
        const fallbackHistory: TrainingRecord[] = await getTrainingHistory()
        setFailureAnalytics(buildTrainingFailureAnalytics(fallbackHistory))
      }

      let nextOptions: ResumeOption[] = []
      if (recoveryPayload && Array.isArray(recoveryPayload.options)) {
        nextOptions = recoveryPayload.options
      } else {
        const history: TrainingRecord[] = await getTrainingHistory()
        const failedOrStopped = (
          history.filter((record) => record.status === 'failed' || record.status === 'stopped') as Array<
            TrainingRecord & { status: 'failed' | 'stopped' }
          >
        ).sort((a, b) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime())

        for (const record of failedOrStopped.slice(0, 6)) {
          const checkpoints: Checkpoint[] = await getTrainingCheckpoints(record.id)
          if (!Array.isArray(checkpoints) || checkpoints.length === 0) continue

          const sortedCheckpoints = checkpoints.slice().sort((a, b) => b.step - a.step)
          const latestCheckpoint = sortedCheckpoints[0]
          if (!latestCheckpoint) continue
          nextOptions.push({
            taskId: record.id,
            status: record.status,
            modelName: record.modelName,
            datasetName: record.datasetName,
            startTime: record.startTime,
            checkpoints: sortedCheckpoints,
            latestCheckpointName: latestCheckpoint.name,
            config: record.config || {},
            reason: record.status === 'failed' ? '最近一次失败任务存在可恢复检查点' : '最近一次停止任务存在可恢复检查点',
          })
        }
      }

      setResumeOptions(nextOptions)
      setSelectedResumeTaskId(nextOptions[0]?.taskId || null)
      setSelectedResumeCheckpointName(nextOptions[0]?.latestCheckpointName || null)
    } catch (error) {
      console.error('Failed to resolve training recovery state:', error)
      setResumeOptions([])
      setSelectedResumeTaskId(null)
      setSelectedResumeCheckpointName(null)
      setFailureAnalytics(null)
    } finally {
      setResumeLoading(false)
    }
  }, [backendStatus])

  const checkTrainingStatus = useCallback(async () => {
    try {
      const data = await getTrainingStatus()
      setBackendTraining(data.is_training)
      if (data.progress) {
        setProgress(data.progress)
        if (data.progress.status === 'stopping') {
          setTrainingStatus('stopping')
          setIsTraining(true)
        } else if (data.progress.status === 'failed') {
          setTrainingStatus('failed')
          setFailureDiagnosis(diagnoseTrainingFailure(data.progress.message))
          setIsTraining(false)
        } else if (data.progress.status === 'completed') {
          setTrainingStatus('completed')
          setFailureDiagnosis(null)
          setIsTraining(false)
        } else if (data.progress.status === 'stopped') {
          setTrainingStatus('idle')
          setFailureDiagnosis(null)
          setIsTraining(false)
        } else if (data.is_training) {
          setTrainingStatus(data.progress.status === 'loading' ? 'loading' : 'training')
          setIsTraining(true)
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
    void resolveTrainingRecoveryState()
  }, [resolveTrainingRecoveryState])

  useEffect(() => {
    if (!selectedResumeTaskId) {
      setSelectedResumeCheckpointName(null)
      return
    }

    const selectedOption = resumeOptions.find((option) => option.taskId === selectedResumeTaskId)
    if (!selectedOption) {
      setSelectedResumeCheckpointName(null)
      return
    }

    const checkpointExists = selectedOption.checkpoints.some((checkpoint) => checkpoint.name === selectedResumeCheckpointName)
    if (!checkpointExists) {
      setSelectedResumeCheckpointName(selectedOption.latestCheckpointName)
    }
  }, [resumeOptions, selectedResumeCheckpointName, selectedResumeTaskId])

  useEffect(() => {
    if (isTraining && backendStatus === 'connected') {
      setTrainingStatus('training')
      setFailureDiagnosis(null)
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
          else if (nextProgress.status === 'stopping') setTrainingStatus('stopping')
          else if (nextProgress.status === 'training' || nextProgress.status === 'running') setTrainingStatus('training')
          else if (nextProgress.status === 'completed') {
            setTrainingStatus('completed')
            setFailureDiagnosis(null)
            setIsTraining(false)
            void resolveTrainingRecoveryState()
            notify.success('训练完成')
          } else if (nextProgress.status === 'failed' || nextProgress.status === 'stopped') {
            setTrainingStatus(nextProgress.status === 'failed' ? 'failed' : 'idle')
            setIsTraining(false)
            if (nextProgress.status === 'failed') {
              setFailureDiagnosis(diagnoseTrainingFailure(nextProgress.message))
              notify.error(nextProgress.message || '训练失败')
              void resolveTrainingRecoveryState()
            } else {
              notify.warning('训练已停止')
              void resolveTrainingRecoveryState()
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

  useEffect(() => {
    if (!preflightResult) return
    if (!preflightFingerprint) return
    const latest = getCurrentPreflightFingerprint()
    if (latest !== preflightFingerprint) {
      setPreflightResult(null)
      setPreflightFingerprint(null)
    }
  }, [
    getCurrentPreflightFingerprint,
    memoryPreset,
    preflightFingerprint,
    preflightResult,
    precisionPreset,
    quantizationBit,
    useFlashAttn,
    useSwift,
    watchedBatchSize,
    watchedDatasetId,
    watchedMaxSeqLength,
    watchedMethod,
    watchedModelId,
  ])

  const confirmRiskStart = useCallback((warnings: string[]) => new Promise<boolean>((resolve) => {
    Modal.confirm({
      title: '预检提示当前配置存在风险',
      content: `检测到 ${warnings.length} 条风险提示。是否仍然继续启动训练？`,
      okText: '仍然启动',
      cancelText: '返回调整',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
      afterClose: () => resolve(false),
    })
  }), [])

  const handleStart = async (values: any) => {
    if (starting || isTraining) return

    const latestFingerprint = getCurrentPreflightFingerprint()
    if (!preflightResult || !preflightFingerprint || latestFingerprint !== preflightFingerprint) {
      notify.warning('请先执行训练前预检；若你修改了配置，需要重新预检后再启动训练。')
      return
    }

    const shouldApplyRecommendedConfig = !preflightResult.passed
      ? await confirmRiskStart(preflightResult.warnings || [])
      : false
    if (!preflightResult.passed && !shouldApplyRecommendedConfig) return

    setStarting(true)
    setTrainingStatus('loading')
    setChartData([])
    setFailureDiagnosis(null)

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
        : await startTraining(config, { applyRecommendedConfig: shouldApplyRecommendedConfig })

      setIsTraining(true)
      addTrainingRecord(result)
      setCurrentTaskId(result.id)
      setResumeOptions([])
      setSelectedResumeTaskId(null)
      setSelectedResumeCheckpointName(null)
      notify.success('训练任务已提交')
    } catch (error: any) {
      setTrainingStatus('idle')
      notify.error(getErrorMessage(error, '启动训练失败'))
    } finally {
      setStarting(false)
    }
  }

  const handleStop = async () => {
    try {
      await stopTraining()
      setTrainingStatus('stopping')
      notify.info('已发送停止请求，等待当前步骤安全退出')
    } catch (error) {
      notify.error(getErrorMessage(error, '停止训练失败'))
    }
  }

  const estimateModelSize = (modelId?: string) => {
    const label = (modelId || '').toUpperCase()
    if (label.includes('14B') || label.includes('13B')) return '13B'
    if (label.includes('8B') || label.includes('7B')) return '7B'
    if (label.includes('3B')) return '3B'
    if (label.includes('1.5B') || label.includes('1B')) return '1.5B'
    return '7B'
  }

  const estimateRequiredVram = (values: any) => {
    const size = estimateModelSize(values.modelId)
    const batchSize = Number(values.batchSize || 1)
    const seqLength = Number(values.maxSeqLength || 512)
    let base = size === '13B' ? 8 : size === '3B' ? 3 : size === '1.5B' ? 2 : 6
    if ((values.method || 'qlora') === 'qlora') base *= 0.7
    if (seqLength > 1024) base += 1
    if (batchSize > 1) base += 0.8 * (batchSize - 1)
    return Number(base.toFixed(1))
  }

  const handlePreflightCheck = async () => {
    const values = form.getFieldsValue()
    if (!values.modelId || !values.datasetId) {
      notify.warning('请先选择模型和数据集，再执行训练前预检')
      return
    }

    setPreflightChecking(true)
    try {
      const result = await checkTrainingResources({
        method: values.method || 'qlora',
        modelSize: estimateModelSize(values.modelId),
        requiredVram: estimateRequiredVram(values),
      })
      setPreflightResult(result)

      const mappedValues: Record<string, any> = {}
      if (result.recommended_config?.batch_size !== undefined) {
        mappedValues.batchSize = result.recommended_config.batch_size
      }
      if (result.recommended_config?.max_seq_length !== undefined) {
        mappedValues.maxSeqLength = result.recommended_config.max_seq_length
      }
      if (result.recommended_config?.method !== undefined) {
        mappedValues.method = result.recommended_config.method
      }
      if (Object.keys(mappedValues).length > 0) {
        form.setFieldsValue(mappedValues)
      }

      setPreflightFingerprint(getCurrentPreflightFingerprint())

      notify.emit(result.passed ? 'success' : 'warning', result.passed ? '训练前预检通过' : '训练前预检发现风险，已返回建议配置')
    } catch (error: any) {
      notify.error(getErrorMessage(error, '训练前预检失败'))
    } finally {
      setPreflightChecking(false)
    }
  }

  const handleApplyConservativePreset = () => {
    form.setFieldsValue({
      method: 'qlora',
      batchSize: 1,
      maxSeqLength: 512,
      rank: 8,
      alpha: 16,
    })
    setGradientAccumulation(16)
    setQuantizationBit(4)
    setMemoryPreset('6gb')
    notify.info('已应用保守训练建议，请重新执行训练前预检。')
  }

  const selectedResumeOption = resumeOptions.find((option) => option.taskId === selectedResumeTaskId) || null
  const selectedResumeCheckpoint = selectedResumeOption?.checkpoints.find((checkpoint) => checkpoint.name === selectedResumeCheckpointName) || null
  const resumeConfigDiff = buildResumeConfigDiff(
    {
      ...form.getFieldsValue(),
      gradientAccumulation,
      quantization: quantizationBit,
    },
    selectedResumeOption?.config,
  )

  const handleResumeFromSelectedCheckpoint = async () => {
    if (!selectedResumeOption || !selectedResumeCheckpoint || resumeStarting || isTraining) return

    setResumeStarting(true)
    try {
      const result = await resumeTraining(selectedResumeOption.taskId, selectedResumeCheckpoint.name)
      setIsTraining(true)
      setTrainingStatus('loading')
      addTrainingRecord(result)
      setCurrentTaskId(result.id)
      notify.success(`已从 ${selectedResumeCheckpoint.name} 恢复训练`)
    } catch (error: any) {
      notify.error(getErrorMessage(error, '从最近检查点恢复失败'))
    } finally {
      setResumeStarting(false)
    }
  }

  const handleUseActiveModel = () => {
    if (!derived.activeModelId) {
      notify.warning('当前运行上下文里还没有可复用的活跃模型')
      return
    }

    form.setFieldsValue({ modelId: derived.activeModelId })
    notify.success('已将当前活跃模型带入训练配置')
  }

  const handlePromoteTrainingModel = () => {
    const selectedModelId = form.getFieldValue('modelId')
    if (!selectedModelId) {
      notify.warning('请先在训练配置里选择一个基座模型')
      return
    }

    syncInferenceSelection({
      backend: derived.activeBackend === 'ollama' ? 'ollama' : 'huggingface',
      modelId: selectedModelId,
    })
    notify.success('当前训练基座模型已同步到平台活跃推理上下文')
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
                <div style={{ marginBottom: 'var(--space-6)' }}>
                  <RuntimeContextPanel page="training" />
                </div>
                <div style={{ marginBottom: 'var(--space-6)' }}>
                  <InsightPanel
                    embedded
                    title="运行桥接"
                    status={{
                      type: 'info',
                      text: '共享运行链',
                    }}
                    summary="训练页现在可以直接复用平台当前活跃模型，也可以把当前训练基座模型同步为后续推理和会话默认上下文。"
                    actions={(
                      <Space wrap>
                        <Button onClick={handleUseActiveModel} disabled={!derived.activeModelId}>
                          使用当前活跃模型
                        </Button>
                        <Button type="primary" onClick={handlePromoteTrainingModel}>
                          设为活跃推理模型
                        </Button>
                      </Space>
                    )}
                  />
                </div>
                {preflightResult && (
                  <div style={{ marginBottom: 'var(--space-6)' }}>
                      <InsightPanel
                        embedded
                        title="训练前预检"
                        status={{
                          type: preflightResult.passed ? 'success' : 'warning',
                          text: preflightResult.passed ? '可启动' : '存在风险',
                        }}
                        summary={`设备：${preflightResult.device_name || '未知'}。当前配置会被映射到实际资源预算，便于在启动前先发现显存和方法选择风险。`}
                        metrics={[
                          {
                            label: '可用显存',
                            value: `${preflightResult.available_vram?.toFixed?.(1) ?? preflightResult.available_vram} GB`,
                          },
                          {
                            label: '预计需求',
                            value: `${preflightResult.required_vram?.toFixed?.(1) ?? preflightResult.required_vram} GB`,
                          },
                        ]}
                        sections={[
                          {
                            title: '风险提示',
                            items: preflightResult.warnings || [],
                            tone: 'warning',
                          },
                          {
                            title: '建议配置',
                            items: preflightResult.suggestions || [],
                          },
                        ]}
                      />
                    </div>
                  )}
                {trainingStatus === 'failed' && failureDiagnosis && (
                  <div style={{ marginBottom: 'var(--space-6)' }}>
                    <InsightPanel
                      embedded
                      title="失败诊断与恢复"
                      status={{
                        type: 'error',
                        text: failureDiagnosis.title,
                      }}
                      summary={failureDiagnosis.summary}
                      sections={[
                        {
                          title: '建议处理',
                          items: failureDiagnosis.suggestions,
                        },
                        {
                          title: '恢复入口',
                          items: selectedResumeOption && selectedResumeCheckpoint
                            ? [
                              `${selectedResumeOption.reason || '检测到可恢复检查点'}：${selectedResumeCheckpoint.name}（step ${selectedResumeCheckpoint.step}）`,
                              `模型：${selectedResumeOption.modelName}，数据集：${selectedResumeOption.datasetName}`,
                            ]
                            : ['当前没有检测到可直接恢复的检查点，可前往训练历史页查看更多记录。'],
                        },
                        {
                          title: '恢复前配置差异',
                          items: selectedResumeOption
                            ? (resumeConfigDiff.length > 0
                              ? resumeConfigDiff
                              : ['当前配置与所选恢复任务配置一致，可直接恢复。'])
                            : ['请选择可恢复任务后查看配置差异。'],
                        },
                      ]}
                      actions={(
                        <Space wrap>
                          <Button onClick={handleApplyConservativePreset}>应用保守参数</Button>
                          <Button onClick={handlePreflightCheck} loading={preflightChecking}>重新预检</Button>
                          <Select
                            size="small"
                            style={{ minWidth: 240 }}
                            placeholder="选择可恢复任务"
                            value={selectedResumeTaskId || undefined}
                            onChange={(taskId) => setSelectedResumeTaskId(taskId)}
                            options={resumeOptions.map((option) => ({
                              value: option.taskId,
                              label: `${option.modelName} · ${option.datasetName} · ${option.status === 'failed' ? '失败' : '已停止'}`,
                            }))}
                            loading={resumeLoading}
                            disabled={!resumeOptions.length || resumeStarting}
                          />
                          <Select
                            size="small"
                            style={{ minWidth: 220 }}
                            placeholder="选择检查点"
                            value={selectedResumeCheckpointName || undefined}
                            onChange={(checkpointName) => setSelectedResumeCheckpointName(checkpointName)}
                            options={(selectedResumeOption?.checkpoints || []).map((checkpoint) => ({
                              value: checkpoint.name,
                              label: `${checkpoint.name} · step ${checkpoint.step}`,
                            }))}
                            disabled={!selectedResumeOption || resumeStarting}
                          />
                          <Button
                            type="primary"
                            onClick={handleResumeFromSelectedCheckpoint}
                            loading={resumeStarting || resumeLoading}
                            disabled={!selectedResumeOption || !selectedResumeCheckpoint}
                          >
                            恢复训练
                          </Button>
                        </Space>
                      )}
                    />
                  </div>
                )}
                {failureAnalytics && (
                  <div style={{ marginBottom: 'var(--space-6)' }}>
                    <InsightPanel
                      embedded
                      title="失败画像（最近训练）"
                      status={{
                        type: failureAnalytics.failedRuns > 0 ? 'warning' : 'success',
                        text: failureAnalytics.failedRuns > 0 ? '存在失败样本' : '暂无失败样本',
                      }}
                      summary={`最近共 ${failureAnalytics.totalRuns} 次训练，失败 ${failureAnalytics.failedRuns} 次，停止 ${failureAnalytics.stoppedRuns} 次，失败率 ${failureAnalytics.failureRate}%。`}
                      metrics={[
                        { label: '高显存风险样本', value: failureAnalytics.suspectedVramPressureCount },
                        { label: '长序列失败样本', value: failureAnalytics.longContextFailureCount },
                        { label: '未量化失败样本', value: failureAnalytics.unquantizedFailureCount },
                        {
                          label: '7天失败率',
                          value: `${failureAnalytics.failureRate7d}%`,
                          hint: `${failureAnalytics.failedRuns7d}/${failureAnalytics.totalRuns7d || 0}`,
                        },
                        {
                          label: '14天失败率',
                          value: `${failureAnalytics.failureRate14d}%`,
                          hint: `${failureAnalytics.failedRuns14d}/${failureAnalytics.totalRuns14d || 0}`,
                        },
                      ]}
                      sections={[
                        {
                          title: '高风险维度',
                          items: [
                            `失败模型 Top: ${failureAnalytics.topFailedModels.join(' / ') || '暂无'}`,
                            `失败数据集 Top: ${failureAnalytics.topFailedDatasets.join(' / ') || '暂无'}`,
                            `失败方法 Top: ${failureAnalytics.topFailedMethods.join(' / ') || '暂无'}`,
                          ],
                          tone: 'warning',
                        },
                        {
                          title: '最近失败样本',
                          items: failureAnalytics.recentFailures.length > 0
                            ? failureAnalytics.recentFailures.map(
                              (item) =>
                                `${new Date(item.startTime).toLocaleString('zh-CN')}｜${item.modelName}｜${item.datasetName}｜${item.method}`,
                            )
                            : ['暂无失败样本'],
                        },
                      ]}
                    />
                  </div>
                )}
                <ConfigForm
                  form={form}
                  onFinish={handleStart}
                  onPreflightCheck={handlePreflightCheck}
                  isTraining={isTraining || backendTraining}
                  starting={starting}
                  preflightChecking={preflightChecking}
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
