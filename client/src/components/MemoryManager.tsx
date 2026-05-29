import {
  CheckCircleOutlined,
  FileMarkdownOutlined,
  HistoryOutlined,
  ReloadOutlined,
  SaveOutlined,
  SearchOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Empty,
  Input,
  List,
  message,
  Modal,
  Segmented,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';

import {
  EpisodeEvent,
  MemoryFile,
  MemoryScope,
  MemorySearchResult,
  MEMORY_SCOPE_LABELS,
  memoryApi,
} from '../services/memoryApi';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface MemoryManagerProps {
  open: boolean;
  onClose: () => void;
}

const DEFAULT_NAMESPACE: Record<MemoryScope, string> = {
  user: 'default',
  agent: 'build',
  org: 'default-org',
};

export default function MemoryManager({ open, onClose }: MemoryManagerProps) {
  const [scope, setScope] = useState<MemoryScope>('user');
  const [namespace, setNamespace] = useState(DEFAULT_NAMESPACE.user);
  const [files, setFiles] = useState<MemoryFile[]>([]);
  const [selectedFileId, setSelectedFileId] = useState<string>();
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MemorySearchResult[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeEvent[]>([]);

  const selectedFile = useMemo(
    () => files.find((file) => file.id === selectedFileId) || files[0],
    [files, selectedFileId],
  );

  useEffect(() => {
    setNamespace(DEFAULT_NAMESPACE[scope]);
  }, [scope]);

  useEffect(() => {
    if (open) {
      loadFiles();
      loadEpisodes();
    }
  }, [open, scope, namespace]);

  useEffect(() => {
    setDraft(selectedFile?.content || '');
    setSelectedFileId(selectedFile?.id);
  }, [selectedFile?.id]);

  const loadFiles = async () => {
    setLoading(true);
    try {
      const nextFiles = await memoryApi.listFiles(scope, namespace);
      setFiles(nextFiles);
      setSelectedFileId((current) => current || nextFiles[0]?.id);
    } catch (error) {
      console.error('加载记忆文件失败:', error);
      message.error('加载记忆文件失败');
    } finally {
      setLoading(false);
    }
  };

  const loadEpisodes = async () => {
    try {
      setEpisodes(await memoryApi.listEpisodes('default'));
    } catch (error) {
      console.error('加载 episode 失败:', error);
    }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    if (!selectedFile.writable) {
      message.warning('该文件是只读策略');
      return;
    }
    setSaving(true);
    try {
      const updated = await memoryApi.updateFile(selectedFile.id, draft, {
        edited_from: 'memory_manager',
      });
      setFiles((current) => current.map((file) => (file.id === updated.id ? updated : file)));
      message.success('记忆文件已保存');
    } catch (error) {
      console.error('保存失败:', error);
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const runSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    setLoading(true);
    try {
      setSearchResults(
        await memoryApi.search({
          query: searchQuery,
          scope,
          namespace,
          user_id: DEFAULT_NAMESPACE.user,
          top_k: 20,
        }),
      );
    } catch (error) {
      console.error('搜索失败:', error);
      message.error('搜索失败');
    } finally {
      setLoading(false);
    }
  };

  const consolidate = async () => {
    try {
      const result = await memoryApi.consolidate('default');
      message.success(`整理完成：写入 ${result.memories_written} 条`);
      await loadFiles();
    } catch (error) {
      console.error('整理失败:', error);
      message.error('整理失败');
    }
  };

  const migrate = async () => {
    try {
      const result = await memoryApi.migrateFromItems('default');
      message.success(`迁移完成：新增 ${result.migrated} 条，跳过 ${result.skipped} 条`);
      await loadFiles();
    } catch (error) {
      console.error('迁移失败:', error);
      message.error('迁移失败');
    }
  };

  const formatDate = (value: string) => {
    try {
      return new Date(value).toLocaleString('zh-CN');
    } catch {
      return value || '-';
    }
  };

  const filePanel = (
    <div style={{ display: 'grid', gridTemplateColumns: '240px minmax(0, 1fr)', gap: 16 }}>
      <div>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Segmented
            block
            value={scope}
            onChange={(value) => setScope(value as MemoryScope)}
            options={[
              { label: 'User', value: 'user' },
              { label: 'Agent', value: 'agent' },
              { label: 'Org', value: 'org' },
            ]}
          />
          <Input
            value={namespace}
            onChange={(event) => setNamespace(event.target.value)}
            onPressEnter={loadFiles}
            addonBefore="namespace"
          />
          <Button icon={<ReloadOutlined />} onClick={loadFiles} block>
            刷新
          </Button>
          <List
            bordered
            size="small"
            dataSource={files}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文件" /> }}
            renderItem={(file) => (
              <List.Item
                style={{
                  cursor: 'pointer',
                  background: file.id === selectedFile?.id ? '#f0f7ff' : undefined,
                }}
                onClick={() => setSelectedFileId(file.id)}
              >
                <Space direction="vertical" size={2}>
                  <Space>
                    <FileMarkdownOutlined />
                    <Text strong={file.id === selectedFile?.id}>{file.relative_path}</Text>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    v{file.version} · {file.writable ? '可写' : '只读'}
                  </Text>
                </Space>
              </List.Item>
            )}
          />
        </Space>
      </div>

      <div>
        {loading ? (
          <Spin style={{ display: 'block', margin: '80px auto' }} />
        ) : selectedFile ? (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space>
                <Tag color={selectedFile.scope === 'org' ? 'gold' : 'blue'}>
                  {MEMORY_SCOPE_LABELS[selectedFile.scope]}
                </Tag>
                <Text strong>{selectedFile.path}</Text>
                <Text type="secondary">v{selectedFile.version}</Text>
              </Space>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                disabled={!selectedFile.writable}
                onClick={saveFile}
              >
                保存
              </Button>
            </Space>
            {!selectedFile.writable && <Alert type="info" showIcon message="组织策略为只读，只能由应用代码更新。" />}
            <TextArea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={18}
              disabled={!selectedFile.writable}
              style={{ fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace' }}
            />
            <Text type="secondary">更新时间：{formatDate(selectedFile.updated_at)}</Text>
          </Space>
        ) : (
          <Empty description="请选择记忆文件" />
        )}
      </div>
    </div>
  );

  const searchPanel = (
    <Space direction="vertical" style={{ width: '100%' }} size={12}>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onPressEnter={runSearch}
          placeholder="搜索当前 namespace 的文件记忆"
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={runSearch}>
          搜索
        </Button>
      </Space.Compact>
      <List
        bordered
        dataSource={searchResults}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无搜索结果" /> }}
        renderItem={(result) => (
          <List.Item>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <Tag>{result.scope}</Tag>
                <Text strong>{result.path}</Text>
                <Text type="secondary">{Math.round(result.score * 100)}%</Text>
              </Space>
              <Paragraph style={{ marginBottom: 0 }}>{result.snippet}</Paragraph>
              <Text type="secondary">{formatDate(result.updated_at)}</Text>
            </Space>
          </List.Item>
        )}
      />
    </Space>
  );

  const episodesPanel = (
    <Space direction="vertical" style={{ width: '100%' }} size={12}>
      <Space>
        <Button icon={<SyncOutlined />} onClick={consolidate}>
          整理近期对话
        </Button>
        <Button icon={<CheckCircleOutlined />} onClick={migrate}>
          迁移旧记忆
        </Button>
        <Button icon={<ReloadOutlined />} onClick={loadEpisodes}>
          刷新
        </Button>
      </Space>
      <List
        bordered
        dataSource={episodes}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 episode" /> }}
        renderItem={(event) => (
          <List.Item>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <HistoryOutlined />
                <Text strong>{event.session_id}</Text>
                <Tag>{event.role}</Tag>
                <Text type="secondary">{formatDate(event.created_at)}</Text>
              </Space>
              <Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }} style={{ marginBottom: 0 }}>
                {event.content}
              </Paragraph>
            </Space>
          </List.Item>
        )}
      />
    </Space>
  );

  return (
    <Modal
      title="DeepAgents 文件记忆"
      open={open}
      onCancel={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}
      width={1040}
    >
      <Tabs
        items={[
          { key: 'files', label: '文件', children: filePanel },
          { key: 'search', label: '搜索', children: searchPanel },
          { key: 'episodes', label: 'Episodes', children: episodesPanel },
        ]}
      />
    </Modal>
  );
}
