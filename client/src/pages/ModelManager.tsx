import {
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FolderOpenOutlined,
  ImportOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Button,
  Empty,
  Form,
  Input,
  message,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Tabs,
  Tag,
} from 'antd';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import GlassCard from '../components/shared/GlassCard';
import glassStyles from '../components/shared/GlassCard.module.css';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import PageHeader from '../components/shared/PageHeader';
import { useOperation } from '../hooks/useOperation';
import {
  deleteModel,
  downloadModel,
  getModelList,
  importModelFromModelScope,
} from '../services/api';
import { useAppStore } from '../store/appStore';
import styles from './ModelManager.module.css';

const popularModels = [
  { value: 'Qwen/Qwen2.5-0.5B-Instruct', label: 'Qwen2.5-0.5B (推荐4GB)' },
  { value: 'Qwen/Qwen2.5-1.5B-Instruct', label: 'Qwen2.5-1.5B (推荐6GB)' },
  { value: 'Qwen/Qwen2.5-7B-Instruct', label: 'Qwen2.5-7B (推荐16GB)' },
  { value: 'THUDM/chatglm3-6b', label: 'ChatGLM3-6B (推荐13GB)' },
  { value: '01ai/Yi-1.5-6B-Chat', label: 'Yi-1.5-6B (推荐13GB)' },
  { value: 'damo/nlp_corom_sentence-embedding_chinese-base', label: '中文嵌入模型 (RAG用)' },
];

const quantizeOptions = [
  { value: 4, label: 'INT4 (最低显存)' },
  { value: 8, label: 'INT8 (均衡)' },
  { value: 16, label: 'FP16 (高精度)' },
];

export default function ModelManager() {
  const { models, setModels, removeModel, addModel, backendStatus } = useAppStore();
  const operation = useOperation();
  const [loading, setLoading] = useState(false);
  const [downloadModalVisible, setDownloadModalVisible] = useState(false);
  const [importModelScopeModalVisible, setImportModelScopeModalVisible] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [importingModelModelScope, setImportingModelScope] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [searchText, setSearchText] = useState('');
  const [downloadForm] = Form.useForm();
  const [importModelScopeForm] = Form.useForm();

  const fetchModels = useCallback(async () => {
    if (backendStatus !== 'connected') return;
    setLoading(true);
    try {
      const list = await getModelList();
      setModels(list);
    } catch (error) {
      message.error('获取模型列表失败');
    } finally {
      setLoading(false);
    }
  }, [backendStatus, setModels]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const filteredModels = useMemo(() => {
    if (!searchText) return models;
    const search = searchText.toLowerCase();
    return models.filter(
      (m) => m.name.toLowerCase().includes(search) || m.id.toLowerCase().includes(search),
    );
  }, [models, searchText]);

  const handleDownload = async (values: { model: string; quantize: number }) => {
    setDownloading(true);
    setDownloadProgress(0);

    const progressInterval = setInterval(() => {
      setDownloadProgress((p) => Math.min(p + 10, 90));
    }, 1000);

    try {
      const result = await downloadModel(values.model, { quantize: values.quantize });
      clearInterval(progressInterval);
      setDownloadProgress(100);

      message.success('模型下载成功');
      addModel(result);
      setDownloadModalVisible(false);
      downloadForm.resetFields();
      setTimeout(() => setDownloadProgress(0), 500);
    } catch (error: unknown) {
      clearInterval(progressInterval);
      setDownloadProgress(0);
      const errorMsg = error instanceof Error ? error.message : '模型下载失败';
      message.error(errorMsg);
    } finally {
      setDownloading(false);
    }
  };

  const handleImportModelScope = async (values: {
    model_name: string;
    modelscope_path?: string;
  }) => {
    setImportingModelScope(true);
    try {
      const result = await importModelFromModelScope(values.model_name, values.modelscope_path);
      message.success('ModelScope 模型导入成功');
      addModel(result);
      setImportModelScopeModalVisible(false);
      importModelScopeForm.resetFields();
    } catch (error: unknown) {
      const errorMsg = error instanceof Error ? error.message : '导入失败';
      message.error(errorMsg);
    } finally {
      setImportingModelScope(false);
    }
  };

  const handleDelete = async (modelId: string) => {
    const deleted = await operation.run(
      async () => {
        await deleteModel(modelId);
        removeModel(modelId);
        return true;
      },
      {
        key: `delete-model:${modelId}`,
        successText: '模型删除成功',
        errorText: '删除模型',
      },
    );
    if (!deleted) {
      fetchModels();
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const getModelStripeColor = (type: string) => {
    if (type === 'lora') return 'var(--accent-primary)';
    if (type === 'merged') return 'var(--accent-primary)';
    return 'var(--accent-primary, #6366f1)';
  };

  const getRecommendedVram = (bytes: number, quantized?: number) => {
    if (bytes < 2 * 1024 * 1024 * 1024) return '4GB+';
    if (quantized === 4) return '6GB+';
    if (quantized === 8) return '10GB+';
    if (bytes > 10 * 1024 * 1024 * 1024) return '24GB+';
    return '16GB+';
  };

  return (
    <MotionList layout className={styles.container} stagger={0.08}>
      <MotionItem layout>
        <PageHeader
          title="模型管理"
          icon={<DatabaseOutlined />}
          helpTooltip="在这里管理和下载本地模型，以供微调或推理使用。"
          extraActions={
            <Input
              placeholder="搜索模型..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ width: 240 }}
              className="glass-input"
              allowClear
            />
          }
          secondaryAction={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchModels} loading={loading}>
                刷新
              </Button>
              <Button icon={<ImportOutlined />} onClick={() => setImportModelScopeModalVisible(true)}>
                导入 ModelScope
              </Button>
            </Space>
          }
          primaryAction={
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              onClick={() => setDownloadModalVisible(true)}
            >
              下载模型
            </Button>
          }
          style={{ marginBottom: 0 }}
        />
      </MotionItem>

      <MotionItem layout className={styles.contentArea}>
        {backendStatus !== 'connected' ? (
          <div className={glassStyles.glassCard} style={{ padding: 40, textAlign: 'center' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="后端服务未连接，请先启动应用"
            />
          </div>
        ) : filteredModels.length === 0 ? (
          <div className={glassStyles.glassCard} style={{ padding: 40, textAlign: 'center' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <div>
                  <div>暂无模型</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 8 }}>
                    点击右上角下载或导入模型开始使用
                  </div>
                </div>
              }
            >
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                onClick={() => setDownloadModalVisible(true)}
              >
                下载模型
              </Button>
            </Empty>
          </div>
        ) : (
          <div className={styles.modelGrid}>
            {filteredModels.map((model) => (
              <GlassCard key={model.id} className={styles.modelCard}>
                <div
                  className={styles.neonStripe}
                  style={{ '--stripe-color': getModelStripeColor(model.type) } as React.CSSProperties}
                />
                
                <div className={styles.modelCardHeader}>
                  <h3 className={styles.modelName}>{model.name}</h3>
                  <div className={styles.modelTypeTag}>
                    <Tag
                      color={
                        model.type === 'base'
                          ? 'blue'
                          : model.type === 'lora'
                            ? 'cyan'
                            : model.type === 'merged'
                              ? 'purple'
                              : 'default'
                      }
                      style={{ margin: 0, border: 'none' }}
                    >
                      {model.type === 'base'
                        ? '基础模型'
                        : model.type === 'lora'
                          ? 'LoRA'
                          : model.type === 'merged'
                            ? '已合并'
                            : model.type}
                    </Tag>
                  </div>
                </div>

                <p className={styles.modelPath} title={model.path}>
                  {model.path}
                </p>

                <div className={styles.modelMetrics}>
                  <div className={styles.metricItem}>
                    <span className={styles.metricLabel}>大小</span>
                    <span className={styles.metricValue}>{formatSize(model.size)}</span>
                  </div>
                  <div className={styles.metricItem}>
                    <span className={styles.metricLabel}>量化</span>
                    <span className={styles.metricValue}>
                      {model.quantized ? `INT${model.quantized}` : '无'}
                    </span>
                  </div>
                  <div className={styles.metricItem}>
                    <span className={styles.metricLabel}>推荐显存</span>
                    <span className={`${styles.metricValue} ${styles.vramValue}`}>
                      {getRecommendedVram(model.size, model.quantized)}
                    </span>
                  </div>
                </div>

                <div className={styles.modelActions}>
                  <Button
                    type="text"
                    icon={<FolderOpenOutlined />}
                    onClick={() => window.electronAPI?.openFolder(model.path)}
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    打开
                  </Button>
                  <Popconfirm
                    title="确认删除此模型?"
                    description="删除后需要重新下载"
                    onConfirm={() => handleDelete(model.id)}
                    okText="确定"
                    cancelText="取消"
                    okButtonProps={{ danger: true, loading: operation.isRunning(`delete-model:${model.id}`) }}
                  >
                    <Button type="text" danger icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </MotionItem>

      <Modal
        title="下载模型（魔搭社区）"
        open={downloadModalVisible}
        onCancel={() => {
          setDownloadModalVisible(false);
          downloadForm.resetFields();
          setDownloadProgress(0);
        }}
        footer={null}
        width={500}
        closable={!downloading}
        maskClosable={!downloading}
        className="glass-modal"
      >
        <Form
          form={downloadForm}
          layout="vertical"
          onFinish={handleDownload}
          initialValues={{ quantize: 4 }}
          style={{ marginTop: 24 }}
        >
          <Form.Item
            label="选择模型"
            name="model"
            rules={[{ required: true, message: '请选择要下载的模型' }]}
          >
            <Select
              placeholder="选择模型"
              options={popularModels}
              showSearch
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              disabled={downloading}
            />
          </Form.Item>

          <Form.Item label="量化级别" name="quantize" rules={[{ required: true }]}>
            <Select options={quantizeOptions} disabled={downloading} />
          </Form.Item>

          {downloading && (
            <div style={{ marginBottom: 24 }}>
              <Progress
                percent={downloadProgress}
                status="active"
                strokeColor="var(--accent-primary)"
              />
              <div
                style={{
                  textAlign: 'center',
                  color: 'var(--text-secondary)',
                  fontSize: 13,
                  marginTop: 8,
                }}
              >
                正在下载模型，请稍候...
              </div>
            </div>
          )}

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setDownloadModalVisible(false)} disabled={downloading}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={downloading}>
                {downloading ? '下载中...' : '开始下载'}
              </Button>
            </Space>
          </Form.Item>
        </Form>

        <div className={styles.modalDescription} style={{ marginTop: 24 }}>
          <b style={{ color: 'var(--text-primary)' }}>显存建议：</b>
          <ul style={{ margin: '8px 0 0', paddingLeft: 20, color: 'var(--text-secondary)' }}>
            <li>INT4: 6GB 显存可运行 7B 模型</li>
            <li>INT8: 10GB 显存可运行 7B 模型</li>
            <li>FP16: 13GB+ 显存可运行 7B 模型</li>
          </ul>
        </div>
      </Modal>

      <Modal
        title="导入 ModelScope 模型"
        open={importModelScopeModalVisible}
        onCancel={() => {
          setImportModelScopeModalVisible(false);
          importModelScopeForm.resetFields();
        }}
        footer={null}
        width={550}
        closable={!importingModelModelScope}
        maskClosable={!importingModelModelScope}
        className="glass-modal"
      >
        <Tabs
          items={[
            {
              key: 'qwen35',
              label: 'Qwen3.5 2B',
              children: (
                <div style={{ paddingTop: 16 }}>
                  <p style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
                    从魔搭社区（ModelScope）导入已下载的{' '}
                    <b style={{ color: 'var(--text-primary)' }}>Qwen3.5 2B</b> 模型。
                  </p>
                  <div className={styles.modalDescription}>
                    <b style={{ color: 'var(--text-primary)' }}>默认路径：</b>
                    <br />
                    <code
                      style={{
                        fontSize: 12,
                        color: 'var(--accent-primary)',
                        marginTop: 8,
                        display: 'block',
                        wordBreak: 'break-all',
                      }}
                    >
                      C:\Users\{'<用户名>'}\.cache\modelscope\hub\models\Qwen\Qwen3.5-2B
                    </code>
                  </div>
                </div>
              ),
            },
            {
              key: 'custom',
              label: '自定义路径',
              children: (
                <div style={{ paddingTop: 16 }}>
                  <p style={{ marginBottom: 16, color: 'var(--text-secondary)' }}>
                    指定 ModelScope 模型目录的自定义路径。
                  </p>
                </div>
              ),
            },
          ]}
        />

        <Form
          form={importModelScopeForm}
          layout="vertical"
          onFinish={handleImportModelScope}
          initialValues={{ model_name: 'Qwen3.5-2B' }}
          style={{ marginTop: 16 }}
        >
          <Form.Item
            label="模型名称"
            name="model_name"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="如：Qwen3.5-2B" disabled={importingModelModelScope} />
          </Form.Item>

          <Form.Item
            label="ModelScope 路径（可选）"
            name="modelscope_path"
            tooltip="不填则使用默认路径"
          >
            <Input
              placeholder="C:\Users\...\AppData\Local\modelscope\hub\models\Qwen\Qwen3.5-2B"
              disabled={importingModelModelScope}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button
                onClick={() => setImportModelScopeModalVisible(false)}
                disabled={importingModelModelScope}
              >
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={importingModelModelScope}>
                {importingModelModelScope ? '导入中...' : '开始导入'}
              </Button>
            </Space>
          </Form.Item>
        </Form>

        <div className={styles.modalDescription} style={{ marginTop: 24 }}>
          <b style={{ color: 'var(--text-primary)' }}>导入说明：</b>
          <ul
            style={{
              margin: '8px 0 0',
              paddingLeft: 20,
              fontSize: 13,
              color: 'var(--text-secondary)',
            }}
          >
            <li>确保模型已从魔搭社区下载完成</li>
            <li>导入过程会复制模型文件到项目目录</li>
            <li>导入完成后可在模型列表中查看</li>
            <li>Qwen3.5 2B 约 4GB，建议 8GB+ 显存使用 INT4 量化</li>
          </ul>
        </div>
      </Modal>
    </MotionList>
  );
}
