import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentWorkbenchPanel from '../components/chat/AgentWorkbenchPanel';

function renderPanel(activeKey = 'execution', onActiveKeyChange = vi.fn()) {
  render(
    <AgentWorkbenchPanel
      activeKey={activeKey}
      onActiveKeyChange={onActiveKeyChange}
      changedFiles={0}
      runContent={<div>运行内容</div>}
      configContent={<div>配置内容</div>}
      progressContent={<div>进度内容</div>}
      asyncTasksContent={<div>子任务内容</div>}
      executionContent={<div>执行内容</div>}
      approvalsContent={<div>确认内容</div>}
      inspectorContent={<div>检查器内容</div>}
      fileTreeContent={<div>文件树</div>}
      editorContent={<div>编辑器</div>}
    />,
  );
  return onActiveKeyChange;
}

describe('AgentWorkbenchPanel', () => {
  it('supports controlled tab changes', () => {
    const onActiveKeyChange = renderPanel();

    fireEvent.click(screen.getByText('子任务'));

    expect(onActiveKeyChange).toHaveBeenCalledWith('subagents');
  });

  it('renders the controlled active tab content', () => {
    renderPanel('subagents');

    expect(screen.getByText('子任务内容')).toBeInTheDocument();
  });

  it('renders execution as a controlled tab', () => {
    renderPanel('execution');

    expect(screen.getByText('执行内容')).toBeInTheDocument();
  });
});
