import { Alert, Badge, Card, Empty, Spin, Tabs } from 'antd';
import { motion } from 'framer-motion';
import React, { useCallback, useEffect, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { API_BASE_URL } from '../services/api';

interface TrainingProgress {
  epoch: number;
  step: number;
  total_steps: number;
  loss: number;
  lr: number;
  vram_used: number;
  elapsed_time: number;
  eta: number;
  status: string;
  message: string;
}

interface ChartData {
  step: number;
  loss: number;
  lr: number;
  vram_used: number;
  epoch: number;
}

interface TrainingChartProps {
  taskId: string;
  autoConnect?: boolean;
}

export const TrainingChart: React.FC<TrainingChartProps> = ({ taskId, autoConnect = true }) => {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [activeTab, setActiveTab] = useState('loss');
  const [error, setError] = useState<string | null>(null);
  const [currentProgress, setCurrentProgress] = useState<TrainingProgress | null>(null);
  const wsRef = React.useRef<WebSocket | null>(null);
  const currentProgressRef = React.useRef<TrainingProgress | null>(null);

  const wsBase = API_BASE_URL.replace(/^http/, 'ws');

  useEffect(() => {
    currentProgressRef.current = currentProgress;
  }, [currentProgress]);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const wsUrl = `${wsBase}/training/v2/ws/${encodeURIComponent(taskId)}`;
    console.log('[TrainingChart] 连接 WebSocket:', wsUrl);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnected(true);
      setError(null);
      const heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
      wsRef.current = ws;
      (ws as any)._heartbeat = heartbeat;
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data);
        if (message?.type === 'pong') return;

        const payload = message?.payload || message?.data || {};
        const isProgressLike =
          typeof payload.step === 'number' ||
          typeof payload.loss === 'number' ||
          typeof payload.final_loss === 'number' ||
          message?.kind === 'metric_update';

        if (isProgressLike) {
          const previous = currentProgressRef.current;
          const progress: TrainingProgress = {
            epoch: Number(payload.epoch ?? previous?.epoch ?? 0),
            step: Number(payload.step ?? previous?.step ?? 0),
            total_steps: Number(
              payload.total_steps ?? payload.totalSteps ?? previous?.total_steps ?? 0,
            ),
            loss: Number(payload.loss ?? payload.final_loss ?? previous?.loss ?? 0),
            lr: Number(payload.lr ?? payload.final_lr ?? previous?.lr ?? 0),
            vram_used: Number(payload.vram_used ?? payload.vramUsed ?? previous?.vram_used ?? 0),
            elapsed_time: Number(
              payload.elapsed_time ?? payload.elapsedTime ?? previous?.elapsed_time ?? 0,
            ),
            eta: Number(payload.eta ?? previous?.eta ?? 0),
            status: String(message?.phase || payload.status || previous?.status || ''),
            message: String(payload.message || previous?.message || ''),
          };
          setCurrentProgress(progress);
          setChartData((prev) => {
            const exists = prev.some(
              (item) => item.step === progress.step && item.epoch === progress.epoch,
            );
            if (exists) return prev;
            const next = [
              ...prev,
              {
                step: progress.step,
                loss: progress.loss,
                lr: progress.lr,
                vram_used: progress.vram_used,
                epoch: progress.epoch,
              },
            ];
            return next.slice(-500);
          });
        }

        if (
          message?.phase === 'completed' ||
          message?.phase === 'failed' ||
          message?.phase === 'stopped'
        ) {
          setLoading(false);
        }
      } catch (e) {
        console.error('[TrainingChart] 解析消息失败:', e);
      }
    };

    ws.onerror = (err: Event) => {
      console.error('[TrainingChart] WebSocket 错误:', err);
      setError('WebSocket 连接失败');
    };

    ws.onclose = () => {
      setConnected(false);
      if (wsRef.current) {
        clearInterval((wsRef.current as any)._heartbeat);
      }
      setTimeout(() => {
        if (autoConnect) connectWebSocket();
      }, 3000);
    };
  }, [autoConnect, taskId, wsBase]);

  const loadHistoricalData = useCallback(async () => {
    try {
      setLoading(true);
      const v2Response = await fetch(
        `${API_BASE_URL}/training/v2/tasks/${encodeURIComponent(taskId)}/metrics?cursor=0&limit=500`,
      );
      if (v2Response.ok) {
        const v2Data = await v2Response.json();
        const items = Array.isArray(v2Data?.items) ? v2Data.items : [];
        const historicalData: ChartData[] = items
          .map((item: any, index: number) => ({
            step: Number(item.step ?? 0),
            loss: Number(item.loss ?? 0),
            lr: Number(item.lr ?? 0),
            vram_used: Number(item.vram_used ?? item.vramUsed ?? 0),
            epoch: Number(item.epoch ?? Math.floor(index / 100) + 1),
          }))
          .filter((point: ChartData) => point.step > 0);
        setChartData(historicalData);
        setLoading(false);
        return;
      }

      // Legacy fallback for older backend builds.
      const response = await fetch(`${API_BASE_URL}/training/chart-data/${taskId}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      const labels = data.loss_chart?.labels || [];
      const lossData = data.loss_chart?.data || [];
      const lrData = data.lr_chart?.data || [];
      const vramData = data.vram_chart?.data || [];
      const historicalData: ChartData[] = labels.map((step: number, i: number) => ({
        step,
        loss: lossData[i] || 0,
        lr: lrData[i] || 0,
        vram_used: vramData[i] || 0,
        epoch: Math.floor(i / 100) + 1,
      }));

      setChartData(historicalData);
    } catch (e) {
      console.error('[TrainingChart] 加载历史数据失败:', e);
      setError('加载历史数据失败');
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    loadHistoricalData();
    if (autoConnect) connectWebSocket();

    return () => {
      if (wsRef.current) {
        clearInterval((wsRef.current as any)._heartbeat);
        wsRef.current.close();
      }
    };
  }, [autoConnect, connectWebSocket, loadHistoricalData, taskId]);

  const renderChart = (dataKey: keyof ChartData, color: string, yAxisLabel: string) => {
    if (chartData.length === 0) return <Empty description="暂无数据" />;

    return (
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="step"
            stroke="#888"
            label={{ value: 'Step', position: 'insideBottom', offset: -5 }}
          />
          <YAxis
            stroke="#888"
            label={{ value: yAxisLabel, angle: -90, position: 'insideLeft' }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(0, 0, 0, 0.8)',
              border: '1px solid #333',
              borderRadius: 4,
            }}
            labelStyle={{ color: '#fff' }}
            formatter={(value: number | undefined) => [value?.toFixed(6) || '0', dataKey]}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    );
  };

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>训练监控</span>
          <Badge
            status={connected ? 'success' : 'error'}
            text={connected ? '实时连接中' : '未连接'}
          />
        </div>
      }
      extra={
        currentProgress && (
          <div style={{ fontSize: 12, color: '#888' }}>
            Epoch: {currentProgress.epoch} | Step: {currentProgress.step}/
            {currentProgress.total_steps} | ETA:{' '}
            {currentProgress.eta > 0 ? `${Math.round(currentProgress.eta / 60)}min` : '-'}
          </div>
        )
      }
    >
      {loading && chartData.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin fullscreen tip="加载数据中..." />
        </div>
      ) : error ? (
        <Alert message={error} type="error" showIcon />
      ) : (
        <>
          {currentProgress && (
            <div style={{ marginBottom: 16, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ fontSize: 14 }}>
                <strong>Loss:</strong> {currentProgress.loss.toFixed(6)}
              </div>
              <div style={{ fontSize: 14 }}>
                <strong>LR:</strong> {currentProgress.lr.toExponential(2)}
              </div>
              <div style={{ fontSize: 14 }}>
                <strong>VRAM:</strong> {currentProgress.vram_used.toFixed(2)} GB
              </div>
              <div style={{ fontSize: 14 }}>
                <strong>Elapsed:</strong> {Math.round(currentProgress.elapsed_time)}s
              </div>
            </div>
          )}

          <motion.div
            initial={{ opacity: 0, clipPath: 'inset(0 100% 0 0)' }}
            animate={{ opacity: 1, clipPath: 'inset(0 0% 0 0)' }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
                {
                  key: 'loss',
                  label: 'Loss 曲线',
                  children: renderChart('loss', '#8884d8', 'Loss'),
                },
                {
                  key: 'lr',
                  label: '学习率',
                  children: renderChart('lr', '#82ca9d', 'Learning Rate'),
                },
                {
                  key: 'vram',
                  label: '显存使用',
                  children: renderChart('vram_used', '#ffc658', 'VRAM (GB)'),
                },
              ]}
            />
          </motion.div>
        </>
      )}
    </Card>
  );
};

export default TrainingChart;
