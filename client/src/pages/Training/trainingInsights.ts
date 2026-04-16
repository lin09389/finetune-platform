import type { TrainingRecord } from '../../types'

export interface TrainingFailureDiagnosis {
  category: 'oom' | 'dataset' | 'model' | 'checkpoint' | 'runtime' | 'unknown'
  title: string
  summary: string
  suggestions: string[]
}

export interface TrainingFailureSnapshot {
  id: string
  modelName: string
  datasetName: string
  method: string
  startTime: string
}

export interface TrainingFailureAnalytics {
  totalRuns: number
  failedRuns: number
  stoppedRuns: number
  completedRuns: number
  failureRate: number
  failureRate7d: number
  failureRate14d: number
  failedRuns7d: number
  failedRuns14d: number
  totalRuns7d: number
  totalRuns14d: number
  suspectedVramPressureCount: number
  longContextFailureCount: number
  unquantizedFailureCount: number
  topFailedModels: string[]
  topFailedDatasets: string[]
  topFailedMethods: string[]
  recentFailures: TrainingFailureSnapshot[]
}

const containsAny = (text: string, keywords: string[]) =>
  keywords.some((keyword) => text.includes(keyword))

export const diagnoseTrainingFailure = (message?: string): TrainingFailureDiagnosis => {
  const raw = (message || '').trim()
  const normalized = raw.toLowerCase()
  const detail = raw || '未返回详细错误信息'

  if (containsAny(normalized, ['outofmemory', 'out of memory', 'cuda oom', '显存', 'oom'])) {
    return {
      category: 'oom',
      title: '显存不足',
      summary: `训练过程中触发显存不足：${detail}`,
      suggestions: [
        '将 batch size 调整为 1，并提高梯度累积步数（例如 16）。',
        '将最大序列长度降到 512 或更低，再执行训练前预检。',
        '优先使用 QLoRA + 4bit 量化，避免在低显存环境启用高吞吐预设。',
      ],
    }
  }

  if (containsAny(normalized, ['dataset', 'json', '样本', '格式', 'unsupported dataset'])) {
    return {
      category: 'dataset',
      title: '数据集格式或内容异常',
      summary: `训练数据在解析阶段出现问题：${detail}`,
      suggestions: [
        '检查数据集是否为 JSON/JSONL 且至少包含一条有效样本。',
        '确认样本字段符合支持格式（messages/text/content/instruction+output）。',
        '重新上传修复后的数据集，再执行预检并启动训练。',
      ],
    }
  }

  if (containsAny(normalized, ['model not found', 'tokenizer', 'config.json', '模型不存在'])) {
    return {
      category: 'model',
      title: '模型资源不可用',
      summary: `模型或分词器加载失败：${detail}`,
      suggestions: [
        '确认本地模型目录完整，包含必要配置文件。',
        '尝试在模型管理页重新下载或重新导入模型。',
        '先用其它可用模型完成一次小规模训练验证链路。',
      ],
    }
  }

  if (containsAny(normalized, ['checkpoint', 'resume', '检查点'])) {
    return {
      category: 'checkpoint',
      title: '检查点恢复失败',
      summary: `恢复训练时检查点不可用或不兼容：${detail}`,
      suggestions: [
        '确认检查点目录存在且与当前模型、数据集匹配。',
        '优先选择最近一次成功保存的 checkpoint 继续训练。',
        '若检查点损坏，建议基于相同配置重新启动训练任务。',
      ],
    }
  }

  if (containsAny(normalized, ['cuda', 'nccl', 'runtime', 'device-side assert'])) {
    return {
      category: 'runtime',
      title: '训练运行时异常',
      summary: `底层运行时或驱动链路出现异常：${detail}`,
      suggestions: [
        '先停止训练并重启后端，确认 GPU 未被其他进程占满。',
        '检查 CUDA / 驱动环境与当前依赖版本兼容性。',
        '降低并发负载后再做一次训练前预检。',
      ],
    }
  }

  return {
    category: 'unknown',
    title: '训练失败（需人工排查）',
    summary: `后端返回：${detail}`,
    suggestions: [
      '先执行训练前预检，确认配置与设备资源匹配。',
      '查看 outputs 下对应任务日志，定位首个异常栈。',
      '优先使用保守配置（QLoRA + 小 batch + 短序列）验证链路。',
    ],
  }
}

export const buildTrainingPreflightFingerprint = (
  values: Record<string, any>,
  runtimeConfig: {
    gradientAccumulation: number
    precisionPreset: 'max' | 'balanced' | 'fast'
    memoryPreset: 'auto' | '6gb' | '8gb' | '12gb'
    useFlashAttn: boolean
    quantizationBit: 0 | 4 | 8
    useSwift: boolean
  },
) =>
  JSON.stringify({
    modelId: values.modelId || '',
    datasetId: values.datasetId || '',
    method: values.method || 'qlora',
    rank: values.rank || 8,
    alpha: values.alpha || 16,
    learningRate: values.learningRate || 5e-5,
    epochs: values.epochs || 3,
    batchSize: values.batchSize || 1,
    maxSeqLength: values.maxSeqLength || 512,
    gradientAccumulation: runtimeConfig.gradientAccumulation,
    precisionPreset: runtimeConfig.precisionPreset,
    memoryPreset: runtimeConfig.memoryPreset,
    useFlashAttn: runtimeConfig.useFlashAttn,
    quantization: runtimeConfig.quantizationBit,
  useSwift: runtimeConfig.useSwift,
  })

const topKeys = (values: string[], topN: number = 3) =>
  Object.entries(
    values.reduce<Record<string, number>>((acc, key) => {
      if (!key) return acc
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {}),
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([key]) => key)

export const buildTrainingFailureAnalytics = (
  records: TrainingRecord[],
): TrainingFailureAnalytics => {
  const now = Date.now()
  const withinDays = (isoTime: string, days: number) => {
    const time = new Date(isoTime).getTime()
    if (Number.isNaN(time)) return false
    const windowMs = days * 24 * 60 * 60 * 1000
    return now - time <= windowMs
  }

  const totalRuns = records.length
  const failedRuns = records.filter((record) => record.status === 'failed')
  const stoppedRuns = records.filter((record) => record.status === 'stopped')
  const completedRuns = records.filter((record) => record.status === 'completed')
  const runs7d = records.filter((record) => withinDays(record.startTime, 7))
  const runs14d = records.filter((record) => withinDays(record.startTime, 14))
  const failedRuns7d = runs7d.filter((record) => record.status === 'failed').length
  const failedRuns14d = runs14d.filter((record) => record.status === 'failed').length

  const suspectedVramPressureCount = failedRuns.filter((record) => {
    const config = record.config || {}
    const batchSize = Number(config.batchSize || 1)
    const maxSeqLength = Number(config.maxSeqLength || 512)
    const quantization = Number(config.quantization ?? 4)
    return batchSize >= 2 || maxSeqLength > 1024 || quantization === 0
  }).length

  const longContextFailureCount = failedRuns.filter((record) => {
    const config = record.config || {}
    return Number(config.maxSeqLength || 512) > 1024
  }).length

  const unquantizedFailureCount = failedRuns.filter((record) => {
    const config = record.config || {}
    return Number(config.quantization ?? 4) === 0
  }).length

  return {
    totalRuns,
    failedRuns: failedRuns.length,
    stoppedRuns: stoppedRuns.length,
    completedRuns: completedRuns.length,
    failureRate: totalRuns > 0 ? Number(((failedRuns.length / totalRuns) * 100).toFixed(1)) : 0,
    failureRate7d: runs7d.length > 0 ? Number(((failedRuns7d / runs7d.length) * 100).toFixed(1)) : 0,
    failureRate14d: runs14d.length > 0 ? Number(((failedRuns14d / runs14d.length) * 100).toFixed(1)) : 0,
    failedRuns7d,
    failedRuns14d,
    totalRuns7d: runs7d.length,
    totalRuns14d: runs14d.length,
    suspectedVramPressureCount,
    longContextFailureCount,
    unquantizedFailureCount,
    topFailedModels: topKeys(failedRuns.map((record) => record.modelName)),
    topFailedDatasets: topKeys(failedRuns.map((record) => record.datasetName)),
    topFailedMethods: topKeys(failedRuns.map((record) => record.method)),
    recentFailures: failedRuns
      .slice()
      .sort((a, b) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime())
      .slice(0, 5)
      .map((record) => ({
        id: record.id,
        modelName: record.modelName,
        datasetName: record.datasetName,
        method: record.method,
        startTime: record.startTime,
      })),
  }
}

export const buildResumeConfigDiff = (
  currentValues: Record<string, any>,
  targetConfig: Record<string, any> | undefined,
) => {
  if (!targetConfig) return []

  const fields: Array<{ label: string; current: any; target: any }> = [
    { label: '微调方法', current: currentValues.method || 'qlora', target: targetConfig.method || 'qlora' },
    { label: 'Batch Size', current: currentValues.batchSize || 1, target: targetConfig.batchSize || 1 },
    { label: '最大序列长度', current: currentValues.maxSeqLength || 512, target: targetConfig.maxSeqLength || 512 },
    { label: '梯度累积', current: currentValues.gradientAccumulation || 16, target: targetConfig.gradientAccumulation || 16 },
    { label: '量化位数', current: currentValues.quantization ?? 4, target: targetConfig.quantization ?? 4 },
  ]

  return fields
    .filter((field) => String(field.current) !== String(field.target))
    .map((field) => `${field.label}: 当前 ${field.current} -> 恢复配置 ${field.target}`)
}
