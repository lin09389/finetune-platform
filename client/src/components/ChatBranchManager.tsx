import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  Tree,
  Button,
  Space,
  Tag,
  Typography,
  message,
  Input,
  Dropdown,
  Card,
} from 'antd';
import {
  BranchesOutlined,
  PlusOutlined,
  DeleteOutlined,
  SwapOutlined,
  MergeOutlined,
  MoreOutlined,
  EditOutlined,
} from '@ant-design/icons';
import type { DataNode } from 'antd/es/tree';

const { Text } = Typography;

interface MessageNode {
  id: string;
  role: string;
  content: string;
  timestamp: string;
  parent_id: string | null;
  children_ids: string[];
  branch_name?: string;
}

interface ChatBranch {
  id: string;
  session_id: string;
  name: string;
  created_at: string;
  root_message_id: string | null;
  message_count: number;
}

interface ChatBranchManagerProps {
  visible: boolean;
  sessionId: string;
  onClose: () => void;
  onBranchSwitch?: (branchId: string) => void;
  onBranchCreate?: (branchId: string) => void;
}

const API_BASE = '/api/chat';

const ChatBranchManager: React.FC<ChatBranchManagerProps> = ({
  visible,
  sessionId,
  onClose,
  onBranchSwitch,
  onBranchCreate,
}) => {
  const [, setLoading] = useState(false);
  const [treeData, setTreeData] = useState<DataNode[]>([]);
  const [, setNodes] = useState<Record<string, MessageNode>>({});
  const [branches, setBranches] = useState<ChatBranch[]>([]);
  const [currentBranchId, setCurrentBranchId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [newBranchName, setNewBranchName] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);

  const fetchData = useCallback(async () => {
    if (!sessionId) return;
    
    setLoading(true);
    try {
      const [treeRes, branchesRes] = await Promise.all([
        fetch(`${API_BASE}/${sessionId}/tree`),
        fetch(`${API_BASE}/${sessionId}/branches`),
      ]);

      if (treeRes.ok) {
        const treeData = await treeRes.json();
        setNodes(treeData.nodes || {});
        setCurrentBranchId(treeData.current_branch_id);
        
        const dataNodes = buildTreeData(treeData.nodes || {}, treeData.root_id);
        setTreeData(dataNodes);
      }

      if (branchesRes.ok) {
        const branchesData = await branchesRes.json();
        setBranches(branchesData.branches || []);
      }
    } catch (error) {
      console.error('Failed to fetch branch data:', error);
      message.error('加载分支数据失败');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    if (visible) {
      fetchData();
    }
  }, [visible, fetchData]);

  const buildTreeData = (
    nodesMap: Record<string, MessageNode>,
    rootId: string | null
  ): DataNode[] => {
    if (!rootId || !nodesMap[rootId]) return [];

    const buildNode = (nodeId: string): DataNode => {
      const node = nodesMap[nodeId];
      if (!node) return { key: nodeId, title: 'Unknown' };

      const children = node.children_ids
        .map((childId) => buildNode(childId))
        .filter((n) => n.key);

      const roleIcon = node.role === 'user' ? '👤' : '🤖';
      const branchTag = node.branch_name ? (
        <Tag color="blue" style={{ marginLeft: 4 }}>
          {node.branch_name}
        </Tag>
      ) : null;

      return {
        key: nodeId,
        title: (
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <span>{roleIcon}</span>
            <Text
              ellipsis
              style={{ maxWidth: 200, marginLeft: 8 }}
            >
              {node.content.substring(0, 30)}...
            </Text>
            {branchTag}
          </div>
        ),
        children: children.length > 0 ? children : undefined,
      };
    };

    return [buildNode(rootId)];
  };

  const handleCreateBranch = async () => {
    if (!selectedNode) {
      message.warning('请先选择一个消息节点');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/branch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          from_message_id: selectedNode,
          branch_name: newBranchName || undefined,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        message.success('分支创建成功');
        setShowCreateModal(false);
        setNewBranchName('');
        fetchData();
        onBranchCreate?.(data.branch.id);
      } else {
        message.error('创建分支失败');
      }
    } catch (error) {
      console.error('Failed to create branch:', error);
      message.error('创建分支失败');
    }
  };

  const handleSwitchBranch = async (branchId: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/${sessionId}/switch-branch/${branchId}`,
        { method: 'POST' }
      );

      if (response.ok) {
        message.success('已切换分支');
        setCurrentBranchId(branchId);
        onBranchSwitch?.(branchId);
      } else {
        message.error('切换分支失败');
      }
    } catch (error) {
      console.error('Failed to switch branch:', error);
      message.error('切换分支失败');
    }
  };

  const handleDeleteBranch = async (branchId: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/${sessionId}/branch/${branchId}`,
        { method: 'DELETE' }
      );

      if (response.ok) {
        message.success('分支已删除');
        fetchData();
      } else {
        message.error('删除分支失败');
      }
    } catch (error) {
      console.error('Failed to delete branch:', error);
      message.error('删除分支失败');
    }
  };

  const handleMergeBranch = async (branchId: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/${sessionId}/merge-branch/${branchId}`,
        { method: 'POST' }
      );

      if (response.ok) {
        message.success('分支已合并');
        fetchData();
      } else {
        message.error('合并分支失败');
      }
    } catch (error) {
      console.error('Failed to merge branch:', error);
      message.error('合并分支失败');
    }
  };

  const handleNodeSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      setSelectedNode(selectedKeys[0] as string);
    }
  };

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
        width={700}
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
          <Text type="secondary">
            选择一个消息节点创建分支，或管理现有分支
          </Text>
        </div>

        <Card title="对话树" size="small" style={{ marginBottom: 16 }}>
          <Tree
            showLine
            defaultExpandAll
            treeData={treeData}
            onSelect={handleNodeSelect}
            selectedKeys={selectedNode ? [selectedNode] : []}
            style={{ marginTop: 8 }}
          />
        </Card>

        <Card title="分支列表" size="small">
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
                    {currentBranchId === branch.id && (
                      <Tag color="blue" style={{ marginLeft: 8 }}>
                        当前
                      </Tag>
                    )}
                  </div>
                  <Space>
                    {currentBranchId !== branch.id && (
                      <Button
                        size="small"
                        icon={<SwapOutlined />}
                        onClick={() => handleSwitchBranch(branch.id)}
                      >
                        切换
                      </Button>
                    )}
                    <Dropdown
                      menu={{
                        items: [
                          {
                            key: 'merge',
                            icon: <MergeOutlined />,
                            label: '合并到当前分支',
                            onClick: () => handleMergeBranch(branch.id),
                            disabled: currentBranchId === branch.id,
                          },
                          {
                            key: 'delete',
                            icon: <DeleteOutlined />,
                            label: '删除分支',
                            danger: true,
                            onClick: () => {
                              Modal.confirm({
                                title: '确认删除',
                                content: '确定要删除此分支吗？',
                                onOk: () => handleDeleteBranch(branch.id),
                              });
                            },
                          },
                        ],
                      }}
                    >
                      <Button size="small" icon={<MoreOutlined />} />
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
        onOk={handleCreateBranch}
        okText="创建"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <Text>将从选中的消息创建新分支</Text>
        </div>
        <Input
          placeholder="分支名称（可选）"
          value={newBranchName}
          onChange={(e) => setNewBranchName(e.target.value)}
          prefix={<EditOutlined />}
        />
      </Modal>
    </>
  );
};

export default ChatBranchManager;
