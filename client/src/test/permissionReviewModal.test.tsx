import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PermissionReviewModal from '../agent/components/PermissionReviewModal';

describe('PermissionReviewModal', () => {
  it('opens outside conversation and submits approve', async () => {
    const onDecide = vi.fn().mockResolvedValue(undefined);
    render(
      <PermissionReviewModal
        permission={{
          part_id: 'part_1',
          title: '确认',
          content: '',
          actions: [
            {
              index: 0,
              name: 'edit_file',
              args: { file_path: '/workspace/src/app.ts' },
              allowed_decisions: ['approve', 'reject'],
            },
          ],
        }}
        onDecide={onDecide}
      />,
    );

    expect(screen.getByTestId('permission-review-modal')).toBeInTheDocument();
    expect(screen.getByText(/需要确认/)).toBeInTheDocument();
    expect(screen.getAllByText(/src\/app\.ts/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /批\s*准/ }));
    await waitFor(() => {
      expect(onDecide).toHaveBeenCalledWith('part_1', [{ type: 'approve' }]);
    });
  });

  it('renders nothing without pending permission', () => {
    const { container } = render(
      <PermissionReviewModal permission={null} onDecide={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
