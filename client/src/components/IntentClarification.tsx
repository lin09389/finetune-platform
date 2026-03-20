import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  Card,
  Button,
  List,
  Tag,
  Progress,
  Space,
  Typography,
  Alert,
  Input,
  message as antdMessage,
  Tooltip,
  Badge,
  Collapse,
  Empty,
  Spin,
} from 'antd';
import {
  QuestionCircleOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
  BulbOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  AppstoreOutlined,
  GlobalOutlined,
  DesktopOutlined,
} from '@ant-design/icons';

const { Text, Title, Paragraph } = Typography;
const { Panel } = Collapse;

interface ExtractedParam {
  name: string;
  value: any;
  param_type: string;
  confidence: number;
  raw_text: string;
}

interface DetectedIntent {
  intent_type: string;
  action: string;
  params: ExtractedParam[];
  confidence: number;
  description: string;
  need_clarification: boolean;
  clarification_question: string;
  raw_match: string;
}

interface ClarificationOption {
  label: string;
  value: string;
  action?: string;
  intent?: DetectedIntent;
}

interface ClarificationDialog {
  dialog_id: string;
  question: string;
  options: ClarificationOption[];
  context: Record<string, any>;
  created_at: string;
}

interface IntentClarificationProps {
  visible: boolean;
  message: string;
  onConfirm: (intent: DetectedIntent, params: Record<string, any>) => void;
  onCancel: () => void;
  onMultiIntentSelect?: (intents: DetectedIntent[]) => void;
  context?: Record<string, any>;
}

const INTENT_TYPE_ICONS: Record<string, React.ReactNode> = {
  file_operation: <FileTextOutlined />,
  code_execution: <ThunderboltOutlined />,
  system_operation: <DesktopOutlined />,
  information_query: <InfoCircleOutlined />,
  app_control: <AppstoreOutlined />,
  browser_operation: <GlobalOutlined />,
  cua_operation: <DesktopOutlined />,
  unknown: <QuestionCircleOutlined />,
};

const INTENT_TYPE_COLORS: Record<string, string> = {
  file_operation: 'blue',
  code_execution: 'purple',
  system_operation: 'orange',
  information_query: 'cyan',
  app_control: 'green',
  browser_operation: 'geekblue',
  cua_operation: 'magenta',
  unknown: 'default',
};

const getConfidenceColor = (confidence: number): string => {
  if (confidence >= 0.9) return 'success';
  if (confidence >= 0.7) return 'warning';
  return 'error';
};

const getConfidenceText = (confidence: number): string => {
  if (confidence >= 0.9) return '高置信度';
  if (confidence >= 0.7) return '中等置信度';
  return '低置信度';
};

const IntentClarification: React.FC<IntentClarificationProps> = ({
  visible,
  message,
  onConfirm,
  onCancel,
  onMultiIntentSelect,
  context,
}) => {
  const [loading, setLoading] = useState(false);
  const [detectedIntents, setDetectedIntents] = useState<DetectedIntent[]>([]);
  const [hasAmbiguity, setHasAmbiguity] = useState(false);
  const [clarificationDialog, setClarificationDialog] = useState<ClarificationDialog | null>(null);
  const [selectedIntent, setSelectedIntent] = useState<DetectedIntent | null>(null);
  const [customParams, setCustomParams] = useState<Record<string, string>>({});
  const [showParamInput, setShowParamInput] = useState(false);

  const detectIntent = useCallback(async () => {
    if (!message) return;

    setLoading(true);
    try {
      const response = await fetch('/api/agent/detect-intent-enhanced', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, context }),
      });

      const data = await response.json();

      if (data.detected) {
        setDetectedIntents(data.intents);
        setHasAmbiguity(data.has_ambiguity);
        setClarificationDialog(data.clarification_dialog);

        if (data.intents.length === 1 && !data.has_ambiguity) {
          setSelectedIntent(data.intents[0]);
        }
      } else {
        antdMessage.warning('未能检测到明确的意图');
        setDetectedIntents([]);
      }
    } catch (error) {
      console.error('意图检测失败:', error);
      antdMessage.error('意图检测失败');
    } finally {
      setLoading(false);
    }
  }, [message, context]);

  useEffect(() => {
    if (visible && message) {
      detectIntent();
    }
  }, [visible, message, detectIntent]);

  useEffect(() => {
    return () => {
      setDetectedIntents([]);
      setSelectedIntent(null);
      setClarificationDialog(null);
      setCustomParams({});
      setShowParamInput(false);
    };
  }, [visible]);

  const handleIntentSelect = (intent: DetectedIntent) => {
    setSelectedIntent(intent);
    
    const missingParams = checkMissingParams(intent);
    if (missingParams.length > 0) {
      setShowParamInput(true);
    }
  };

  const checkMissingParams = (intent: DetectedIntent): string[] => {
    const requiredParams: Record<string, string[]> = {
      file_create: ['file_path'],
      file_read: ['file_path'],
      file_write: ['file_path', 'content'],
      file_delete: ['file_path'],
      app_open: ['app_name'],
      url_open: ['url'],
      mouse_click: ['x', 'y'],
      keyboard_type: ['text'],
    };

    const required = requiredParams[intent.action] || [];
    const existing = intent.params.map(p => p.name);
    
    return required.filter(p => !existing.includes(p) || !intent.params.find(ep => ep.name === p)?.value);
  };

  const handleConfirm = () => {
    if (!selectedIntent) return;

    const params: Record<string, any> = {};
    selectedIntent.params.forEach(p => {
      params[p.name] = p.value;
    });

    Object.entries(customParams).forEach(([key, value]) => {
      if (value) params[key] = value;
    });

    onConfirm(selectedIntent, params);
  };

  const handleMultiIntentConfirm = () => {
    if (onMultiIntentSelect && detectedIntents.length > 0) {
      onMultiIntentSelect(detectedIntents);
    }
  };

  const handleClarificationResponse = async (response: string) => {
    if (!clarificationDialog) return;

    try {
      const res = await fetch('/api/agent/clarification/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dialog_id: clarificationDialog.dialog_id,
          response,
        }),
      });

      const data = await res.json();

      if (data.success && data.selected_option) {
        if (data.selected_option.value === 'confirm' && data.selected_option.intent) {
          setSelectedIntent(data.selected_option.intent);
        } else if (data.selected_option.value === 'all') {
          handleMultiIntentConfirm();
        } else if (data.selected_option.value === 'cancel') {
          onCancel();
        }
      }
    } catch (error) {
      console.error('处理澄清响应失败:', error);
      antdMessage.error('处理响应失败');
    }
  };

  const renderIntentCard = (intent: DetectedIntent, index: number) => {
    const isSelected = selectedIntent === intent;
    const missingParams = checkMissingParams(intent);

    return (
      <Card
        key={index}
        hoverable
        onClick={() => handleIntentSelect(intent)}
        style={{
          marginBottom: 12,
          border: isSelected ? '2px solid #1890ff' : undefined,
          backgroundColor: isSelected ? '#f0f5ff' : undefined,
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            {INTENT_TYPE_ICONS[intent.intent_type] || <QuestionCircleOutlined />}
            <Text strong>{intent.description}</Text>
            <Tag color={INTENT_TYPE_COLORS[intent.intent_type] || 'default'}>
              {intent.intent_type}
            </Tag>
          </Space>

          <Space>
            <Text type="secondary">操作：</Text>
            <Tag>{intent.action}</Tag>
          </Space>

          <div>
            <Text type="secondary">置信度：</Text>
            <Progress
              percent={Math.round(intent.confidence * 100)}
              size="small"
              status={getConfidenceColor(intent.confidence) as any}
              style={{ width: 150, display: 'inline-block', marginLeft: 8 }}
            />
            <Tag color={getConfidenceColor(intent.confidence)} style={{ marginLeft: 8 }}>
              {getConfidenceText(intent.confidence)}
            </Tag>
          </div>

          {intent.params.length > 0 && (
            <div>
              <Text type="secondary">参数：</Text>
              <Space wrap style={{ marginLeft: 8 }}>
                {intent.params.map((param, i) => (
                  <Tooltip key={i} title={`类型: ${param.param_type}, 置信度: ${(param.confidence * 100).toFixed(0)}%`}>
                    <Tag color="blue">
                      {param.name}: {String(param.value).substring(0, 30)}
                      {String(param.value).length > 30 && '...'}
                    </Tag>
                  </Tooltip>
                ))}
              </Space>
            </div>
          )}

          {missingParams.length > 0 && (
            <Alert
              message={`缺少必要参数: ${missingParams.join(', ')}`}
              type="warning"
              showIcon
              style={{ marginTop: 8 }}
            />
          )}

          {intent.need_clarification && (
            <Alert
              message={intent.clarification_question}
              type="info"
              showIcon
              style={{ marginTop: 8 }}
            />
          )}
        </Space>
      </Card>
    );
  };

  const renderClarificationDialog = () => {
    if (!clarificationDialog) return null;

    return (
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space>
            <BulbOutlined style={{ color: '#faad14' }} />
            <Text strong>{clarificationDialog.question}</Text>
          </Space>
          <Space wrap>
            {clarificationDialog.options.map((option, index) => (
              <Button
                key={index}
                type={option.value === 'confirm' || option.value === 'all' ? 'primary' : 'default'}
                onClick={() => handleClarificationResponse(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </Space>
        </Space>
      </Card>
    );
  };

  const renderParamInput = () => {
    if (!showParamInput || !selectedIntent) return null;

    const missingParams = checkMissingParams(selectedIntent);

    return (
      <Card style={{ marginTop: 16 }}>
        <Title level={5}>请补充缺失参数</Title>
        <Space direction="vertical" style={{ width: '100%' }}>
          {missingParams.map(param => (
            <div key={param}>
              <Text type="secondary">{param}:</Text>
              <Input
                value={customParams[param] || ''}
                onChange={e => setCustomParams({ ...customParams, [param]: e.target.value })}
                placeholder={`请输入 ${param}`}
                style={{ marginTop: 4 }}
              />
            </div>
          ))}
        </Space>
      </Card>
    );
  };

  return (
    <Modal
      title={
        <Space>
          <QuestionCircleOutlined />
          <span>意图确认</span>
        </Space>
      }
      open={visible}
      onCancel={onCancel}
      width={700}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="confirm"
          type="primary"
          onClick={handleConfirm}
          disabled={!selectedIntent}
          icon={<CheckCircleOutlined />}
        >
          确认执行
        </Button>,
        detectedIntents.length > 1 && (
          <Button
            key="all"
            type="default"
            onClick={handleMultiIntentConfirm}
            icon={<ThunderboltOutlined />}
          >
            全部执行
          </Button>
        ),
      ].filter(Boolean)}
    >
      <Spin spinning={loading}>
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <Alert
            message="原始消息"
            description={message}
            type="info"
            showIcon
          />

          {hasAmbiguity && renderClarificationDialog()}

          {detectedIntents.length > 0 ? (
            <>
              <Title level={5}>
                检测到的意图
                <Badge count={detectedIntents.length} style={{ marginLeft: 8 }} />
              </Title>
              <List
                dataSource={detectedIntents}
                renderItem={(intent, index) => renderIntentCard(intent, index)}
              />
            </>
          ) : (
            !loading && (
              <Empty
                description="未检测到明确意图"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )
          )}

          {renderParamInput()}

          {selectedIntent && (
            <Collapse ghost>
              <Panel header="详细信息" key="1">
                <Paragraph>
                  <Text strong>匹配文本：</Text>
                  <Text code>{selectedIntent.raw_match}</Text>
                </Paragraph>
                <Paragraph>
                  <Text strong>意图类型：</Text>
                  <Text>{selectedIntent.intent_type}</Text>
                </Paragraph>
                <Paragraph>
                  <Text strong>操作类型：</Text>
                  <Text>{selectedIntent.action}</Text>
                </Paragraph>
              </Panel>
            </Collapse>
          )}
        </Space>
      </Spin>
    </Modal>
  );
};

export default IntentClarification;
