import {
  CheckCircleOutlined,
  CodeOutlined,
  PartitionOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, Modal, Select, Space, Tag, message } from 'antd';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import {
  approveDigitalTeamTask,
  createDigitalTeamProject,
  getDigitalTeamArtifacts,
  getDigitalTeamProject,
  getDigitalTeamProjects,
  getDigitalTeamTemplates,
  getDigitalTeamTimeline,
  getSavedCloudProviders,
  retryDigitalTeamTask,
  runDigitalTeamProject,
} from '../services/api';
import type { SavedCloudProvider } from '../services/api';
import styles from './DigitalTeam.module.css';

interface DigitalTask {
  id: string;
  role: string;
  title: string;
  description: string;
  status: string;
  requires_approval: boolean;
  output?: any;
  error?: string;
}

interface DigitalProject {
  id: string;
  title: string;
  goal: string;
  template_id: string;
  project_path?: string;
  provider: string;
  model?: string;
  approval_mode: string;
  status: string;
  current_stage?: string;
  tasks: DigitalTask[];
  updated_at: string;
}

interface TeamTemplate {
  id: string;
  name: string;
  description: string;
}

const roleMeta: Record<string, { label: string; icon: ReactNode }> = {
  ceo: { label: 'CEO', icon: <PartitionOutlined /> },
  developer: { label: '程序员', icon: <CodeOutlined /> },
  reviewer: { label: '质检', icon: <SafetyCertificateOutlined /> },
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

export default function DigitalTeam() {
  const [templates, setTemplates] = useState<TeamTemplate[]>([]);
  const [projects, setProjects] = useState<DigitalProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<DigitalProject | null>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [cloudProviders, setCloudProviders] = useState<SavedCloudProvider[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const selectedFormProvider = Form.useWatch('provider', form);

  const selectedId = selectedProject?.id;

  useEffect(() => {
    void loadInitialData();
  }, []);

  useEffect(() => {
    if (selectedId) {
      void loadProjectDetails(selectedId);
    }
  }, [selectedId]);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const [templateData, projectData] = await Promise.all([
        getDigitalTeamTemplates(),
        getDigitalTeamProjects(),
      ]);
      const providerData = await getSavedCloudProviders().catch(() => ({ keys: [] }));
      setTemplates(templateData || []);
      setProjects(projectData || []);
      setCloudProviders(providerData?.keys || []);
      setSelectedProject((projectData || [])[0] || null);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '数字团队数据加载失败');
    } finally {
      setLoading(false);
    }
  };

  const loadProjectDetails = async (projectId: string) => {
    try {
      const [project, timelineData, artifactData] = await Promise.all([
        getDigitalTeamProject(projectId),
        getDigitalTeamTimeline(projectId),
        getDigitalTeamArtifacts(projectId),
      ]);
      setSelectedProject(project);
      setTimeline(timelineData?.events || []);
      setArtifacts(artifactData?.artifacts || []);
      setProjects((items) => items.map((item) => (item.id === project.id ? project : item)));
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '项目详情加载失败');
    }
  };

  const handleCreate = async (values: any) => {
    try {
      const project = await createDigitalTeamProject({
        title: values.title,
        goal: values.goal,
        template_id: values.template_id || 'software_dev_team',
        project_path: values.project_path,
        provider: values.provider || 'minimax',
        model: values.model,
        approval_mode: 'manual',
      });
      message.success('数字团队项目已创建');
      setCreateOpen(false);
      form.resetFields();
      setProjects((items) => [project, ...items]);
      setSelectedProject(project);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '创建失败');
    }
  };

  const handleRun = async () => {
    if (!selectedProject) return;
    setLoading(true);
    try {
      const project = await runDigitalTeamProject(selectedProject.id);
      setSelectedProject(project);
      await loadProjectDetails(project.id);
      message.success('CEO Agent 已完成第一轮拆解');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '运行失败');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (taskId: string) => {
    setLoading(true);
    try {
      const project = await approveDigitalTeamTask(taskId, { approved: true });
      setSelectedProject(project);
      await loadProjectDetails(project.id);
      message.success('审批已通过');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '审批失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async (taskId: string) => {
    setLoading(true);
    try {
      const project = await retryDigitalTeamTask(taskId);
      setSelectedProject(project);
      await loadProjectDetails(project.id);
      message.success('任务已重试');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '重试失败');
    } finally {
      setLoading(false);
    }
  };

  const awaitingTasks = useMemo(
    () =>
      (selectedProject?.tasks || []).filter((task) =>
        ['awaiting_approval', 'needs_manual_review', 'failed'].includes(task.status),
      ),
    [selectedProject],
  );

  const tasksByRole = useMemo(() => {
    const map: Record<string, DigitalTask | undefined> = {};
    (selectedProject?.tasks || []).forEach((task) => {
      map[task.role] = task;
    });
    return map;
  }, [selectedProject]);

  const providerOptions = useMemo(() => {
    const savedOptions = cloudProviders.map((provider) => ({
      value: provider.provider,
      label: `${provider.name || provider.provider} (${provider.provider})`,
    }));
    if (savedOptions.length) {
      return savedOptions;
    }
    return [
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
      template_id: 'software_dev_team',
    });
    setCreateOpen(true);
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h2>
            <TeamOutlined /> AI 数字团队
          </h2>
          <p>软件开发团队 MVP：拆需求、出方案、做质检，关键节点由你审批。</p>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadInitialData} loading={loading}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            新建项目
          </Button>
        </Space>
      </div>

      <div className={styles.layout}>
        <aside className={styles.panel}>
          <h3 className={styles.panelTitle}>团队模板</h3>
          <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
            {(templates.length ? templates : [{ id: 'software_dev_team', name: 'AI 软件开发团队', description: 'CEO / 程序员 / 质检' }]).map(
              (template) => (
                <div key={template.id} className={styles.projectItem}>
                  <div className={styles.projectTitle}>{template.name}</div>
                  <div className={styles.projectMeta}>{template.description}</div>
                </div>
              ),
            )}
          </Space>
          <h3 className={styles.panelTitle}>项目列表</h3>
          <div className={styles.projectList}>
            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                className={`${styles.projectItem} ${
                  selectedProject?.id === project.id ? styles.projectItemActive : ''
                }`}
                onClick={() => setSelectedProject(project)}
              >
                <div className={styles.projectTitle}>{project.title}</div>
                <div className={styles.projectMeta}>
                  <Tag color={statusColor[project.status] || 'default'}>{project.status}</Tag>
                  {new Date(project.updated_at).toLocaleString()}
                </div>
              </button>
            ))}
            {!projects.length && <div className={styles.emptyState}>暂无项目</div>}
          </div>
        </aside>

        <main className={styles.panel}>
          <div className={styles.header}>
            <div>
              <h3 className={styles.panelTitle}>{selectedProject?.title || '选择或创建一个项目'}</h3>
              {selectedProject && (
                <Tag color={statusColor[selectedProject.status] || 'default'}>
                  {selectedProject.status}
                </Tag>
              )}
            </div>
            {selectedProject?.status === 'draft' && (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleRun} loading={loading}>
                启动团队
              </Button>
            )}
          </div>

          {selectedProject ? (
            <>
              <div className={styles.outputBox}>{selectedProject.goal}</div>
              <div className={styles.board} style={{ marginTop: 16 }}>
                {['ceo', 'developer', 'reviewer'].map((role) => {
                  const task = tasksByRole[role];
                  const meta = roleMeta[role] || { label: role, icon: null };
                  return (
                    <div key={role} className={styles.taskCard}>
                      <div className={styles.taskHeader}>
                        <span className={styles.taskRole}>
                          {meta.icon} {meta.label}
                        </span>
                        <Tag color={statusColor[task?.status || 'pending'] || 'default'}>
                          {task?.status || 'pending'}
                        </Tag>
                      </div>
                      <p className={styles.taskDescription}>
                        {task?.description || '等待上一节点完成。'}
                      </p>
                      {task && <div className={styles.outputBox}>{compactJson(task.output)}</div>}
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>创建项目后，团队流程会显示在这里</div>
          )}
        </main>

        <aside className={styles.panel}>
          <h3 className={styles.panelTitle}>审批与操作</h3>
          <Space direction="vertical" style={{ width: '100%' }}>
            {awaitingTasks.map((task) => (
              <div key={task.id} className={styles.artifactItem}>
                <div className={styles.artifactTitle}>{task.title}</div>
                <div className={styles.projectMeta}>{task.status}</div>
                <Space style={{ marginTop: 10 }}>
                  {task.status !== 'failed' && (
                    <Button
                      type="primary"
                      size="small"
                      icon={<CheckCircleOutlined />}
                      onClick={() => handleApprove(task.id)}
                      loading={loading}
                    >
                      审批通过
                    </Button>
                  )}
                  <Button size="small" icon={<ReloadOutlined />} onClick={() => handleRetry(task.id)} loading={loading}>
                    重试
                  </Button>
                </Space>
              </div>
            ))}
            {!awaitingTasks.length && <div className={styles.emptyState}>暂无待审批任务</div>}
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
        title="新建数字团队项目"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={loading}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="title" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="例如：新增数字团队页面" />
          </Form.Item>
          <Form.Item name="goal" label="业务目标" rules={[{ required: true, message: '请输入目标' }]}>
            <Input.TextArea rows={5} placeholder="描述你希望 AI 软件开发团队完成的需求" />
          </Form.Item>
          <Form.Item name="project_path" label="项目路径">
            <Input placeholder="默认可留空；例如 C:\\Users\\JHJ\\Desktop\\finetune-platform" />
          </Form.Item>
          <Form.Item name="template_id" label="团队模板" initialValue="software_dev_team">
            <Select
              options={(templates.length ? templates : [{ id: 'software_dev_team', name: 'AI 软件开发团队' }]).map(
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
