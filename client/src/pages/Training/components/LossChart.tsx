import { LineChartOutlined } from '@ant-design/icons';
import React from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import styles from './LossChart.module.css';

interface ChartDataPoint {
  step: number;
  loss: number;
  lr: number;
}

interface LossChartProps {
  data: ChartDataPoint[];
}

const LossChart: React.FC<LossChartProps> = ({ data }) => {
  if (data.length === 0) return null;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <LineChartOutlined className={styles.icon} />
        <h4 className={styles.title}>Loss 实时收敛曲线</h4>
      </div>

      <div className={styles.chartWrapper}>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
            <XAxis
              dataKey="step"
              stroke="var(--text-tertiary)"
              fontSize={10}
              tickLine={false}
              axisLine={false}
            />
            <YAxis stroke="var(--text-tertiary)" fontSize={10} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-lg)',
                boxShadow: 'var(--shadow-lg)',
                fontSize: '12px',
                color: 'var(--text-primary)',
              }}
              labelStyle={{ fontWeight: 700, marginBottom: 4 }}
              cursor={{ stroke: 'var(--accent-primary)', strokeWidth: 1, strokeDasharray: '4 4' }}
            />
            <ReferenceLine y={0} stroke="var(--text-tertiary)" strokeOpacity={0.2} />
            <Line
              type="monotone"
              dataKey="loss"
              stroke="var(--accent-primary)"
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 4, fill: 'var(--accent-primary)', strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default LossChart;
