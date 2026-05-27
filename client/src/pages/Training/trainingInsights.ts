export const buildTrainingPreflightFingerprint = (
  values: Record<string, any>,
  runtimeConfig: {
    gradientAccumulation: number;
    precisionPreset: 'max' | 'balanced' | 'fast';
    memoryPreset: 'auto' | '6gb' | '8gb' | '12gb';
    useFlashAttn: boolean;
    quantizationBit: 0 | 4 | 8;
    useSwift: boolean;
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
  });
