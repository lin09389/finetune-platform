import { useReducedMotion } from 'framer-motion';
import { useTheme } from '../../theme';

/**
 * Claude-style background — clean, warm, paper-like.
 *
 * Claude's aesthetic is editorial and calm: a solid warm off-white
 * (light) or warm dark charcoal (dark) with no grid patterns, no
 * animated floating glows, and no tech aesthetics. The background
 * should feel like a beautifully typeset book page.
 *
 * We keep a single, extremely subtle static warm radial wash so the
 * page never feels flat, but it never competes with content.
 */
export default function TechBackground() {
  const reduceMotion = useReducedMotion();
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: -1,
        overflow: 'hidden',
        background: 'var(--bg-primary)',
      }}
    >
      {/* Single subtle static warm wash — barely perceptible */}
      <div
        style={{
          position: 'absolute',
          top: '-10%',
          right: '-5%',
          width: '60vw',
          height: '60vw',
          maxWidth: '900px',
          maxHeight: '900px',
          background: isDark
            ? 'radial-gradient(circle, color-mix(in srgb, var(--accent-primary) 3%, transparent) 0%, transparent 65%)'
            : 'radial-gradient(circle, color-mix(in srgb, var(--accent-primary) 2.5%, transparent) 0%, transparent 65%)',
          filter: 'blur(80px)',
          opacity: reduceMotion ? 0.5 : 0.8,
        }}
      />
    </div>
  );
}
