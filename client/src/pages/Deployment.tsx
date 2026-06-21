import {
  ApiOutlined,
  CheckCircleFilled,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  HistoryOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import {
  Button,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Popconfirm,
  Space,
  Steps,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import PageHeader from '../components/shared/PageHeader';
import {
  API_BASE_URL,
  activateDeploymentPackage,
  checkDeploymentHealth,
  createDeploymentPackage,
  deactivateDeploymentPackage,
  deleteDeploymentPackage,
  getDeploymentPackage,
  listDeploymentPackages,
  rollbackDeploymentPackage,
} from '../services/api';
import { getTrainingHistory } from '../services/trainingApi';
import type { DeploymentPackage } from '../types';
import styles from './Deployment.module.css';

const { Text, Title } = Typography;

type DeploymentPackageSummary = {
  package_id: string;
  training_task_id?: string;
  evaluation_run_id?: string;
  created_at?: string;
  model_name?: string;
  status?: 'draft' | 'active' | 'inactive';
  activated_at?: string | null;
  health?: DeploymentPackage['health'];
};

const statusMeta = {
  draft: { color: 'blue', label: '草稿' },
  active: { color: 'green', label: '在线' },
  inactive: { color: 'default', label: '已停用' },
} as const;

const formatPercent = (value?: number) =>
  typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—';

export default function Deployment() {
  const [form] = Form.useForm();
  const [searchParams] = useSearchParams();
  const [selected, setSelected] = useState<DeploymentPackage | null>(null);
  const [history, setHistory] = useState<DeploymentPackageSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const watchedTrainingTaskId = Form.useWatch('training_task_id', form) as string | undefined;

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const items = await listDeploymentPackages(100);
      setHistory(Array.isArray(items) ? items : []);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    void loadHistory();
  }, []);

  useEffect(() => {
    const values: Record<string, string> = {};
    [
      'training_task_id',
      'base_model',
      'adapter_path',
      'merged_model_path',
      'evaluation_run_id',
      'model_alias',
    ].forEach((key) => {
      const value = searchParams.get(key);
      if (value) values[key] = value;
    });
    if (Object.keys(values).length) form.setFieldsValue(values);
  }, [form, searchParams]);

  useEffect(() => {
    if (!watchedTrainingTaskId) return;
    void getTrainingHistory().then((records) => {
      const record = records.find((item) => item.id === watchedTrainingTaskId);
      if (!record) return;
      form.setFieldsValue({
        base_model: form.getFieldValue('base_model') || record.baseModelId,
        adapter_path: form.getFieldValue('adapter_path') || record.adapterPath,
        merged_model_path:
          form.getFieldValue('merged_model_path') ||
          (record.method === 'full' ? record.checkpointPath || record.outputPath : undefined),
        evaluation_run_id:
          form.getFieldValue('evaluation_run_id') || record.evaluationRunId,
      });
    });
  }, [form, watchedTrainingTaskId]);

  const openPackage = async (packageId: string) => {
    setAction(`open:${packageId}`);
    try {
      const payload = await getDeploymentPackage(packageId);
      setSelected(payload);
      form.setFieldsValue({
        training_task_id: payload.training_task_id,
        base_model: payload.base_model,
        adapter_path: payload.adapter_path,
        merged_model_path: payload.merged_model_path,
        evaluation_run_id: payload.evaluation_run_id,
        model_alias: payload.inference_target?.model_alias,
      });
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '打开发布版本失败');
    } finally {
      setAction(null);
    }
  };

  const createPackage = async (values: Record<string, string>) => {
    setAction('create');
    try {
      const payload = await createDeploymentPackage({
        ...values,
        service_base_url: API_BASE_URL,
      });
      setSelected(payload);
      await loadHistory();
      message.success('发布草稿已创建，健康检查通过后即可激活');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '创建发布草稿失败');
    } finally {
      setAction(null);
    }
  };

  const runAction = async (
    name: string,
    handler: (packageId: string) => Promise<DeploymentPackage>,
    success: string,
  ) => {
    if (!selected) return;
    setAction(name);
    try {
      const payload = await handler(selected.package_id);
      setSelected(payload);
      await loadHistory();
      message.success(success);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '操作失败');
    } finally {
      setAction(null);
    }
  };

  const deletePackage = async (packageId: string) => {
    setAction(`delete:${packageId}`);
    try {
      await deleteDeploymentPackage(packageId);
      if (selected?.package_id === packageId) setSelected(null);
      await loadHistory();
      message.success('发布草稿已删除');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '删除失败');
    } finally {
      setAction(null);
    }
  };

  const gate = selected?.evaluation_gate;
  const metrics = gate?.metrics || {};
  const releaseStatus = selected?.status || 'draft';
  const pipelineStep = releaseStatus === 'active' ? 3 : selected ? 2 : 1;
  const examples = selected?.openai_compatible_examples || {};
  const envText = selected
    ? Object.entries(selected.env_template).map(([key, value]) => `${key}=${value}`).join('\n')
    : '';
  const scoreCoverage = useMemo(() => {
    const count = gate?.case_count || 0;
    const scored = metrics.scored_count ?? metrics.human_score_count ?? 0;
    return count ? scored / count : undefined;
  }, [gate?.case_count, metrics.human_score_count, metrics.scored_count]);

  const copy = async (content: string) => {
    await navigator.clipboard.writeText(content);
    message.success('已复制');
  };

  const download = () => {
    if (!selected) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(selected, null, 2)], { type: 'application/json' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${selected.package_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={styles.page}>
      <PageHeader
        title="发布控制台"
        icon={<ApiOutlined />}
        helpTooltip="以不可变训练制品和独立评估证据创建、检查、激活和回滚在线发布。"
      />

      <section className={styles.pipeline}>
        <Steps
          current={pipelineStep}
          items={[
            { title: '训练完成', description: selected?.training_task_id || '选择训练任务' },
            { title: '评估通过', description: selected?.evaluation_run_id || '绑定质量证据' },
            { title: '发布草稿', description: selected?.package_id || '创建候选版本' },
            { title: '在线服务', description: releaseStatus === 'active' ? '当前别名已生效' : '尚未激活' },
          ]}
        />
      </section>

      <div className={styles.workspace}>
        <aside className={styles.leftRail}>
          <section className={styles.panel}>
            <Title level={4}>选择发布</Title>
            <Form form={form} layout="vertical" onFinish={createPackage}>
              <Form.Item name="training_task_id" label="训练任务" rules={[{ required: true }]}>
                <Input placeholder="train_..." />
              </Form.Item>
              <Form.Item name="evaluation_run_id" label="评估运行" rules={[{ required: true }]}>
                <Input placeholder="eval_..." />
              </Form.Item>
              <Form.Item name="model_alias" label="模型别名" rules={[{ required: true }]}>
                <Input placeholder="customer-support-v1" />
              </Form.Item>
              <Form.Item name="base_model" hidden><Input /></Form.Item>
              <Form.Item name="adapter_path" hidden><Input /></Form.Item>
              <Form.Item name="merged_model_path" hidden><Input /></Form.Item>
              <Button type="primary" htmlType="submit" block loading={action === 'create'}>
                创建发布草稿
              </Button>
            </Form>
          </section>

          <section className={styles.panel}>
            <div className={styles.sectionHeading}>
              <Title level={4}>版本列表</Title>
              <Button type="text" icon={<ReloadOutlined />} onClick={() => void loadHistory()} />
            </div>
            <List
              loading={historyLoading}
              dataSource={history}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无发布版本" /> }}
              renderItem={(item) => {
                const meta = statusMeta[item.status || 'draft'];
                return (
                  <List.Item
                    className={`${styles.releaseRow} ${selected?.package_id === item.package_id ? styles.selectedRow : ''}`}
                    onClick={() => void openPackage(item.package_id)}
                    actions={[
                      <Popconfirm
                        key="delete"
                        title="删除发布草稿？"
                        disabled={item.status === 'active'}
                        onConfirm={() => void deletePackage(item.package_id)}
                      >
                        <Button
                          type="text"
                          danger
                          disabled={item.status === 'active'}
                          loading={action === `delete:${item.package_id}`}
                          icon={<DeleteOutlined />}
                        />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={<Space>{item.model_name || item.package_id}<Tag color={meta.color}>{meta.label}</Tag></Space>}
                      description={`${item.evaluation_run_id || '未绑定评估'} · ${item.created_at || '—'}`}
                    />
                  </List.Item>
                );
              }}
            />
          </section>
        </aside>

        <main className={styles.main}>
          {!selected ? (
            <section className={`${styles.panel} ${styles.empty}`}>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="选择一个版本，或从已通过评估的训练任务创建发布草稿"
              />
            </section>
          ) : (
            <>
              <section className={styles.panel}>
                <div className={styles.releaseHeader}>
                  <div>
                    <Text type="secondary">发布概览</Text>
                    <Title level={3}>{selected.inference_target?.model_alias || selected.package_id}</Title>
                  </div>
                  <Space>
                    <Tag color={statusMeta[releaseStatus].color}>{statusMeta[releaseStatus].label}</Tag>
                    <Button icon={<DownloadOutlined />} onClick={download}>下载 JSON</Button>
                  </Space>
                </div>
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="训练来源">{selected.training_task_id}</Descriptions.Item>
                  <Descriptions.Item label="评估来源">{selected.evaluation_run_id}</Descriptions.Item>
                  <Descriptions.Item label="基础模型">{selected.base_model}</Descriptions.Item>
                  <Descriptions.Item label="后端">{selected.inference_target?.backend}</Descriptions.Item>
                  <Descriptions.Item label="制品身份" span={2}>
                    <Text code copyable>{gate?.artifact_digest || selected.health?.artifact_digest || '等待健康检查'}</Text>
                  </Descriptions.Item>
                </Descriptions>
              </section>

              <div className={styles.evidenceGrid}>
                <section className={styles.panel}>
                  <div className={styles.sectionHeading}>
                    <Title level={4}>质量门禁</Title>
                    <Tag color={gate?.passed ? 'green' : 'red'}>
                      {gate?.passed ? <><CheckCircleFilled /> 已通过</> : '未通过'}
                    </Tag>
                  </div>
                  <div className={styles.metricTable}>
                    <div><span>独立样本数</span><strong>{gate?.case_count || '—'}</strong></div>
                    <div><span>评分覆盖率</span><strong>{formatPercent(scoreCoverage)}</strong></div>
                    <div><span>胜率</span><strong>{formatPercent(metrics.win_rate)}</strong></div>
                    <div><span>净胜率</span><strong>{formatPercent(metrics.net_win_rate)}</strong></div>
                    <div><span>数据隔离</span><strong>{gate?.data_provenance?.isolated_from_training ? '已验证' : '未验证'}</strong></div>
                  </div>
                </section>

                <section className={styles.panel}>
                  <div className={styles.sectionHeading}>
                    <Title level={4}>部署健康</Title>
                    <Tag color={selected.health?.status === 'healthy' ? 'green' : selected.health?.status === 'failed' ? 'red' : 'default'}>
                      {selected.health?.status === 'healthy' ? '健康' : selected.health?.status === 'failed' ? '失败' : '未检查'}
                    </Tag>
                  </div>
                  <Text>{selected.health?.detail || '激活前会验证制品存在性和评估身份。'}</Text>
                  <div className={styles.healthAction}>
                    <Button
                      icon={<SafetyCertificateOutlined />}
                      loading={action === 'health'}
                      onClick={() => void runAction('health', checkDeploymentHealth, '健康检查完成')}
                    >
                      健康检查
                    </Button>
                  </div>
                </section>
              </div>

              <section className={styles.actionBar}>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  disabled={releaseStatus === 'active'}
                  loading={action === 'activate'}
                  onClick={() => void runAction('activate', activateDeploymentPackage, '发布已激活')}
                >
                  激活发布
                </Button>
                <Button
                  icon={<PauseCircleOutlined />}
                  disabled={releaseStatus !== 'active'}
                  loading={action === 'deactivate'}
                  onClick={() => void runAction('deactivate', deactivateDeploymentPackage, '发布已停用')}
                >
                  停用
                </Button>
                <Popconfirm
                  title="回滚到该别名的上一个版本？"
                  onConfirm={() => void runAction('rollback', rollbackDeploymentPackage, '已回滚到上一版本')}
                >
                  <Button icon={<HistoryOutlined />} loading={action === 'rollback'}>回滚</Button>
                </Popconfirm>
                <Text type="secondary">只有 active 版本会被推理别名解析。</Text>
              </section>

              <section className={styles.panel}>
                <div className={styles.sectionHeading}><Title level={4}><CodeOutlined /> 接入示例</Title></div>
                <Tabs
                  items={[
                    ...Object.entries(examples).map(([key, value]) => ({
                      key,
                      label: key,
                      children: <CodePane content={value} onCopy={copy} />,
                    })),
                    {
                      key: 'env',
                      label: '.env',
                      children: <CodePane content={envText} onCopy={copy} />,
                    },
                  ]}
                />
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function CodePane({ content, onCopy }: { content: string; onCopy: (value: string) => Promise<void> }) {
  return (
    <div className={styles.codePane}>
      <Button size="small" icon={<CopyOutlined />} onClick={() => void onCopy(content)}>复制</Button>
      <pre>{content}</pre>
    </div>
  );
}
