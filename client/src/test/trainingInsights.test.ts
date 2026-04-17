import { describe, expect, it } from 'vitest';
import {
  buildResumeConfigDiff,
  buildRuntimeTrainingGuardrail,
  buildTrainingFailureAnalytics,
  buildTrainingPreflightFingerprint,
  diagnoseTrainingFailure,
} from '../pages/Training/trainingInsights';

describe('trainingInsights', () => {
  it('categorizes OOM-like failures and returns actionable suggestions', () => {
    const diagnosis = diagnoseTrainingFailure('CUDA out of memory while allocating tensor');

    expect(diagnosis.category).toBe('oom');
    expect(diagnosis.title).toContain('显存');
    expect(diagnosis.suggestions.length).toBeGreaterThan(1);
  });

  it('falls back to unknown when error message has no known signature', () => {
    const diagnosis = diagnoseTrainingFailure('unexpected panic in worker thread');

    expect(diagnosis.category).toBe('unknown');
    expect(diagnosis.summary).toContain('unexpected panic');
  });

  it('builds stable fingerprint for unchanged preflight inputs', () => {
    const values = {
      modelId: 'model-a',
      datasetId: 'dataset-a',
      method: 'qlora',
      batchSize: 1,
      maxSeqLength: 512,
    };
    const runtimeConfig = {
      gradientAccumulation: 16,
      precisionPreset: 'balanced' as const,
      memoryPreset: 'auto' as const,
      useFlashAttn: false,
      quantizationBit: 4 as const,
      useSwift: false,
    };

    const first = buildTrainingPreflightFingerprint(values, runtimeConfig);
    const second = buildTrainingPreflightFingerprint(values, runtimeConfig);
    expect(first).toBe(second);
  });

  it('changes fingerprint when key training config changes', () => {
    const runtimeConfig = {
      gradientAccumulation: 16,
      precisionPreset: 'balanced' as const,
      memoryPreset: 'auto' as const,
      useFlashAttn: false,
      quantizationBit: 4 as const,
      useSwift: false,
    };

    const first = buildTrainingPreflightFingerprint(
      {
        modelId: 'model-a',
        datasetId: 'dataset-a',
        method: 'qlora',
        batchSize: 1,
        maxSeqLength: 512,
      },
      runtimeConfig,
    );
    const second = buildTrainingPreflightFingerprint(
      {
        modelId: 'model-a',
        datasetId: 'dataset-a',
        method: 'lora',
        batchSize: 1,
        maxSeqLength: 512,
      },
      runtimeConfig,
    );

    expect(first).not.toBe(second);
  });

  it('builds failure analytics from training history records', () => {
    const baseConfig = {
      modelId: 'qwen-7b',
      datasetId: 'dataset-a',
      method: 'qlora' as const,
      rank: 8,
      alpha: 16,
      learningRate: 5e-5,
      epochs: 3,
      batchSize: 1,
      gradientAccumulation: 16,
      maxSeqLength: 512,
      warmupSteps: 100,
      saveSteps: 500,
      loggingSteps: 10,
    };

    const analytics = buildTrainingFailureAnalytics([
      {
        id: 'run-1',
        modelName: 'qwen-7b',
        datasetName: 'dataset-a',
        method: 'qlora',
        status: 'failed',
        startTime: '2026-04-16T10:00:00',
        endTime: '2026-04-16T10:10:00',
        outputPath: '/tmp/run-1',
        config: { ...baseConfig, batchSize: 2, maxSeqLength: 2048, quantization: 0 },
      },
      {
        id: 'run-2',
        modelName: 'qwen-7b',
        datasetName: 'dataset-b',
        method: 'qlora',
        status: 'failed',
        startTime: '2026-04-16T11:00:00',
        endTime: '2026-04-16T11:05:00',
        outputPath: '/tmp/run-2',
        config: {
          ...baseConfig,
          datasetId: 'dataset-b',
          batchSize: 1,
          maxSeqLength: 512,
          quantization: 4,
        },
      },
      {
        id: 'run-3',
        modelName: 'qwen-3b',
        datasetName: 'dataset-c',
        method: 'lora',
        status: 'completed',
        startTime: '2026-04-16T12:00:00',
        endTime: '2026-04-16T12:20:00',
        outputPath: '/tmp/run-3',
        config: {
          ...baseConfig,
          modelId: 'qwen-3b',
          datasetId: 'dataset-c',
          method: 'lora',
          batchSize: 1,
          maxSeqLength: 512,
          quantization: 4,
        },
      },
    ]);

    expect(analytics.totalRuns).toBe(3);
    expect(analytics.failedRuns).toBe(2);
    expect(analytics.completedRuns).toBe(1);
    expect(analytics.failureRate).toBeCloseTo(66.7, 1);
    expect(analytics.totalRuns7d).toBeGreaterThan(0);
    expect(analytics.totalRuns14d).toBeGreaterThan(0);
    expect(analytics.failureRate14d).toBeGreaterThanOrEqual(analytics.failureRate7d);
    expect(analytics.suspectedVramPressureCount).toBe(1);
    expect(analytics.longContextFailureCount).toBe(1);
    expect(analytics.unquantizedFailureCount).toBe(1);
    expect(analytics.topFailedModels[0]).toBe('qwen-7b');
    expect(analytics.recentFailures[0]?.id).toBe('run-2');
  });

  it('builds readable resume config diff entries', () => {
    const diff = buildResumeConfigDiff(
      {
        method: 'qlora',
        batchSize: 1,
        maxSeqLength: 512,
        gradientAccumulation: 16,
        quantization: 4,
      },
      {
        method: 'lora',
        batchSize: 2,
        maxSeqLength: 1024,
        gradientAccumulation: 8,
        quantization: 0,
      },
    );

    expect(diff.length).toBeGreaterThan(0);
    expect(diff.join(' | ')).toContain('微调方法');
    expect(diff.join(' | ')).toContain('Batch Size');
  });

  it('builds runtime guardrail for failed training phase', () => {
    const guardrail = buildRuntimeTrainingGuardrail('failed', 'CUDA OOM on step 120');

    expect(guardrail.statusType).toBe('error');
    expect(guardrail.statusText).toContain('失败');
    expect(guardrail.summary).toContain('CUDA OOM');
    expect(guardrail.actions.length).toBeGreaterThan(1);
  });

  it('builds runtime guardrail for stopping phase', () => {
    const guardrail = buildRuntimeTrainingGuardrail('stopping');

    expect(guardrail.statusType).toBe('warning');
    expect(guardrail.statusText).toContain('停止');
    expect(guardrail.summary).toContain('收敛');
  });
});
