import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import InsightPanel from '../components/shared/InsightPanel'

describe('InsightPanel', () => {
  it('renders status, metrics, and sections in embedded mode', () => {
    render(
      <InsightPanel
        embedded
        title="运行观测"
        status={{ type: 'info', text: '已采样' }}
        summary="用于统一展示能力状态。"
        metrics={[
          { label: '请求数', value: 12 },
          { label: '平均耗时', value: '320 ms' },
        ]}
        sections={[
          { title: '建议', items: ['先预热模型', '检查后端切换'] },
        ]}
        testId="insight-panel"
      />
    )

    expect(screen.getByTestId('insight-panel')).toBeInTheDocument()
    expect(screen.getByText('运行观测')).toBeInTheDocument()
    expect(screen.getByText('已采样')).toBeInTheDocument()
    expect(screen.getByText('请求数')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('先预热模型')).toBeInTheDocument()
  })
})
