import { describe, expect, it } from 'vitest';
import { buildTrainingPreflightFingerprint } from '../pages/Training/trainingInsights';

describe('trainingInsights', () => {
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
});
