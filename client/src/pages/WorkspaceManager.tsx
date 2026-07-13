import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  CheckOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  ImportOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { App, Badge, Button, Drawer, Form, Input, Modal, Space, Steps, Tag, Tooltip } from 'antd';
import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import EmptyState from '../components/shared/EmptyState';
import LoadingState from '../components/shared/LoadingState';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import StatusState from '../components/shared/StatusState';
import {
  WorkspaceContinuationContext,
  WorkspaceImportCommitResult,
  WorkspaceImportInspectResult,
  WorkspacePortabilityPreview,
  WorkspacePortabilityResource,
  browseFolderBackend,
  browseWorkspaceFolder,
  commitWorkspaceImport,
  createWorkspace,
  createWorkspaceContinuationSession,
  deleteWorkspace,
  exportWorkspacePackage,
  getWorkspacePortabilityError,
  getWorkspacePortabilityPreview,
  inspectWorkspacePackage,
  listWorkspaces,
  updateWorkspace,
} from '../services/api';
import { appModal } from '../utils/modal';
import { activatePersistedAgentSession } from '../agent/runtime/sessionPersistence';
import styles from './WorkspaceManager.module.css';

const { TextArea } = Input;

interface Workspace {
  id: string;
  name: string;
  description?: string;
  local_path?: string | null;
  created_at: string;
  updated_at: string;
  document_count: number;
  vector_count: number;
}

type WorkspaceListResponse = Workspace[] | { workspaces?: Workspace[] };

function normalizeWorkspaces(data: WorkspaceListResponse): Workspace[] {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.workspaces)) return data.workspaces;
  return [];
}

function normalizePath(value: string | undefined | null) {
  return value?.trim().replace(/[\\/]+$/, '') || '';
}

function portabilityStatusLabel(status: WorkspacePortabilityResource['status']) {
  const labels: Record<WorkspacePortabilityResource['status'], string> = {
    resolved: '已就绪',
    missing: '需要重新绑定',
    mismatch: '需要确认新版本',
    unsupported: '当前设备不支持',
  };
  return labels[status];
}

function portabilityStatusColor(status: WorkspacePortabilityResource['status']) {
  return status === 'resolved' ? 'success' : status === 'unsupported' ? 'default' : 'warning';
}

type ElectronWorkspaceApi = typeof window.electronAPI & {
  openFolder?: (path: string) => void | Promise<void>;
  selectFolder?: (initialPath?: string) => Promise<string | null>;
};

export default function WorkspaceManager() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>(
    () => localStorage.getItem('chat_workspace_id_v1') || '',
  );
  const [modalVisible, setModalVisible] = useState(false);
  const [editingWorkspace, setEditingWorkspace] = useState<Workspace | null>(null);
  const [form] = Form.useForm();
  const [previewWorkspace, setPreviewWorkspace] = useState<Workspace | null>(null);
  const [portabilityPreview, setPortabilityPreview] = useState<WorkspacePortabilityPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [inspectResult, setInspectResult] = useState<WorkspaceImportInspectResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [importName, setImportName] = useState('');
  const [projectPath, setProjectPath] = useState('');
  const [resourceBindings, setResourceBindings] = useState<Record<string, string>>({});
  const [commitResult, setCommitResult] = useState<WorkspaceImportCommitResult | null>(null);

  const pathValue = Form.useWatch('local_path', form);
  const normalizedPath = useMemo(() => normalizePath(pathValue), [pathValue]);
  const selectedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === editingWorkspace?.id) || null,
    [editingWorkspace?.id, workspaces],
  );
  const editingWorkspacePath = normalizePath(editingWorkspace?.local_path);
  const pathState = useMemo(() => {
    if (!normalizedPath) return { status: 'empty' as const, text: '可留空，仅创建命名工作空间。' };
    if (!selectedWorkspace && !editingWorkspace) {
      return { status: 'info' as const, text: '将用于 Agent 执行时的项目根目录。' };
    }
    if (selectedWorkspace?.local_path && normalizePath(selectedWorkspace.local_path) === normalizedPath) {
      return { status: 'success' as const, text: '当前路径与所选工作区一致。' };
    }
    if (editingWorkspacePath && editingWorkspacePath === normalizedPath) {
      return { status: 'success' as const, text: '当前路径与工作区保存值一致。' };
    }
    return { status: 'warning' as const, text: '路径已被修改，保存后将覆盖当前绑定。' };
  }, [editingWorkspace, editingWorkspacePath, normalizedPath, selectedWorkspace]);

  const repairableResources = useMemo(
    () => inspectResult?.preview.resources.filter((resource) => resource.status === 'missing' || resource.status === 'mismatch') || [],
    [inspectResult],
  );
  const unsupportedResources = useMemo(
    () => inspectResult?.preview.resources.filter((resource) => resource.status === 'unsupported') || [],
    [inspectResult],
  );
  const importStep = commitResult ? 2 : inspectResult ? 1 : 0;

  useEffect(() => {
    const handleWorkspaceChange = (event: Event) => {
      const detail = (event as CustomEvent<{ workspaceId?: string }>).detail || {};
      if (detail.workspaceId) setActiveWorkspaceId(detail.workspaceId);
    };
    window.addEventListener('chat-workspace-change', handleWorkspaceChange);
    return () => window.removeEventListener('chat-workspace-change', handleWorkspaceChange);
  }, []);

  const handleSelectActiveWorkspace = (ws: Workspace) => {
    localStorage.setItem('chat_workspace_id_v1', ws.id);
    localStorage.setItem('chat_project_path_v1', ws.local_path || '');
    setActiveWorkspaceId(ws.id);
    window.dispatchEvent(new CustomEvent('chat-workspace-change', { detail: { workspaceId: ws.id, projectPath: ws.local_path || '' } }));
    message.success(`已切换活动工作空间为：${ws.name}`);
  };

  const handleOpenFolder = (path: string | undefined | null) => {
    if (!path) return;
    const electronApi = typeof window !== 'undefined' ? (window.electronAPI as ElectronWorkspaceApi | undefined) : undefined;
    if (electronApi?.openFolder) {
      void electronApi.openFolder(path);
      return;
    }
    message.info('浏览器模式无法直接打开本地目录，请手动打开文件夹。');
  };

  const loadWorkspaces = useCallback(async () => {
    try {
      const data = await listWorkspaces();
      setWorkspaces(normalizeWorkspaces(data as unknown as WorkspaceListResponse));
    } catch {
      message.error('加载工作空间失败');
    }
  }, [message]);

  useEffect(() => {
    void loadWorkspaces();
  }, [loadWorkspaces]);

  const handleCreate = async (values: { name: string; description?: string; local_path?: string }) => {
    try {
      await createWorkspace({ ...values, local_path: normalizePath(values.local_path) || undefined });
      message.success('工作空间创建成功');
      setModalVisible(false);
      form.resetFields();
      await loadWorkspaces();
    } catch {
      message.error('创建工作空间失败');
    }
  };

  const handleUpdate = async (values: { name?: string; description?: string; local_path?: string }) => {
    if (!editingWorkspace) return;
    try {
      await updateWorkspace(editingWorkspace.id, { ...values, local_path: normalizePath(values.local_path) });
      message.success('工作空间更新成功');
      setModalVisible(false);
      setEditingWorkspace(null);
      form.resetFields();
      await loadWorkspaces();
    } catch {
      message.error('更新工作空间失败');
    }
  };

  const handleDelete = async (id: string) => {
    appModal.confirm({
      title: '确认删除',
      content: '删除后将无法恢复，确认继续吗？',
      onOk: async () => {
        try {
          await deleteWorkspace(id);
          message.success('工作空间已删除');
          await loadWorkspaces();
        } catch {
          message.error('删除工作空间失败');
        }
      },
    });
  };

  const openModal = (workspace?: Workspace) => {
    if (workspace) {
      setEditingWorkspace(workspace);
      form.setFieldsValue({ name: workspace.name, description: workspace.description, local_path: normalizePath(workspace.local_path) });
    } else {
      setEditingWorkspace(null);
      form.resetFields();
    }
    setModalVisible(true);
  };

  const handleBrowseFolder = async () => {
    const electronApi = typeof window !== 'undefined' ? (window.electronAPI as ElectronWorkspaceApi | undefined) : undefined;
    if (electronApi?.selectFolder) {
      const folder = await electronApi.selectFolder(form.getFieldValue('local_path') || undefined);
      if (folder) form.setFieldValue('local_path', folder);
      return;
    }
    try {
      const res = await browseFolderBackend(form.getFieldValue('local_path') || undefined);
      if (res.status === 'success' && res.path) {
        form.setFieldValue('local_path', res.path);
        message.success('选择路径成功');
      } else if (res.status === 'error') {
        message.warning(`文件夹选择失败: ${res.message || '请手动输入路径'}`);
      }
    } catch {
      message.error('无法激活文件夹选择，请手动输入路径');
    }
  };

  const quickFillActivePath = () => {
    const path = selectedWorkspace?.local_path || editingWorkspace?.local_path;
    if (path) {
      form.setFieldValue('local_path', path);
      message.success('已填入当前工作区路径');
    }
  };

  const openPreview = async (workspace: Workspace) => {
    setPreviewWorkspace(workspace);
    setPortabilityPreview(null);
    setPreviewLoading(true);
    try {
      setPortabilityPreview(await getWorkspacePortabilityPreview(workspace.id));
    } catch (error) {
      message.error(getWorkspacePortabilityError(error).message);
      setPreviewWorkspace(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleExport = async () => {
    if (!previewWorkspace) return;
    setExporting(true);
    try {
      const packageBlob = await exportWorkspacePackage(previewWorkspace.id);
      const url = URL.createObjectURL(packageBlob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${previewWorkspace.name || 'workspace'}.ftworkspace`;
      anchor.click();
      URL.revokeObjectURL(url);
      message.success('Workspace 导出已开始');
      setPreviewWorkspace(null);
    } catch (error) {
      message.error(getWorkspacePortabilityError(error).message);
    } finally {
      setExporting(false);
    }
  };

  const resetImport = () => {
    setImportFile(null);
    setInspectResult(null);
    setImportError(null);
    setImportName('');
    setProjectPath('');
    setResourceBindings({});
    setCommitResult(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const openImport = () => {
    resetImport();
    setImportOpen(true);
  };

  const handleImportFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setImportError(null);
    setInspectResult(null);
    if (file && !file.name.toLowerCase().endsWith('.ftworkspace')) {
      setImportFile(null);
      setImportError('请选择 .ftworkspace 导入包。');
      return;
    }
    setImportFile(file);
  };

  const handleInspect = async () => {
    if (!importFile) {
      setImportError('请选择 .ftworkspace 导入包后再检查。');
      return;
    }
    setInspecting(true);
    setImportError(null);
    try {
      const result = await inspectWorkspacePackage(importFile);
      setInspectResult(result);
      setImportName(result.preview.workspace?.name || importFile.name.replace(/\.ftworkspace$/i, ''));
      setResourceBindings({});
    } catch (error) {
      const portabilityError = getWorkspacePortabilityError(error);
      const friendlyMessage: Record<string, string> = {
          unsupported_version: '这个包使用了当前版本尚不支持的 schema，未写入任何工作空间。',
          tampered: '完整性检查未通过。请重新获取原始导出包。',
          archive_tampered: '完整性检查未通过。请重新获取原始导出包。',
        unsafe_archive: '这个导入包不符合安全归档规范，未写入任何工作空间。',
      };
      setImportError(friendlyMessage[portabilityError.code] || portabilityError.message);
    } finally {
      setInspecting(false);
    }
  };

  const handleBrowseImportProject = async () => {
    try {
      const path = await browseWorkspaceFolder(projectPath || undefined);
      if (path) setProjectPath(path);
    } catch (error) {
      message.warning(getWorkspacePortabilityError(error).message);
    }
  };

  const handleCommitImport = async () => {
    if (!inspectResult) return;
    if (!importName.trim()) {
      setImportError('请为导入的 Workspace 填写名称。');
      return;
    }
    if (!normalizePath(projectPath)) {
      setImportError('请选择当前设备上的项目目录；源码不会包含在导入包中。');
      return;
    }
    const incomplete = repairableResources.find((resource) => !resourceBindings[resource.reference_id]?.trim());
    if (incomplete) {
      setImportError(`请先为“${incomplete.display_name}”重新绑定资源。`);
      return;
    }
    setCommitting(true);
    setImportError(null);
    try {
      const result = await commitWorkspaceImport(inspectResult.import_token, {
        name: importName.trim(),
        project_path: normalizePath(projectPath),
        resource_bindings: repairableResources.map((resource) => ({
          reference_id: resource.reference_id,
          locator: resourceBindings[resource.reference_id]!.trim(),
        })),
      });
      setCommitResult(result);
      await loadWorkspaces();
    } catch (error) {
      setImportError(getWorkspacePortabilityError(error).message);
    } finally {
      setCommitting(false);
    }
  };

  const handleContinueTask = async (continuation: WorkspaceContinuationContext) => {
    if (!commitResult) return;
    try {
      const session = await createWorkspaceContinuationSession(commitResult.workspace.id, continuation.id);
      activatePersistedAgentSession(session);
      message.success('已在当前设备策略下新建任务会话');
      navigate('/agent');
    } catch (error) {
      message.error(getWorkspacePortabilityError(error).message);
    }
  };

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
        <div className={styles.headerCard}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}><FolderOutlined /></div>
            <div>
              <h2 className={styles.headerTitle}>工作空间管理</h2>
              <p className={styles.headerSubtitle}>Beta 能力：管理知识库工作空间，具体能力仍取决于本地存储与索引状态</p>
            </div>
          </div>
          <Space wrap className={styles.headerActions}>
            <Button type="primary" icon={<ImportOutlined />} onClick={openImport}>导入 Workspace</Button>
            <Button icon={<PlusOutlined />} data-testid="workspace-create-primary" onClick={() => openModal()}>新建工作空间</Button>
          </Space>
        </div>

        <div className={styles.listCard}>
          <div className={styles.toolbarRow}>
            <div className={styles.toolbarHint}>工作空间结构已经可试用，但文档解析、向量构建和后续检索质量仍会受到本地环境影响。</div>
            <Button icon={<ReloadOutlined />} onClick={() => void loadWorkspaces()}>刷新列表</Button>
          </div>
          {workspaces.length > 0 ? (
            <div className={styles.wsGrid}>
              {workspaces.map((ws) => {
                const isActive = activeWorkspaceId === ws.id;
                return (
                  <div
                    key={ws.id}
                    className={`${styles.wsCard} ${isActive ? styles.wsCardActive : ''}`}
                    onClick={(event) => {
                      if ((event.target as HTMLElement).closest('button') || (event.target as HTMLElement).closest('.ant-modal')) return;
                      handleSelectActiveWorkspace(ws);
                    }}
                    title="点击可设为当前活动工作空间"
                  >
                    <div className={styles.wsCardTitle}>
                      <FolderOutlined className={styles.wsIcon} />
                      <span>{ws.name}</span>
                      <Badge count={ws.vector_count} size="small" color="blue" />
                    </div>
                    <div className={styles.wsDesc}>{ws.description || '暂无描述'}</div>
                    <div className={styles.wsTime}>{ws.local_path ? `本地路径：${ws.local_path}` : '未绑定本地目录'}</div>
                    {isActive && <Tag color="green" className={styles.activeTag}>当前活动工作区</Tag>}
                    <div className={styles.wsMetaRow}>
                      <span className={styles.documentMeta}>{ws.document_count} 文档</span>
                      <span className={styles.vectorMeta}>{ws.vector_count} 向量</span>
                    </div>
                    <div className={styles.wsTime}>创建于：{new Date(ws.created_at).toLocaleDateString('zh-CN')}</div>
                    <div className={styles.wsActions}>
                      {isActive ? (
                        <Button type="primary" size="small" icon={<ArrowRightOutlined />} onClick={(event) => { event.stopPropagation(); navigate('/chat'); }}>进入 Chat 编程</Button>
                      ) : (
                        <Button type="dashed" size="small" icon={<CheckOutlined />} onClick={(event) => { event.stopPropagation(); handleSelectActiveWorkspace(ws); }}>设为活动</Button>
                      )}
                      <Button type="text" size="small" icon={<DownloadOutlined />} onClick={(event) => { event.stopPropagation(); void openPreview(ws); }}>导出</Button>
                      <Button type="text" size="small" icon={<SafetyCertificateOutlined />} onClick={(event) => { event.stopPropagation(); void openPreview(ws); }}>迁移检查</Button>
                      {ws.local_path && <Button type="text" size="small" icon={<FolderOpenOutlined />} onClick={(event) => { event.stopPropagation(); handleOpenFolder(ws.local_path); }}>打开文件夹</Button>}
                      <Button type="text" size="small" icon={<EditOutlined />} onClick={(event) => { event.stopPropagation(); openModal(ws); }}>编辑</Button>
                      <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={(event) => { event.stopPropagation(); handleDelete(ws.id); }}>删除</Button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              type="data"
              title="暂无工作空间"
              description="创建一个工作空间，或从 .ftworkspace 包导入已有上下文。"
              action={{ text: '创建工作空间', onClick: () => openModal(), icon: <PlusOutlined /> }}
            />
          )}
        </div>

        <Modal
          title={previewWorkspace ? `${previewWorkspace.name} 的迁移检查` : '迁移检查'}
          open={Boolean(previewWorkspace)}
          onCancel={() => setPreviewWorkspace(null)}
          footer={[
            <Button key="cancel" onClick={() => setPreviewWorkspace(null)}>关闭</Button>,
            <Button key="export" type="primary" icon={<DownloadOutlined />} loading={exporting} disabled={!portabilityPreview} onClick={() => void handleExport()}>导出 Workspace</Button>,
          ]}
        >
          {previewLoading ? <LoadingState tip="正在准备导出预览" /> : portabilityPreview && (
            <div className={styles.previewContent}>
              <div className={styles.previewFacts}>
                <span><SafetyCertificateOutlined aria-hidden /> Schema v{portabilityPreview.schema_version}</span>
                <span><CheckCircleOutlined aria-hidden /> {portabilityPreview.integrity.algorithm.toUpperCase()} 完整性</span>
                <span>{portabilityPreview.task_count} 个任务摘要</span>
              </div>
              <section className={styles.previewSection}>
                <h3>不会包含的内容</h3>
                <ul>{portabilityPreview.exclusions.map((item) => <li key={item}>{item}</li>)}</ul>
              </section>
              <section className={styles.previewSection}>
                <h3>会迁移的引用</h3>
                <p>仅迁移任务摘要、执行计划、验证结果和资源引用；不会包含源码、数据集内容、模型权重、凭据或旧的执行权限。</p>
              </section>
            </div>
          )}
        </Modal>

        <Modal
          title={editingWorkspace ? '编辑工作空间' : '创建工作空间'}
          open={modalVisible}
          onOk={() => form.submit()}
          onCancel={() => { setModalVisible(false); setEditingWorkspace(null); form.resetFields(); }}
        >
          <Form form={form} layout="vertical" onFinish={editingWorkspace ? handleUpdate : handleCreate}>
            <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}><Input placeholder="例如：个人知识库、项目文档" /></Form.Item>
            <Form.Item name="description" label="描述"><TextArea rows={3} placeholder="可选，用于说明该工作空间用途" /></Form.Item>
            <Form.Item name="local_path" label="本地项目路径" extra={pathState.text} validateStatus={pathState.status === 'empty' || pathState.status === 'info' ? undefined : pathState.status}>
              <Space.Compact block>
                <Form.Item name="local_path" noStyle><Input placeholder="例如：C:\\Projects\\my-app" /></Form.Item>
                <Tooltip title="选择本地项目文件夹"><Button icon={<FolderOpenOutlined />} onClick={() => void handleBrowseFolder()}>浏览</Button></Tooltip>
              </Space.Compact>
            </Form.Item>
            <div className={styles.modalFooterHint}>
              <span>保存后会用于 Agent 的 project_path，请确保目录真实存在且在允许范围内。</span>
              <Button size="small" onClick={quickFillActivePath} disabled={!selectedWorkspace?.local_path && !editingWorkspace?.local_path}>填入当前路径</Button>
            </div>
          </Form>
        </Modal>

        <Drawer
          title="导入 Workspace"
          open={importOpen}
          onClose={() => setImportOpen(false)}
          width={620}
          className={styles.importDrawer}
          destroyOnClose
          extra={<Button onClick={() => setImportOpen(false)}>关闭</Button>}
        >
          <Steps current={importStep} className={styles.importSteps} items={[{ title: '选择文件' }, { title: '检查与重新绑定' }, { title: '完成' }]} />
          {importError && <StatusState tone="warning" title="需要处理" description={importError} className={styles.importStatus} />}

          {importStep === 0 && (
            <section className={styles.drawerSection}>
              <h3>选择 .ftworkspace 包</h3>
              <p className={styles.drawerHint}>检查只会校验包内容，不会写入 Workspace、运行命令或恢复旧会话权限。</p>
              <button type="button" className={styles.filePicker} onClick={() => fileInputRef.current?.click()}>
                <ImportOutlined aria-hidden />
                <span>{importFile ? importFile.name : '选择导出包'}</span>
                <small>{importFile ? '已选择，下一步将进行安全检查' : '仅支持 .ftworkspace'}</small>
              </button>
              <input ref={fileInputRef} data-testid="workspace-import-file" className={styles.fileInput} type="file" accept=".ftworkspace,application/zip" onChange={handleImportFileChange} />
              <div className={styles.drawerActions}>
                <Button type="primary" icon={<SafetyCertificateOutlined />} loading={inspecting} onClick={() => void handleInspect()} disabled={!importFile}>检查包内容</Button>
              </div>
            </section>
          )}

          {importStep === 1 && inspectResult && (
            <section className={styles.drawerSection}>
              <div className={styles.inspectHeading}>
                <div><h3>检查完成</h3><p>完整性已验证。为新设备确认项目目录，并修复缺失的资源引用。</p></div>
                <Tag color={portabilityStatusColor(inspectResult.preview.integrity.status === 'tampered' ? 'unsupported' : 'resolved')} icon={<SafetyCertificateOutlined />}>Schema v{inspectResult.preview.schema_version} · {inspectResult.preview.integrity.algorithm.toUpperCase()}</Tag>
              </div>
              <div className={styles.summaryGrid}>
                <span><strong>{inspectResult.preview.task_count}</strong> 个任务摘要</span>
                <span><strong>{inspectResult.preview.resources.length}</strong> 个资源引用</span>
                <span><strong>{repairableResources.length}</strong> 项待修复</span>
              </div>
              <label className={styles.fieldLabel} htmlFor="workspace-import-name">新 Workspace 名称</label>
              <Input id="workspace-import-name" value={importName} onChange={(event) => setImportName(event.target.value)} />
              <label className={styles.fieldLabel} htmlFor="workspace-import-project">项目目录（必需，不会从包中恢复）</label>
              <Space.Compact block>
                <Input id="workspace-import-project" value={projectPath} placeholder="选择此设备上的项目目录" onChange={(event) => setProjectPath(event.target.value)} />
                <Button icon={<FolderOpenOutlined />} onClick={() => void handleBrowseImportProject()}>浏览</Button>
              </Space.Compact>
              <div className={styles.resourceList}>
                {inspectResult.preview.resources.map((resource) => (
                  <div className={styles.resourceRow} key={resource.reference_id}>
                    <div className={styles.resourceHeader}>
                      <div><strong>{resource.display_name}</strong><span>{resource.kind} · {resource.detail || '安全资源引用'}</span></div>
                      <Tag color={portabilityStatusColor(resource.status)} icon={resource.status === 'resolved' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}>{portabilityStatusLabel(resource.status)}</Tag>
                    </div>
                    {(resource.status === 'missing' || resource.status === 'mismatch') && (
                      <div className={styles.resourceRepair}>
                        <label htmlFor={`resource-${resource.reference_id}`}>{resource.display_name} 的新位置</label>
                        <Input id={`resource-${resource.reference_id}`} value={resourceBindings[resource.reference_id] || ''} placeholder="输入当前设备中的资源位置或 ID" onChange={(event) => setResourceBindings((current) => ({ ...current, [resource.reference_id]: event.target.value }))} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {unsupportedResources.length > 0 && <StatusState tone="info" title="部分资源不会在此设备启用" description="这些资源不会阻止导入；依赖它们的任务会标记为待处理，直到设备具备对应能力。" className={styles.importStatus} />}
              <div className={styles.drawerActions}>
                <Button onClick={resetImport}>选择其他文件</Button>
                <Button type="primary" loading={committing} onClick={() => void handleCommitImport()}>导入并创建工作空间</Button>
              </div>
            </section>
          )}

          {importStep === 2 && commitResult && (
            <section className={styles.drawerSection}>
              <EmptyState compact icon={<CheckCircleOutlined className={styles.successIcon} />} title="Workspace 已导入" description="已创建新的本机 Workspace；历史任务只作为只读上下文，继续时会在当前设备策略下新建会话。" />
              <div className={styles.continuationList}>
                {commitResult.continuations.length > 0 ? commitResult.continuations.map((continuation) => (
                  <div className={styles.continuationRow} key={continuation.id}>
                    <div><strong>{continuation.title}</strong><span>{continuation.mode} · {continuation.blocked ? continuation.blocked_reason || '等待资源修复' : '可安全继续'}</span></div>
                    <Button type="primary" size="small" disabled={continuation.blocked} onClick={() => void handleContinueTask(continuation)}>继续最近任务</Button>
                  </div>
                )) : <p className={styles.drawerHint}>这个包没有可继续的任务摘要。</p>}
              </div>
              <div className={styles.drawerActions}><Button onClick={() => navigate('/workspace')}>进入 Workspace</Button><Button type="primary" onClick={() => setImportOpen(false)}>完成</Button></div>
            </section>
          )}
        </Drawer>
      </MotionItem>
    </MotionList>
  );
}
