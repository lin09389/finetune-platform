import { AnimatePresence, motion } from 'framer-motion';
import React, { forwardRef } from 'react';
import styles from './PremiumInput.module.css';

interface PremiumInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
  suffix?: React.ReactNode;
  containerClassName?: string;
}

const PremiumInput = forwardRef<HTMLInputElement, PremiumInputProps>(
  ({ label, error, icon, suffix, containerClassName = '', className = '', ...props }, ref) => {
    return (
      <div className={`${styles.container} ${containerClassName}`}>
        {label && <label className={styles.label}>{label}</label>}
        <div className={styles.inputWrapper}>
          {icon && <span className={styles.icon}>{icon}</span>}
          <input
            ref={ref}
            className={`${styles.input} ${icon ? styles.withIcon : ''} ${suffix ? styles.withSuffix : ''} ${error ? styles.error : ''} ${className}`}
            {...props}
          />
          {suffix && <span className={styles.suffix}>{suffix}</span>}
        </div>
        <AnimatePresence>
          {error && (
            <motion.p
              className={styles.errorText}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              {error}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    );
  },
);

PremiumInput.displayName = 'PremiumInput';

export default PremiumInput;
