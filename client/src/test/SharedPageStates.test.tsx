import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import EmptyState from '../components/shared/EmptyState';
import LoadingState from '../components/shared/LoadingState';
import StatusState from '../components/shared/StatusState';

describe('shared page states', () => {
  it('announces a loading operation instead of rendering a decorative spinner alone', () => {
    render(<LoadingState tip="正在读取设备状态" />);

    expect(screen.getByRole('status')).toHaveAccessibleName('正在读取设备状态');
  });

  it('keeps a compact empty state focusable and actionable', () => {
    const onAction = vi.fn();
    render(
      <EmptyState
        compact
        title="暂无训练记录"
        description="创建一次训练后，结果会显示在这里。"
        action={{ text: '开始训练', onClick: onAction }}
      />,
    );

    const action = screen.getByRole('button', { name: '开始训练' });
    action.focus();
    expect(action).toHaveFocus();
    fireEvent.click(action);

    expect(onAction).toHaveBeenCalledOnce();
    expect(screen.getByText('暂无训练记录')).toBeVisible();
  });

  it('explains failed work and exposes a real retry action', () => {
    const onRetry = vi.fn();
    render(
      <StatusState
        tone="error"
        title="模型运行中心暂时无法加载"
        description="检查本地服务后重试。"
        action={{ text: '重试加载', onClick: onRetry }}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('模型运行中心暂时无法加载');
    expect(screen.getByRole('alert')).toHaveTextContent('检查本地服务后重试。');
    fireEvent.click(screen.getByRole('button', { name: '重试加载' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
