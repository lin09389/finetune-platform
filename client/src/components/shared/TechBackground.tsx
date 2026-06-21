import { m, useMotionValue, useReducedMotion, useSpring, useTransform, useMotionTemplate } from 'framer-motion';
import { useEffect } from 'react';
import { useTheme } from '../../theme';

export default function TechBackground() {
  const reduceMotion = useReducedMotion();
  const { theme } = useTheme();

  const isDark = theme === 'dark';

  // Pixel-based mouse coordinates initialized to center screen safely
  const mouseX = useMotionValue(typeof window !== 'undefined' ? window.innerWidth / 2 : 0);
  const mouseY = useMotionValue(typeof window !== 'undefined' ? window.innerHeight / 2 : 0);

  // Premium spring physics for ultra-smooth responsiveness
  const springConfig = { damping: 50, stiffness: 150, mass: 0.6 };
  const smoothX = useSpring(mouseX, springConfig);
  const smoothY = useSpring(mouseY, springConfig);

  useEffect(() => {
    if (reduceMotion) return undefined;
    let rafId: number;
    const handleMouseMove = (e: MouseEvent) => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        mouseX.set(e.clientX);
        mouseY.set(e.clientY);
      });
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(rafId);
    };
  }, [mouseX, mouseY, reduceMotion]);

  // Dynamic vector spotlight mask following the cursor
  const maskImage = useMotionTemplate`radial-gradient(450px circle at ${smoothX}px ${smoothY}px, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 80%)`;

  // Compute a highly subtle grid parallax shift for a 3D sense of depth
  const parallaxIntensity = isDark ? 16 : 6;
  const gridParallaxX = useTransform(smoothX, [0, typeof window !== 'undefined' ? window.innerWidth : 1920], [-parallaxIntensity, parallaxIntensity]);
  const gridParallaxY = useTransform(smoothY, [0, typeof window !== 'undefined' ? window.innerHeight : 1080], [-parallaxIntensity, parallaxIntensity]);

  if (reduceMotion) {
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
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: `linear-gradient(rgba(255, 255, 255, 0.008) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.008) 1px, transparent 1px)`,
            backgroundSize: '40px 40px',
            opacity: 0.5,
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: '30%',
            left: '30%',
            width: '600px',
            height: '600px',
            background: isDark
              ? 'radial-gradient(circle, rgba(99, 102, 241, 0.04) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(56, 189, 248, 0.06) 0%, transparent 70%)',
            filter: 'blur(100px)',
          }}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        zIndex: -1,
        overflow: 'hidden',
        background: 'var(--bg-primary)'
      }}
    >
      {/* 1. Base Static Grid (Tactile and elegant, always visible at low opacity) */}
      <div
        style={{
          position: 'absolute',
          inset: '-50px',
          backgroundImage: isDark
            ? `linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px)`
            : `linear-gradient(rgba(0, 0, 0, 0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 0, 0, 0.015) 1px, transparent 1px)`,
          backgroundSize: '40px 40px',
          maskImage: 'radial-gradient(ellipse at center, black 40%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(ellipse at center, black 40%, transparent 100%)',
        }}
      />

      {/* 2. Follow Spotlight Vector Grid (Dynamic highlight on movement) */}
      <m.div
        style={{
          position: 'absolute',
          inset: '-50px',
          x: gridParallaxX,
          y: gridParallaxY,
          backgroundImage: isDark
            ? `linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px)`
            : `linear-gradient(rgba(0, 0, 0, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 0, 0, 0.03) 1px, transparent 1px)`,
          backgroundSize: '40px 40px',
          maskImage,
          WebkitMaskImage: maskImage,
          willChange: 'transform',
        }}
      />

      {/* 3. Floating Organic Glows (Slow-panning theme-aware glows) */}
      <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', mixBlendMode: isDark ? 'screen' : 'multiply', opacity: isDark ? 1 : 0.6 }}>
        {/* Glow 1 */}
        <m.div
          style={{
            position: 'absolute',
            top: '5%',
            left: '10%',
            width: '600px',
            height: '600px',
            borderRadius: '50%',
            background: isDark
              ? 'radial-gradient(circle, rgba(99, 102, 241, 0.12) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(167, 139, 250, 0.15) 0%, transparent 70%)',
            filter: 'blur(100px)',
            willChange: 'transform',
          }}
          animate={{
            x: [0, 80, -40, 0],
            y: [0, -60, 50, 0],
            scale: [1, 1.12, 0.92, 1],
          }}
          transition={{
            duration: 25,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />

        {/* Glow 2 */}
        <m.div
          style={{
            position: 'absolute',
            top: '30%',
            left: '55%',
            width: '500px',
            height: '500px',
            borderRadius: '50%',
            background: isDark
              ? 'radial-gradient(circle, rgba(6, 182, 212, 0.1) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(56, 189, 248, 0.12) 0%, transparent 70%)',
            filter: 'blur(100px)',
            willChange: 'transform',
          }}
          animate={{
            x: [0, -90, 60, 0],
            y: [0, 80, -50, 0],
            scale: [1, 0.88, 1.1, 1],
          }}
          transition={{
            duration: 20,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />

        {/* Glow 3 */}
        <m.div
          style={{
            position: 'absolute',
            top: '60%',
            left: '25%',
            width: '550px',
            height: '550px',
            borderRadius: '50%',
            background: isDark
              ? 'radial-gradient(circle, rgba(217, 70, 239, 0.08) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(16, 185, 129, 0.08) 0%, transparent 70%)',
            filter: 'blur(110px)',
            willChange: 'transform',
          }}
          animate={{
            x: [0, 50, -70, 0],
            y: [0, 70, -40, 0],
            scale: [1, 1.08, 0.95, 1],
          }}
          transition={{
            duration: 22,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
      </div>
    </div>
  );
}
