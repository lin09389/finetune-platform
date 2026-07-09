/**
 * 用户引导组件
 *
 * 功能：
 * - 新手引导流程
 * - 功能提示
 * - 步骤指引
 */
import {
  BulbOutlined,
  CheckCircleOutlined,
  CloseOutlined,
  LeftOutlined,
  QuestionCircleOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { Button, Card, Modal, Progress, Space, Steps, Tag, Tooltip, Typography } from 'antd';
import React, { useEffect, useState } from 'react';

const { Title, Paragraph, Text } = Typography;

interface GuideStep {
  key: string;
  title: string;
  description: string;
  icon?: React.ReactNode;
  target?: string;
  completed?: boolean;
}

interface UserGuideProps {
  guideKey: string;
  steps: GuideStep[];
  onComplete?: () => void;
  onSkip?: () => void;
  autoStart?: boolean;
}

const STORAGE_KEY_PREFIX = 'user_guide_completed_';

const UserGuide: React.FC<UserGuideProps> = ({
  guideKey,
  steps,
  onComplete,
  onSkip,
  autoStart = false,
}) => {
  const [visible, setVisible] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY_PREFIX + guideKey);
    if (stored) {
      setCompletedSteps(new Set(JSON.parse(stored)));
    }

    if (autoStart && !stored) {
      setVisible(true);
    }
  }, [guideKey, autoStart]);

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleComplete = () => {
    const newCompleted = new Set(completedSteps);
    const currentStepKey = steps[currentStep]?.key;
    if (currentStepKey) {
      newCompleted.add(currentStepKey);
    }
    setCompletedSteps(newCompleted);
    localStorage.setItem(STORAGE_KEY_PREFIX + guideKey, JSON.stringify([...newCompleted]));

    if (currentStep === steps.length - 1) {
      setVisible(false);
      onComplete?.();
    } else {
      handleNext();
    }
  };

  const handleSkip = () => {
    setVisible(false);
    onSkip?.();
  };

  const currentStepData = steps[currentStep];
  const progress = ((currentStep + 1) / steps.length) * 100;

  return (
    <>
      <Tooltip title="显示引导">
        <Button type="text" icon={<QuestionCircleOutlined />} aria-label="显示引导" onClick={() => setVisible(true)} />
      </Tooltip>

      <Modal
        open={visible}
        onCancel={handleSkip}
        footer={null}
        width={600}
        closable={false}
        maskClosable={false}
      >
        <div style={{ marginBottom: 24 }}>
          <Progress percent={progress} showInfo={false} strokeColor="#1890ff" />
        </div>

        <Steps current={currentStep} size="small" style={{ marginBottom: 24 }}>
          {steps.map((step, index) => (
            <Steps.Step
              key={step.key}
              title={step.title}
              status={
                completedSteps.has(step.key) ? 'finish' : index === currentStep ? 'process' : 'wait'
              }
            />
          ))}
        </Steps>

        <Card style={{ marginBottom: 24 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Title level={4}>
              {currentStepData?.icon} {currentStepData?.title}
            </Title>
            <Paragraph>{currentStepData?.description}</Paragraph>
          </Space>
        </Card>

        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Space>
            <Button onClick={handleSkip}>跳过引导</Button>
          </Space>
          <Space>
            {currentStep > 0 && (
              <Button onClick={handlePrev} icon={<LeftOutlined />}>
                上一步
              </Button>
            )}
            <Button
              type="primary"
              onClick={handleComplete}
              icon={currentStep === steps.length - 1 ? <CheckCircleOutlined /> : <RightOutlined />}
            >
              {currentStep === steps.length - 1 ? '完成' : '下一步'}
            </Button>
          </Space>
        </div>
      </Modal>
    </>
  );
};

interface QuickTipProps {
  title: string;
  content: string;
  type?: 'info' | 'success' | 'warning' | 'error';
  dismissible?: boolean;
  onDismiss?: () => void;
}

export const QuickTip: React.FC<QuickTipProps> = ({
  title,
  content,
  type = 'info',
  dismissible = true,
  onDismiss,
}) => {
  const [visible, setVisible] = useState(true);

  const handleDismiss = () => {
    setVisible(false);
    onDismiss?.();
  };

  if (!visible) return null;

  const colorMap = {
    info: '#1890ff',
    success: '#52c41a',
    warning: '#faad14',
    error: '#ff4d4f',
  };

  return (
    <Card
      size="small"
      style={{
        borderLeft: `3px solid ${colorMap[type]}`,
        marginBottom: 16,
      }}
      extra={
        dismissible && (
          <Button type="text" size="small" icon={<CloseOutlined />} aria-label="关闭提示" onClick={handleDismiss} />
        )
      }
    >
      <Space>
        <BulbOutlined style={{ color: colorMap[type] }} />
        <div>
          <Text strong>{title}</Text>
          <br />
          <Text type="secondary">{content}</Text>
        </div>
      </Space>
    </Card>
  );
};

interface FeatureHighlightProps {
  features: {
    key: string;
    title: string;
    description: string;
    icon?: React.ReactNode;
    tag?: string;
  }[];
  title?: string;
}

export const FeatureHighlight: React.FC<FeatureHighlightProps> = ({
  features,
  title = '功能亮点',
}) => {
  return (
    <Card title={title} size="small">
      <Space direction="vertical" style={{ width: '100%' }}>
        {features.map((feature) => (
          <Card key={feature.key} size="small" hoverable>
            <Space>
              {feature.icon && <div style={{ fontSize: 24 }}>{feature.icon}</div>}
              <div>
                <Space>
                  <Text strong>{feature.title}</Text>
                  {feature.tag && <Tag color="blue">{feature.tag}</Tag>}
                </Space>
                <br />
                <Text type="secondary">{feature.description}</Text>
              </div>
            </Space>
          </Card>
        ))}
      </Space>
    </Card>
  );
};

export const GETTING_STARTED_STEPS: GuideStep[] = [
  {
    key: 'welcome',
    title: '欢迎使用微调平台',
    description: '这是一个企业级大模型微调平台，支持 LoRA/QLoRA 微调、模型管理、推理服务等功能。',
  },
  {
    key: 'device',
    title: '检查设备状态',
    description:
      '首先检查您的设备状态，确保 GPU 可用。前往"设备信息"页面查看 GPU、CPU 和内存状态。',
  },
  {
    key: 'model',
    title: '下载模型',
    description:
      '前往"模型管理"页面，下载您想要微调的基础模型。支持从 HuggingFace 下载或使用本地模型。',
  },
  {
    key: 'dataset',
    title: '准备数据集',
    description:
      '前往"数据集管理"页面，上传您的训练数据。支持 JSONL 格式，每行包含 input 和 output 字段。',
  },
  {
    key: 'training',
    title: '开始训练',
    description:
      '前往"训练"页面，选择模型和数据集，配置训练参数，然后开始训练。您可以通过进度条实时监控训练状态。',
  },
  {
    key: 'inference',
    title: '测试推理',
    description: '训练完成后，前往"推理"页面测试微调后的模型效果。支持对话和文本生成两种模式。',
  },
];

export default UserGuide;
