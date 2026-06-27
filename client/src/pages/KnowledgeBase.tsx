import {
  BookOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  FileTextOutlined,
  InboxOutlined,
  LoadingOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Button, Progress, Select, Tag, Upload } from 'antd';
import type { UploadProps } from 'antd/es/upload/interface';
import { useCallback, useEffect, useState } from 'react';
import glassStyles from '../components/shared/GlassCard.module.css';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { useOperation } from '../hooks/useOperation';
import { useRuntimeContext } from '../runtime/RuntimeContext';
import { API_BASE_URL } from '../services/api';
import { notify } from '../utils/notify';
import styles from './KnowledgeBase.module.css';

const { Dragger } = Upload;

interface DocumentItem {
  doc_id: string;
  source: string;
  chunk_count: number;
  uploaded_at: string;
}

interface CollectionInfo {
  name: string;
  count: number;
  documents: DocumentItem[];
}

interface EmbedderStatus {
  loaded: boolean;
  model_name?: string;
  dimension?: number;
  error?: string;
}

interface UploadTaskStatus {
  task_id: string;
  status: string;
  progress: number;
  message: string;
  result?: {
    file_name?: string;
    chunk_count?: number;
  };
  error?: string;
}

const getErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error && error.message ? error.message : fallback;

export default function KnowledgeBase() {
  const runtime = useRuntimeContext();
  const { actions, derived, observed } = runtime;
  const { refreshKnowledge, syncKnowledgeCollection } = actions;
  const operation = useOperation();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [collectionId, setCollectionId] = useState(derived.activeKnowledgeCollection || 'default');
  const [collectionInfo, setCollectionInfo] = useState<CollectionInfo | null>(null);
  const [preloading, setPreloading] = useState(false);
  const [activeUploadTask, setActiveUploadTask] = useState<UploadTaskStatus | null>(null);
  const embedderStatus = observed.knowledge.embedderStatus as EmbedderStatus | null;

  const loadCollectionInfo = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/collections/${collectionId}`, {
        signal: AbortSignal.timeout(30000),
      });
      if (response.ok) {
        const data = await response.json();
        setCollectionInfo(data);
      }
    } catch {
      setCollectionInfo(null);
    }
  }, [collectionId]);

  useEffect(() => {
    loadCollectionInfo();
  }, [loadCollectionInfo]);

  useEffect(() => {
    syncKnowledgeCollection(collectionId);
  }, [collectionId, syncKnowledgeCollection]);

  const preloadEmbedder = async () => {
    setPreloading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/embedder/preload`, {
        method: 'POST',
        signal: AbortSignal.timeout(120000),
      });
      if (response.ok) {
        const data = await response.json();
        notify.success(`嵌入模型已加载，维度: ${data.dimension}`);
        await refreshKnowledge();
      } else {
        const error = await response.json();
        notify.error(error.detail || '预加载失败');
      }
    } catch (error: unknown) {
      notify.error(getErrorMessage(error, '预加载失败'));
    } finally {
      setPreloading(false);
    }
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.pdf,.docx,.doc,.txt,.md,.markdown',
    beforeUpload: (file) => {
      const validTypes = ['.pdf', '.docx', '.doc', '.txt', '.md', '.markdown'];
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();

      if (!validTypes.includes(ext)) {
        notify.error(`不支持的文件格式：${ext}`);
        return false;
      }

      if (file.size > 50 * 1024 * 1024) {
        notify.error('文件大小不能超过 50MB');
        return false;
      }

      return true;
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      setUploading(true);
      setUploadProgress(0);
      setUploadStatus('准备上传...');

      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
        notify.error('上传超时，请检查服务器状态或尝试较小的文件');
        setUploading(false);
        setUploadProgress(0);
        setUploadStatus('');
      }, 60000);

      try {
        const progressInterval = setInterval(() => {
          setUploadProgress((prev) => {
            if (prev >= 85) return prev;
            return prev + 5;
          });
        }, 1000);

        const formData = new FormData();
        formData.append('collection_id', collectionId);
        formData.append('file', file as File);

        setUploadStatus('正在上传文件...');

        const response = await fetch(`${API_BASE_URL}/knowledge/upload/async`, {
          method: 'POST',
          body: formData,
          signal: controller.signal,
        });

        clearInterval(progressInterval);
        clearTimeout(timeoutId);

        if (!response.ok) {
          let errorMessage = '上传失败';
          try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorMessage;
          } catch {
            errorMessage = `服务器错误: ${response.status}`;
          }
          throw new Error(errorMessage);
        }

        const result = await response.json();
        setActiveUploadTask({
          task_id: result.task_id,
          status: result.status,
          progress: 5,
          message: result.message,
        });
        setUploadStatus(result.message || '文档上传中');
        await pollUploadStatus(result.task_id);
        onSuccess?.(result);
      } catch (error: unknown) {
        clearTimeout(timeoutId);
        if (error instanceof Error && error.name === 'AbortError') {
          notify.error('上传超时，请检查服务器状态');
        } else {
          notify.error(getErrorMessage(error, '上传失败'));
        }
        onError?.(error instanceof Error ? error : new Error('上传失败'));
      } finally {
        setTimeout(() => {
          setUploading(false);
          setUploadProgress(0);
          setUploadStatus('');
        }, 1000);
      }
    },
  };

  const pollUploadStatus = async (taskId: string) => {
    let finished = false;

    while (!finished) {
      const response = await fetch(`${API_BASE_URL}/knowledge/upload/status/${taskId}`);
      if (!response.ok) {
        throw new Error('无法获取上传任务状态');
      }

      const task = (await response.json()) as UploadTaskStatus;
      setActiveUploadTask(task);
      setUploadProgress(task.progress || 0);
      setUploadStatus(task.message || '');

      if (task.status === 'completed') {
        finished = true;
        setUploadProgress(100);
        notify.success(
          `文档上传成功：${task.result?.file_name || '文件'}, ${task.result?.chunk_count || 0} 个文本块`,
        );
        loadCollectionInfo();
      } else if (task.status === 'failed') {
        finished = true;
        throw new Error(task.error || task.message || '上传失败');
      } else {
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
    }
  };

  const handleDelete = async (doc: DocumentItem) => {
    await operation.run(
      async () => {
        const response = await fetch(
          `${API_BASE_URL}/knowledge/collections/${collectionId}/documents/${doc.doc_id}`,
          { method: 'DELETE' },
        );

        if (!response.ok) {
          const error = await response.json().catch(() => null);
          throw new Error(error?.detail || `删除失败 (${response.status})`);
        }

        await loadCollectionInfo();
      },
      {
        key: `delete-knowledge-doc:${collectionId}:${doc.doc_id}`,
        successText: '文档已删除',
        errorText: '删除文档',
        confirm: {
          title: '删除知识库文档？',
          content: `将从集合 ${collectionId} 中移除「${doc.source}」及其向量索引。`,
          okText: '删除',
          tone: 'danger',
        },
      },
    );
  };

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
        {/* 标题栏 */}
        <div className={`${glassStyles.glassCard} ${styles.headerCard}`}>
          <h1 className={styles.title}>
            <BookOutlined />
            RAG 知识库
          </h1>
          {embedderStatus && (
            <div
              className={`${styles.statusBanner} ${embedderStatus.loaded ? styles.statusBannerSuccess : styles.statusBannerWarning}`}
            >
              {embedderStatus.loaded ? (
                <>
                  <CheckCircleOutlined />
                  <span>
                    嵌入模型就绪 · {embedderStatus.model_name} · {embedderStatus.dimension}维
                  </span>
                </>
              ) : (
                <>
                  <WarningOutlined />
                  <span>嵌入模型未加载</span>
                  <Button
                    size="small"
                    type="primary"
                    onClick={preloadEmbedder}
                    loading={preloading}
                    style={{ marginLeft: 8 }}
                  >
                    {preloading ? '加载中...' : '立即加载'}
                  </Button>
                </>
              )}
            </div>
          )}
        </div>

        {/* 上传文档 */}
        <div className={`${glassStyles.glassCard} ${styles.card}`}>
          <div className={styles.workspaceInput}>
            <span>工作空间 ID：</span>
            {observed.knowledge.collections.length > 0 && (
              <Select
                value={
                  observed.knowledge.collections.some(
                    (collection) => collection.id === collectionId,
                  )
                    ? collectionId
                    : undefined
                }
                onChange={(value) => setCollectionId(value)}
                placeholder="从已知集合中选择"
                style={{ minWidth: 220 }}
                options={observed.knowledge.collections.map((collection) => ({
                  value: collection.id,
                  label: `${collection.name} (${collection.count})`,
                }))}
              />
            )}
            <input
              value={collectionId}
              onChange={(e) => setCollectionId(e.target.value)}
              placeholder="输入工作空间 ID"
            />
          </div>

          <div className={styles.draggerWrap}>
            <Dragger {...uploadProps} disabled={uploading}>
              <p className="ant-upload-drag-icon">
                {uploading ? (
                  <LoadingOutlined style={{ fontSize: 40, color: 'var(--accent-primary)' }} />
                ) : (
                  <InboxOutlined style={{ fontSize: 40, color: 'var(--accent-primary)' }} />
                )}
              </p>
              <p className="ant-upload-text" style={{ color: 'var(--text-primary)', fontSize: 16 }}>
                {uploading ? '上传处理中...' : '点击或拖拽文件到此区域上传'}
              </p>
              <p className="ant-upload-hint" style={{ color: 'var(--text-secondary)' }}>
                支持格式：PDF, DOCX, TXT, MD | 最大 50MB
              </p>
            </Dragger>
          </div>

          {uploading && (
            <div className={styles.progressArea}>
              <Progress
                percent={uploadProgress}
                status="active"
                strokeColor="var(--accent-primary)"
              />
              {activeUploadTask && (
                <div style={{ marginTop: 12, textAlign: 'left' }}>
                  <div
                    style={{
                      color: 'var(--text-secondary)',
                      fontSize: 13,
                      marginTop: 8,
                      textAlign: 'center',
                    }}
                  >
                    {uploadStatus || activeUploadTask.message} ({activeUploadTask.progress || uploadProgress}%)
                  </div>
                </div>
              )}
              {!activeUploadTask && (
                <div
                  style={{
                    color: 'var(--text-secondary)',
                    fontSize: 13,
                    marginTop: 8,
                    textAlign: 'center',
                  }}
                >
                  {uploadStatus}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 文档列表 */}
        <div className={`${glassStyles.glassCard} ${styles.card}`}>
          <div className={styles.cardTitle}>
            <span>文档列表</span>
            <Button icon={<ReloadOutlined />} onClick={loadCollectionInfo} size="small">
              刷新
            </Button>
          </div>

          {collectionInfo && (collectionInfo.documents || []).length > 0 ? (
            (collectionInfo.documents || []).map((doc) => (
              <div key={doc.doc_id} className={styles.docItem}>
                <div className={styles.docItemInfo}>
                  <div className={styles.docItemName}>
                    <FileTextOutlined style={{ color: 'var(--accent-primary)' }} />
                    <span>{doc.source}</span>
                    <Tag color="blue" style={{ borderRadius: 4 }}>
                      {doc.chunk_count} 块
                    </Tag>
                  </div>
                  <div className={styles.docItemMeta}>
                    <span>ID: {doc.doc_id}</span>
                    <span>上传于 {new Date(doc.uploaded_at).toLocaleString('zh-CN')}</span>
                  </div>
                </div>
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  loading={operation.isRunning(`delete-knowledge-doc:${collectionId}:${doc.doc_id}`)}
                  onClick={() => handleDelete(doc)}
                  size="small"
                >
                  删除
                </Button>
              </div>
            ))
          ) : (
            <div className={styles.emptyState}>暂无文档，请上传知识库文件</div>
          )}
        </div>

        {/* 使用说明 */}
        <div className={`${glassStyles.glassCard} ${styles.helpCard}`}>
          <div className={styles.cardTitle} style={{ marginBottom: 16 }}>
            使用说明
          </div>
          <ol className={styles.helpList}>
            <li>
              <strong>上传文档：</strong>选择工作空间 ID，上传 PDF / DOCX / TXT / MD 文件
            </li>
            <li>
              <strong>自动处理：</strong>系统自动解析文档、分块、向量化并存储
            </li>
            <li>
              <strong>语义搜索：</strong>使用自然语言查询，检索相关文档片段
            </li>
            <li>
              <strong>RAG 聊天：</strong>在聊天时启用 RAG 增强，基于知识库内容回答
            </li>
            <li>
              <strong>注意：</strong>首次上传需要下载嵌入模型（约 400MB），请耐心等待
            </li>
          </ol>
        </div>
      </MotionItem>
    </MotionList>
  );
}
