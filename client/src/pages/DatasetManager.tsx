import {
  DeleteOutlined,
  EyeOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  InboxOutlined,
} from '@ant-design/icons';
import { Drawer, Popconfirm, message } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import PageHeader from '../components/shared/PageHeader';
import JSONDataEditor from '../components/shared/JSONDataEditor';
import { deleteDataset, getDatasetList, previewDataset, uploadDataset } from '../services/api';
import { useAppStore } from '../store/appStore';
import type { DatasetInfo } from '../types';
import styles from './DatasetManager.module.css';

export default function DatasetManager() {
  const { datasets, setDatasets, removeDataset, addDataset, backendStatus } = useAppStore();
  const [, setLoading] = useState(false);
  const [previewVisible, setPreviewVisible] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [previewData, setPreviewData] = useState<{
    total_samples: number;
    preview: unknown[];
  } | null>(null);
  const [, setPreviewLoading] = useState(false);

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
          const fileData = await window.electronAPI.readFile(filePath);
          if (!fileData) {
            throw new Error('无法读取文件');
          }
          const byteCharacters = atob(fileData.data);
          const byteNumbers = new Array(byteCharacters.length);
          for (let i = 0; i < byteCharacters.length; i++) {
            byteNumbers[i] = byteCharacters.charCodeAt(i);
          }
          const byteArray = new Uint8Array(byteNumbers);
          const blob = new Blob([byteArray]);
          const file = new File([blob], fileData.name, { type: 'application/json' });
          const result = await uploadDataset(file);
          message.success('数据集上传成功');
          addDataset(result);
          fetchDatasets();
        } catch (error: any) {
          message.error(error.message || '数据集上传失败');
        } finally {
          setLoading(false);
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
      const result = await uploadDataset(file);
      message.success('数据集上传成功');
      addDataset(result);
      fetchDatasets();
    } catch (error: any) {
      message.error(error.message || '数据集上传失败');
    } finally {
      setLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDelete = async (datasetId: string) => {
    try {
      await deleteDataset(datasetId);
      removeDataset(datasetId);
      message.success('数据集删除成功');
    } catch (error) {
      message.error('删除失败');
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
      setPreviewData(data);
      setPreviewVisible(true);
    } catch (error) {
      message.error('预览失败');
    } finally {
      setPreviewLoading(false);
    }
  };

  const renderDatasetCard = (record: DatasetInfo) => {
    // Generate a pseudo-health score based on samples count (just for visual representation)
    const healthPercentage = Math.min(100, Math.max(10, (record.samples / 5000) * 100));

    return (
      <MotionItem key={record.id}>
        <div className={styles.bentoCard}>
          <div className={styles.cardHeader}>
            <h3 className={styles.cardTitle}>{record.name}</h3>
            <span className={`${styles.cardFormat} ${styles[record.format] || ''}`}>
              {record.format}
            </span>
          </div>
          
          <div className={styles.metricsRow}>
            <div className={styles.metric}>
              <div className={styles.metricLabel}>Samples</div>
              <div className={styles.metricValue}>{record.samples.toLocaleString()}</div>
            </div>
            <div className={styles.metric}>
              <div className={styles.metricLabel}>Size</div>
              <div className={styles.metricValue}>{formatSize(record.size)}</div>
            </div>
          </div>

          <div className={styles.healthScore}>
            <div className={styles.metricLabel}>Data Health Score</div>
            <div className={styles.healthBar}>
              <div className={styles.healthFill} style={{ width: `${healthPercentage}%` }} />
            </div>
          </div>

          <div className={styles.cardActions}>
            <button className={styles.actionBtn} onClick={() => handlePreview(record.id)}>
              <EyeOutlined /> Preview
            </button>
            <button className={styles.actionBtn} onClick={() => window.electronAPI?.openFolder(record.path)}>
              <FolderOpenOutlined /> Open
            </button>
            <Popconfirm
              title="Confirm Delete?"
              onConfirm={() => handleDelete(record.id)}
              okText="Yes"
              cancelText="No"
            >
              <button className={`${styles.actionBtn} ${styles.danger}`}>
                <DeleteOutlined />
              </button>
            </Popconfirm>
          </div>
        </div>
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
        title="Data Logistics Hub"
        icon={<FileTextOutlined />}
        helpTooltip="Manage datasets for fine-tuning using Bento Grid architecture."
        style={{ marginBottom: 0 }}
      />

      <div className={styles.dropzone} onClick={handleSelectFile}>
        <InboxOutlined className={styles.dropIcon} />
        <div className={styles.dropText}>Click or drag to upload JSON/JSONL dataset</div>
        <div className={styles.dropSubtext}>Structured files will be validated and hashed upon upload.</div>
      </div>

      {backendStatus !== 'connected' ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-secondary)' }}>
          Backend offline. Please start the service.
        </div>
      ) : (
        <MotionList className={styles.bentoGrid} stagger={0.08}>
          {datasets.map(renderDatasetCard)}
        </MotionList>
      )}

      <Drawer
        title="Deep Data Inspection"
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
              <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>TOTAL SAMPLES:</strong>
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
    </div>
  );
}
