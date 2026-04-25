import {
  ApiOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Popconfirm,
  Row,
  Space,
  Tabs,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import PageHeader from '../components/shared/PageHeader';
import {
  createDeploymentPackage,
  deleteDeploymentPackage,
  getDeploymentPackage,
  listDeploymentPackages,
} from '../services/api';
import { getTrainingHistory } from '../services/trainingApi';
import type { DeploymentPackage } from '../types';

const { Text } = Typography;

const codeBlockStyle = {
  whiteSpace: 'pre-wrap',
  margin: 0,
  wordBreak: 'break-word',
} as const;

type DeploymentPackageSummary = {
  package_id: string;
  training_task_id?: string;
  created_at?: string;
  base_model?: string;
  adapter_path?: string;
  merged_model_path?: string;
  model_name?: string;
};

export default function Deployment() {
  const [form] = Form.useForm();
  const [searchParams] = useSearchParams();
  const [deploymentPackage, setDeploymentPackage] = useState<DeploymentPackage | null>(null);
  const [packageHistory, setPackageHistory] = useState<DeploymentPackageSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const watchedTrainingTaskId = Form.useWatch('training_task_id', form) as string | undefined;

  const fillFormFromPackage = (payload: DeploymentPackage) => {
    form.setFieldsValue({
      training_task_id: payload.training_task_id,
      base_model: payload.base_model,
      adapter_path: payload.adapter_path,
      merged_model_path: payload.merged_model_path,
      model_alias: payload.env_template?.MODEL_NAME,
      service_base_url: payload.env_template?.OPENAI_BASE_URL?.replace(/\/v1\/?$/, ''),
    });
  };

  const loadPackageHistory = async () => {
    setHistoryLoading(true);
    try {
      const items = await listDeploymentPackages(20);
      setPackageHistory(Array.isArray(items) ? items : []);
    } catch (error) {
      console.error('Failed to load deployment package history:', error);
      setPackageHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    void loadPackageHistory();
  }, []);

  useEffect(() => {
    const values: Record<string, string> = {};
    [
      'training_task_id',
      'base_model',
      'adapter_path',
      'merged_model_path',
      'model_alias',
      'service_base_url',
    ].forEach((key) => {
      const value = searchParams.get(key);
      if (value) values[key] = value;
    });

    if (Object.keys(values).length) {
      form.setFieldsValue(values);
    }
  }, [form, searchParams]);

  useEffect(() => {
    if (!watchedTrainingTaskId) return;

    const resolveFromHistory = async () => {
      try {
        const history = await getTrainingHistory();
        const record = history.find((item) => item.id === watchedTrainingTaskId);
        if (!record) return;

        const values: Record<string, string> = {};
        if (!form.getFieldValue('base_model') && record.baseModelId) {
          values.base_model = record.baseModelId;
        }
        if (!form.getFieldValue('adapter_path') && record.adapterPath) {
          values.adapter_path = record.adapterPath;
        }
        if (
          !form.getFieldValue('merged_model_path') &&
          record.method === 'full' &&
          record.outputPath
        ) {
          values.merged_model_path = record.outputPath;
        }

        if (Object.keys(values).length) {
          form.setFieldsValue(values);
        }
      } catch (error) {
        console.error('Failed to resolve deployment inputs from training history:', error);
      }
    };

    void resolveFromHistory();
  }, [form, watchedTrainingTaskId]);

  const handleCreate = async (values: {
    training_task_id: string;
    base_model: string;
    adapter_path: string;
    merged_model_path?: string;
    model_alias?: string;
    service_base_url?: string;
  }) => {
    setLoading(true);
    try {
      const payload = await createDeploymentPackage({
        service_base_url: 'http://127.0.0.1:8000',
        ...values,
      });
      setDeploymentPackage(payload);
      fillFormFromPackage(payload);
      void loadPackageHistory();
      message.success('部署包已生成');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '生成部署包失败');
    } finally {
      setLoading(false);
    }
  };

  const examples = deploymentPackage?.openai_compatible_examples ?? {};
  const envTemplate = deploymentPackage
    ? Object.entries(deploymentPackage.env_template)
        .map(([key, value]) => `${key}=${value}`)
        .join('\n')
    : '';

  const copyText = async (content: string, label: string) => {
    if (!content) {
      message.warning(`${label} 为空，暂时无法复制`);
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      message.success(`${label} 已复制`);
    } catch {
      message.error(`复制 ${label} 失败，请手动选中内容复制`);
    }
  };

  const downloadPackageJson = (payload: DeploymentPackage) => {
    const content = JSON.stringify(payload, null, 2);
    const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${payload.package_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
    message.success('部署包 JSON 已下载');
  };

  const openPackage = async (packageId: string) => {
    setHistoryLoading(true);
    try {
      const payload = await getDeploymentPackage(packageId);
      setDeploymentPackage(payload);
      fillFormFromPackage(payload);
      message.success('部署包已打开');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '打开部署包失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  const deletePackage = async (packageId: string) => {
    setHistoryLoading(true);
    try {
      await deleteDeploymentPackage(packageId);
      if (deploymentPackage?.package_id === packageId) {
        setDeploymentPackage(null);
      }
      await loadPackageHistory();
      message.success('部署包已删除');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '删除部署包失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title="部署接入台"
        icon={<CloudUploadOutlined />}
        helpTooltip="为微调结果生成 Adapter 路径、Ollama Modelfile 和兼容 OpenAI 的调用示例。"
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={9}>
          <Card title="生成部署包" variant="borderless">
            <Form
              form={form}
              layout="vertical"
              initialValues={{ service_base_url: 'http://127.0.0.1:8000' }}
              onFinish={handleCreate}
            >
              <Form.Item name="training_task_id" label="训练任务 ID" rules={[{ required: true }]}>
                <Input placeholder="train_..." />
              </Form.Item>
              <Form.Item name="base_model" label="基础模型">
                <Input placeholder="qwen2.5:7b" />
              </Form.Item>
              <Form.Item name="adapter_path" label="LoRA Adapter 路径">
                <Input placeholder="outputs/run/adapter" />
              </Form.Item>
              <Form.Item name="merged_model_path" label="合并模型路径">
                <Input placeholder="outputs/run/merged" />
              </Form.Item>
              <Form.Item name="model_alias" label="模型别名">
                <Input placeholder="customer-support-v1" />
              </Form.Item>
              <Form.Item name="service_base_url" label="服务地址">
                <Input />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} icon={<ApiOutlined />}>
                生成部署包
              </Button>
            </Form>
          </Card>

          <Card title="最近部署包" variant="borderless" style={{ marginTop: 16 }}>
            {packageHistory.length ? (
              <List
                loading={historyLoading}
                dataSource={packageHistory}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Button
                        key="open"
                        size="small"
                        type="link"
                        onClick={() => void openPackage(item.package_id)}
                      >
                        打开
                      </Button>,
                      <Popconfirm
                        key="delete"
                        title="删除部署包"
                        description="删除后需要重新生成部署包。"
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => void deletePackage(item.package_id)}
                      >
                        <Button size="small" type="link" danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={item.model_name || item.package_id}
                      description={
                        <Space direction="vertical" size={2}>
                          <Text type="secondary">{item.package_id}</Text>
                          <Text type="secondary">
                            {item.training_task_id || '-'} · {item.created_at || '-'}
                          </Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={historyLoading ? '正在加载部署包' : '暂无部署包'}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={15}>
          {!deploymentPackage ? (
            <Card variant="borderless">
              <Space direction="vertical">
                <Text strong>部署包会包含：</Text>
                <Text>LoRA Adapter 路径、合并模型路径、Ollama Modelfile、curl/Python/TypeScript 调用示例和 .env 模板。</Text>
              </Space>
            </Card>
          ) : (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Card
                title={deploymentPackage.package_id}
                variant="borderless"
                extra={
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    onClick={() => downloadPackageJson(deploymentPackage)}
                  >
                    下载 JSON
                  </Button>
                }
              >
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="训练任务">{deploymentPackage.training_task_id}</Descriptions.Item>
                  <Descriptions.Item label="Adapter">{deploymentPackage.adapter_path}</Descriptions.Item>
                  <Descriptions.Item label="合并模型">
                    {deploymentPackage.merged_model_path || '未提供，先以 Adapter 交付'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>

              <Card title="Ollama 模型文件" variant="borderless">
                <div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                    <Button
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => void copyText(deploymentPackage.ollama_modelfile || '', 'Ollama Modelfile')}
                    >
                      复制
                    </Button>
                  </div>
                  <pre style={codeBlockStyle}>{deploymentPackage.ollama_modelfile}</pre>
                </div>
              </Card>

              <Card title=".env 模板" variant="borderless">
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                  <Button
                    size="small"
                    icon={<CopyOutlined />}
                    onClick={() => void copyText(envTemplate, '.env 模板')}
                  >
                    复制
                  </Button>
                </div>
                <pre style={codeBlockStyle}>{envTemplate}</pre>
              </Card>

              <Card title={<Space><CodeOutlined /> 接入示例</Space>} variant="borderless">
                <Tabs
                  items={Object.entries(examples).map(([key, value]) => ({
                    key,
                    label: key,
                    children: (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                          <Button
                            size="small"
                            icon={<CopyOutlined />}
                            onClick={() => void copyText(value, `${key} 示例`)}
                          >
                            复制
                          </Button>
                        </div>
                        <pre style={codeBlockStyle}>{value}</pre>
                      </>
                    ),
                  }))}
                />
              </Card>
            </Space>
          )}
        </Col>
      </Row>
    </div>
  );
}
