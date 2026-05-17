import React, { useState } from 'react';
import { Form, InputNumber, Select, Switch, Slider } from 'antd';
import { motion } from 'framer-motion';
import {
  ThunderboltOutlined,
  PlayCircleOutlined,
  StopOutlined,
  DownOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import styles from './HyperparameterPanel.module.css';

interface PreflightCheck {
  key: string;
  label: string;
  status: 'passed' | 'warning' | 'blocked';
  message: string;
  detail?: string;
}

interface PreflightStatus {
  status?: 'ready' | 'warning' | 'blocked';
  summary?: string;
  checks?: PreflightCheck[];
  blockers?: string[];
  warnings?: string[];
  suggestions?: string[];
}

interface HyperparameterPanelProps {
  form: any;
  onFinish: (values: any) => void;
  onPreflightCheck: () => void;
  isTraining: boolean;
  starting: boolean;
  preflightChecking: boolean;
  onStop: () => void;
  models: { id: string; name: string; quantized?: number }[];
  datasets: { id: string; name: string; samples: number }[];
  useSwift: boolean;
  onSwiftChange: (checked: boolean) => void;
  precisionPreset?: 'max' | 'balanced' | 'fast';
  onPrecisionChange?: (preset: any) => void;
  memoryPreset?: 'auto' | '6gb' | '8gb' | '12gb';
  onMemoryChange?: (preset: any) => void;
  quantizationBit: 0 | 4 | 8;
  onQuantizationChange: (bit: any) => void;
  gradientAccumulation?: number;
  onGradAccChange?: (val: number) => void;
  preflightResult?: PreflightStatus | null;
  onApplyConservativePreset?: () => void;
}

const GlowingSwitch = ({ checked, onChange, disabled }: any) => (
  <div className={`${styles.glowingSwitch} ${checked ? styles.active : ''}`}>
    <Switch checked={checked} onChange={onChange} disabled={disabled} />
  </div>
);

const LrDecayVisualizer = () => (
  <div className={styles.microVis}>
    <svg width="100%" height="32" viewBox="0 0 120 32" preserveAspectRatio="none">
      <defs>
        <linearGradient id="lrGradient" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="rgba(0, 255, 194, 0.6)" />
          <stop offset="100%" stopColor="rgba(0, 255, 194, 0.05)" />
        </linearGradient>
      </defs>
      <motion.path
        d="M 0,4 C 20,4 35,4 50,10 S 80,26 120,30"
        fill="none"
        stroke="url(#lrGradient)"
        strokeWidth="1.5"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 1.2, ease: "easeOut" }}
      />
      <motion.circle
        cx="120" cy="30" r="2"
        fill="#FF6B6B"
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 0.8 }}
        transition={{ delay: 1.2 }}
      />
    </svg>
    <div className={styles.visLabel}>学习率衰减</div>
  </div>
);

interface CollapsibleSectionProps {
  title: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}

const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  title,
  defaultExpanded = true,
  children,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className={styles.section}>
      <div
        className={`${styles.sectionHeader} ${expanded ? styles.expanded : ''}`}
        onClick={() => setExpanded(!expanded)}
      >
        <h3 className={styles.sectionTitle}>{title}</h3>
        <DownOutlined className={`${styles.sectionChevron} ${expanded ? '' : styles.rotated}`} />
      </div>
      <div className={`${styles.sectionBody} ${expanded ? '' : styles.collapsed}`}>
        {children}
      </div>
    </div>
  );
};

const HyperparameterPanel: React.FC<HyperparameterPanelProps> = ({
  form,
  onFinish,
  onPreflightCheck,
  isTraining,
  starting,
  preflightChecking,
  onStop,
  models,
  datasets,
  useSwift,
  onSwiftChange,
  quantizationBit,
  onQuantizationChange,
  gradientAccumulation,
  onGradAccChange,
  preflightResult,
  onApplyConservativePreset,
}) => {
  const preflightStatus = preflightResult?.status || null;

  return (
    <div className={`deep-tech-panel ${styles.panelContainer}`}>
      <div className={styles.panelHeader}>
        <ThunderboltOutlined className={styles.iconCyan} />
        <h2>控制台</h2>
      </div>

      <Form form={form} layout="vertical" onFinish={onFinish} disabled={isTraining} className={styles.deepForm}>
        {/* Section: Foundation */}
        <CollapsibleSection title="基础设置">
          <Form.Item label="基座模型" name="modelId" rules={[{ required: true, message: '请选择模型' }]}>
            <Select
              className={styles.deepSelect}
              placeholder="选择模型..."
              options={models.map(m => ({ value: m.id, label: `${m.name}${m.quantized ? ` (INT${m.quantized})` : ''}` }))}
              showSearch
              filterOption={(input, option) =>
                String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item label="数据集" name="datasetId" rules={[{ required: true, message: '请选择数据集' }]}>
            <Select
              className={styles.deepSelect}
              placeholder="选择数据集..."
              options={datasets.map(d => ({ value: d.id, label: `${d.name} (${(d.samples ?? 0).toLocaleString()})` }))}
              showSearch
              filterOption={(input, option) =>
                String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item label="应用目标" name="taskGoal" initialValue="qa_assistant">
            <Select className={styles.deepSelect}>
              <Select.Option value="qa_assistant">客服/知识问答助手</Select.Option>
              <Select.Option value="structured_extraction">结构化输出/信息抽取</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="微调方法" name="method" initialValue="qlora">
            <Select className={styles.deepSelect}>
              <Select.Option value="qlora">QLoRA</Select.Option>
              <Select.Option value="lora">LoRA</Select.Option>
            </Select>
          </Form.Item>
        </CollapsibleSection>

        {/* Section: Architecture */}
        <CollapsibleSection title="架构参数">
          <Form.Item label="LoRA 秩" name="rank" initialValue={8}>
            <Slider min={4} max={128} marks={{ 4: '4', 32: '32', 64: '64', 128: '128' }} className={styles.deepSlider} />
          </Form.Item>
          <Form.Item label="LoRA 缩放系数" name="alpha" initialValue={16}>
            <Slider min={8} max={256} marks={{ 8: '8', 64: '64', 128: '128', 256: '256' }} className={styles.deepSlider} />
          </Form.Item>
        </CollapsibleSection>

        {/* Section: Optimization */}
        <CollapsibleSection title="优化设置">
          <Form.Item label="学习率" name="learningRate" initialValue={5e-5}>
            <InputNumber min={1e-6} max={1e-3} step={1e-5} style={{ width: '100%' }} />
          </Form.Item>
          <LrDecayVisualizer />
          <div className={styles.inlineRow}>
            <Form.Item label="训练轮数" name="epochs" initialValue={3}>
              <InputNumber min={1} max={100} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="批大小" name="batchSize" initialValue={1}>
              <InputNumber min={1} max={64} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <div className={styles.inlineRow}>
            <Form.Item label="最大序列长度" name="maxSeqLength" initialValue={512}>
              <InputNumber min={128} max={4096} step={128} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="预热步数" name="warmupSteps" initialValue={100}>
              <InputNumber min={0} max={10000} step={10} style={{ width: '100%' }} />
            </Form.Item>
          </div>
        </CollapsibleSection>

        {/* Section: Engine & Memory */}
        <CollapsibleSection title="引擎与显存" defaultExpanded={false}>
          <div className={styles.switchGroup}>
            <span>SWIFT 加速引擎</span>
            <GlowingSwitch checked={useSwift} onChange={onSwiftChange} />
          </div>
          <Form.Item label="量化位数" style={{ marginTop: 8 }}>
            <Select value={quantizationBit} onChange={onQuantizationChange} className={styles.deepSelect}>
              <Select.Option value={4}>INT4</Select.Option>
              <Select.Option value={8}>INT8</Select.Option>
              <Select.Option value={0}>FP16 (无量化)</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item label="梯度累积">
            <InputNumber
              min={1}
              max={128}
              value={gradientAccumulation}
              onChange={(v) => onGradAccChange?.(v || 16)}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <div className={styles.inlineRow}>
            <Form.Item label="保存步数" name="saveSteps" initialValue={500}>
              <InputNumber min={10} max={10000} step={10} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="日志步数" name="loggingSteps" initialValue={10}>
              <InputNumber min={1} max={1000} step={5} style={{ width: '100%' }} />
            </Form.Item>
          </div>
        </CollapsibleSection>
      </Form>

      {/* Action Center */}
      <div className={styles.actionCenter}>
        {/* Preflight Status Badge */}
        {preflightStatus && (
          <div className={`${styles.preflightBadge} ${styles[preflightStatus]}`}>
            {preflightStatus === 'ready' && <><CheckCircleOutlined /> 预检通过</>}
            {preflightStatus === 'warning' && <><WarningOutlined /> 预检警告</>}
            {preflightStatus === 'blocked' && <><CloseCircleOutlined /> 预检阻塞</>}
          </div>
        )}

        {preflightResult?.checks && preflightResult.checks.length > 0 && (
          <div style={{ marginTop: 8, fontSize: 12, maxHeight: 160, overflowY: 'auto' }}>
            {preflightResult.checks.map((check) => (
              <div
                key={check.key}
                style={{
                  padding: '4px 6px',
                  marginBottom: 4,
                  borderRadius: 4,
                  background: check.status === 'blocked'
                    ? 'rgba(255, 77, 79, 0.08)'
                    : check.status === 'warning'
                      ? 'rgba(250, 173, 20, 0.08)'
                      : 'rgba(0, 255, 194, 0.05)',
                  borderLeft: `3px solid ${
                    check.status === 'blocked'
                      ? 'var(--error)'
                      : check.status === 'warning'
                        ? 'var(--warning)'
                        : 'var(--accent-neon-cyan)'
                  }`,
                }}
              >
                <div style={{ fontWeight: 500 }}>{check.label}</div>
                <div style={{ color: 'var(--text-secondary)' }}>{check.message}</div>
                {check.detail && (
                  <div style={{ color: 'var(--text-tertiary)', fontSize: 11, marginTop: 2 }}>{check.detail}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {preflightResult?.blockers && preflightResult.blockers.length > 0 && (
          <div style={{ marginTop: 6, fontSize: 12 }}>
            {preflightResult.blockers.map((b, i) => (
              <div key={i} style={{ color: 'var(--error)', padding: '2px 0' }}>
                <CloseCircleOutlined style={{ marginRight: 4 }} />{b}
              </div>
            ))}
          </div>
        )}

        {preflightResult?.summary && preflightStatus === 'blocked' && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
            {preflightResult.summary}
          </div>
        )}
        {!preflightStatus && !isTraining && (
          <div className={`${styles.preflightBadge} ${styles.pending}`}>
            <SafetyOutlined /> 需要预检
          </div>
        )}

        {isTraining ? (
          <button type="button" className={`${styles.actionBtn} ${styles.btnDanger}`} onClick={onStop}>
            <StopOutlined /> 终止训练
          </button>
        ) : (
          <>
            <button
              type="button"
              className={`${styles.actionBtn} ${styles.btnSecondary}`}
              onClick={onPreflightCheck}
              disabled={starting || preflightChecking}
            >
              {preflightChecking ? '正在检查...' : '运行预检'}
            </button>
            <button
              type="button"
              className={`${styles.actionBtn} ${styles.btnPrimary} ${starting ? styles.blinking : ''}`}
              disabled={starting}
              onClick={() => form.submit()}
            >
              <PlayCircleOutlined /> {starting ? '启动中...' : '开始训练'}
            </button>
            {onApplyConservativePreset && (
              <button
                type="button"
                className={`${styles.actionBtn} ${styles.btnConservative}`}
                onClick={onApplyConservativePreset}
                disabled={starting}
              >
                <SafetyOutlined /> 保守配置预设
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default HyperparameterPanel;
