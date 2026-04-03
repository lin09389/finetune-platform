import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import History from '../pages/History'

const mockUseAppStore = vi.hoisted(() => vi.fn())
const mockGetTrainingHistory = vi.hoisted(() => vi.fn())
const mockGetTrainingCheckpoints = vi.hoisted(() => vi.fn())
const mockResumeTraining = vi.hoisted(() => vi.fn())
const messageSuccess = vi.hoisted(() => vi.fn())
const messageError = vi.hoisted(() => vi.fn())

vi.mock('../store/appStore', () => ({
  useAppStore: mockUseAppStore,
}))

vi.mock('../services/trainingApi', () => ({
  getTrainingHistory: mockGetTrainingHistory,
  getTrainingCheckpoints: mockGetTrainingCheckpoints,
  resumeTraining: mockResumeTraining,
}))

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd') as Record<string, any>
  return {
    ...actual,
    message: {
      success: messageSuccess,
      error: messageError,
    },
  }
})

describe('History page', () => {
  const mockSetTrainingRecords = vi.fn()
  const mockRemoveTrainingRecord = vi.fn()
  const mockSetIsTraining = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    mockUseAppStore.mockReturnValue({
      trainingRecords: [
        {
          id: 'task-1',
          modelName: 'demo-model',
          datasetName: 'demo-dataset',
          method: 'qlora',
          status: 'completed',
          startTime: '2026-04-02T00:00:00',
          endTime: '2026-04-02T00:05:00',
          outputPath: '/tmp/output',
          config: {
            rank: 8,
            alpha: 16,
            learningRate: 0.0002,
            epochs: 3,
            batchSize: 2,
          },
        },
      ],
      setTrainingRecords: mockSetTrainingRecords,
      removeTrainingRecord: mockRemoveTrainingRecord,
      setIsTraining: mockSetIsTraining,
    })

    mockGetTrainingHistory.mockResolvedValue([
      {
        id: 'task-1',
        modelName: 'demo-model',
        datasetName: 'demo-dataset',
        method: 'qlora',
        status: 'completed',
        startTime: '2026-04-02T00:00:00',
        endTime: '2026-04-02T00:05:00',
        outputPath: '/tmp/output',
        config: {},
      },
    ])

    mockGetTrainingCheckpoints.mockResolvedValue([
      {
        name: 'checkpoint-10',
        path: '/tmp/output/checkpoints/checkpoint-10',
        step: 10,
        created: '2026-04-02T00:03:00',
      },
    ])

    mockResumeTraining.mockResolvedValue({
      id: 'task-1',
      modelName: 'demo-model',
      datasetName: 'demo-dataset',
      method: 'qlora',
      status: 'running',
      startTime: '2026-04-02T00:00:00',
      outputPath: '/tmp/output',
      config: {},
    })
  })

  it('loads history records on mount', async () => {
    render(<History />)

    await waitFor(() => {
      expect(mockGetTrainingHistory).toHaveBeenCalled()
      expect(mockSetTrainingRecords).toHaveBeenCalled()
    })
  })

  it('loads checkpoints when opening record detail', async () => {
    render(<History />)

    fireEvent.click(screen.getByRole('button', { name: /详情/ }))

    await waitFor(() => {
      expect(mockGetTrainingCheckpoints).toHaveBeenCalledWith('task-1')
      expect(screen.getByText(/checkpoint-10/i)).toBeInTheDocument()
    })
  })

  it('resumes training from a checkpoint', async () => {
    render(<History />)

    fireEvent.click(screen.getByRole('button', { name: /详情/ }))

    expect(await screen.findByText(/checkpoint-10/i, {}, { timeout: 10000 })).toBeInTheDocument()

    const resumeButton = await screen.findByRole('button', { name: /恢复训练|resume/i }, { timeout: 10000 })
    fireEvent.click(resumeButton)

    await waitFor(() => {
      expect(mockResumeTraining).toHaveBeenCalledWith('task-1', 'checkpoint-10')
      expect(mockSetIsTraining).toHaveBeenCalledWith(true)
      expect(messageSuccess).toHaveBeenCalled()
    }, { timeout: 10000 })
  }, 15000)
})
