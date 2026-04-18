import { ThunderboltOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { motion, AnimatePresence } from 'framer-motion';
import React from 'react';
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
  if (!suggestions || suggestions.length === 0) return null;

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
            <ThunderboltOutlined className={styles.headerIcon} />
            <span>您可以尝试这样问</span>
          </div>
          <div className={styles.suggestionsList}>
            {suggestions.map((suggestion, index) => (
              <motion.div
                key={suggestion}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
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
