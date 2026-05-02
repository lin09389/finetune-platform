import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'framer-motion';
import { useEffect } from 'react';

export default function TechBackground() {
  const reduceMotion = useReducedMotion();
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = { damping: 80, stiffness: 100, mass: 1 };
  const smoothX = useSpring(mouseX, springConfig);
  const smoothY = useSpring(mouseY, springConfig);

  useEffect(() => {
    let rafId: number;
    const handleMouseMove = (e: MouseEvent) => {
      // Throttle via rAF to prevent rapid state dispatching which freezes UI
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const normalizedX = (e.clientX / window.innerWidth) * 2 - 1;
        const normalizedY = (e.clientY / window.innerHeight) * 2 - 1;
        mouseX.set(normalizedX);
        mouseY.set(normalizedY);
      });
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(rafId);
    };
  }, [mouseX, mouseY]);

  const gridX = useTransform(smoothX, [-1, 1], [-20, 20]);
  const gridY = useTransform(smoothY, [-1, 1], [-20, 20]);
  
  const particlesX = useTransform(smoothX, [-1, 1], [-60, 60]);
  const particlesY = useTransform(smoothY, [-1, 1], [-60, 60]);

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
      {/* Dynamic Grid */}
      {!reduceMotion && (
        <motion.div
          style={{
            position: 'absolute',
            inset: '-50%',
            x: gridX,
            y: gridY,
            z: 0, // Force hardware acceleration without breaking x/y
            backgroundImage: `linear-gradient(var(--border-color) 1px, transparent 1px), linear-gradient(90deg, var(--border-color) 1px, transparent 1px)`,
            backgroundSize: '40px 40px',
            opacity: 0.15, // Reduced opacity for performance
            maskImage: 'radial-gradient(ellipse at center, black 10%, transparent 60%)',
            WebkitMaskImage: 'radial-gradient(ellipse at center, black 10%, transparent 60%)',
          }}
        />
      )}

      {/* Floating Glows */}
      {!reduceMotion && (
        <motion.div
          style={{ 
            position: 'absolute',
            inset: 0,
            x: particlesX, 
            y: particlesY,
            z: 0, // Force hardware acceleration
          }}
        >
          {/* Removed mixBlendMode and reduced blur for extreme performance stability */}
          <div style={{
            position: 'absolute',
            top: '10%',
            left: '20%',
            width: '400px',
            height: '400px',
            background: 'var(--accent-primary)',
            opacity: 0.08,
            borderRadius: '50%',
            filter: 'blur(100px)',
          }} />
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '60%',
            width: '400px',
            height: '400px',
            background: 'var(--accent-secondary)',
            opacity: 0.06,
            borderRadius: '50%',
            filter: 'blur(100px)',
          }} />
        </motion.div>
      )}
    </div>
  );
}
