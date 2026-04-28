import { ThunderboltOutlined, SyncOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { motion, AnimatePresence } from 'framer-motion';
import React, { useState, useEffect } from 'react';
import styles from './FollowUpSuggestions.module.css';

interface FollowUpSuggestionsProps {
  suggestions: string[];
  onSuggestionClick: (suggestion: string) => void;
  isVisible: boolean;
}

const FollowUpSuggestions: React.FC<FollowUpSuggestionsProps> = ({
  suggestions,
  onSuggestionClick,
  isVisible,
}) => {
  const displayCount = 4;
  const [startIndex, setStartIndex] = useState(0);

  // Reset when suggestions change
  useEffect(() => {
    setStartIndex(0);
  }, [suggestions]);

  if (!suggestions || suggestions.length === 0) return null;

  const handleRefresh = () => {
    setStartIndex((prev) => (prev + displayCount) % suggestions.length);
  };

  // Get current batch of suggestions (wrap around if needed)
  const currentSuggestions: string[] = [];
  for (let i = 0; i < Math.min(displayCount, suggestions.length); i++) {
    const item = suggestions[(startIndex + i) % suggestions.length];
    if (item) currentSuggestions.push(item);
  }

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 5 }}
          className={styles.suggestionsWrapper}
        >
          <div className={styles.suggestionsHeader}>
            <div className={styles.headerLeft}>
              <ThunderboltOutlined className={styles.headerIcon} />
              <span>您可以尝试这样问</span>
            </div>
            {suggestions.length > displayCount && (
              <Button 
                type="text" 
                size="small" 
                icon={<SyncOutlined />} 
                onClick={handleRefresh}
                className={styles.refreshBtn}
              >
                换一换
              </Button>
            )}
          </div>
          <div className={styles.suggestionsList}>
            {currentSuggestions.map((suggestion, index) => (
              <motion.div
                key={`${suggestion}-${startIndex}`}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
              >
                <Button
                  className={styles.suggestionBtn}
                  onClick={() => onSuggestionClick(suggestion)}
                >
                  {suggestion}
                </Button>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default FollowUpSuggestions;
