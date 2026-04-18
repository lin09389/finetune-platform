import {
  CheckCircleOutlined,
  PlayCircleOutlined,
  StopOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Alert, Button, Col, Divider, Form, InputNumber, Row, Select, Space, Switch } from 'antd';
import React from 'react';
import NeumorphicButton from '../../../components/shared/NeumorphicButton';
import styles from './ConfigForm.module.css';

interface ConfigFormProps {
  form: any;
  onFinish: (values: any) => void;
  onPreflightCheck: () => void;
  isTraining: boolean;
  starting: boolean;
  preflightChecking: boolean;
  onStop: () => void;
  models: { id: string; name: string; quantized?: number }[];
  datasets: { id: string; name: string; samples: number }[];
  swiftAvailable: boolean;
  useSwift: boolean;
  onSwiftChange: (checked: boolean) => void;
  precisionPreset: 'max' | 'balanced' | 'fast';
  onPrecisionChange: (preset: any) => void;
  memoryPreset: 'auto' | '6gb' | '8gb' | '12gb';
  onMemoryChange: (preset: any) => void;
  useFlashAttn: boolean;
  onFlashAttnChange: (checked: boolean) => void;
  quantizationBit: 0 | 4 | 8;
  onQuantizationChange: (bit: any) => void;
  gradientAccumulation: number;
  onGradAccChange: (val: number) => void;
  onApplyPreset: (preset: 'low' | 'medium' | 'high') => void;
}

const ConfigForm: React.FC<ConfigFormProps> = ({
  form,
  onFinish,
  onPreflightCheck,
  isTraining,
  starting,
  preflightChecking,
  onStop,
  models,
  datasets,
  swiftAvailable,
  useSwift,
  onSwiftChange,
  precisionPreset,
  onPrecisionChange,
  memoryPreset,
  onMemoryChange,
  useFlashAttn,
  onFlashAttnChange,
  quantizationBit,
  onQuantizationChange,
  gradientAccumulation,
  onGradAccChange,
  onApplyPreset,
}) => {
  const evalSteps = Form.useWatch('evalSteps', form) ?? 100;
  const saveSteps = Form.useWatch('saveSteps', form) ?? 500;
  const loadBestModel = Form.useWatch('loadBestModel', form) ?? true;

  const normalizedEvalSteps = Math.max(1, Number(evalSteps || 1));
  const normalizedSaveSteps = Math.max(1, Number(saveSteps || 1));
  const suggestedSaveSteps =
    Math.ceil(normalizedSaveSteps / normalizedEvalSteps) * normalizedEvalSteps;
  const needsSaveStepAlignment =
    loadBestModel && normalizedSaveSteps % normalizedEvalSteps !== 0;

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={onFinish}
      disabled={isTraining}
      className={styles.form}
    >
      <Row gutter={24}>
        <Col span={8}>
          <Form.Item label="基础模型" name="modelId" rules={[{ required: true }]}>
            <Select
              placeholder="选择基础模型"
              options={models.map((m) => ({
                value: m.id,
                label: `${m.name} ${m.quantized ? `(INT${m.quantized})` : ''}`,
              }))}
              showSearch
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="训练数据集" name="datasetId" rules={[{ required: true }]}>
            <Select
              placeholder="选择数据集"
              options={datasets.map((d) => ({ value: d.id, label: `${d.name} (${d.samples}条)` }))}
              showSearch
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="微调方法" name="method" initialValue="qlora">
            <Select>
              <Select.Option value="qlora">QLoRA（推荐）</Select.Option>
              <Select.Option value="lora">LoRA</Select.Option>
            </Select>
          </Form.Item>
        </Col>
      </Row>

      <Divider className={styles.divider}>加速与精度策略</Divider>

      <Row gutter={24}>
        <Col span={8}>
          <Form.Item
            label={
              <span className={styles.labelWithIcon}>
                <ThunderboltOutlined /> SWIFT 框架（实验）
              </span>
            }
            tooltip="SWIFT 作为可选实验后端保留，发布版主推 LoRA / QLoRA"
          >
            <Switch checked={useSwift} onChange={onSwiftChange} disabled={!swiftAvailable} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            label={
              <span className={styles.labelWithIcon}>
                <CheckCircleOutlined /> 精度预设
              </span>
            }
          >
            <Select value={precisionPreset} onChange={onPrecisionChange}>
              <Select.Option value="max">最高 (Max)</Select.Option>
              <Select.Option value="balanced">平衡 (Balanced)</Select.Option>
              <Select.Option value="fast">快速 (Fast)</Select.Option>
            </Select>
          </Form.Item>
        </Col>
        <Col span={8}>
          <Alert
            type="info"
            showIcon
            message={<span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>发布版已关闭 DoRA / LoRA+ / GaLore</span>}
            description={<span style={{ color: 'var(--text-secondary)' }}>当前仅开放 LoRA / QLoRA 主线训练，避免将实验性能力误当成稳定能力使用。</span>}
          />
        </Col>
      </Row>

      <Divider className={styles.divider}>显存与吞吐优化</Divider>

      <Row gutter={24}>
        <Col span={12}>
          <Form.Item label="显存优化预设">
            <Select value={memoryPreset} onChange={onMemoryChange}>
              <Select.Option value="auto">自动检测</Select.Option>
              <Select.Option value="6gb">6GB (极致省显存)</Select.Option>
              <Select.Option value="8gb">8GB (平衡)</Select.Option>
              <Select.Option value="12gb">12GB (高吞吐)</Select.Option>
            </Select>
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="量化策略">
            <Select
              value={quantizationBit}
              onChange={onQuantizationChange}
              disabled={memoryPreset !== 'auto'}
            >
              <Select.Option value={4}>4bit (省显存)</Select.Option>
              <Select.Option value={8}>8bit (平衡)</Select.Option>
              <Select.Option value={0}>不量化 (高精度)</Select.Option>
            </Select>
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={24}>
        <Col span={8}>
          <Form.Item label="梯度累积">
            <InputNumber
              min={1}
              max={128}
              value={gradientAccumulation}
              onChange={(v) => onGradAccChange(v || 16)}
              style={{ width: '100%' }}
              disabled={memoryPreset !== 'auto'}
            />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="Flash Attention">
            <Switch checked={useFlashAttn} onChange={onFlashAttnChange} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <div className={styles.presetGroup}>
            <label className={styles.smallLabel}>快捷预设</label>
            <Space>
              <Button size="small" onClick={() => onApplyPreset('low')}>
                6GB
              </Button>
              <Button size="small" onClick={() => onApplyPreset('medium')}>
                8GB
              </Button>
              <Button size="small" onClick={() => onApplyPreset('high')}>
                12G+
              </Button>
            </Space>
          </div>
        </Col>
      </Row>

      <Divider className={styles.divider}>训练参数</Divider>

      <Row gutter={16}>
        <Col span={8}>
          <Form.Item label="训练轮数" name="epochs">
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="LoRA Rank" name="rank">
            <InputNumber min={4} max={128} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="LoRA Alpha" name="alpha">
            <InputNumber min={8} max={256} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={12}>
          <Form.Item label="学习率" name="learningRate">
            <InputNumber min={1e-6} max={1e-3} step={1e-5} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="最大序列长度" name="maxSeqLength">
            <InputNumber min={128} max={4096} step={128} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={8}>
          <Form.Item label="评估间隔步数" name="evalSteps" initialValue={100}>
            <InputNumber min={10} max={5000} step={10} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item label="保存间隔步数" name="saveSteps" initialValue={500}>
            <InputNumber min={10} max={10000} step={10} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item
            label="结束时加载最佳模型"
            name="loadBestModel"
            valuePropName="checked"
            initialValue
          >
            <Switch />
          </Form.Item>
        </Col>
      </Row>

      {loadBestModel && (
        <Alert
          className={styles.stepHint}
          type={needsSaveStepAlignment ? 'warning' : 'info'}
          showIcon
          message={
            needsSaveStepAlignment
              ? `将自动调整 save_steps: ${normalizedSaveSteps} -> ${suggestedSaveSteps}`
              : `当前步长合法：save_steps(${normalizedSaveSteps}) 是 eval_steps(${normalizedEvalSteps}) 的整数倍`
          }
          description="开启“结束时加载最佳模型”时，后端会确保 save_steps 是 eval_steps 的整数倍。"
        />
      )}

      <Form.Item style={{ marginTop: 'var(--space-6)', textAlign: 'right' }}>
        <Space size="large">
          {isTraining ? (
            <NeumorphicButton variant="danger" size="lg" onClick={onStop} icon={<StopOutlined />}>
              停止训练
            </NeumorphicButton>
          ) : (
            <>
              <Button
                size="large"
                onClick={onPreflightCheck}
                loading={preflightChecking}
                disabled={!models.length || !datasets.length || starting}
              >
                训练前预检
              </Button>
              <NeumorphicButton
                variant="primary"
                size="lg"
                htmlType="submit"
                loading={starting}
                disabled={!models.length || !datasets.length}
                icon={<PlayCircleOutlined />}
              >
                开始训练
              </NeumorphicButton>
            </>
          )}
        </Space>
      </Form.Item>
    </Form>
  );
};

export default ConfigForm;
