import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GlassHoverCard, InteractiveButton, SmoothLoader } from '../components/motion';

// Mock useMotionConfig
vi.mock('../components/motion/useMotionConfig', () => ({
  useMotionConfig: () => ({
    shouldReduceMotion: false,
    getDuration: (d: number) => d,
    safeTransition: { duration: 0.2 },
    getSafeVariants: (v: any) => v,
  }),
}));

describe('Motion Components', () => {
  describe('InteractiveButton', () => {
    it('renders with children', () => {
      render(<InteractiveButton>Click Me</InteractiveButton>);
      expect(screen.getByText('Click Me')).toBeInTheDocument();
    });

    it('handles click events', () => {
      const handleClick = vi.fn();
      render(<InteractiveButton onClick={handleClick}>Click Me</InteractiveButton>);
      fireEvent.click(screen.getByText('Click Me'));
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('is disabled when disabled prop is true', () => {
      const handleClick = vi.fn();
      render(
        <InteractiveButton disabled onClick={handleClick}>
          Disabled
        </InteractiveButton>
      );
      fireEvent.click(screen.getByText('Disabled'));
      expect(handleClick).not.toHaveBeenCalled();
    });
  });

  describe('GlassHoverCard', () => {
    it('renders content correctly', () => {
      render(
        <GlassHoverCard>
          <div>Card Content</div>
        </GlassHoverCard>
      );
      expect(screen.getByText('Card Content')).toBeInTheDocument();
    });
  });

  describe('SmoothLoader', () => {
    it('renders loader SVG', () => {
      const { container } = render(<SmoothLoader size="md" />);
      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('renders fullscreen wrapper when fullscreen is true', () => {
      const { container } = render(<SmoothLoader fullscreen />);
      // 应该包含 fixed 和 inset-0 样式
      expect(container.firstChild).toHaveClass('fixed', 'inset-0');
    });
  });
});
