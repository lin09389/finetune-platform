import {
  BookOutlined,
  ClearOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  ImportOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Badge,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  message,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Slider,
  Space,
  Spin,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { useEffect, useState } from 'react';

import { Memory, MEMORY_TYPES, MemoryStats, memoryApi } from '../services/memoryApi';

const { Search, TextArea } = Input;
const { Text } = Typography;
const { Option } = Select;

interface MemoryManagerProps {
  open: boolean;
  onClose: () => void;
}

interface MemoryFormValues {
  content: string;
  type: string;
  importance: number;
}

export default function MemoryManager({ open, onClose }: MemoryManagerProps) {
  const [form] = Form.useForm<MemoryFormValues>();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeType, setActiveType] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);

  useEffect(() => {
    if (open) {
      loadData();
    }
  }, [open, activeType]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [memoriesData, statsData] = await Promise.all([
        memoryApi.listMemories('default', activeType === 'all' ? undefined : activeType, 100),
        memoryApi.getStats(),
      ]);
      setMemories(memoriesData.memories);
      setTotalCount(memoriesData.count);
      setStats(statsData);
    } catch (error) {
      console.error('加载记忆失败:', error);
      message.error('加载记忆失败');
    } finally {
      setLoading(false);
    }
  };

  const searchMemories = async () => {
    if (!searchQuery.trim()) {
      loadData();
      return;
    }

    setLoading(true);
    try {
      const results = await memoryApi.recall(
        searchQuery,
        'default',
        20,
        activeType === 'all' ? undefined : activeType,
      );
      setMemories(results);
      setTotalCount(results.length);
    } catch (error) {
      console.error('搜索失败:', error);
      message.error('搜索失败');
    } finally {
      setLoading(false);
    }
  };

  const openCreateEditor = () => {
    setSelectedMemory(null);
    form.setFieldsValue({ content: '', type: 'knowledge', importance: 0.5 });
    setEditorOpen(true);
  };

  const openEditEditor = (memory: Memory) => {
    setSelectedMemory(memory);
    form.setFieldsValue({
      content: memory.content,
      type: memory.type,
      importance: memory.importance,
    });
    setEditorOpen(true);
  };

  const saveMemory = async () => {
    const values = await form.validateFields();
    try {
      if (selectedMemory) {
        await memoryApi.updateMemory(selectedMemory.id, {
          content: values.content,
          importance: values.importance,
        });
        message.success('记忆已更新');
      } else {
        await memoryApi.addMemory(values.content, values.type, values.importance);
        message.success('记忆已创建');
      }
      setEditorOpen(false);
      setSelectedMemory(null);
      loadData();
    } catch (error) {
      console.error('保存记忆失败:', error);
      message.error('保存记忆失败');
    }
  };

  const deleteMemory = async (memoryId: string) => {
    try {
      await memoryApi.deleteMemory(memoryId);
      message.success('已删除');
      loadData();
    } catch (error) {
      console.error('删除失败:', error);
      message.error('删除失败');
    }
  };

  const clearAllMemories = async () => {
    try {
      await memoryApi.clearAll();
      message.success('所有记忆已清除');
      setMemories([]);
      setTotalCount(0);
      loadData();
    } catch (error) {
      console.error('清除失败:', error);
      message.error('清除失败');
    }
  };

  const exportState = async () => {
    try {
      const state = await memoryApi.exportState();
      const blob = new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `memory-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      message.success('导出成功');
    } catch (error) {
      message.error('导出失败');
    }
  };

  const importState = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file) return;

      try {
        const text = await file.text();
        await memoryApi.importState(JSON.parse(text));
        message.success('导入成功');
        loadData();
      } catch (error) {
        message.error('导入失败');
      }
    };
    input.click();
  };

  const getTypeConfig = (type: string) => {
    return MEMORY_TYPES[type] || { label: type, color: 'default', icon: '📄' };
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    try {
      return new Date(dateStr).toLocaleString('zh-CN');
    } catch {
      return dateStr;
    }
  };

  const renderImportance = (importance: number) => (
    <Progress
      percent={Math.round(importance * 100)}
      size="small"
      showInfo={false}
      strokeColor={{
        '0%': '#ff4d4f',
        '50%': '#faad14',
        '100%': '#52c41a',
      }}
      style={{ width: 64 }}
    />
  );

  return (
    <Modal
      title={
        <Space>
          <BookOutlined />
          <span>长期记忆管理</span>
          <Badge count={totalCount} />
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={
        <Space>
          <Button icon={<ExportOutlined />} onClick={exportState}>
            导出
          </Button>
          <Button icon={<ImportOutlined />} onClick={importState}>
            导入
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </Space>
      }
      width={860}
    >
      <Space style={{ width: '100%', marginBottom: 16, justifyContent: 'space-between' }}>
        <Space wrap>
          <Search
            placeholder="搜索长期记忆..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onSearch={searchMemories}
            style={{ width: 300 }}
            enterButton={<SearchOutlined />}
          />
          <Select value={activeType} onChange={setActiveType} style={{ width: 150 }}>
            <Option value="all">全部类型</Option>
            {Object.entries(MEMORY_TYPES).map(([key, config]) => (
              <Option key={key} value={key}>
                {config.icon} {config.label}
              </Option>
            ))}
          </Select>
        </Space>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateEditor}>
            新建
          </Button>
          <Popconfirm
            title="确定清除所有记忆？"
            description="此操作不可恢复"
            onConfirm={clearAllMemories}
          >
            <Button danger icon={<ClearOutlined />}>
              清除全部
            </Button>
          </Popconfirm>
        </Space>
      </Space>

      {stats && (
        <Space style={{ marginBottom: 16 }}>
          <Card size="small">
            <Statistic title="总记忆数" value={stats.total_memories} prefix={<BookOutlined />} />
          </Card>
          <Card size="small">
            <Statistic title="向量索引" value={stats.vector_collection_count} />
          </Card>
          <Card size="small">
            <Statistic title="存储模式" value={stats.collection_name || 'SQLite FTS'} />
          </Card>
        </Space>
      )}

      {loading ? (
        <Spin style={{ display: 'block', margin: '40px auto' }} />
      ) : memories.length === 0 ? (
        <Empty description="暂无记忆" image={Empty.PRESENTED_IMAGE_SIMPLE}>
          <Text type="secondary">对话中提到的重要信息会保存为长期记忆</Text>
        </Empty>
      ) : (
        <List
          dataSource={memories}
          style={{ maxHeight: 460, overflow: 'auto' }}
          renderItem={(memory) => {
            const config = getTypeConfig(memory.type);

            return (
              <List.Item
                actions={[
                  <Tooltip key="edit" title="编辑">
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(event) => {
                        event.stopPropagation();
                        openEditEditor(memory);
                      }}
                    />
                  </Tooltip>,
                  <Popconfirm
                    key="delete"
                    title="确定删除这条记忆？"
                    onConfirm={() => deleteMemory(memory.id)}
                  >
                    <Button
                      type="text"
                      danger
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={(event) => event.stopPropagation()}
                    />
                  </Popconfirm>,
                ]}
                onClick={() => {
                  setSelectedMemory(memory);
                  setDetailDrawerOpen(true);
                }}
              >
                <List.Item.Meta
                  avatar={
                    <Tag color={config.color} style={{ padding: '4px 8px' }}>
                      {config.icon}
                    </Tag>
                  }
                  title={<Text style={{ fontSize: 14 }}>{memory.content}</Text>}
                  description={
                    <Space split={<span style={{ color: '#d9d9d9' }}>|</span>} style={{ fontSize: 12 }}>
                      <span>
                        <ClockCircleOutlined /> {formatDate(memory.created_at)}
                      </span>
                      <span>重要度: {renderImportance(memory.importance)}</span>
                      <span>访问: {memory.access_count}次</span>
                      {memory.relevance !== undefined && memory.relevance > 0 && (
                        <span>相关度: {(memory.relevance * 100).toFixed(0)}%</span>
                      )}
                    </Space>
                  }
                />
              </List.Item>
            );
          }}
        />
      )}

      <Modal
        title={selectedMemory ? '编辑记忆' : '新建记忆'}
        open={editorOpen}
        onOk={saveMemory}
        onCancel={() => setEditorOpen(false)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="content" label="内容" rules={[{ required: true, message: '请输入记忆内容' }]}>
            <TextArea rows={4} />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select disabled={Boolean(selectedMemory)}>
              {Object.entries(MEMORY_TYPES).map(([key, config]) => (
                <Option key={key} value={key}>
                  {config.icon} {config.label}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="importance" label="重要度">
            <Slider min={0} max={1} step={0.1} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title="记忆详情"
        placement="right"
        width={400}
        open={detailDrawerOpen}
        onClose={() => setDetailDrawerOpen(false)}
      >
        {selectedMemory && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <strong>ID:</strong> {selectedMemory.id}
            </div>
            <div>
              <strong>类型:</strong> {getTypeConfig(selectedMemory.type).label}
            </div>
            <div>
              <strong>内容:</strong>
            </div>
            <Card size="small">{selectedMemory.content}</Card>
            <div>
              <strong>重要度:</strong> {renderImportance(selectedMemory.importance)}
            </div>
            <div>
              <strong>创建时间:</strong> {formatDate(selectedMemory.created_at)}
            </div>
            <div>
              <strong>最后访问:</strong> {formatDate(selectedMemory.last_accessed)}
            </div>
            <div>
              <strong>访问次数:</strong> {selectedMemory.access_count}
            </div>
            <div>
              <strong>索引状态:</strong> {selectedMemory.vector_state || '-'}
            </div>
          </Space>
        )}
      </Drawer>
    </Modal>
  );
}
