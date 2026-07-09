import {
  BranchesOutlined,
  DeleteOutlined,
  EditOutlined,
  MergeOutlined,
  MoreOutlined,
  PlusOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { Button, Card, Dropdown, Input, Modal, Space, Tag, Tree, Typography, message } from 'antd';
import type { DataNode } from 'antd/es/tree';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createConversationBranch,
  deleteConversationBranch,
  fetchConversationTreeState,
  mergeConversationBranch,
  switchConversationBranch,
  type ConversationBranchSummary,
  type ConversationTreeNode,
} from '../services/conversationTreeApi';
import { appModal } from '../utils/modal';

const { Text } = Typography;

interface ChatBranchManagerProps {
  visible: boolean;
  sessionId: string;
  onClose: () => void;
  onBranchSwitch?: (branchId: string) => void;
  onBranchCreate?: (branchId: string) => void;
}

const ChatBranchManager: React.FC<ChatBranchManagerProps> = ({
  visible,
  sessionId,
  onClose,
  onBranchSwitch,
  onBranchCreate,
}) => {
  const [loading, setLoading] = useState(false);
  const [nodes, setNodes] = useState<Record<string, ConversationTreeNode>>({});
  const [rootId, setRootId] = useState<string | null>(null);
  const [branches, setBranches] = useState<ConversationBranchSummary[]>([]);
  const [currentBranchId, setCurrentBranchId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [newBranchName, setNewBranchName] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);

  const loadBranchState = useCallback(async () => {
    if (!sessionId) {
      return;
    }

    setLoading(true);
    try {
      const state = await fetchConversationTreeState(sessionId);
      setNodes(state.tree.nodes || {});
      setRootId(state.tree.root_id || null);
      setCurrentBranchId(state.tree.current_branch_id || null);
      setBranches(state.branches || []);
    } catch {
      message.error('加载分支数据失败');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    if (visible) {
      void loadBranchState();
    }
  }, [loadBranchState, visible]);

  const treeData = useMemo<DataNode[]>(() => {
    if (!rootId || !nodes[rootId]) {
      return [];
    }

    const buildNode = (nodeId: string): DataNode => {
      const node = nodes[nodeId];
      if (!node) {
        return { key: nodeId, title: 'Unknown node' };
      }

      const roleIcon = node.role === 'user' ? 'U' : node.role === 'assistant' ? 'A' : 'S';
      return {
        key: nodeId,
        title: (
          <Space size={8}>
            <Tag
              color={
                node.role === 'user' ? 'cyan' : node.role === 'assistant' ? 'purple' : 'default'
              }
            >
              {roleIcon}
            </Tag>
            <Text ellipsis style={{ maxWidth: 240 }}>
              {node.content.slice(0, 40) || '(empty message)'}
            </Text>
            {node.branch_name ? <Tag color="blue">{node.branch_name}</Tag> : null}
            {node.children_ids.length > 1 ? <Tag color="magenta">Branch point</Tag> : null}
          </Space>
        ),
        children: node.children_ids.map((childId) => buildNode(childId)),
      };
    };

    return [buildNode(rootId)];
  }, [nodes, rootId]);

  const handleCreateBranch = useCallback(async () => {
    if (!selectedNode) {
      message.warning('请先选择一条消息作为分支起点');
      return;
    }

    try {
      const data = await createConversationBranch(
        sessionId,
        selectedNode,
        newBranchName.trim() || undefined,
      );

      if (!data.branch?.id) {
        throw new Error('未返回新分支 ID');
      }

      message.success('分支创建成功');
      setShowCreateModal(false);
      setNewBranchName('');
      await loadBranchState();
      onBranchCreate?.(data.branch.id);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建分支失败');
    }
  }, [loadBranchState, newBranchName, onBranchCreate, selectedNode, sessionId]);

  const handleSwitchBranch = useCallback(
    async (branchId: string) => {
      try {
        await switchConversationBranch(sessionId, branchId);
        message.success('已切换分支');
        setCurrentBranchId(branchId);
        await loadBranchState();
        onBranchSwitch?.(branchId);
      } catch (error) {
        message.error(error instanceof Error ? error.message : '切换分支失败');
      }
    },
    [loadBranchState, onBranchSwitch, sessionId],
  );

  const handleDeleteBranch = useCallback(
    async (branchId: string) => {
      try {
        await deleteConversationBranch(sessionId, branchId);
        message.success('分支已删除');
        await loadBranchState();
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除分支失败');
      }
    },
    [loadBranchState, sessionId],
  );

  const handleMergeBranch = useCallback(
    async (branchId: string) => {
      try {
        const data = await mergeConversationBranch(sessionId, branchId);
        const mergedCount = typeof data.merged_count === 'number' ? data.merged_count : null;
        message.success(
          mergedCount !== null ? `分支已合并，共整理 ${mergedCount} 条消息` : '分支已合并',
        );
        await loadBranchState();
      } catch (error) {
        message.warning(error instanceof Error ? error.message : '合并分支失败');
      }
    },
    [loadBranchState, sessionId],
  );

  return (
    <>
      <Modal
        title={
          <Space>
            <BranchesOutlined />
            <span>对话分支管理</span>
          </Space>
        }
        open={visible}
        onCancel={onClose}
        width={720}
        footer={[
          <Button key="close" onClick={onClose}>
            关闭
          </Button>,
          <Button
            key="create"
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setShowCreateModal(true)}
            disabled={!selectedNode}
          >
            创建分支
          </Button>,
        ]}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">选择一条消息作为分叉点，然后创建、切换、合并或删除分支。</Text>
        </div>

        <Card title="对话树" size="small" style={{ marginBottom: 16 }} loading={loading}>
          <Tree
            showLine
            defaultExpandAll
            treeData={treeData}
            onSelect={(selectedKeys) => setSelectedNode((selectedKeys[0] as string) || null)}
            selectedKeys={selectedNode ? [selectedNode] : []}
            style={{ marginTop: 8 }}
          />
        </Card>

        <Card title="分支列表" size="small" loading={loading}>
          {branches.length === 0 ? (
            <Text type="secondary">暂无分支</Text>
          ) : (
            <Space direction="vertical" style={{ width: '100%' }}>
              {branches.map((branch) => (
                <div
                  key={branch.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 12px',
                    background: currentBranchId === branch.id ? '#e6f7ff' : '#fafafa',
                    borderRadius: 6,
                  }}
                >
                  <div>
                    <Text strong>{branch.name}</Text>
                    <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                      {branch.message_count} 条消息
                    </Text>
                    {currentBranchId === branch.id ? (
                      <Tag color="blue" style={{ marginLeft: 8 }}>
                        当前
                      </Tag>
                    ) : null}
                  </div>
                  <Space>
                    {currentBranchId !== branch.id ? (
                      <Button
                        size="small"
                        icon={<SwapOutlined />}
                        onClick={() => {
                          void handleSwitchBranch(branch.id);
                        }}
                      >
                        切换
                      </Button>
                    ) : null}
                    <Dropdown
                      menu={{
                        items: [
                          {
                            key: 'merge',
                            icon: <MergeOutlined />,
                            label: '合并到当前分支',
                            onClick: () => {
                              void handleMergeBranch(branch.id);
                            },
                            disabled: currentBranchId === branch.id,
                          },
                          {
                            key: 'delete',
                            icon: <DeleteOutlined />,
                            label: '删除分支',
                            danger: true,
                            onClick: () => {
                              appModal.confirm({
                                title: '确认删除',
                                content: '确定要删除这个分支吗？',
                                okButtonProps: { danger: true },
                                onOk: async () => {
                                  await handleDeleteBranch(branch.id);
                                },
                              });
                            },
                          },
                        ],
                      }}
                    >
                      <Button size="small" icon={<MoreOutlined />} aria-label="更多操作" />
                    </Dropdown>
                  </Space>
                </div>
              ))}
            </Space>
          )}
        </Card>
      </Modal>

      <Modal
        title="创建新分支"
        open={showCreateModal}
        onCancel={() => {
          setShowCreateModal(false);
          setNewBranchName('');
        }}
        onOk={() => {
          void handleCreateBranch();
        }}
        okText="创建"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <Text>将从当前选中的消息创建一条新分支。</Text>
        </div>
        <Input
          placeholder="分支名称（可选）"
          value={newBranchName}
          onChange={(event) => setNewBranchName(event.target.value)}
          prefix={<EditOutlined />}
        />
      </Modal>
    </>
  );
};

export default ChatBranchManager;
