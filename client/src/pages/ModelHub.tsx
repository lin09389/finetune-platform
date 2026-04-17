import {
  CloudDownloadOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { App, Button, Input, Modal, Progress, Segmented, Space, Table, Tag, Tooltip } from 'antd';
import { useEffect, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { API_BASE_URL } from '../services/api';
import styles from './ModelHub.module.css';

interface ModelSuggestion {
  repo_id: string;
  name: string;
  description: string;
  size: string;
  category: string;
  source: string;
}

interface LocalModel {
  id: string;
  name: string;
  path: string;
  size: number;
  created_at: string;
}

interface DownloadTask {
  task_id: string;
  status: string;
  progress: number;
  error?: string;
  source?: string;
}

interface SearchResult {
  id: string;
  modelId: string;
  name: string;
  downloads: number;
  likes: number;
  library_name?: string;
  tags: string[];
  source: string;
}

export default function ModelHub() {
  const { message } = App.useApp();
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [suggestions, setSuggestions] = useState<ModelSuggestion[]>([]);
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [downloadTasks, setDownloadTasks] = useState<Record<string, DownloadTask>>({});
  const [modelSource, setModelSource] = useState<string>('modelscope');
  const [, setDefaultSource] = useState<string>('modelscope');

  useEffect(() => {
    loadSuggestions();
    loadLocalModels();
    loadModelSource();
  }, []);

  const loadModelSource = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/model-center/source`);
      if (response.ok) {
        const data = await response.json();
        setModelSource(data.current_source);
        setDefaultSource(data.default_source);
      }
    } catch (error) {
      console.error('Failed to load model source:', error);
    }
  };

  const loadSuggestions = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/model-center/suggestions`);
      if (response.ok) {
        const data = await response.json();
        setSuggestions(data.suggestions);
        setDefaultSource(data.default_source || 'modelscope');
      }
    } catch (error) {
      console.error('Failed to load suggestions:', error);
    }
  };

  const loadLocalModels = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/model-center/local`);
      if (response.ok) {
        const data = await response.json();
        setLocalModels(data);
      }
    } catch (error) {
      console.error('Failed to load local models:', error);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const response = await fetch(`${API_BASE_URL}/model-center/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, limit: 20, source: modelSource }),
      });
      if (response.ok) {
        const data = await response.json();
        setSearchResults(data);
      }
    } catch (error) {
      message.error('搜索失败');
    } finally {
      setSearching(false);
    }
  };

  const handleDownload = async (repoId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/model-center/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_id: repoId,
          revision: modelSource === 'modelscope' ? 'master' : 'main',
          source: modelSource,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        message.success(
          `开始下载：${repoId}（${data.source === 'modelscope' ? '魔搭社区' : 'HuggingFace'}）`,
        );
        setDownloadTasks((prev) => ({
          ...prev,
          [data.task_id]: {
            task_id: data.task_id,
            status: 'pending',
            progress: 0,
            source: data.source,
          },
        }));
        pollProgress(data.task_id);
      }
    } catch (error) {
      message.error('下载失败');
    }
  };

  const pollProgress = async (taskId: string) => {
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/model-center/download/${taskId}`);
        if (response.ok) {
          const data = await response.json();
          setDownloadTasks((prev) => ({
            ...prev,
            [taskId]: {
              task_id: data.task_id,
              status: data.status,
              progress: data.progress,
              error: data.error,
            },
          }));
          if (data.status === 'completed' || data.status === 'failed') {
            if (data.status === 'completed') {
              message.success('下载完成');
              loadLocalModels();
            } else {
              message.error(`下载失败：${data.error}`);
            }
          } else {
            setTimeout(poll, 2000);
          }
        }
      } catch (error) {
        console.error('Failed to poll progress:', error);
      }
    };
    setTimeout(poll, 2000);
  };

  const handleDeleteLocal = async (modelId: string) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除模型 ${modelId} 吗？`,
      onOk: async () => {
        try {
          const response = await fetch(`${API_BASE_URL}/model-center/local/${modelId}`, {
            method: 'DELETE',
          });
          if (response.ok) {
            message.success('已删除');
            loadLocalModels();
          } else {
            message.error('删除失败');
          }
        } catch (error) {
          message.error('删除失败');
        }
      },
    });
  };

  const handleSourceChange = (value: string) => {
    setModelSource(value);
    setSearchResults([]);
  };

  const localColumns = [
    { title: '模型名称', dataIndex: 'name', key: 'name' },
    { title: '路径', dataIndex: 'path', key: 'path', ellipsis: true },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      render: (size: number) => `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`,
    },
    { title: '下载时间', dataIndex: 'created_at', key: 'created_at' },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: LocalModel) => (
        <Button
          danger
          size="small"
          icon={<DeleteOutlined />}
          onClick={() => handleDeleteLocal(record.id)}
        >
          删除
        </Button>
      ),
    },
  ];

  const categoryColor = (cat: string) =>
    cat === 'chat' ? 'blue' : cat === 'embedding' ? 'purple' : 'orange';

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
        {/* 标题栏 */}
        <div className={styles.headerCard}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <CloudServerOutlined />
            </div>
            <div>
              <h2 className={styles.headerTitle}>模型中心</h2>
              <p className={styles.headerSubtitle}>
                Beta 能力：搜索、下载并管理本地模型，但可用性仍受外部源和网络状态影响
              </p>
            </div>
          </div>
        </div>

        {/* 搜索区域 */}
        <div className={styles.searchCard}>
          <div className={styles.sectionTitle}>
            <SearchOutlined /> 搜索模型
          </div>
          <div style={{ marginBottom: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
            搜索结果、下载速度和可访问性会随 `ModelScope / HuggingFace`
            源状态变化，请以实际返回结果为准。
          </div>
          <div className={styles.sourceToggle}>
            <Segmented
              value={modelSource}
              onChange={(value) => handleSourceChange(value as string)}
              options={[
                { label: '魔搭社区 (ModelScope)', value: 'modelscope' },
                { label: 'HuggingFace', value: 'huggingface' },
              ]}
            />
            <Tooltip
              title={
                modelSource === 'modelscope'
                  ? '国内访问更稳定，下载速度更快'
                  : '国际模型库，模型资源丰富'
              }
            >
              <InfoCircleOutlined style={{ color: 'var(--text-tertiary)' }} />
            </Tooltip>
          </div>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              placeholder={
                modelSource === 'modelscope'
                  ? '输入模型名称，如：Qwen、ChatGLM、Yi'
                  : '输入模型名称，如：llama, qwen, chatglm'
              }
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onPressEnter={handleSearch}
              size="large"
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={handleSearch}
              loading={searching}
              size="large"
            >
              搜索
            </Button>
          </Space.Compact>
        </div>

        {/* 下载进度 */}
        {Object.keys(downloadTasks).length > 0 && (
          <div className={styles.downloadCard}>
            <div className={styles.sectionTitle}>
              <DownloadOutlined /> 下载进度
            </div>
            {Object.values(downloadTasks).map((task) => (
              <div key={task.task_id} className={styles.downloadItem}>
                <div className={styles.downloadMeta}>
                  <span>任务：{task.task_id}</span>
                  <Space>
                    {task.source && (
                      <Tag color={task.source === 'modelscope' ? 'green' : 'blue'}>
                        {task.source === 'modelscope' ? '魔搭社区' : 'HuggingFace'}
                      </Tag>
                    )}
                    <Tag
                      color={
                        task.status === 'completed'
                          ? 'green'
                          : task.status === 'failed'
                            ? 'red'
                            : 'blue'
                      }
                    >
                      {task.status}
                    </Tag>
                  </Space>
                </div>
                <Progress
                  percent={Math.round(task.progress)}
                  status={task.status === 'failed' ? 'exception' : 'active'}
                />
                {task.error && (
                  <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>{task.error}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 推荐模型 */}
        {searchResults.length === 0 && suggestions.length > 0 && (
          <div className={styles.suggestionsCard}>
            <div className={styles.cardTitleRow}>
              <div className={styles.sectionTitle} style={{ marginBottom: 0 }}>
                推荐模型
              </div>
              <Button type="link" icon={<ReloadOutlined />} onClick={loadSuggestions}>
                刷新
              </Button>
            </div>
            <div className={styles.modelGrid}>
              {suggestions.map((model) => (
                <div key={model.repo_id} className={styles.modelCard}>
                  <div className={styles.modelName}>{model.name}</div>
                  <div className={styles.modelTagRow}>
                    <Tag color={categoryColor(model.category)}>{model.category}</Tag>
                    <Tag color="green">魔搭社区</Tag>
                  </div>
                  <div className={styles.modelDesc}>{model.description}</div>
                  <div className={styles.modelMeta}>
                    大小：{model.size} · {model.repo_id}
                  </div>
                  <div className={styles.modelCardFooter}>
                    <Button
                      type="primary"
                      size="small"
                      icon={<DownloadOutlined />}
                      onClick={() => handleDownload(model.repo_id)}
                    >
                      下载
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 搜索结果 */}
        {searchResults.length > 0 && (
          <div className={styles.searchResultCard}>
            <div className={styles.cardTitleRow}>
              <div className={styles.sectionTitle} style={{ marginBottom: 0 }}>
                搜索结果（{searchResults.length}）
              </div>
              <Button onClick={() => setSearchResults([])}>清空</Button>
            </div>
            {searchResults.map((model) => (
              <div key={model.id} className={styles.resultItem}>
                <div className={styles.resultInfo}>
                  <div className={styles.resultName}>
                    <span>{model.modelId}</span>
                    {model.library_name && <Tag color="blue">{model.library_name}</Tag>}
                    <Tag color={model.source === 'modelscope' ? 'green' : 'blue'}>
                      {model.source === 'modelscope' ? '魔搭社区' : 'HuggingFace'}
                    </Tag>
                  </div>
                  <div className={styles.resultStats}>
                    <span>{model.downloads} 下载</span>
                    <span>·</span>
                    <span>{model.likes} 喜欢</span>
                    {model.tags?.slice(0, 3).map((tag: string) => (
                      <Tag key={tag} style={{ fontSize: 11, margin: 0 }}>
                        {tag}
                      </Tag>
                    ))}
                  </div>
                </div>
                <Button
                  type="primary"
                  icon={<CloudDownloadOutlined />}
                  onClick={() => handleDownload(model.modelId)}
                >
                  下载
                </Button>
              </div>
            ))}
          </div>
        )}

        {/* 本地模型 */}
        <div className={styles.localCard}>
          <div className={styles.cardTitleRow}>
            <div className={styles.sectionTitle} style={{ marginBottom: 0 }}>
              本地模型
            </div>
            <Button icon={<ReloadOutlined />} onClick={loadLocalModels}>
              刷新
            </Button>
          </div>
          {localModels.length > 0 ? (
            <Table columns={localColumns} dataSource={localModels} rowKey="id" pagination={false} />
          ) : (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>📦</div>
              <div>暂无本地模型</div>
            </div>
          )}
        </div>
      </MotionItem>
    </MotionList>
  );
}
