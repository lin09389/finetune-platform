import { DeleteOutlined, EditOutlined, FolderOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { App, Badge, Button, Form, Input, Modal, Tag } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { API_BASE_URL } from '../services/api';
import { appModal } from '../utils/modal';
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

export default function WorkspaceManager() {
  const { message } = App.useApp();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingWorkspace, setEditingWorkspace] = useState<Workspace | null>(null);
  const [form] = Form.useForm();

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

  useEffect(() => {
    void loadWorkspaces();
  }, []);

  const loadWorkspaces = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/workspace/workspaces`);
      if (!response.ok) {
        message.error('加载工作空间失败');
        return;
      }
      const data = (await response.json()) as WorkspaceListResponse;
      setWorkspaces(normalizeWorkspaces(data));
    } catch (error) {
      console.error('Failed to load workspaces:', error);
      message.error('加载工作空间失败');
    }
  };

  const handleCreate = async (values: { name: string; description?: string; local_path?: string }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/workspace/workspaces`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...values, local_path: normalizePath(values.local_path) || undefined }),
      });
      if (response.ok) {
        message.success('工作空间创建成功');
        setModalVisible(false);
        form.resetFields();
        await loadWorkspaces();
      } else {
        message.error('创建工作空间失败');
      }
    } catch {
      message.error('创建工作空间失败');
    }
  };

  const handleUpdate = async (values: { name?: string; description?: string; local_path?: string }) => {
    if (!editingWorkspace) return;
    try {
      const response = await fetch(`${API_BASE_URL}/workspace/workspaces/${editingWorkspace.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...values, local_path: normalizePath(values.local_path) }),
      });
      if (response.ok) {
        message.success('工作空间更新成功');
        setModalVisible(false);
        setEditingWorkspace(null);
        form.resetFields();
        await loadWorkspaces();
      } else {
        message.error('更新工作空间失败');
      }
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
          const response = await fetch(`${API_BASE_URL}/workspace/workspaces/${id}`, {
            method: 'DELETE',
          });
          if (response.ok) {
            message.success('工作空间已删除');
            await loadWorkspaces();
          } else {
            message.error('删除工作空间失败');
          }
        } catch {
          message.error('删除工作空间失败');
        }
      },
    });
  };

  const openModal = (workspace?: Workspace) => {
    if (workspace) {
      setEditingWorkspace(workspace);
      form.setFieldsValue({
        name: workspace.name,
        description: workspace.description,
        local_path: normalizePath(workspace.local_path),
      });
    } else {
      setEditingWorkspace(null);
      form.resetFields();
    }
    setModalVisible(true);
  };

  const quickFillActivePath = () => {
    if (selectedWorkspace?.local_path) {
      form.setFieldValue('local_path', selectedWorkspace.local_path);
      message.success('已填入当前工作区路径');
      return;
    }
    if (editingWorkspace?.local_path) {
      form.setFieldValue('local_path', editingWorkspace.local_path);
      message.success('已恢复当前工作区路径');
    }
  };

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
        {/* 标题栏 */}
        <div className={styles.headerCard}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <FolderOutlined />
            </div>
            <div>
              <h2 className={styles.headerTitle}>工作空间管理</h2>
              <p className={styles.headerSubtitle}>
                Beta 能力：管理知识库工作空间，具体能力仍取决于本地存储与索引状态
              </p>
            </div>
          </div>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            data-testid="workspace-create-primary"
            onClick={() => openModal()}
          >
            新建工作空间
          </Button>
        </div>

        {/* 工作空间列表 */}
        <div className={styles.listCard}>
          <div className={styles.toolbarRow}>
            <div className={styles.toolbarHint}>
              工作空间结构已经可试用，但文档解析、向量构建和后续检索质量仍会受到本地环境影响。
            </div>
            <Button icon={<ReloadOutlined />} onClick={() => void loadWorkspaces()}>
              刷新列表
            </Button>
          </div>
          {workspaces.length > 0 ? (
            <div className={styles.wsGrid}>
              {workspaces.map((ws) => (
                <div key={ws.id} className={styles.wsCard}>
                  <div className={styles.wsCardTitle}>
                    <FolderOutlined className={styles.wsIcon} />
                    <span>{ws.name}</span>
                    <Badge count={ws.vector_count} size="small" color="blue" />
                  </div>
                  <div className={styles.wsDesc}>{ws.description || '暂无描述'}</div>
                  {ws.local_path ? (
                    <div className={styles.wsTime}>本地路径：{ws.local_path}</div>
                  ) : (
                    <div className={styles.wsTime}>未绑定本地目录</div>
                  )}
                  {selectedWorkspace?.id === ws.id && (
                    <Tag color="green" style={{ marginTop: 8, borderRadius: 999 }}>
                      当前已选中
                    </Tag>
                  )}
                  <div className={styles.wsMetaRow}>
                    <span
                      style={{
                        fontSize: 12,
                        color: 'var(--accent-blue)',
                        background: 'rgba(22,119,255,0.1)',
                        padding: '1px 8px',
                        borderRadius: 4,
                      }}
                    >
                      {ws.document_count} 文档
                    </span>
                    <span
                      style={{
                        fontSize: 12,
                        color: '#06b6d4',
                        background: 'rgba(6,182,212,0.1)',
                        padding: '1px 8px',
                        borderRadius: 4,
                      }}
                    >
                      {ws.vector_count} 向量
                    </span>
                  </div>
                  <div className={styles.wsTime}>
                    创建于：{new Date(ws.created_at).toLocaleDateString('zh-CN')}
                  </div>
                  <div className={styles.wsActions}>
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => openModal(ws)}
                    >
                      编辑
                    </Button>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleDelete(ws.id)}
                    >
                      删除
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>📁</div>
              <div className={styles.emptyText}>暂无工作空间</div>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                data-testid="workspace-create-empty"
                onClick={() => openModal()}
              >
                创建工作空间
              </Button>
            </div>
          )}
        </div>

        {/* 编辑/创建弹窗 */}
        <Modal
          title={editingWorkspace ? '编辑工作空间' : '创建工作空间'}
          open={modalVisible}
          onOk={() => form.submit()}
          onCancel={() => {
            setModalVisible(false);
            setEditingWorkspace(null);
            form.resetFields();
          }}
        >
          <Form
            form={form}
            layout="vertical"
            onFinish={editingWorkspace ? handleUpdate : handleCreate}
          >
            <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
              <Input placeholder="例如：个人知识库、项目文档" />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <TextArea rows={3} placeholder="可选，用于说明该工作空间用途" />
            </Form.Item>
            <Form.Item
              name="local_path"
              label="本地项目路径"
              extra={pathState.text}
              validateStatus={
                pathState.status === 'empty'
                  ? undefined
                  : pathState.status === 'info'
                    ? undefined
                    : pathState.status
              }
            >
              <Input placeholder="例如：C:\\Projects\\my-app" />
            </Form.Item>
            <div className={styles.modalFooterHint}>
              <span>保存后会用于 Agent 的 `project_path`，请确保目录真实存在且在允许范围内。</span>
              <Button size="small" onClick={quickFillActivePath} disabled={!selectedWorkspace?.local_path && !editingWorkspace?.local_path}>
                填入当前路径
              </Button>
            </div>
          </Form>
        </Modal>
      </MotionItem>
    </MotionList>
  );
}
