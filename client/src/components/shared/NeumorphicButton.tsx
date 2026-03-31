import React from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import styles from './NeumorphicButton.module.css';

interface NeumorphicButtonProps extends HTMLMotionProps<'button'> {
  children: React.ReactNode;
  className?: string;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  active?: boolean;
  icon?: React.ReactNode;
  htmlType?: 'button' | 'submit' | 'reset';
  loading?: boolean;
}

const NeumorphicButton: React.FC<NeumorphicButtonProps> = ({
  children,
  className = '',
  variant = 'primary',
  size = 'md',
  active = false,
  icon,
  htmlType = 'button',
  loading = false,
  ...props
}) => {
  const variantClass = styles[`variant-${variant}`];
  const sizeClass = styles[`size-${size}`];
  const activeClass = active ? styles.active : '';

  return (
    <motion.button
      type={htmlType}
      className={`${styles.button} ${variantClass} ${sizeClass} ${activeClass} ${className}`}
      whileHover={{ y: -1, scale: 1.02 }}
      whileTap={{ y: 1, scale: 0.98, boxShadow: 'var(--shadow-neumorph-in)' }}
      transition={{ duration: 0.1, ease: 'easeOut' }}
      disabled={props.disabled || loading}
      {...props}
    >
      <div className={styles.inner}>
        {loading ? <span className={styles.loadingIcon}>⏳</span> : icon && <span className={styles.icon}>{icon}</span>}
        {children}
      </div>
    </motion.button>
  );
};

export default NeumorphicButton;
