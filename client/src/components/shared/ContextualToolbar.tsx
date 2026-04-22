import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { LikeOutlined, DislikeOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons';
import { message } from 'antd';
import styles from './ContextualToolbar.module.css';

interface ToolbarPosition {
  x: number;
  y: number;
}

const ContextualToolbar: React.FC = () => {
  const [position, setPosition] = useState<ToolbarPosition | null>(null);

  useEffect(() => {
    const handleMouseUp = () => {
      const selection = window.getSelection();
      const text = selection?.toString().trim();
      
      if (text && selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        
        setPosition({
          x: rect.left + rect.width / 2,
          y: rect.top - 10
        });
      } else {
        setPosition(null);
      }
    };

    document.addEventListener('mouseup', handleMouseUp);
    return () => document.removeEventListener('mouseup', handleMouseUp);
  }, []);

  const handleAction = (action: string) => {
    message.success(`Saved for RLHF: [${action}]`);
    // Here we would typically dispatch to a store or make an API call
    // to save the interaction as an RLHF sample.
    setPosition(null);
    window.getSelection()?.removeAllRanges();
  };

  if (!position) return null;

  return createPortal(
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 10, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        className={styles.toolbarContainer}
        style={{
          left: position.x,
          top: position.y,
        }}
      >
        <button className={styles.toolBtn} onClick={() => handleAction('positive')} title="Good Response">
          <LikeOutlined />
        </button>
        <button className={styles.toolBtn} onClick={() => handleAction('negative')} title="Bad Response">
          <DislikeOutlined />
        </button>
        <div className={styles.divider} />
        <button className={styles.toolBtn} onClick={() => handleAction('edit')} title="Rewrite">
          <EditOutlined />
        </button>
        <button className={styles.toolBtn} onClick={() => handleAction('save')} title="Save to Dataset">
          <SaveOutlined />
        </button>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
};

export default ContextualToolbar;
