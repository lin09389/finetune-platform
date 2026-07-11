import React from 'react';

interface AnimatedLayoutProps {
  children: React.ReactNode;
  animationKey?: string;
}

/**
 * Kept as a layout-only compatibility wrapper. Route transitions are owned by
 * PageTransition, so pages do not animate twice when navigating.
 */
const AnimatedLayout: React.FC<AnimatedLayoutProps> = ({ children }) => (
  <div style={{ width: '100%', height: '100%', maxWidth: '1600px', margin: '0 auto' }}>
    {children}
  </div>
);

export default AnimatedLayout;
