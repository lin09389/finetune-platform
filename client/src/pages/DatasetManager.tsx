import {
  BarChartOutlined,
  DeleteOutlined,
  EyeOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { Drawer, Popconfirm, Progress, Space, Tag, message } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import GlassCard from '../components/shared/GlassCard';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import PageHeader from '../components/shared/PageHeader';
import JSONDataEditor from '../components/shared/JSONDataEditor';
import { useOperation } from '../hooks/useOperation';
import {
  analyzeDataset,
  deleteDataset,
  getDatasetList,
  previewDataset,
  splitDataset,
  transformDataset,
  uploadDataset,
} from '../services/api';
import { useAppStore } from '../store/appStore';
import type { DatasetAnalysisResult, DatasetInfo } from '../types';
import styles from './DatasetManager.module.css';

export default function DatasetManager() {
  const navigate = useNavigate();
  const { datasets, setDatasets, removeDataset, addDataset, backendStatus } = useAppStore();
  const operation = useOperation();
  const [, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [previewData, setPreviewData] = useState<{
    total_samples: number;
    preview: unknown[];
  } | null>(null);
  const [, setPreviewLoading] = useState(false);
  const [analysisVisible, setAnalysisVisible] = useState(false);
  const [analysisData, setAnalysisData] = useState<DatasetAnalysisResult | null>(null);
  const [analysisDatasetName, setAnalysisDatasetName] = useState('');
  const [analysisDatasetId, setAnalysisDatasetId] = useState('');

  const fetchDatasets = async () => {
    if (backendStatus !== 'connected') return;
    setLoading(true);
    try {
      const list = await getDatasetList();
      setDatasets(list);
    } catch (error) {
      message.error('获取数据集列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDatasets();
  }, [backendStatus]);

  const handleSelectFile = async () => {
    if (window.electronAPI) {
      const filePath = await window.electronAPI.selectFile([
        { name: 'JSON/JSONL', extensions: ['json', 'jsonl'] },
      ]);
      if (filePath) {
        try {
          setLoading(true);
          setUploadProgress(0);
          const fileData = await window.electronAPI.readFile(filePath);
          if (!fileData) {
            throw new Error('无法读取文件');
          }
          const byteArray = Uint8Array.from(atob(fileData.data), c => c.charCodeAt(0));
          const blob = new Blob([byteArray]);
          const file = new File([blob], fileData.name, { type: 'application/json' });
          const result = await uploadDataset(file, undefined, undefined, setUploadProgress);
          message.success('数据集上传成功');
          addDataset(result);
          fetchDatasets();
        } catch (error: any) {
          message.error(error.message || '数据集上传失败');
        } finally {
          setLoading(false);
          setUploadProgress(null);
        }
      }
    } else {
      fileInputRef.current?.click();
    }
  };

  const handleWebFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setLoading(true);
      setUploadProgress(0);
      const result = await uploadDataset(file, undefined, undefined, setUploadProgress);
      message.success('数据集上传成功');
      addDataset(result);
      fetchDatasets();
    } catch (error: any) {
      message.error(error.message || '数据集上传失败');
    } finally {
      setLoading(false);
      setUploadProgress(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDelete = async (datasetId: string) => {
    const deleted = await operation.run(
      async () => {
        await deleteDataset(datasetId);
        removeDataset(datasetId);
        return true;
      },
      {
        key: `delete-dataset:${datasetId}`,
        successText: '数据集删除成功',
        errorText: '删除数据集',
      },
    );
    if (!deleted) {
      fetchDatasets();
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    if (bytes < 1024 * 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const handlePreview = async (datasetId: string) => {
    setPreviewLoading(true);
    try {
      const data = await previewDataset(datasetId, 10);
      setPreviewData({
        total_samples: data.total_samples ?? data.total_shown ?? data.samples?.length ?? 0,
        preview: data.preview ?? data.samples ?? [],
      });
      setPreviewVisible(true);
    } catch (error) {
      message.error('预览失败');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleAnalyze = async (record: DatasetInfo) => {
    try {
      const data = await analyzeDataset(record.id);
      setAnalysisData(data);
      setAnalysisDatasetName(record.name);
      setAnalysisDatasetId(record.id);
      setAnalysisVisible(true);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '分析失败');
    }
  };

  const getRecommendedTaskGoal = () =>
    analysisData?.recommended_target_format === 'input_schema_output_jsonl'
      ? 'structured_extraction'
      : 'qa_assistant';

  const openTrainingWithDataset = (datasetId = analysisDatasetId) => {
    if (!datasetId) {
      message.warning('请先选择一个数据集');
      return;
    }

    const params = new URLSearchParams();
    params.set('dataset_id', datasetId);
    params.set('task_goal', getRecommendedTaskGoal());
    navigate(`/training?${params.toString()}`);
  };

  const handleTransform = async () => {
    if (!analysisDatasetId || !analysisData) return;
    try {
      const taskGoal = getRecommendedTaskGoal();
      const result = await transformDataset(analysisDatasetId, {
        target_format: analysisData.recommended_target_format,
        task_goal: taskGoal,
      });
      message.success(`已导出 ${result.sample_count} 条标准训练样本`);
      void fetchDatasets();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '转换失败');
    }
  };

  const handleSplit = async () => {
    if (!analysisDatasetId) return;
    try {
      await splitDataset(analysisDatasetId, {
        train_ratio: 0.8,
        validation_ratio: 0.1,
        test_ratio: 0.1,
        seed: 42,
      });
      message.success('已生成 train / validation / test 切分');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '切分失败');
    }
  };

  const handleOpenFolder = (path: string) => {
    if (window.electronAPI?.openFolder) {
      window.electronAPI.openFolder(path);
      return;
    }
    message.info('浏览器模式无法直接打开本地目录，请在桌面端使用此操作。');
  };

  const getDatasetStripeColor = (format: string) => {
    if (format === 'jsonl') return 'var(--accent-neon-cyan, #00FFC2)';
    if (format === 'json') return 'var(--accent-neon-purple, #9D00FF)';
    return 'var(--accent-primary, #6366f1)';
  };

  const isElectron = typeof window !== 'undefined' && Boolean(window.electronAPI);

  const renderDatasetCard = (record: DatasetInfo) => {
    // 规模等级：< 500 微型, < 2000 小型, < 10000 中型, >= 10000 大型
    const sizePercent = record.samples < 500
      ? Math.max(8, (record.samples / 500) * 25)
      : record.samples < 2000
        ? 25 + ((record.samples - 500) / 1500) * 25
        : record.samples < 10000
          ? 50 + ((record.samples - 2000) / 8000) * 35
          : Math.min(100, 85 + ((record.samples - 10000) / 90000) * 15);

    const sizeLabel = record.samples < 500
      ? '微型'
      : record.samples < 2000
        ? '小型'
        : record.samples < 10000
          ? '中型'
          : '大型';

    return (
      <MotionItem layout key={record.id}>
        <GlassCard className={styles.datasetCard}>
          <div
            className={styles.neonStripe}
            style={{ '--stripe-color': getDatasetStripeColor(record.format) } as React.CSSProperties}
          />
          <div className={styles.cardHeader}>
            <h3 className={styles.cardTitle}>{record.name}</h3>
            <span className={`${styles.cardFormat} ${styles[record.format] || ''}`}>
              {record.format}
            </span>
          </div>
          
          <div className={styles.metricsRow}>
            <div className={styles.metric}>
              <div className={styles.metricLabel}>样本数</div>
              <div className={styles.metricValue}>{record.samples.toLocaleString()}</div>
            </div>
            <div className={styles.metric}>
              <div className={styles.metricLabel}>大小</div>
              <div className={styles.metricValue}>{formatSize(record.size)}</div>
            </div>
          </div>

          <div className={styles.healthScore}>
            <div className={styles.sizeScoreHeader}>
              <span className={styles.metricLabel}>数据集规模参考</span>
              <span className={styles.sizeBadge}>{sizeLabel}</span>
            </div>
            <div className={styles.healthBar}>
              <div className={styles.sizeBarFill} style={{ width: `${sizePercent}%` }} />
            </div>
          </div>

          <div className={styles.cardActions}>
            <button className={styles.actionBtn} onClick={() => handleAnalyze(record)}>
              <BarChartOutlined /> 分析
            </button>
            <button className={styles.actionBtn} onClick={() => handlePreview(record.id)}>
              <EyeOutlined /> 预览
            </button>
            <button
              className={`${styles.actionBtn} ${!isElectron ? styles.actionBtnDisabled : ''}`}
              onClick={() => handleOpenFolder(record.path)}
              disabled={!isElectron}
              title={!isElectron ? '仅支持桌面端（Electron）' : '在文件管理器中打开目录'}
            >
              <FolderOpenOutlined /> 打开
            </button>
            <Popconfirm
              title="确认删除？"
              onConfirm={() => handleDelete(record.id)}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true, loading: operation.isRunning(`delete-dataset:${record.id}`) }}
            >
              <button className={`${styles.actionBtn} ${styles.danger}`}>
                <DeleteOutlined />
              </button>
            </Popconfirm>
          </div>
        </GlassCard>
      </MotionItem>
    );
  };

  return (
    <div className={styles.container}>
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,.jsonl"
        style={{ display: 'none' }}
        onChange={handleWebFileUpload}
      />
      <PageHeader
        title="数据准备中心"
        icon={<FileTextOutlined />}
        helpTooltip="上传、分析、转换和切分微调数据集。"
        style={{ marginBottom: 0 }}
      />

      <div className={styles.dropzone} onClick={handleSelectFile}>
        <InboxOutlined className={styles.dropIcon} />
        <div className={styles.dropText}>点击或拖拽上传 JSON / JSONL 数据集</div>
        <div className={styles.dropSubtext}>上传后会自动校验结构、统计样本并计算文件哈希。</div>
      </div>

      {uploadProgress !== null && (
        <div style={{ padding: '8px 0' }}>
          <Progress
            percent={uploadProgress}
            status={uploadProgress < 100 ? 'active' : 'success'}
            size="small"
            format={(percent) => (percent ?? 0) < 100 ? `上传中 ${percent}%` : '处理中...'}
          />
        </div>
      )}

      {backendStatus !== 'connected' ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
          后端服务未连接，请先启动服务。
        </div>
      ) : (
        <MotionList layout className={styles.bentoGrid} stagger={0.08}>
          {datasets.map(renderDatasetCard)}
        </MotionList>
      )}

      <Drawer
        title="数据预览"
        placement="right"
        width={800}
        open={previewVisible}
        onClose={() => setPreviewVisible(false)}
        className="deep-tech-drawer"
        style={{ background: 'var(--bg-pure-black)' }}
      >
        {previewData && (
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div
              style={{
                marginBottom: 16,
                padding: '12px 16px',
                background: 'rgba(0, 255, 194, 0.05)',
                borderRadius: 8,
                border: '1px solid rgba(0, 255, 194, 0.2)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>样本总数：</strong>
              <span style={{ color: 'var(--accent-neon-cyan)', fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                {previewData.total_samples}
              </span>
            </div>
            <div className={styles.editorWrapper}>
              <JSONDataEditor data={previewData.preview} />
            </div>
          </div>
        )}
      </Drawer>

      <Drawer
        title={`数据健康分析 - ${analysisDatasetName}`}
        placement="right"
        width={720}
        open={analysisVisible}
        onClose={() => setAnalysisVisible(false)}
      >
        {analysisData && (
          <Space direction="vertical" size={18} style={{ width: '100%' }}>
            <Space wrap>
              <Tag color="blue">格式：{analysisData.detected_format}</Tag>
              <Tag color="green">目标格式：{analysisData.recommended_target_format}</Tag>
              <Tag>样本数：{analysisData.sample_count}</Tag>
              <Tag>可训练：{analysisData.valid_count}</Tag>
            </Space>
            <Space wrap>
              <button className={styles.actionBtn} onClick={handleTransform}>
                导出训练 JSONL
              </button>
              <button className={styles.actionBtn} onClick={handleSplit}>
                按 80/10/10 切分
              </button>
              <button className={styles.actionBtn} onClick={() => openTrainingWithDataset()}>
                <PlayCircleOutlined /> 进入训练配置
              </button>
            </Space>

            <div>
              <strong>JSON 合法率</strong>
              <Progress percent={Math.round(analysisData.health.json_valid_ratio * 100)} />
              <strong>字段完整率</strong>
              <Progress percent={Math.round(analysisData.health.field_completeness * 100)} />
              <strong>过长样本比例</strong>
              <Progress percent={Math.round(analysisData.health.overlong_sample_ratio * 100)} status="exception" />
            </div>

            <div>
              <h3>长度统计</h3>
              <p>
                平均 {analysisData.length_stats.avg_chars} 字符 · 最大{' '}
                {analysisData.length_stats.max_chars} 字符 · 重复率{' '}
                {Math.round(analysisData.health.duplicate_sample_ratio * 100)}%
              </p>
            </div>

            <div>
              <h3>字段候选</h3>
              {Object.entries(analysisData.field_candidates).map(([group, fields]) => (
                <p key={group}>
                  <strong>{group}:</strong> {fields.length ? fields.join(', ') : '-'}
                </p>
              ))}
            </div>

            <div>
              <h3>问题列表</h3>
              {[...analysisData.errors, ...analysisData.warnings].slice(0, 12).map((issue, index) => (
                <p key={`${issue.line}-${index}`} style={{ color: issue.severity === 'error' ? 'var(--error)' : 'var(--warning)' }}>
                  第 {issue.line} 行：{issue.message}
                </p>
              ))}
              {!analysisData.errors.length && !analysisData.warnings.length && <p>未发现阻塞问题。</p>}
            </div>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
