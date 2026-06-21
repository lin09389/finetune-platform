import {
  API_BASE_URL,
  apiClient,
  checkTrainingResources as checkRawTrainingResources,
  checkTrainingPreflight as checkRawTrainingPreflight,
  getTrainingCheckpoints as getRawTrainingCheckpoints,
  getTrainingHistory as getRawTrainingHistory,
  getTrainingTaskMetricsV2 as getRawTrainingTaskMetricsV2,
  resumeTraining as resumeRawTraining,
  startSwiftTraining as startRawSwiftTraining,
  startTraining as startRawTraining,
  stopTraining,
  subscribeTrainingEventsV2 as subscribeRawTrainingEventsV2,
  subscribeTrainingLogs as subscribeRawTrainingLogs,
  subscribeTrainingProgress as subscribeRawTrainingProgress,
  type TrainingEventV2,
} from './api';

const normalizeTrainingConfig = (config: any = {}) => ({
  modelId: config.modelId ?? config.model_id ?? '',
  model_id: config.model_id ?? config.modelId ?? '',
  datasetId: config.datasetId ?? config.dataset_id ?? '',
  dataset_id: config.dataset_id ?? config.datasetId ?? '',
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
  taskGoal: config.taskGoal ?? config.task_goal ?? 'qa_assistant',
  task_goal: config.task_goal ?? config.taskGoal ?? 'qa_assistant',
  testDatasetId: config.testDatasetId ?? config.test_dataset_id ?? '',
  test_dataset_id: config.test_dataset_id ?? config.testDatasetId ?? '',
  validationDatasetId: config.validationDatasetId ?? config.validation_dataset_id ?? '',
  validation_dataset_id: config.validation_dataset_id ?? config.validationDatasetId ?? '',
  resume_from_checkpoint: config.resume_from_checkpoint,
  resume_from_adapter: config.resume_from_adapter,
});

export const normalizeTrainingRecord = (record: any) => {
  const config = normalizeTrainingConfig(record.config);
  const outputPath = record.outputPath ?? record.output_path ?? '';
  const checkpointPath = record.checkpointPath ?? record.checkpoint_path;

  return {
    id: record.id,
    modelName: record.modelName ?? record.model_name ?? '',
    datasetName: record.datasetName ?? record.dataset_name ?? '',
    baseModelId:
      record.baseModelId ??
      record.base_model_id ??
      config.modelId ??
      record.modelName ??
      record.model_name ??
      '',
    datasetId:
      record.datasetId ??
      record.dataset_id ??
      config.testDatasetId ??
      config.validationDatasetId ??
      config.datasetId ??
      record.datasetName ??
      record.dataset_name ??
      '',
    taskGoal:
      record.taskGoal ??
      record.task_goal ??
      config.taskGoal ??
      config.task_goal ??
      'qa_assistant',
    adapterPath: record.adapterPath ?? record.adapter_path ?? checkpointPath ?? undefined,
    releaseId: record.releaseId ?? record.release_id,
    artifactManifestPath: record.artifactManifestPath ?? record.artifact_manifest_path,
    promotionState: record.promotionState ?? record.promotion_state,
    evaluationRunId: record.evaluationRunId ?? record.evaluation_run_id,
    deploymentPackageId: record.deploymentPackageId ?? record.deployment_package_id,
    configHash: record.configHash ?? record.config_hash,
    datasetFingerprint: record.datasetFingerprint ?? record.dataset_fingerprint,
    evaluationSnapshotPath:
      record.evaluationSnapshotPath ?? record.evaluation_snapshot_path,
    evaluationSnapshotHash:
      record.evaluationSnapshotHash ?? record.evaluation_snapshot_hash,
    artifactDigest: record.artifactDigest ?? record.artifact_digest,
    method: record.method,
    status: record.status,
    startTime: record.startTime ?? record.start_time,
    endTime: record.endTime ?? record.end_time,
    config,
    outputPath,
    checkpointPath,
    finalLoss: record.finalLoss ?? record.final_loss,
    finalLr: record.finalLr ?? record.final_lr,
    elapsedTime: record.elapsedTime ?? record.elapsed_time,
    totalSteps: record.totalSteps ?? record.total_steps,
  };
};

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
  queuePosition: progress.queuePosition ?? progress.queue_position,
  estimatedWaitSeconds: progress.estimatedWaitSeconds ?? progress.estimated_wait_seconds,
  errorCode: progress.errorCode ?? progress.error_code,
  errorCategory: progress.errorCategory ?? progress.error_category,
  actionableSuggestions: progress.actionableSuggestions ?? progress.actionable_suggestions,
});

export const startTraining = async (config: any, options?: { applyRecommendedConfig?: boolean }) =>
  normalizeTrainingRecord(await startRawTraining(config, options));

export const startSwiftTraining = async (config: any) =>
  normalizeTrainingRecord(await startRawSwiftTraining(config));

export const getTrainingHistory = async () => {
  const records = await getRawTrainingHistory();
  return Array.isArray(records) ? records.map(normalizeTrainingRecord) : [];
};

export const getTrainingCheckpoints = async (trainingId: string) =>
  getRawTrainingCheckpoints(trainingId);

export const resumeTraining = async (trainingId: string, checkpoint: string) =>
  normalizeTrainingRecord(await resumeRawTraining(trainingId, checkpoint));

export const subscribeTrainingProgress = (
  onProgress: (progress: any) => void,
  onError?: (error: Error) => void,
) =>
  subscribeRawTrainingProgress(
    (progress) => onProgress(normalizeTrainingProgress(progress)),
    onError,
  );

export const subscribeTrainingLogs = (
  taskId: string,
  onLine: (line: string) => void,
  onError?: (error: Error) => void,
  history?: number,
) => subscribeRawTrainingLogs(taskId, onLine, onError, history);

export const subscribeTrainingEventsV2 = (
  options: { taskId?: string; lastEventId?: string; heartbeatTimeoutMs?: number },
  onEvent: (event: TrainingEventV2) => void,
  onError?: (error: Error) => void,
) => subscribeRawTrainingEventsV2(options, onEvent, onError);

export const getTrainingTaskMetricsV2 = async (
  taskId: string,
  cursor: number = 0,
  limit: number = 200,
) => getRawTrainingTaskMetricsV2(taskId, cursor, limit);

export const getTrainingStatus = async () => {
  const response = await apiClient.get('/training/status');
  const data = response.data;
  return {
    ...data,
    record: data.record ? normalizeTrainingRecord(data.record) : null,
    progress: data.progress ? normalizeTrainingProgress(data.progress) : null,
  };
};

export const checkTrainingResources = async (params: {
  method?: string;
  modelSize?: string;
  requiredVram?: number;
}) => checkRawTrainingResources(params);

export const checkTrainingPreflight = async (config: any) => checkRawTrainingPreflight(config);

export {
  cleanupTrainingCheckpoints,
  compareTrainingCheckpoints,
} from './api';

export { API_BASE_URL, stopTraining };
