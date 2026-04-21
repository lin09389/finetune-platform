import {
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  HistoryOutlined,
  LineChartOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Space,
  Spin,
  Table,
  Tag,
  message,
} from 'antd';
import { useEffect, useRef, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import glassStyles from '../components/shared/GlassCard.module.css';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import PageHeader from '../components/shared/PageHeader';
import { mergeLora } from '../services/api';
import {
  getTrainingCheckpoints,
  getTrainingHistory,
  getTrainingTaskMetricsV2,
  resumeTraining,
} from '../services/trainingApi';
import { useAppStore } from '../store/appStore';
import type { Checkpoint, TrainingRecord } from '../types';
import styles from './History.module.css';

type TrainingMetricPoint = {
  step?: number;
  global_step?: number;
  loss?: number;
  train_loss?: number;
  lr?: number;
  learning_rate?: number;
  vram_used?: number;
  vramUsed?: number;
};

type TrainingMetricsPage = {
  items?: TrainingMetricPoint[];
  has_more?: boolean;
  hasMore?: boolean;
  next_cursor?: number;
  nextCursor?: number;
};

type CompareChartRow = { step: number } & Record<string, number | null>;

interface HistoryProps {
  mode?: 'history' | 'compare';
}

const compareColors = ['#1677ff', '#22a06b', '#f59e0b', '#d4380d'];

const getCompareColor = (index: number) =>
  compareColors[index % compareColors.length] || '#1677ff';

const escapeMarkdownTableCell = (value: unknown) =>
  String(value ?? '-')
    .replace(/\|/g, '\\|')
    .replace(/\r?\n/g, ' ');

const escapeCsvCell = (value: unknown) => {
  const text = String(value ?? '-');
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

const minCompareRecords = 2;
const maxCompareRecords = 4;
const compareMetricsPageSize = 1000;
const maxCompareMetricPages = 20;

const isFiniteMetric = (value: unknown) => {
  if (value === undefined || value === null || value === '') return false;
  const numeric = Number(value);
  return Number.isFinite(numeric);
};

const isComparableRecord = (record: TrainingRecord) =>
  record.status === 'completed' || record.status === 'stopped';

const hasCompareSignal = (record: TrainingRecord) =>
  isFiniteMetric(record.finalLoss) ||
  isFiniteMetric(record.finalLr) ||
  isFiniteMetric(record.elapsedTime) ||
  isFiniteMetric(record.totalSteps) ||
  Boolean(record.outputPath || record.checkpointPath);

const getComparableRecordTime = (record: TrainingRecord) => {
  const timestamp = new Date(record.endTime || record.startTime).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
};

const sortRecentFirst = (records: TrainingRecord[]) =>
  [...records].sort(
    (left, right) => getComparableRecordTime(right) - getComparableRecordTime(left),
  );

const buildDefaultCompareIds = (records: TrainingRecord[]) => {
  const comparableRecords = records.filter(isComparableRecord);
  const richRecords = sortRecentFirst(comparableRecords.filter(hasCompareSignal));
  const plainRecords = sortRecentFirst(
    comparableRecords.filter((record) => !hasCompareSignal(record)),
  );
  const selected = richRecords.slice(0, maxCompareRecords);

  if (selected.length < minCompareRecords) {
    selected.push(...plainRecords.slice(0, maxCompareRecords - selected.length));
  }

  return selected.length >= minCompareRecords
    ? selected.slice(0, maxCompareRecords).map((record) => record.id)
    : [];
};

const areSameIds = (left: string[], right: string[]) =>
  left.length === right.length && left.every((id, index) => id === right[index]);

export default function History({ mode = 'history' }: HistoryProps) {
  const { trainingRecords, setTrainingRecords, removeTrainingRecord, setIsTraining } =
    useAppStore();
  const [mergeForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<TrainingRecord | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [checkpointsLoading, setCheckpointsLoading] = useState(false);
  const [resumingCheckpoint, setResumingCheckpoint] = useState<string | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [merging, setMerging] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareMetrics, setCompareMetrics] = useState<Record<string, TrainingMetricPoint[]>>({});
  const autoCompareIdsRef = useRef<string[]>([]);
  const compareSelectionTouchedRef = useRef(false);

  useEffect(() => {
    void loadRecords();
  }, []);

  useEffect(() => {
    if (mode !== 'compare' || compareSelectionTouchedRef.current) return;

    const defaultCompareIds = buildDefaultCompareIds(trainingRecords);
    if (defaultCompareIds.length < minCompareRecords) return;

    const canReplaceSelection =
      compareIds.length === 0 || areSameIds(compareIds, autoCompareIdsRef.current);

    if (!canReplaceSelection || areSameIds(compareIds, defaultCompareIds)) return;

    autoCompareIdsRef.current = defaultCompareIds;
    setCompareIds(defaultCompareIds);
  }, [compareIds, mode, trainingRecords]);

  const loadRecords = async () => {
    setLoading(true);
    try {
      const records = await getTrainingHistory();
      setTrainingRecords(records);
    } catch (error) {
      console.error('Failed to load records:', error);
      message.error(getErrorMessage(error, '加载训练历史失败'));
    } finally {
      setLoading(false);
    }
  };

  const getErrorMessage = (error: any, fallback: string) => {
    return error?.response?.data?.detail || error?.message || fallback;
  };

  const isEligibleForMerge = (record: TrainingRecord | null) =>
    Boolean(
      record &&
        (record.status === 'completed' || record.status === 'stopped') &&
        record.method !== 'full' &&
        record.checkpointPath &&
        (record.config?.modelId || (record.config as any)?.model_id),
    );

  const getBaseModelId = (record: TrainingRecord | null) =>
    record?.config?.modelId || (record?.config as any)?.model_id || '';

  const getRecordLabel = (record: TrainingRecord) =>
    record.modelName ? `${record.modelName} · ${record.id}` : record.id;

  const buildDefaultOutputName = (record: TrainingRecord | null) => {
    const source = record?.modelName || record?.id || 'merged-model';
    return `${source}-merged`.replace(/[\\/\s]+/g, '-');
  };

  const handleDelete = async (id: string) => {
    removeTrainingRecord(id);
    message.success('记录已删除');
  };

  const loadCheckpoints = async (record: TrainingRecord) => {
    setCheckpointsLoading(true);
    try {
      const items = await getTrainingCheckpoints(record.id);
      setCheckpoints(items);
    } catch (error) {
      console.error('Failed to load checkpoints:', error);
      setCheckpoints([]);
      message.error(getErrorMessage(error, '加载检查点失败'));
    } finally {
      setCheckpointsLoading(false);
    }
  };

  const openDetail = async (record: TrainingRecord) => {
    setSelectedRecord(record);
    setDetailOpen(true);
    await loadCheckpoints(record);
  };

  const closeDetail = () => {
    setDetailOpen(false);
    setSelectedRecord(null);
    setCheckpoints([]);
    setMergeOpen(false);
    mergeForm.resetFields();
  };

  const openMergeModal = () => {
    if (!isEligibleForMerge(selectedRecord)) return;
    mergeForm.setFieldsValue({
      outputName: buildDefaultOutputName(selectedRecord),
    });
    setMergeOpen(true);
  };

  const handleMergeExport = async (values?: { outputName?: string }) => {
    if (!isEligibleForMerge(selectedRecord)) {
      message.warning('当前记录不满足合并导出条件');
      return;
    }

    const outputName = String(values?.outputName || mergeForm.getFieldValue('outputName') || '')
      .trim();
    if (!outputName) {
      message.warning('请输入输出名称');
      return;
    }

    const modelId = getBaseModelId(selectedRecord);
    if (!modelId) {
      message.error('缺少基础模型 ID，无法执行合并导出');
      return;
    }

    setMerging(true);
    try {
      await mergeLora(modelId, {
        adapter_path: selectedRecord.checkpointPath,
        training_id: selectedRecord.id,
        output_name: outputName,
      });
      message.success('合并导出已提交');
      setMergeOpen(false);
      mergeForm.resetFields();
    } catch (error) {
      console.error('Failed to merge and export LoRA:', error);
      message.error(getErrorMessage(error, '合并导出失败'));
    } finally {
      setMerging(false);
    }
  };

  const selectedCompareRecords = trainingRecords.filter((record) => compareIds.includes(record.id));

  const getMetricNumber = (value: unknown) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : undefined;
  };

  const getMetricLoss = (metric: TrainingMetricPoint) =>
    getMetricNumber(metric.loss ?? metric.train_loss);

  const getMetricStep = (metric: TrainingMetricPoint, index: number) =>
    getMetricNumber(metric.step ?? metric.global_step) ?? index + 1;

  const getRecordFinalLoss = (record: TrainingRecord) => {
    if (typeof record.finalLoss === 'number' && Number.isFinite(record.finalLoss)) {
      return record.finalLoss;
    }

    const metrics = compareMetrics[record.id] || [];
    for (let index = metrics.length - 1; index >= 0; index -= 1) {
      const metric = metrics[index];
      if (!metric) continue;
      const loss = getMetricLoss(metric);
      if (loss !== undefined) return loss;
    }
    return undefined;
  };

  const getRecordTotalSteps = (record: TrainingRecord) => {
    if (record.totalSteps !== undefined && record.totalSteps !== null) {
      return record.totalSteps;
    }

    const metrics = compareMetrics[record.id] || [];
    const lastMetric = metrics[metrics.length - 1];
    return lastMetric ? getMetricStep(lastMetric, metrics.length - 1) : undefined;
  };

  const formatLoss = (loss?: number) =>
    loss !== undefined && Number.isFinite(loss) ? loss.toFixed(6) : '-';

  const toggleCompareRecord = (record: TrainingRecord) => {
    compareSelectionTouchedRef.current = true;
    setCompareIds((current) => {
      if (current.includes(record.id)) {
        return current.filter((id) => id !== record.id);
      }
      if (current.length >= 4) {
        message.warning('最多选择 4 条训练记录进行对比');
        return current;
      }
      return [...current, record.id];
    });
  };

  const loadAllCompareMetrics = async (taskId: string) => {
    const allItems: TrainingMetricPoint[] = [];
    let cursor = 0;

    for (let page = 0; page < maxCompareMetricPages; page += 1) {
      const data = (await getTrainingTaskMetricsV2(
        taskId,
        cursor,
        compareMetricsPageSize,
      )) as TrainingMetricsPage;
      const items = Array.isArray(data?.items) ? data.items : [];
      allItems.push(...items);

      const nextCursor = Number(data?.next_cursor ?? data?.nextCursor);
      const hasMore = Boolean(data?.has_more ?? data?.hasMore);
      if (!hasMore || !Number.isFinite(nextCursor) || nextCursor <= cursor) break;

      cursor = nextCursor;
    }

    return allItems;
  };

  const openCompareDrawer = async () => {
    const records = trainingRecords.filter((record) => compareIds.includes(record.id));
    if (records.length < 2) {
      message.warning('请选择至少 2 条训练记录进行对比');
      return;
    }

    setCompareOpen(true);
    setCompareLoading(true);
    try {
      const metricEntries = await Promise.all(
        records.map(async (record) => {
          const items = await loadAllCompareMetrics(record.id);
          return [record.id, items] as const;
        }),
      );
      setCompareMetrics(Object.fromEntries(metricEntries));
    } catch (error) {
      console.error('Failed to load compare metrics:', error);
      message.error(getErrorMessage(error, '加载训练对比指标失败'));
    } finally {
      setCompareLoading(false);
    }
  };

  const buildCompareChartData = (records: TrainingRecord[]) => {
    const rows = new Map<number, CompareChartRow>();

    records.forEach((record) => {
      const metrics = compareMetrics[record.id] || [];
      metrics.forEach((metric, index) => {
        const loss = getMetricLoss(metric);
        if (loss === undefined) return;

        const step = getMetricStep(metric, index);
        const row = rows.get(step) || ({ step } as CompareChartRow);
        row[record.id] = Number(loss.toFixed(6));
        rows.set(step, row);
      });
    });

    return Array.from(rows.values()).sort((left, right) => left.step - right.step);
  };

  const getMetricSummary = (record: TrainingRecord) => {
    const metrics = compareMetrics[record.id] || [];
    const losses = metrics
      .map((metric) => getMetricLoss(metric))
      .filter((loss): loss is number => loss !== undefined);

    return {
      metricCount: metrics.length,
      firstLoss: losses[0],
      bestLoss: losses.length ? Math.min(...losses) : undefined,
      lastLoss: losses.length ? losses[losses.length - 1] : undefined,
    };
  };

  const getConfigValue = (record: TrainingRecord, key: string, fallback: string = '-') => {
    const config = record.config as any;
    const value = config?.[key];
    if (value === undefined || value === null || value === '') return fallback;
    if (typeof value === 'number') {
      return Math.abs(value) < 0.001 && value !== 0 ? value.toExponential(2) : String(value);
    }
    if (Array.isArray(value)) return value.join(', ');
    return String(value);
  };

  const buildConfigCompareRows = (records: TrainingRecord[]) => {
    const items = [
      {
        key: 'model',
        label: '基础模型',
        getValue: (record: TrainingRecord) => getBaseModelId(record) || record.modelName || '-',
      },
      {
        key: 'dataset',
        label: '数据集',
        getValue: (record: TrainingRecord) => record.datasetName || '-',
      },
      {
        key: 'method',
        label: '训练方法',
        getValue: (record: TrainingRecord) => record.method || '-',
      },
      {
        key: 'rank',
        label: 'Rank',
        getValue: (record: TrainingRecord) => getConfigValue(record, 'rank'),
      },
      {
        key: 'alpha',
        label: 'Alpha',
        getValue: (record: TrainingRecord) => getConfigValue(record, 'alpha'),
      },
      {
        key: 'learningRate',
        label: '学习率',
        getValue: (record: TrainingRecord) => getConfigValue(record, 'learningRate'),
      },
      {
        key: 'epochs',
        label: 'Epochs',
        getValue: (record: TrainingRecord) => getConfigValue(record, 'epochs'),
      },
      {
        key: 'batchSize',
        label: 'Batch Size',
        getValue: (record: TrainingRecord) => getConfigValue(record, 'batchSize'),
      },
      {
        key: 'maxSeqLength',
        label: '上下文长度',
        getValue: (record: TrainingRecord) => getConfigValue(record, 'maxSeqLength'),
      },
      {
        key: 'quantization',
        label: '量化',
        getValue: (record: TrainingRecord) => getConfigValue(record, 'quantization'),
      },
    ];

    return items.map((item) => {
      const values = records.map((record) => item.getValue(record));
      const row: Record<string, string | boolean> = {
        key: item.key,
        label: item.label,
        isDifferent: new Set(values).size > 1,
      };
      records.forEach((record, index) => {
        row[record.id] = values[index] ?? '-';
      });
      return row;
    });
  };

  const buildCompareReport = (records: TrainingRecord[]) => {
    const generatedAt = new Date().toLocaleString('zh-CN');
    const summaryRows = records.map((record) => [
      record.id,
      record.modelName || '-',
      record.datasetName || '-',
      record.method || '-',
      record.status || '-',
      formatLoss(getRecordFinalLoss(record)),
      getRecordTotalSteps(record) ?? '-',
      record.elapsedTime !== undefined && record.elapsedTime !== null
        ? formatElapsed(record.elapsedTime)
        : calculateDuration(record.startTime, record.endTime),
      record.outputPath || '-',
    ]);
    const metricRows = records.map((record) => {
      const summary = getMetricSummary(record);
      return [
        record.id,
        summary.metricCount,
        formatLoss(summary.firstLoss),
        formatLoss(summary.bestLoss),
        formatLoss(summary.lastLoss),
      ];
    });
    const configRows = buildConfigCompareRows(records).map((row) => [
      row.label,
      ...records.map((record) => row[record.id] || '-'),
    ]);

    const toTable = (headers: string[], rows: unknown[][]) => [
      `| ${headers.map(escapeMarkdownTableCell).join(' | ')} |`,
      `| ${headers.map(() => '---').join(' | ')} |`,
      ...rows.map((row) => `| ${row.map(escapeMarkdownTableCell).join(' | ')} |`),
    ];

    return [
      '# 训练对比报告',
      '',
      `生成时间：${generatedAt}`,
      '',
      '## 结果概览',
      '',
      ...toTable(
        ['训练 ID', '模型', '数据集', '方法', '状态', '最终 Loss', '步数', '耗时', '输出路径'],
        summaryRows,
      ),
      '',
      '## 指标摘要',
      '',
      ...toTable(['训练 ID', '指标点数', '起始 Loss', '最低 Loss', '末次 Loss'], metricRows),
      '',
      '## 关键配置差异',
      '',
      ...toTable(['配置项', ...records.map(getRecordLabel)], configRows),
      '',
    ].join('\n');
  };

  const buildCompareCsv = (records: TrainingRecord[]) => {
    const generatedAt = new Date().toLocaleString('zh-CN');
    const rows: unknown[][] = [];

    const pushRecordValue = (
      section: string,
      field: string,
      record: TrainingRecord,
      value: unknown,
    ) => {
      rows.push([
        section,
        field,
        record.id,
        record.modelName || '-',
        record.datasetName || '-',
        record.method || '-',
        record.status || '-',
        value ?? '-',
      ]);
    };

    rows.push(['metadata', 'generated_at', '-', '-', '-', '-', '-', generatedAt]);

    records.forEach((record) => {
      const duration =
        record.elapsedTime !== undefined && record.elapsedTime !== null
          ? formatElapsed(record.elapsedTime)
          : calculateDuration(record.startTime, record.endTime);
      pushRecordValue('summary', 'final_loss', record, formatLoss(getRecordFinalLoss(record)));
      pushRecordValue('summary', 'total_steps', record, getRecordTotalSteps(record) ?? '-');
      pushRecordValue('summary', 'duration', record, duration);
      pushRecordValue('summary', 'output_path', record, record.outputPath || '-');

      const metricSummary = getMetricSummary(record);
      pushRecordValue('metric_summary', 'metric_count', record, metricSummary.metricCount);
      pushRecordValue('metric_summary', 'first_loss', record, formatLoss(metricSummary.firstLoss));
      pushRecordValue('metric_summary', 'best_loss', record, formatLoss(metricSummary.bestLoss));
      pushRecordValue('metric_summary', 'last_loss', record, formatLoss(metricSummary.lastLoss));
    });

    buildConfigCompareRows(records).forEach((row) => {
      records.forEach((record) => {
        pushRecordValue('config', String(row.label), record, row[record.id] || '-');
      });
    });

    const headers = ['section', 'field', 'training_id', 'model', 'dataset', 'method', 'status', 'value'];
    const csv = [headers, ...rows].map((row) => row.map(escapeCsvCell).join(',')).join('\n');
    return `\ufeff${csv}`;
  };

  const downloadTextFile = (content: string, filename: string, type: string) => {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportCompareReport = () => {
    const records = trainingRecords.filter((record) => compareIds.includes(record.id));
    if (records.length < 2) {
      message.warning('请选择至少 2 条训练记录进行对比');
      return;
    }

    const content = buildCompareReport(records);
    const date = new Date().toISOString().slice(0, 10);
    downloadTextFile(content, `training-compare-${date}.md`, 'text/markdown;charset=utf-8');
    message.success('对比报告已导出');
  };

  const handleExportCompareCsv = () => {
    const records = trainingRecords.filter((record) => compareIds.includes(record.id));
    if (records.length < 2) {
      message.warning('请选择至少 2 条训练记录进行对比');
      return;
    }

    const content = buildCompareCsv(records);
    const date = new Date().toISOString().slice(0, 10);
    downloadTextFile(content, `training-compare-${date}.csv`, 'text/csv;charset=utf-8');
    message.success('CSV 已导出');
  };

  const handleResume = async (checkpointName: string) => {
    if (!selectedRecord) return;

    setResumingCheckpoint(checkpointName);
    try {
      await resumeTraining(selectedRecord.id, checkpointName);
      setIsTraining(true);
      message.success(`已从 ${checkpointName} 恢复训练`);
      await loadRecords();
    } catch (error) {
      console.error('Failed to resume training:', error);
      message.error(getErrorMessage(error, '恢复训练失败'));
    } finally {
      setResumingCheckpoint(null);
    }
  };

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; text: string }> = {
      running: { color: 'blue', text: '训练中' },
      completed: { color: 'green', text: '已完成' },
      failed: { color: 'red', text: '失败' },
      stopped: { color: 'default', text: '已停止' },
    };
    const config = statusMap[status] || { color: 'default', text: status };
    return <Tag color={config.color}>{config.text}</Tag>;
  };

  const getMethodTag = (method: string) => {
    const methodMap: Record<string, { color: string; text: string }> = {
      lora: { color: 'blue', text: 'LoRA' },
      qlora: { color: 'purple', text: 'QLoRA' },
      full: { color: 'orange', text: '全量' },
    };
    const config = methodMap[method] || { color: 'default', text: method };
    return <Tag color={config.color}>{config.text}</Tag>;
  };

  const calculateDuration = (start: string, end?: string) => {
    if (!end) return '-';
    const duration = new Date(end).getTime() - new Date(start).getTime();
    const minutes = Math.floor(duration / 60000);
    const seconds = Math.floor((duration % 60000) / 1000);
    return `${minutes}分 ${seconds}秒`;
  };

  const formatElapsed = (seconds?: number) => {
    if (seconds === undefined || seconds === null || Number.isNaN(seconds) || seconds < 0) {
      return '-';
    }
    const minutes = Math.floor(seconds / 60);
    const remainSeconds = Math.floor(seconds % 60);
    return `${minutes}分 ${remainSeconds}秒`;
  };

  const columns = [
    {
      title: '训练 ID',
      dataIndex: 'id',
      key: 'id',
      ellipsis: true,
    },
    {
      title: '模型',
      dataIndex: 'modelName',
      key: 'modelName',
    },
    {
      title: '数据集',
      dataIndex: 'datasetName',
      key: 'datasetName',
    },
    {
      title: '训练方法',
      dataIndex: 'method',
      key: 'method',
      render: (method: string) => getMethodTag(method),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '开始时间',
      dataIndex: 'startTime',
      key: 'startTime',
      render: (time: string) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: TrainingRecord) => (
        <Space>
          <Button icon={<EyeOutlined />} size="small" onClick={() => void openDetail(record)}>
            详情
          </Button>
          <Button
            icon={<LineChartOutlined />}
            size="small"
            onClick={() => toggleCompareRecord(record)}
          >
            {compareIds.includes(record.id) ? '移出对比' : '加入对比'}
          </Button>
          <Button
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => void handleDelete(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const compareChartData = buildCompareChartData(selectedCompareRecords);
  const bestLoss = selectedCompareRecords
    .map((record) => getRecordFinalLoss(record))
    .filter((loss): loss is number => loss !== undefined)
    .reduce<number | undefined>(
      (best, loss) => (best === undefined || loss < best ? loss : best),
      undefined,
    );
  const compareConfigRows = buildConfigCompareRows(selectedCompareRecords);
  const compareConfigColumns = [
    {
      title: '配置项',
      dataIndex: 'label',
      key: 'label',
      width: 120,
    },
    ...selectedCompareRecords.map((record) => ({
      title: getRecordLabel(record),
      dataIndex: record.id,
      key: record.id,
      render: (value: string, row: Record<string, string | boolean>) => (
        <span className={row.isDifferent ? styles.configDifferent : undefined}>{value}</span>
      ),
    })),
  ];
  const pageTitle = mode === 'compare' ? '训练对比' : '训练历史';
  const pageHelpTooltip =
    mode === 'compare'
      ? '选择 2-4 条历史训练记录，横向比较 Loss、耗时、步数和关键配置。'
      : '查看历史训练记录，并从失败或停止的任务检查点恢复训练。';

  return (
    <MotionList className={styles.container} stagger={0.08}>
      <MotionItem>
        <PageHeader
          title={pageTitle}
          icon={mode === 'compare' ? <LineChartOutlined /> : <HistoryOutlined />}
          helpTooltip={pageHelpTooltip}
          primaryAction={
            <Space>
              <Button
                icon={<LineChartOutlined />}
                onClick={() => void openCompareDrawer()}
                disabled={compareIds.length < 2}
                style={{ borderRadius: 8 }}
              >
                对比训练
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => void loadRecords()}
                loading={loading}
                style={{ borderRadius: 8 }}
              >
                刷新
              </Button>
            </Space>
          }
          style={{ marginBottom: 0 }}
        />
      </MotionItem>

      <MotionItem>
        <div className={`${glassStyles.glassCard} ${styles.tableCard}`}>
          <Table
            columns={columns}
            dataSource={trainingRecords}
            rowKey="id"
            rowSelection={{
              selectedRowKeys: compareIds,
              onChange: (keys) => {
                compareSelectionTouchedRef.current = true;
                setCompareIds(keys.map(String).slice(0, maxCompareRecords));
              },
              getCheckboxProps: (record: TrainingRecord) => ({
                disabled:
                  compareIds.length >= maxCompareRecords && !compareIds.includes(record.id),
              }),
            }}
            loading={loading}
            pagination={{ pageSize: 10 }}
            locale={{ emptyText: '暂无训练记录' }}
          />
        </div>
      </MotionItem>

      <Drawer
        title="训练详情"
        placement="right"
        width={600}
        open={detailOpen}
        onClose={closeDetail}
        extra={[
          selectedRecord ? (
            <Button
              key="reload"
              icon={<ReloadOutlined />}
              loading={checkpointsLoading}
              onClick={() => void loadCheckpoints(selectedRecord)}
              size="small"
            >
              刷新检查点
            </Button>
          ) : null,
          selectedRecord && isEligibleForMerge(selectedRecord) ? (
            <Button
              key="merge"
              icon={<DownloadOutlined />}
              size="small"
              onClick={openMergeModal}
              style={{ borderRadius: 8 }}
            >
              合并导出
            </Button>
          ) : null,
          <Button key="close" onClick={closeDetail}>
            关闭
          </Button>,
        ]}
      >
        {selectedRecord && (
          <>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="训练 ID">{selectedRecord.id}</Descriptions.Item>
              <Descriptions.Item label="模型">{selectedRecord.modelName}</Descriptions.Item>
              <Descriptions.Item label="数据集">{selectedRecord.datasetName}</Descriptions.Item>
              <Descriptions.Item label="训练方法">
                {getMethodTag(selectedRecord.method)}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {getStatusTag(selectedRecord.status)}
              </Descriptions.Item>
              <Descriptions.Item label="开始时间">
                {new Date(selectedRecord.startTime).toLocaleString('zh-CN')}
              </Descriptions.Item>
              {selectedRecord.endTime && (
                <Descriptions.Item label="结束时间">
                  {new Date(selectedRecord.endTime).toLocaleString('zh-CN')}
                </Descriptions.Item>
              )}
              <Descriptions.Item label="训练耗时">
                {selectedRecord.elapsedTime !== undefined && selectedRecord.elapsedTime !== null
                  ? formatElapsed(selectedRecord.elapsedTime)
                  : calculateDuration(selectedRecord.startTime, selectedRecord.endTime)}
              </Descriptions.Item>
              <Descriptions.Item label="最终 Loss">
                {selectedRecord.finalLoss !== undefined && selectedRecord.finalLoss !== null
                  ? selectedRecord.finalLoss.toFixed(6)
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="最终步数">
                {selectedRecord.totalSteps !== undefined && selectedRecord.totalSteps !== null
                  ? selectedRecord.totalSteps
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="输出路径">{selectedRecord.outputPath}</Descriptions.Item>
              <Descriptions.Item label="训练配置">
                <div style={{ fontSize: 12, lineHeight: 1.8 }}>
                  <div>Rank: {selectedRecord.config?.rank || '-'}</div>
                  <div>Alpha: {selectedRecord.config?.alpha || '-'}</div>
                  <div>
                    Learning Rate: {selectedRecord.config?.learningRate?.toExponential?.(2) || '-'}
                  </div>
                  <div>Epochs: {selectedRecord.config?.epochs || '-'}</div>
                  <div>Batch Size: {selectedRecord.config?.batchSize || '-'}</div>
                </div>
              </Descriptions.Item>
            </Descriptions>

            <div className={styles.detailSection}>
              <div className={styles.detailSectionTitle}>可恢复检查点</div>
              <Spin spinning={checkpointsLoading}>
                {checkpoints.length > 0 ? (
                  checkpoints.map((checkpoint) => (
                    <div key={checkpoint.name} className={styles.checkpointItem}>
                      <div>
                        <div className={styles.checkpointName}>
                          {checkpoint.name} · step {checkpoint.step}
                        </div>
                        <div className={styles.checkpointMeta}>
                          创建于 {new Date(checkpoint.created).toLocaleString('zh-CN')}
                        </div>
                      </div>
                      <Button
                        type="primary"
                        ghost
                        size="small"
                        icon={<PlayCircleOutlined />}
                        loading={resumingCheckpoint === checkpoint.name}
                        onClick={() => void handleResume(checkpoint.name)}
                        style={{ borderRadius: 6 }}
                      >
                        恢复训练
                      </Button>
                    </div>
                  ))
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有可用检查点" />
                )}
              </Spin>
            </div>
          </>
        )}
      </Drawer>

      <Modal
        title="合并导出"
        open={mergeOpen}
        onCancel={() => {
          setMergeOpen(false);
          mergeForm.resetFields();
        }}
        onOk={() =>
          void mergeForm
            .validateFields()
            .then((values) => handleMergeExport(values))
            .catch(() => null)
        }
        confirmLoading={merging}
        okText="开始合并"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={mergeForm} layout="vertical">
          <Descriptions column={1} size="small" bordered style={{ marginBottom: 16 }}>
            <Descriptions.Item label="训练 ID">{selectedRecord?.id || '-'}</Descriptions.Item>
            <Descriptions.Item label="基础模型 ID">
              {getBaseModelId(selectedRecord) || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="Adapter 路径">
              {selectedRecord?.checkpointPath || '-'}
            </Descriptions.Item>
          </Descriptions>
          <Form.Item
            label="输出名称"
            name="outputName"
            rules={[{ required: true, message: '请输入输出名称' }]}
          >
            <Input placeholder="merged-model-name" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title="训练对比"
        placement="right"
        width={920}
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        extra={
          <Space>
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExportCompareCsv}
              disabled={selectedCompareRecords.length < 2}
              size="small"
            >
              导出 CSV
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExportCompareReport}
              disabled={selectedCompareRecords.length < 2}
              size="small"
            >
              导出报告
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => void openCompareDrawer()}
              loading={compareLoading}
              size="small"
            >
              刷新指标
            </Button>
          </Space>
        }
      >
        <Spin spinning={compareLoading}>
          {selectedCompareRecords.length >= 2 ? (
            <>
              <div className={styles.compareSummaryGrid}>
                {selectedCompareRecords.map((record, index) => {
                  const finalLoss = getRecordFinalLoss(record);
                  return (
                    <div key={record.id} className={styles.compareSummaryItem}>
                      <div
                        className={styles.compareColor}
                        style={{ background: getCompareColor(index) }}
                      />
                      <div className={styles.compareTitle}>{record.modelName || record.id}</div>
                      <div className={styles.compareMeta}>{record.datasetName || '-'}</div>
                      <div className={styles.compareStats}>
                        <span>Loss {formatLoss(finalLoss)}</span>
                        {bestLoss !== undefined && finalLoss === bestLoss ? (
                          <Tag color="green">最低</Tag>
                        ) : null}
                      </div>
                      <div className={styles.compareMeta}>
                        步数 {getRecordTotalSteps(record) ?? '-'} · 耗时{' '}
                        {record.elapsedTime !== undefined && record.elapsedTime !== null
                          ? formatElapsed(record.elapsedTime)
                          : calculateDuration(record.startTime, record.endTime)}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Loss 曲线</div>
                {compareChartData.length > 0 ? (
                  <div className={styles.compareChart}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={compareChartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="step" tick={{ fontSize: 12 }} />
                        <YAxis tick={{ fontSize: 12 }} width={72} />
                        <RechartsTooltip />
                        <Legend />
                        {selectedCompareRecords.map((record, index) => (
                          <Line
                            key={record.id}
                            type="monotone"
                            dataKey={record.id}
                            name={record.modelName || record.id}
                            stroke={getCompareColor(index)}
                            dot={false}
                            strokeWidth={2}
                            connectNulls
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可对比指标曲线" />
                )}
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>关键配置差异</div>
                <Table
                  size="small"
                  columns={compareConfigColumns}
                  dataSource={compareConfigRows}
                  pagination={false}
                  rowKey="key"
                />
              </div>
            </>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择至少 2 条训练记录" />
          )}
        </Spin>
      </Drawer>
    </MotionList>
  );
}
