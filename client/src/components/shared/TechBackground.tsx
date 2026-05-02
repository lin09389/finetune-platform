import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from 'framer-motion';
import { useEffect } from 'react';

export default function TechBackground() {
  const reduceMotion = useReducedMotion();
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = { damping: 50, stiffness: 200, mass: 0.5 };
  const smoothX = useSpring(mouseX, springConfig);
  const smoothY = useSpring(mouseY, springConfig);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const normalizedX = (e.clientX / window.innerWidth) * 2 - 1;
      const normalizedY = (e.clientY / window.innerHeight) * 2 - 1;
      mouseX.set(normalizedX);
      mouseY.set(normalizedY);
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [mouseX, mouseY]);

  const gridX = useTransform(smoothX, [-1, 1], [-20, 20]);
  const gridY = useTransform(smoothY, [-1, 1], [-20, 20]);
  
  const particlesX = useTransform(smoothX, [-1, 1], [-50, 50]);
  const particlesY = useTransform(smoothY, [-1, 1], [-50, 50]);

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
            backgroundImage: `linear-gradient(var(--border-color) 1px, transparent 1px), linear-gradient(90deg, var(--border-color) 1px, transparent 1px)`,
            backgroundSize: '40px 40px',
            opacity: 0.25,
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
            y: particlesY 
          }}
        >
          <div style={{
            position: 'absolute',
            top: '10%',
            left: '20%',
            width: '400px',
            height: '400px',
            background: 'var(--accent-primary)',
            opacity: 0.15,
            borderRadius: '50%',
            filter: 'blur(100px)',
            mixBlendMode: 'screen',
          }} />
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '60%',
            width: '400px',
            height: '400px',
            background: 'var(--accent-secondary)',
            opacity: 0.12,
            borderRadius: '50%',
            filter: 'blur(100px)',
            mixBlendMode: 'screen',
          }} />
        </motion.div>
      )}
    </div>
  );
}
