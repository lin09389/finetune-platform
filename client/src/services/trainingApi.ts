import {
  API_BASE_URL,
  apiClient,
  getTrainingCheckpoints as getRawTrainingCheckpoints,
  getTrainingHistory as getRawTrainingHistory,
  resumeTraining as resumeRawTraining,
  startSwiftTraining as startRawSwiftTraining,
  startTraining as startRawTraining,
  stopTraining,
  subscribeTrainingProgress as subscribeRawTrainingProgress,
} from './api'

const normalizeTrainingConfig = (config: any = {}) => ({
  modelId: config.modelId ?? config.model_id ?? '',
  datasetId: config.datasetId ?? config.dataset_id ?? '',
  method: config.method ?? 'qlora',
  rank: config.rank ?? 8,
  alpha: config.alpha ?? 16,
  learningRate: config.learningRate ?? config.learning_rate ?? 5e-5,
  epochs: config.epochs ?? 3,
  batchSize: config.batchSize ?? config.batch_size ?? 1,
  gradientAccumulation: config.gradientAccumulation ?? config.gradient_accumulation ?? 16,
  maxSeqLength: config.maxSeqLength ?? config.max_seq_length ?? 512,
  warmupSteps: config.warmupSteps ?? config.warmup_steps ?? 100,
  saveSteps: config.saveSteps ?? config.save_steps ?? 500,
  loggingSteps: config.loggingSteps ?? config.logging_steps ?? 10,
  useDora: config.useDora ?? config.use_dora,
  lrScheduler: config.lrScheduler ?? config.lr_scheduler,
  warmupRatio: config.warmupRatio ?? config.warmup_ratio,
  weightDecay: config.weightDecay ?? config.weight_decay,
  labelSmoothing: config.labelSmoothing ?? config.label_smoothing,
  gradientCheckpointing: config.gradientCheckpointing ?? config.gradient_checkpointing,
  bf16: config.bf16,
  evalSteps: config.evalSteps ?? config.eval_steps,
  loadBestModel: config.loadBestModel ?? config.load_best_model,
  targetModules: config.targetModules ?? config.target_modules,
  loraDropout: config.loraDropout ?? config.lora_dropout,
  maxGradNorm: config.maxGradNorm ?? config.max_grad_norm,
  precisionPreset: config.precisionPreset ?? config.precision_preset,
  memoryPreset: config.memoryPreset ?? config.memory_preset,
  useFlashAttn: config.useFlashAttn ?? config.use_flash_attn,
  deepspeedStage: config.deepspeedStage ?? config.deepspeed_stage,
  offloadOptimizer: config.offloadOptimizer ?? config.offload_optimizer,
  quantization: config.quantization ?? 4,
  resume_from_checkpoint: config.resume_from_checkpoint,
})

export const normalizeTrainingRecord = (record: any) => ({
  id: record.id,
  modelName: record.modelName ?? record.model_name ?? '',
  datasetName: record.datasetName ?? record.dataset_name ?? '',
  method: record.method,
  status: record.status,
  startTime: record.startTime ?? record.start_time,
  endTime: record.endTime ?? record.end_time,
  config: normalizeTrainingConfig(record.config),
  outputPath: record.outputPath ?? record.output_path ?? '',
  checkpointPath: record.checkpointPath ?? record.checkpoint_path,
})

export const normalizeTrainingProgress = (progress: any) => ({
  epoch: progress.epoch ?? 0,
  step: progress.step ?? 0,
  totalSteps: progress.totalSteps ?? progress.total_steps ?? 0,
  loss: progress.loss ?? 0,
  lr: progress.lr ?? 0,
  vramUsed: progress.vramUsed ?? progress.vram_used ?? 0,
  elapsedTime: progress.elapsedTime ?? progress.elapsed_time ?? 0,
  eta: progress.eta ?? 0,
  status: progress.status,
  message: progress.message,
})

export const startTraining = async (config: any) => normalizeTrainingRecord(await startRawTraining(config))

export const startSwiftTraining = async (config: any) => normalizeTrainingRecord(await startRawSwiftTraining(config))

export const getTrainingHistory = async () => {
  const records = await getRawTrainingHistory()
  return Array.isArray(records) ? records.map(normalizeTrainingRecord) : []
}

export const getTrainingCheckpoints = async (trainingId: string) => getRawTrainingCheckpoints(trainingId)

export const resumeTraining = async (trainingId: string, checkpoint: string) =>
  normalizeTrainingRecord(await resumeRawTraining(trainingId, checkpoint))

export const subscribeTrainingProgress = (
  onProgress: (progress: any) => void,
  onError?: (error: Error) => void,
) => subscribeRawTrainingProgress((progress) => onProgress(normalizeTrainingProgress(progress)), onError)

export const getTrainingStatus = async () => {
  const response = await apiClient.get('/training/status')
  const data = response.data
  return {
    ...data,
    record: data.record ? normalizeTrainingRecord(data.record) : null,
    progress: data.progress ? normalizeTrainingProgress(data.progress) : null,
  }
}

export { API_BASE_URL, stopTraining }
