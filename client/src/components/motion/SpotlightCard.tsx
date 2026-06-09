import React, { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useTheme } from '../../theme';

interface SpotlightCardProps {
  children: React.ReactNode;
  className?: string;
  spotlightColor?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
}

export const SpotlightCard: React.FC<SpotlightCardProps> = ({
  children,
  className = '',
  spotlightColor,
  style = {},
  onClick,
}) => {
  const divRef = useRef<HTMLDivElement>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [opacity, setOpacity] = useState(0);
  const { theme } = useTheme();

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!divRef.current || isFocused) return;

    const div = divRef.current;
    const rect = div.getBoundingClientRect();

    setPosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const handleFocus = () => {
    setIsFocused(true);
    setOpacity(1);
  };

  const handleBlur = () => {
    setIsFocused(false);
    setOpacity(0);
  };

  const handleMouseEnter = () => {
    setOpacity(1);
  };

  const handleMouseLeave = () => {
    setOpacity(0);
  };

  const defaultSpotlightColor = theme === 'dark' 
    ? 'rgba(129, 140, 248, 0.15)' 
    : 'rgba(99, 102, 241, 0.05)';

  const activeSpotlightColor = spotlightColor || defaultSpotlightColor;

  return (
    <motion.div
      ref={divRef}
      onMouseMove={handleMouseMove}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
      className={`relative overflow-hidden rounded-2xl border transition-all duration-500 ${
        theme === 'dark'
          ? 'border-white/5 bg-black/40 hover:border-white/10'
          : 'border-black/5 bg-white/40 hover:border-black/10'
      } ${className}`}
      style={{
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        cursor: onClick ? 'pointer' : 'default',
        ...style
      }}
      whileHover={{ scale: onClick ? 1.01 : 1, y: onClick ? -2 : 0 }}
      whileTap={{ scale: onClick ? 0.98 : 1 }}
    >
      <div
        className="pointer-events-none absolute -inset-px opacity-0 transition duration-300"
        style={{
          opacity,
          background: `radial-gradient(600px circle at ${position.x}px ${position.y}px, ${activeSpotlightColor}, transparent 40%)`,
        }}
      />
      <div className="relative h-full w-full z-10">
        {children}
      </div>
    </motion.div>
  );
};
