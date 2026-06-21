import { Button, Form } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DisconnectOutlined,
  FileSearchOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AnimatedLayout from '../../components/shared/AnimatedLayout';
import { useRuntimeContext } from '../../runtime/RuntimeContext';
import { getDatasetList, getModelList, type TrainingEventV2 } from '../../services/api';
import {
  checkTrainingResources,
  checkTrainingPreflight,
  getTrainingStatus,
  getTrainingTaskMetricsV2,
  resumeTraining,
  startSwiftTraining,
  startTraining,
  stopTraining,
  subscribeTrainingProgress,
} from '../../services/trainingApi';
import { useAppStore } from '../../store/appStore';
import type {
  TrainingProgress as TrainingProgressType,
  TrainingRecord as TrainingRecordType,
} from '../../types';
import { notify } from '../../utils/notify';
import { appModal } from '../../utils/modal';
import HyperparameterPanel from './components/HyperparameterPanel';
import TrainingDashboard from './components/TrainingDashboard';
import { buildTrainingPreflightFingerprint } from './trainingInsights';
import { useTrainingEventStreamV2 } from './useTrainingEventStreamV2';
import layoutStyles from './Training.module.css';

interface ChartDataPoint {
  step: number;
  loss: number;
  lr: number;
}

interface PreflightResult {
  passed: boolean;
  status?: 'ready' | 'warning' | 'blocked';
  summary?: string;
  checks?: Array<{
    key: string;
    label: string;
    status: 'passed' | 'warning' | 'blocked';
    message: string;
    detail?: string;
  }>;
  blockers?: string[];
  available_vram: number | null;
  required_vram: number | null;
  suggestions: string[];
  warnings: string[];
  recommended_config: Record<string, any>;
  device_name?: string;
}

const getErrorMessage = (error: any, fallback: string) =>
  error?.response?.data?.detail?.message ||
  error?.response?.data?.detail ||
  error?.message ||
  fallback;

const TrainingPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const {
    models,
    datasets,
    backendStatus,
    isTraining,
    setIsTraining,
    addTrainingRecord,
    setModels,
    setDatasets,
  } = useAppStore();
  const { actions } = useRuntimeContext();
  const { setTrainingSelection } = actions;
  const [form] = Form.useForm();
  const searchParamString = searchParams.toString();
  const [progress, setProgress] = useState<TrainingProgressType | null>(null);
  const [starting, setStarting] = useState(false);
  const [trainingStatus, setTrainingStatus] = useState<
    'idle' | 'queued' | 'loading' | 'training' | 'saving' | 'stopping' | 'completed' | 'failed'
  >('idle');
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const [lastV2EventAt, setLastV2EventAt] = useState<number>(0);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [currentTrainingRecord, setCurrentTrainingRecord] = useState<TrainingRecordType | null>(null);
  const [backendTraining, setBackendTraining] = useState(false);
  const [phaseDurations, setPhaseDurations] = useState<Record<string, number>>({});
  const [currentPhase, setCurrentPhase] = useState<string>('');
  const [retryCount, setRetryCount] = useState(0);
  const [preflightResult, setPreflightResult] = useState<PreflightResult | null>(null);
  const [preflightChecking, setPreflightChecking] = useState(false);
  const [preflightFingerprint, setPreflightFingerprint] = useState<string | null>(null);

  const [useSwift, setUseSwift] = useState(false);
  const swiftAvailable = false;
  const [precisionPreset, setPrecisionPreset] = useState<'max' | 'balanced' | 'fast'>('balanced');
  const [memoryPreset, setMemoryPreset] = useState<'auto' | '6gb' | '8gb' | '12gb'>('auto');
  const useFlashAttn = false;
  const [quantizationBit, setQuantizationBit] = useState<4 | 8 | 0>(4);
  const [configCollapsed, setConfigCollapsed] = useState(false);
  const [gradientAccumulation, setGradientAccumulation] = useState<number>(16);
  const watchedModelId = Form.useWatch('modelId', form);
  const watchedDatasetId = Form.useWatch('datasetId', form);
  const watchedMethod = Form.useWatch('method', form);
  const watchedBatchSize = Form.useWatch('batchSize', form);
  const watchedMaxSeqLength = Form.useWatch('maxSeqLength', form);

  useEffect(() => {
    const params = new URLSearchParams(searchParamString);
    const nextValues: Record<string, string> = {};
    const modelId = params.get('model_id') || params.get('modelId') || params.get('base_model');
    const datasetId = params.get('dataset_id') || params.get('datasetId') || params.get('test_dataset_id');
    const taskGoal = params.get('task_goal') || params.get('taskGoal') || params.get('scenario');

    if (modelId) nextValues.modelId = modelId;
    if (datasetId) nextValues.datasetId = datasetId;
    if (taskGoal === 'qa_assistant' || taskGoal === 'structured_extraction') {
      nextValues.taskGoal = taskGoal;
    }

    if (Object.keys(nextValues).length > 0) {
      form.setFieldsValue(nextValues);
    }
  }, [form, searchParamString]);

  useEffect(() => {
    setTrainingSelection({
      modelId: watchedModelId,
      datasetId: watchedDatasetId,
    });
  }, [setTrainingSelection, watchedDatasetId, watchedModelId]);

  const syncTrainingCatalog = useCallback(async () => {
    if (backendStatus !== 'connected') return;

    try {
      const [modelList, datasetList] = await Promise.all([getModelList(), getDatasetList()]);
      setModels(Array.isArray(modelList) ? modelList : []);
      setDatasets(Array.isArray(datasetList) ? datasetList : []);
    } catch (error) {
      console.error('Failed to sync training catalog:', error);
    }
  }, [backendStatus, setDatasets, setModels]);

  const getCurrentPreflightFingerprint = useCallback(() => {
    const values = form.getFieldsValue();
    return buildTrainingPreflightFingerprint(values, {
      gradientAccumulation,
      precisionPreset,
      memoryPreset,
      useFlashAttn,
      quantizationBit,
      useSwift,
    });
  }, [
    form,
    gradientAccumulation,
    memoryPreset,
    precisionPreset,
    quantizationBit,
    useFlashAttn,
    useSwift,
  ]);

  const applyIncomingProgress = useCallback(
    (nextProgress: any, source: 'v1' | 'v2') => {
      setProgress(nextProgress);
      if (nextProgress.loss !== undefined && nextProgress.step !== undefined) {
        setChartData((prev) => {
          const alreadyExists = prev.some((point) => point.step === nextProgress.step);
          if (alreadyExists) return prev;
          const newData = [
            ...prev,
            {
              step: nextProgress.step,
              loss: nextProgress.loss,
              lr: nextProgress.lr || 0,
              vram: nextProgress.vramUsed || nextProgress.vram_used || 0,
            },
          ];
          return newData.length > 800 ? newData.slice(newData.length - 800) : newData;
        });
      }

      // 阶段信息
      if (nextProgress.currentPhase || nextProgress.current_phase) {
        setCurrentPhase(nextProgress.currentPhase || nextProgress.current_phase);
      }
      if (nextProgress.phaseDurations || nextProgress.phase_durations) {
        setPhaseDurations(nextProgress.phaseDurations || nextProgress.phase_durations);
      }
      if (nextProgress.retryCount !== undefined || nextProgress.retry_count !== undefined) {
        setRetryCount(nextProgress.retryCount || nextProgress.retry_count || 0);
      }

      // Checkpoint saved notification
      const msg = nextProgress.message || '';
      if (typeof msg === 'string' && msg.includes('Checkpoint saved')) {
        notify.success(msg);
      }

      if (nextProgress.status === 'queued') setTrainingStatus('queued');
      else if (nextProgress.status === 'loading') setTrainingStatus('loading');
      else if (nextProgress.status === 'stopping') setTrainingStatus('stopping');
      else if (nextProgress.status === 'training' || nextProgress.status === 'running')
        setTrainingStatus('training');
      else if (nextProgress.status === 'saving') setTrainingStatus('saving');
      else if (nextProgress.status === 'completed') {
        setTrainingStatus('completed');
        setIsTraining(false);
        setCurrentPhase('');
        notify.success('训练完成');
      } else if (nextProgress.status === 'failed' || nextProgress.status === 'stopped') {
        setTrainingStatus(nextProgress.status === 'failed' ? 'failed' : 'idle');
        setIsTraining(false);
        setCurrentPhase('');
        if (nextProgress.status === 'failed') {
          notify.error(nextProgress.message || '训练失败');
        } else {
          notify.warning('训练已停止');
        }
      }

      if (source === 'v2') {
        setLastV2EventAt(Date.now());
      }
    },
    [setIsTraining],
  );

  const lastV2EventAtRef = useRef<number>(0);
  useEffect(() => {
    lastV2EventAtRef.current = lastV2EventAt;
  }, [lastV2EventAt]);

  const checkTrainingStatus = useCallback(async () => {
    const recentV2Signal = Date.now() - lastV2EventAtRef.current < 20000;
    try {
      const data = await getTrainingStatus();
      setBackendTraining(data.is_training);
      if (data.record?.id) {
        setCurrentTaskId(data.record.id);
        setCurrentTrainingRecord(data.record);
      }
      if (data.progress) {
        // Don't overwrite progress if V2 stream is actively sending data
        if (!recentV2Signal) {
          setProgress(data.progress);
        }
        if (data.progress.status === 'stopping') {
          setTrainingStatus('stopping');
          setIsTraining(true);
        } else if (data.progress.status === 'failed') {
          setTrainingStatus('failed');
          setIsTraining(false);
        } else if (data.progress.status === 'completed') {
          setTrainingStatus('completed');
          setIsTraining(false);
        } else if (data.progress.status === 'stopped') {
          setTrainingStatus('idle');
          setIsTraining(false);
        } else if (data.progress.status === 'saving') {
          setTrainingStatus('saving');
          setIsTraining(true);
        } else if (data.is_training) {
          setTrainingStatus(data.progress.status === 'loading' ? 'loading' : 'training');
          setIsTraining(true);
        }
      }
    } catch (error) {
      console.error('Failed to check training status:', error);
    }
  }, [setIsTraining]);

  useEffect(() => {
    const interval = setInterval(checkTrainingStatus, 15000);
    void checkTrainingStatus();
    return () => clearInterval(interval);
  }, [checkTrainingStatus]);

  useEffect(() => {
    void syncTrainingCatalog();
  }, [syncTrainingCatalog]);

  useEffect(() => {
    if (isTraining && backendStatus === 'connected') {
      const shouldUseLegacySse = Date.now() - lastV2EventAtRef.current > 8000;
      if (!shouldUseLegacySse) return;
      setTrainingStatus('training');
      setChartData([]);
      unsubscribeRef.current = subscribeTrainingProgress(
        (nextProgress: any) => {
          applyIncomingProgress(nextProgress, 'v1');
        },
        (error: Error) => {
          console.error('SSE error:', error);
        },
      );
    }
    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
      }
    };
  }, [applyIncomingProgress, backendStatus, isTraining]);

  const progressRef = useRef<TrainingProgressType | null>(null);
  useEffect(() => {
    progressRef.current = progress;
  }, [progress]);

  const handleV2Event = useCallback(
    (event: TrainingEventV2) => {
      if (currentTaskId && event.task_id !== currentTaskId) {
        return;
      }
      const payload = event.payload || {};
      const currentProgress = progressRef.current;
      const normalizedProgress = {
        epoch: payload.epoch ?? currentProgress?.epoch ?? 0,
        step: payload.step ?? currentProgress?.step ?? 0,
        totalSteps: payload.total_steps ?? payload.totalSteps ?? currentProgress?.totalSteps ?? 0,
        loss: payload.loss ?? payload.final_loss ?? currentProgress?.loss ?? 0,
        lr: payload.lr ?? payload.final_lr ?? currentProgress?.lr ?? 0,
        vramUsed: payload.vram_used ?? payload.vramUsed ?? currentProgress?.vramUsed ?? 0,
        elapsedTime:
          payload.elapsed_time ??
          payload.elapsedTime ??
          payload.final_elapsed_time ??
          currentProgress?.elapsedTime ??
          0,
        eta: payload.eta ?? currentProgress?.eta ?? 0,
        status: event.phase === 'queued' ? 'queued' : payload.status || event.phase,
        message: payload.message || currentProgress?.message || '',
        queuePosition: payload.queue_position ?? payload.queuePosition,
        estimatedWaitSeconds: payload.estimated_wait_seconds ?? payload.estimatedWaitSeconds,
        errorCode: payload.error_code ?? payload.errorCode,
        errorCategory: payload.error_category ?? payload.errorCategory,
        actionableSuggestions: payload.actionable_suggestions ?? payload.actionableSuggestions,
      };
      applyIncomingProgress(normalizedProgress, 'v2');
    },
    [applyIncomingProgress, currentTaskId],
  );

  const handleV2SequenceGap = useCallback(async () => {
    if (!currentTaskId) return;
    try {
      const backfill = await getTrainingTaskMetricsV2(currentTaskId, 0, 1000);
      const items: any[] = Array.isArray(backfill)
        ? backfill
        : Array.isArray(backfill?.items)
        ? backfill.items
        : [];
      if (items.length === 0) return;
      setChartData((prev) => {
        const existingSteps = new Set(prev.map((point) => point.step));
        const merged = [...prev];
        for (const item of items) {
          const step = Number(item.step ?? 0);
          if (!step || existingSteps.has(step)) continue;
          merged.push({
            step,
            loss: Number(item.loss ?? 0),
            lr: Number(item.lr ?? 0),
          });
        }
        merged.sort((a, b) => a.step - b.step);
        return merged.slice(-800);
      });
    } catch (error) {
      console.error('Failed to backfill metrics after V2 sequence gap:', error);
    }
  }, [currentTaskId]);

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _v2Stream = useTrainingEventStreamV2({
    taskId: currentTaskId || undefined,
    enabled: backendStatus === 'connected',
    onEvent: handleV2Event,
    onSequenceGap: handleV2SequenceGap,
  });
  void _v2Stream;

  useEffect(() => {
    if (!preflightResult) return;
    if (!preflightFingerprint) return;
    const latest = getCurrentPreflightFingerprint();
    if (latest !== preflightFingerprint) {
      setPreflightResult(null);
      setPreflightFingerprint(null);
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
  ]);

  const confirmRiskStart = useCallback(
    (warnings: string[]) =>
      new Promise<boolean>((resolve) => {
        appModal.confirm({
          title: '预检提示当前配置存在风险',
          content: `检测到 ${warnings.length} 条风险提示。是否仍然继续启动训练？`,
          okText: '仍然启动',
          cancelText: '返回调整',
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
          afterClose: () => resolve(false),
        });
      }),
    [],
  );

  const buildTrainingConfig = useCallback(
    (values: any) => ({
      model_id: values.modelId,
      dataset_id: values.datasetId,
      task_goal: values.taskGoal || 'qa_assistant',
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
    }),
    [gradientAccumulation, memoryPreset, precisionPreset, quantizationBit, useFlashAttn],
  );

  const handleStart = async (values: any) => {
    if (starting || isTraining) return;

    const latestFingerprint = getCurrentPreflightFingerprint();
    if (!preflightResult || !preflightFingerprint || latestFingerprint !== preflightFingerprint) {
      notify.warning('请先执行训练前预检；若你修改了配置，需要重新预检后再启动训练。');
      return;
    }

    if (preflightResult.status === 'blocked' || !preflightResult.passed) {
      notify.error(preflightResult.summary || '预检存在阻塞项，请修复后再启动训练。');
      return;
    }

    const riskMessages = [
      ...(preflightResult.warnings || []),
      ...(preflightResult.suggestions || []),
    ];
    const hasRisk = preflightResult.status === 'warning' || riskMessages.length > 0;
    const shouldApplyRecommendedConfig = hasRisk
      ? await confirmRiskStart(riskMessages.length ? riskMessages : ['当前配置存在预检风险'])
      : false;
    if (hasRisk && !shouldApplyRecommendedConfig) return;

    setStarting(true);
    setTrainingStatus('loading');
    setChartData([]);

    try {
      const config = buildTrainingConfig(values);

      const result =
        useSwift && swiftAvailable
          ? await startSwiftTraining(config)
          : await startTraining(config, { applyRecommendedConfig: shouldApplyRecommendedConfig });

      setIsTraining(true);
      addTrainingRecord(result);
      setCurrentTaskId(result.id);
      setCurrentTrainingRecord(result);
      notify.success('训练任务已提交');
    } catch (error: any) {
      setTrainingStatus('idle');
      notify.error(getErrorMessage(error, '启动训练失败'));
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async () => {
    try {
      await stopTraining();
      setTrainingStatus('stopping');
      notify.info('已发送停止请求，等待当前步骤安全退出');
    } catch (error) {
      notify.error(getErrorMessage(error, '停止训练失败'));
    }
  };

  const handleResumeTraining = async (taskId: string, checkpointName: string) => {
    try {
      setTrainingStatus('loading');
      const result = await resumeTraining(taskId, checkpointName);
      setIsTraining(true);
      addTrainingRecord(result);
      setCurrentTaskId(result.id);
      setCurrentTrainingRecord(result);
      setChartData([]);
      notify.success('已从检查点恢复训练');
    } catch (error: any) {
      setTrainingStatus('idle');
      notify.error(getErrorMessage(error, '恢复训练失败'));
    }
  };

  const estimateModelSize = (modelId?: string) => {
    const label = (modelId || '').toUpperCase();
    if (label.includes('14B') || label.includes('13B')) return '13B';
    if (label.includes('8B') || label.includes('7B')) return '7B';
    if (label.includes('3B')) return '3B';
    if (label.includes('1.5B') || label.includes('1B')) return '1.5B';
    return '7B';
  };

  const estimateRequiredVram = (values: any) => {
    const size = estimateModelSize(values.modelId);
    const batchSize = Number(values.batchSize || 1);
    const seqLength = Number(values.maxSeqLength || 512);
    let base = size === '13B' ? 8 : size === '3B' ? 3 : size === '1.5B' ? 2 : 6;
    if ((values.method || 'qlora') === 'qlora') base *= 0.7;
    if (seqLength > 1024) base += 1;
    if (batchSize > 1) base += 0.8 * (batchSize - 1);
    return Number(base.toFixed(1));
  };

  const handlePreflightCheck = async () => {
    const values = form.getFieldsValue();
    if (!values.modelId || !values.datasetId) {
      notify.warning('请先选择模型和数据集，再执行训练前预检');
      return;
    }

    setPreflightChecking(true);
    try {
      const result = await checkTrainingPreflight(buildTrainingConfig(values));
      setPreflightResult(result);

      setPreflightFingerprint(getCurrentPreflightFingerprint());

      if (result.status === 'blocked') {
        notify.error('训练前预检发现阻塞项，请先查看预检面板');
      } else if (result.status === 'warning') {
        notify.warning('训练前预检通过但存在风险，请确认后再启动');
      } else {
        notify.success('训练前预检通过');
      }
    } catch (error: any) {
      try {
        const fallback = await checkTrainingResources({
          method: values.method || 'qlora',
          modelSize: estimateModelSize(values.modelId),
          requiredVram: estimateRequiredVram(values),
        });
        setPreflightResult({
          ...fallback,
          status: fallback.passed ? 'ready' : 'warning',
          summary: fallback.passed ? '资源预检通过。' : '资源预检存在风险。',
          checks: [
            {
              key: 'resources',
              label: '显存与设备',
              status: fallback.passed ? 'passed' : 'warning',
              message: fallback.passed ? '资源预算通过' : '显存预算偏紧',
            },
          ],
          blockers: [],
        });
        setPreflightFingerprint(getCurrentPreflightFingerprint());
        notify.warning('完整预检不可用，已回退到资源预检');
      } catch {
        notify.error(getErrorMessage(error, '训练前预检失败'));
      }
    } finally {
      setPreflightChecking(false);
    }
  };

  const _handleApplyConservativePreset = () => {
    form.setFieldsValue({
      method: 'qlora',
      batchSize: 1,
      maxSeqLength: 512,
      rank: 8,
      alpha: 16,
    });
    setGradientAccumulation(16);
    setQuantizationBit(4);
    setMemoryPreset('6gb');
    notify.info('已应用保守训练建议，请重新执行训练前预检。');
  };

  const statusLabels: Record<typeof trainingStatus, string> = {
    idle: '待命',
    queued: '队列中',
    loading: '加载中',
    training: '训练中',
    saving: '模型保存中',
    stopping: '停止中',
    completed: '已完成',
    failed: '已失败',
  };

  const handleResetTraining = () => {
    setTrainingStatus('idle');
    setProgress(null);
    setChartData([]);
    setCurrentTaskId(null);
    setPhaseDurations({});
    setCurrentPhase('');
    setRetryCount(0);
  };

  const formatElapsed = (seconds?: number) => {
    if (!seconds) return '--:--';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const openCurrentEvaluation = () => {
    const values = form.getFieldsValue();
    const params = new URLSearchParams();
    const scenario =
      values.taskGoal === 'structured_extraction' ? 'structured_extraction' : 'qa_assistant';

    params.set('scenario', scenario);
    params.set('backend', 'huggingface');
    params.set('run_inference', 'true');
    params.set('auto_merge_adapter', 'true');
    if (currentTaskId) params.set('training_task_id', currentTaskId);
    if (values.modelId) params.set('base_model', values.modelId);
    // Do not reuse the training dataset for release evaluation. The backend binds
    // this run to the held-out snapshot created during training.
    if (currentTrainingRecord?.adapterPath) {
      params.set('adapter_path', currentTrainingRecord.adapterPath);
    }
    if (currentTrainingRecord?.method === 'full' && currentTrainingRecord.checkpointPath) {
      params.set('finetuned_model', currentTrainingRecord.checkpointPath);
    }

    navigate(`/evaluation?${params.toString()}`);
  };

  return (
    <AnimatedLayout animationKey="training">
      {backendStatus !== 'connected' ? (
        <div className={layoutStyles.workspace}>
          <div className={layoutStyles.disconnectedContainer}>
            <DisconnectOutlined className={layoutStyles.disconnectedIcon} />
            <div className={layoutStyles.disconnectedText}>
              后端服务未连接，请先启动应用。
            </div>
          </div>
        </div>
      ) : (
        <div className={layoutStyles.workspace}>
          {/* ── Header Bar ── */}
          <div className={layoutStyles.headerBar}>
            <button
              className={layoutStyles.collapseToggle}
              onClick={() => setConfigCollapsed(!configCollapsed)}
              title={configCollapsed ? '显示配置' : '隐藏配置'}
            >
              {configCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </button>

            <div className={layoutStyles.headerTitle}>
              <div className={layoutStyles.headerIcon}>
                <ThunderboltOutlined />
              </div>
              <span className={layoutStyles.headerLabel}>模型训练</span>
            </div>

            <div
              className={layoutStyles.statusIndicator}
              data-status={trainingStatus}
            >
              <span className={layoutStyles.statusDot} />
              {statusLabels[trainingStatus]}
            </div>

            <div className={layoutStyles.headerSpacer} />

            {(trainingStatus === 'training' || trainingStatus === 'loading') && (
              <div className={layoutStyles.headerTimer}>
                已耗时 <span className={layoutStyles.timerValue}>{formatElapsed(progress?.elapsedTime)}</span>
              </div>
            )}

            {trainingStatus === 'completed' && (
              <Button
                type="primary"
                icon={<FileSearchOutlined />}
                onClick={openCurrentEvaluation}
                style={{ borderRadius: 8 }}
              >
                进入评估
              </Button>
            )}
          </div>

          {/* ── Two-pane Layout ── */}
          <div className={layoutStyles.paneContainer}>
            <div className={`${layoutStyles.configPane} ${configCollapsed ? layoutStyles.collapsed : ''}`}>
              <HyperparameterPanel
                form={form}
                onFinish={handleStart}
                onPreflightCheck={handlePreflightCheck}
                isTraining={isTraining || backendTraining}
                starting={starting}
                preflightChecking={preflightChecking}
                onStop={handleStop}
                models={models}
                datasets={datasets}
                useSwift={useSwift}
                onSwiftChange={setUseSwift}
                precisionPreset={precisionPreset}
                onPrecisionChange={setPrecisionPreset}
                memoryPreset={memoryPreset}
                onMemoryChange={setMemoryPreset}
                quantizationBit={quantizationBit}
                onQuantizationChange={setQuantizationBit}
                gradientAccumulation={gradientAccumulation}
                onGradAccChange={setGradientAccumulation}
                preflightResult={preflightResult}
                onApplyConservativePreset={_handleApplyConservativePreset}
              />
            </div>

            <div className={layoutStyles.dashboardPane}>
              <TrainingDashboard
                progress={progress}
                chartData={chartData}
                status={trainingStatus}
                selectedModel={watchedModelId}
                selectedDataset={watchedDatasetId}
                selectedMethod={watchedMethod}
                onReset={handleResetTraining}
                phaseDurations={phaseDurations}
                currentPhase={currentPhase}
                retryCount={retryCount}
                currentTaskId={currentTaskId}
                onResume={handleResumeTraining}
              />
            </div>
          </div>
        </div>
      )}
    </AnimatedLayout>
  );
};

export default TrainingPage;
