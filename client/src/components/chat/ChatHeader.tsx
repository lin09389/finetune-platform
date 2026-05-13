import {
  BulbOutlined,
  ClearOutlined,
  ExportOutlined,
  HistoryOutlined,
  MoreOutlined,
  PlusOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Button, Dropdown, Space, Tooltip, Typography, message } from 'antd';
import { motion } from 'framer-motion';
import React, { useCallback } from 'react';
import { useResponsive } from '../../hooks/useResponsive';
import { transitions } from '../../theme/animations';
import { appModal } from '../../utils/modal';
import styles from './ChatHeader.module.css';

const { Text } = Typography;

interface ChatHeaderProps {
  onNewChat: () => void;
  onOpenHistory: () => void;
  onOpenMemory: () => void;
  onOpenContextPanel?: () => void;
  onClearChat: () => void;
  onExportChat: (format: 'markdown' | 'json') => void;
  messageCount: number;
  activeModeLabel: string;
  activeModelLabel: string;
}

const ChatHeader: React.FC<ChatHeaderProps> = ({
  onNewChat,
  onOpenHistory,
  onOpenMemory,
  onOpenContextPanel,
  onClearChat,
  onExportChat,
  messageCount,
  activeModeLabel,
  activeModelLabel,
}) => {
  const { isMobile } = useResponsive();

  const handleExport = useCallback(
    (format: 'markdown' | 'json') => {
      if (messageCount === 0) {
        message.warning('暂无对话内容');
        return;
      }
      onExportChat(format);
    },
    [messageCount, onExportChat],
  );

  const handleClear = useCallback(() => {
    if (messageCount === 0) return;

    appModal.confirm({
      title: '确认清空',
      content: '确定要清空当前对话吗？',
      okText: '清空',
      okButtonProps: { danger: true },
      onOk: onClearChat,
    });
  }, [messageCount, onClearChat]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.08, ...transitions.base }}
      className={`${styles.header} ${isMobile ? styles.headerMobile : ''}`}
    >
      <div className={styles.headerLeft}>
        <Space size={8}>
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={onNewChat}
              className={`${styles.actionButton} ${styles.newChatBtn}`}
            >
              新对话
            </Button>
          </motion.div>

          {!isMobile && (
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Button
                icon={<HistoryOutlined />}
                onClick={onOpenHistory}
                className={`${styles.actionButton} ${styles.historyBtn}`}
              >
                历史
              </Button>
            </motion.div>
          )}
        </Space>

        {!isMobile && (
          <div className={styles.contextSummary}>
            <span className={styles.modeDot} />
            <Text className={styles.summaryText}>{activeModeLabel}</Text>
            <Text className={styles.summaryModel}>{activeModelLabel}</Text>
          </div>
        )}
      </div>

      <div className={styles.headerRight}>
        <Space wrap>
          {isMobile && onOpenContextPanel && (
            <Tooltip title="打开对话设置">
              <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                <Button
                  icon={<SettingOutlined />}
                  onClick={onOpenContextPanel}
                  className={styles.actionButton}
                />
              </motion.div>
            </Tooltip>
          )}


          <Dropdown
            menu={{
              items: [
                {
                  key: 'history',
                  label: '对话历史',
                  icon: <HistoryOutlined />,
                  onClick: onOpenHistory,
                },
                { type: 'divider' },
                {
                  key: 'md',
                  label: '导出 Markdown',
                  icon: <ExportOutlined />,
                  onClick: () => handleExport('markdown'),
                  disabled: messageCount === 0,
                },
                {
                  key: 'json',
                  label: '导出 JSON',
                  icon: <ExportOutlined />,
                  onClick: () => handleExport('json'),
                  disabled: messageCount === 0,
                },
                { type: 'divider' },
                {
                  key: 'memory',
                  label: '管理记忆',
                  icon: <BulbOutlined />,
                  onClick: onOpenMemory,
                },
                {
                  key: 'clear',
                  label: '清空对话',
                  icon: <ClearOutlined />,
                  danger: true,
                  onClick: handleClear,
                  disabled: messageCount === 0,
                },
              ],
            }}
          >
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Button icon={<MoreOutlined />} className={styles.actionButton} />
            </motion.div>
          </Dropdown>
        </Space>
      </div>
    </motion.div>
  );
};

export default ChatHeader;
