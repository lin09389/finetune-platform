import {
  CheckCircleOutlined,
  CodeOutlined,
  PartitionOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, Modal, Select, Space, Tag, message } from 'antd';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  approveWorkflowStep,
  createWorkflow,
  getSavedCloudProviders,
  getWorkflow,
  getWorkflowArtifacts,
  getWorkflowTemplates,
  getWorkflowTimeline,
  getWorkflows,
  retryWorkflowStep,
  runWorkflow,
} from '../services/api';
import type { SavedCloudProvider, Workflow, WorkflowStep, WorkflowTemplate } from '../services/api';
import styles from './DigitalTeam.module.css';

const stepMeta: Record<string, { label: string; icon: ReactNode }> = {
  plan: { label: 'Plan', icon: <PartitionOutlined /> },
  implement: { label: 'Implement', icon: <CodeOutlined /> },
  review: { label: 'Review', icon: <SafetyCertificateOutlined /> },
};

const statusColor: Record<string, string> = {
  draft: 'default',
  planning: 'processing',
  awaiting_approval: 'warning',
  implementing: 'processing',
  reviewing: 'processing',
  completed: 'success',
  failed: 'error',
  running: 'processing',
  approved: 'success',
  needs_manual_review: 'warning',
};

function compactJson(value: any) {
  if (!value || Object.keys(value).length === 0) {
    return '暂无输出';
  }
  if (value.summary) {
    return [value.summary, value.next_action].filter(Boolean).join('\n\n');
  }
  return JSON.stringify(value, null, 2);
}

export default function Workflows() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [cloudProviders, setCloudProviders] = useState<SavedCloudProvider[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const selectedFormProvider = Form.useWatch('provider', form);

  const selectedId = selectedWorkflow?.workflow_id || selectedWorkflow?.id;

  useEffect(() => {
    void loadInitialData();
  }, []);

  useEffect(() => {
    if (selectedId) {
      void loadWorkflowDetails(selectedId);
    }
  }, [selectedId]);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const [templateData, workflowData, providerData] = await Promise.all([
        getWorkflowTemplates(),
        getWorkflows(),
        getSavedCloudProviders().catch(() => ({ keys: [] })),
      ]);
      const items: Workflow[] = workflowData || [];
      const preferredId = searchParams.get('workflow');
      setTemplates(templateData || []);
      setWorkflows(items);
      setCloudProviders(providerData?.keys || []);
      setSelectedWorkflow(items.find((item) => item.workflow_id === preferredId || item.id === preferredId) || items[0] || null);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '工作流数据加载失败');
    } finally {
      setLoading(false);
    }
  };

  const loadWorkflowDetails = async (workflowId: string) => {
    try {
      const [workflow, timelineData, artifactData] = await Promise.all([
        getWorkflow(workflowId),
        getWorkflowTimeline(workflowId),
        getWorkflowArtifacts(workflowId),
      ]);
      setSelectedWorkflow(workflow);
      setTimeline(timelineData?.events || []);
      setArtifacts(artifactData?.artifacts || []);
      setWorkflows((items) => items.map((item) => (item.id === workflow.id ? workflow : item)));
      if (searchParams.get('workflow') !== workflow.workflow_id) {
        setSearchParams({ workflow: workflow.workflow_id });
      }
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '工作流详情加载失败');
    }
  };

  const handleCreate = async (values: any) => {
    try {
      const workflow = await createWorkflow({
        title: values.title,
        goal: values.goal,
        template_id: values.template_id || 'software_delivery',
        project_path: values.project_path,
        provider: values.provider || 'minimax',
        model: values.model,
        approval_mode: 'manual',
      });
      message.success('工作流已创建');
      setCreateOpen(false);
      form.resetFields();
      setWorkflows((items) => [workflow, ...items]);
      setSelectedWorkflow(workflow);
      setSearchParams({ workflow: workflow.workflow_id });
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '创建失败');
    }
  };

  const handleRun = async () => {
    if (!selectedWorkflow) return;
    setLoading(true);
    try {
      const workflow = await runWorkflow(selectedWorkflow.workflow_id);
      setSelectedWorkflow(workflow);
      await loadWorkflowDetails(workflow.workflow_id);
      message.success('工作流已生成计划节点');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '运行失败');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (stepId: string) => {
    setLoading(true);
    try {
      const workflow = await approveWorkflowStep(stepId, { approved: true });
      setSelectedWorkflow(workflow);
      await loadWorkflowDetails(workflow.workflow_id);
      message.success('审批已通过');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '审批失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async (stepId: string) => {
    setLoading(true);
    try {
      const workflow = await retryWorkflowStep(stepId);
      setSelectedWorkflow(workflow);
      await loadWorkflowDetails(workflow.workflow_id);
      message.success('步骤已重试');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '重试失败');
    } finally {
      setLoading(false);
    }
  };

  const actionableSteps = useMemo(
    () =>
      (selectedWorkflow?.steps || []).filter((step) =>
        ['awaiting_approval', 'needs_manual_review', 'failed'].includes(step.status),
      ),
    [selectedWorkflow],
  );

  const stepsByKey = useMemo(() => {
    const map: Record<string, WorkflowStep | undefined> = {};
    (selectedWorkflow?.steps || []).forEach((step) => {
      map[step.step_key] = step;
    });
    return map;
  }, [selectedWorkflow]);

  const providerOptions = useMemo(() => {
    const savedOptions = cloudProviders.map((provider) => ({
      value: provider.provider,
      label: `${provider.name || provider.provider} (${provider.provider})`,
    }));
    return savedOptions.length
      ? savedOptions
      : [
          { value: 'minimax', label: 'Minimax' },
          { value: 'minimax-coding', label: 'Minimax Coding' },
          { value: 'glm', label: 'GLM' },
        ];
  }, [cloudProviders]);

  const selectedCloudProvider = useMemo(
    () => cloudProviders.find((provider) => provider.provider === selectedFormProvider),
    [cloudProviders, selectedFormProvider],
  );

  const modelOptions = useMemo(() => {
    const models = selectedCloudProvider?.models?.length
      ? selectedCloudProvider.models
      : selectedCloudProvider?.default_model
        ? [selectedCloudProvider.default_model]
        : [];
    return models.map((model) => ({ value: model, label: model }));
  }, [selectedCloudProvider]);

  const openCreateModal = () => {
    const defaultProvider = cloudProviders[0]?.provider || 'minimax';
    const defaultModel = cloudProviders[0]?.default_model || cloudProviders[0]?.models?.[0] || undefined;
    form.setFieldsValue({
      provider: defaultProvider,
      model: defaultModel,
      template_id: 'software_delivery',
    });
    setCreateOpen(true);
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>
            <PartitionOutlined /> 多 Agent 工作流
          </h2>
          <p>用通用工作流视角编排 Planner、Implementer、Reviewer，关键步骤由你审批。</p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadInitialData} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            新建工作流
          </Button>
        </Space>
      </div>

      <div className={styles.layout}>
        <aside className={styles.panel}>
          <h3 className={styles.panelTitle}>模板</h3>
          <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
            {(templates.length
              ? templates
              : [{ id: 'software_delivery', name: 'AI 软件交付流程', description: 'Plan / Implement / Review' }]
            ).map((template) => (
              <div key={template.id} className={styles.projectItem}>
                <div className={styles.projectTitle}>{template.name}</div>
                <div className={styles.projectMeta}>{template.description}</div>
              </div>
            ))}
          </Space>

          <h3 className={styles.panelTitle}>工作流列表</h3>
          <div className={styles.projectList}>
            {workflows.map((workflow) => (
              <button
                key={workflow.workflow_id}
                type="button"
                className={`${styles.projectItem} ${
                  selectedWorkflow?.workflow_id === workflow.workflow_id ? styles.projectItemActive : ''
                }`}
                onClick={() => {
                  setSelectedWorkflow(workflow);
                  setSearchParams({ workflow: workflow.workflow_id });
                }}
              >
                <div className={styles.projectTitle}>{workflow.title}</div>
                <div className={styles.projectMeta}>
                  <Tag color={statusColor[workflow.status] || 'default'}>{workflow.status}</Tag>
                  {new Date(workflow.updated_at).toLocaleString()}
                </div>
              </button>
            ))}
            {!workflows.length && <div className={styles.emptyState}>暂无工作流</div>}
          </div>
        </aside>

        <main className={styles.panel}>
          <div className={styles.header}>
            <div>
              <h3 className={styles.panelTitle}>{selectedWorkflow?.title || '选择或创建一个工作流'}</h3>
              {selectedWorkflow && (
                <Tag color={statusColor[selectedWorkflow.status] || 'default'}>
                  {selectedWorkflow.status}
                </Tag>
              )}
            </div>
            {selectedWorkflow?.status === 'draft' && (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleRun} loading={loading}>
                运行工作流
              </Button>
            )}
          </div>

          {selectedWorkflow ? (
            <>
              <div className={styles.outputBox}>{selectedWorkflow.goal}</div>
              <div className={styles.board} style={{ marginTop: 16 }}>
                {['plan', 'implement', 'review'].map((stepKey) => {
                  const step = stepsByKey[stepKey];
                  const meta = stepMeta[stepKey] || { label: stepKey, icon: null };
                  return (
                    <div key={stepKey} className={styles.taskCard}>
                      <div className={styles.taskHeader}>
                        <span className={styles.taskRole}>
                          {meta.icon} {meta.label}
                        </span>
                        <Tag color={statusColor[step?.status || 'pending'] || 'default'}>
                          {step?.status || 'pending'}
                        </Tag>
                      </div>
                      <p className={styles.taskDescription}>
                        {step?.description || '等待上一节点完成。'}
                      </p>
                      {step && <div className={styles.outputBox}>{compactJson(step.output_data || step.output)}</div>}
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>创建工作流后，步骤流程会显示在这里</div>
          )}
        </main>

        <aside className={styles.panel}>
          <h3 className={styles.panelTitle}>审批与操作</h3>
          <Space direction="vertical" style={{ width: '100%' }}>
            {actionableSteps.map((step) => (
              <div key={step.step_id} className={styles.artifactItem}>
                <div className={styles.artifactTitle}>{step.title}</div>
                <div className={styles.projectMeta}>
                  {step.agent_id} · {step.status}
                </div>
                <Space style={{ marginTop: 10 }}>
                  {step.status !== 'failed' && (
                    <Button
                      type="primary"
                      size="small"
                      icon={<CheckCircleOutlined />}
                      onClick={() => handleApprove(step.step_id)}
                      loading={loading}
                    >
                      审批通过
                    </Button>
                  )}
                  <Button size="small" icon={<ReloadOutlined />} onClick={() => handleRetry(step.step_id)} loading={loading}>
                    重试
                  </Button>
                </Space>
              </div>
            ))}
            {!actionableSteps.length && <div className={styles.emptyState}>暂无待处理步骤</div>}
          </Space>

          <h3 className={styles.panelTitle} style={{ marginTop: 18 }}>
            时间线
          </h3>
          <div className={styles.timeline}>
            {timeline.map((event) => (
              <div key={event.id} className={styles.eventItem}>
                <div className={styles.eventMessage}>{event.message}</div>
                <div className={styles.eventTime}>{new Date(event.created_at).toLocaleString()}</div>
              </div>
            ))}
            {!timeline.length && <div className={styles.emptyState}>暂无事件</div>}
          </div>

          <h3 className={styles.panelTitle} style={{ marginTop: 18 }}>
            产物
          </h3>
          <div className={styles.artifactList}>
            {artifacts.map((artifact) => (
              <div key={artifact.id} className={styles.artifactItem}>
                <div className={styles.artifactTitle}>{artifact.title}</div>
                <div className={styles.projectMeta}>{artifact.artifact_type}</div>
                <div className={styles.artifactContent}>
                  {JSON.stringify(artifact.content, null, 2)}
                </div>
              </div>
            ))}
            {!artifacts.length && <div className={styles.emptyState}>暂无产物</div>}
          </div>
        </aside>
      </div>

      <Modal
        title="新建工作流"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={loading}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="title" label="工作流名称" rules={[{ required: true, message: '请输入工作流名称' }]}>
            <Input placeholder="例如：新增通用工作流页面" />
          </Form.Item>
          <Form.Item name="goal" label="目标" rules={[{ required: true, message: '请输入目标' }]}>
            <Input.TextArea rows={5} placeholder="描述你希望多 Agent 工作流完成的目标" />
          </Form.Item>
          <Form.Item name="project_path" label="项目路径">
            <Input placeholder="默认可留空；例如 C:\\Users\\JHJ\\Desktop\\finetune-platform" />
          </Form.Item>
          <Form.Item name="template_id" label="工作流模板" initialValue="software_delivery">
            <Select
              options={(templates.length ? templates : [{ id: 'software_delivery', name: 'AI 软件交付流程' }]).map(
                (template) => ({ value: template.id, label: template.name }),
              )}
            />
          </Form.Item>
          <Space style={{ width: '100%' }} align="start">
            <Form.Item
              name="provider"
              label="云端服务商"
              initialValue={cloudProviders[0]?.provider || 'minimax'}
              rules={[{ required: true, message: '请选择云端服务商' }]}
              extra={cloudProviders.length ? '来自云端 API 页面已保存的供应商配置' : '暂无已保存配置，先显示内置服务商'}
            >
              <Select
                style={{ width: 240 }}
                options={providerOptions}
                onChange={(provider) => {
                  const savedProvider = cloudProviders.find((item) => item.provider === provider);
                  form.setFieldValue(
                    'model',
                    savedProvider?.default_model || savedProvider?.models?.[0] || undefined,
                  );
                }}
              />
            </Form.Item>
            <Form.Item name="model" label="模型">
              <Select
                allowClear
                showSearch
                style={{ width: 260 }}
                placeholder="留空使用供应商默认模型"
                options={modelOptions}
                optionFilterProp="label"
                notFoundContent={selectedCloudProvider ? '该供应商没有保存模型，可留空使用默认模型' : '请选择供应商'}
              />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
