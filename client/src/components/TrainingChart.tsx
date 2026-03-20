import React, { useEffect, useState, useCallback } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { Card, Spin, Empty, Alert, Badge, Tabs } from 'antd';

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

/**
 * P2-1: 训练可视化组件
 * 功能：
 * - WebSocket 实时连接
 * - Loss/LR/VRAM 曲线展示
 * - 实时数据更新
 */
export const TrainingChart: React.FC<TrainingChartProps> = ({
  taskId,
  autoConnect = true
}) => {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [activeTab, setActiveTab] = useState('loss');
  const [error, setError] = useState<string | null>(null);
  const [currentProgress, setCurrentProgress] = useState<TrainingProgress | null>(null);
  const wsRef = React.useRef<WebSocket | null>(null);

  // 连接 WebSocket
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/training/ws/${taskId}`;
    
    console.log('[TrainingChart] 连接 WebSocket:', wsUrl);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[TrainingChart] WebSocket 已连接');
      setConnected(true);
      setError(null);
      
      // 发送心跳
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
        
        if (message.type === 'progress') {
          const progress: TrainingProgress = message.data;
          setCurrentProgress(progress);
          
          // 更新图表数据
          setChartData(prev => {
            const newData = [...prev, {
              step: progress.step,
              loss: progress.loss,
              lr: progress.lr,
              vram_used: progress.vram_used,
              epoch: progress.epoch
            }];
            // 限制数据点数量，避免图表过密
            return newData.slice(-500);
          });
        } else if (message.type === 'event') {
          console.log('[TrainingChart] 收到事件:', message.event, message.data);
          
          if (message.event === 'training_completed') {
            setLoading(false);
          }
        } else if (message.type === 'pong') {
          // 心跳响应
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
      console.log('[TrainingChart] WebSocket 已断开');
      setConnected(false);
      
      if (wsRef.current) {
        clearInterval((wsRef.current as any)._heartbeat);
      }
      
      // 3 秒后尝试重连
      setTimeout(() => {
        if (autoConnect) {
          console.log('[TrainingChart] 尝试重连...');
          connectWebSocket();
        }
      }, 3000);
    };
  }, [taskId, autoConnect]);

  // 加载历史数据
  const loadHistoricalData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/training/chart-data/${taskId}`);
      const data = await response.json();
      
      const historicalData: ChartData[] = [];
      const labels = data.loss_chart?.labels || [];
      const lossData = data.loss_chart?.data || [];
      const lrData = data.lr_chart?.data || [];
      const vramData = data.vram_chart?.data || [];
      
      for (let i = 0; i < labels.length; i++) {
        historicalData.push({
          step: labels[i],
          loss: lossData[i] || 0,
          lr: lrData[i] || 0,
          vram_used: vramData[i] || 0,
          epoch: Math.floor(i / 100) + 1 // 估算
        });
      }
      
      setChartData(historicalData);
      setLoading(false);
    } catch (e) {
      console.error('[TrainingChart] 加载历史数据失败:', e);
      setError('加载历史数据失败');
      setLoading(false);
    }
  }, [taskId]);

  // 初始化
  useEffect(() => {
    // 先加载历史数据
    loadHistoricalData();
    
    // 连接 WebSocket
    if (autoConnect) {
      connectWebSocket();
    }

    return () => {
      if (wsRef.current) {
        clearInterval((wsRef.current as any)._heartbeat);
        wsRef.current.close();
      }
    };
  }, [taskId, autoConnect, connectWebSocket, loadHistoricalData]);

  // 渲染图表
  const renderChart = (dataKey: keyof ChartData, color: string, yAxisLabel: string) => {
    if (chartData.length === 0) {
      return (
        <Empty description="暂无数据" />
      );
    }

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
              borderRadius: '4px'
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
          <Badge status={connected ? 'success' : 'error'} text={connected ? '实时连接中' : '未连接'} />
        </div>
      }
      extra={
        currentProgress && (
          <div style={{ fontSize: 12, color: '#888' }}>
            Epoch: {currentProgress.epoch} | Step: {currentProgress.step}/{currentProgress.total_steps} | 
            ETA: {currentProgress.eta > 0 ? `${Math.round(currentProgress.eta / 60)}min` : '-'}
          </div>
        )
      }
    >
      {loading && chartData.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin tip="加载数据中..." />
        </div>
      ) : error ? (
        <Alert message={error} type="error" showIcon />
      ) : (
        <>
          {/* 实时状态 */}
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

          {/* 图表 Tab */}
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'loss',
                label: 'Loss 曲线',
                children: renderChart('loss', '#8884d8', 'Loss')
              },
              {
                key: 'lr',
                label: '学习率',
                children: renderChart('lr', '#82ca9d', 'Learning Rate')
              },
              {
                key: 'vram',
                label: '显存使用',
                children: renderChart('vram_used', '#ffc658', 'VRAM (GB)')
              }
            ]}
          />
        </>
      )}
    </Card>
  );
};

export default TrainingChart;
