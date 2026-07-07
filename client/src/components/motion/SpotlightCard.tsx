import React from 'react';
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
  style = {},
  onClick,
}) => {
  const { theme } = useTheme();

  return (
    <div
      onClick={onClick}
      className={`rounded-2xl border transition-all duration-200 ${
        theme === 'dark'
          ? 'border-white/5 bg-black/40 hover:border-white/10'
          : 'border-black/5 bg-white/60 hover:border-black/10'
      } ${className}`}
      style={{
        cursor: onClick ? 'pointer' : 'default',
        ...style
      }}
    >
      <div className="relative h-full w-full">
        {children}
      </div>
    </div>
  );
};
