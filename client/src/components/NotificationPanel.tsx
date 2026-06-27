import {
  BellOutlined,
  CheckCircleOutlined,
  CheckOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { Avatar, Badge, Button, Drawer, Empty, List, Space, Tag, Tooltip } from 'antd';
import { useCallback, useState } from 'react';

export interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  timestamp: number;
  read: boolean;
}

interface NotificationPanelProps {
  notifications: Notification[];
  onClear: () => void;
  onMarkAsRead: (id: string) => void;
  onDelete: (id: string) => void;
}

const getTypeConfig = (type: string) => {
  switch (type) {
    case 'success':
      return {
        color: 'var(--success)',
        bgColor: '#d1fae5',
        icon: <CheckCircleOutlined />,
        label: '成功',
      };
    case 'warning':
      return {
        color: 'var(--warning)',
        bgColor: '#fef3c7',
        icon: <ExclamationCircleOutlined />,
        label: '警告',
      };
    case 'error':
      return {
        color: '#ef4444',
        bgColor: '#fee2e2',
        icon: <CloseCircleOutlined />,
        label: '错误',
      };
    default:
      return {
        color: 'var(--accent-primary)',
        bgColor: '#dbeafe',
        icon: <InfoCircleOutlined />,
        label: '通知',
      };
  }
};

export const NotificationPanel: React.FC<NotificationPanelProps> = ({
  notifications,
  onClear,
  onMarkAsRead,
  onDelete,
}) => {
  const [visible, setVisible] = useState(false);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;
    if (days < 7) return `${days}天前`;
    return date.toLocaleDateString('zh-CN');
  };

  return (
    <>
      <Tooltip title="通知中心">
        <div
          onClick={() => setVisible(true)}
          style={{
            padding: '8px 12px',
            cursor: 'pointer',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            position: 'relative',
            transition: 'all 0.3s ease',
            background: 'transparent',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--bg-hover)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
          }}
        >
          <Badge
            count={unreadCount}
            overflowCount={99}
            style={{
              background: unreadCount > 0 ? 'var(--error)' : 'transparent',
              boxShadow: '0 2px 8px rgba(239, 68, 68, 0.4)',
            }}
          >
            <BellOutlined
              style={{
                fontSize: 18,
                color: unreadCount > 0 ? 'var(--error)' : 'var(--text-secondary)',
                transition: 'color 0.3s ease',
              }}
            />
          </Badge>
        </div>
      </Tooltip>

      <Drawer
        title={
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px 0',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: '8px',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-color)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '18px',
                  color: 'var(--text-primary)',
                }}
              >
                <BellOutlined />
              </div>
              <div>
                <div style={{ fontSize: '16px', fontWeight: 600 }}>通知中心</div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {unreadCount > 0 ? `${unreadCount} 条未读` : '全部已读'}
                </div>
              </div>
            </div>
            <Space>
              {notifications.length > 0 && (
                <>
                  <Button
                    size="small"
                    onClick={onClear}
                    icon={<CheckOutlined />}
                    style={{ borderRadius: '8px' }}
                  >
                    全部已读
                  </Button>
                  <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      onClear();
                      setVisible(false);
                    }}
                    style={{ borderRadius: '8px' }}
                  >
                    清空
                  </Button>
                </>
              )}
            </Space>
          </div>
        }
        placement="right"
        width={420}
        open={visible}
        onClose={() => setVisible(false)}
        styles={{
          body: { padding: '16px' },
          header: { borderBottom: '1px solid var(--border-color)' },
        }}
      >
        {notifications.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div>
                <p style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>暂无通知</p>
                <p style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                  当有新的系统消息时，会显示在这里
                </p>
              </div>
            }
            style={{ marginTop: 60 }}
          />
        ) : (
          <List
            dataSource={notifications}
            renderItem={(item, index) => {
              const config = getTypeConfig(item.type);
              return (
                <List.Item
                  className="notification-item"
                  style={{
                    background: item.read ? 'var(--bg-secondary)' : config.bgColor,
                    padding: '16px',
                    borderRadius: '12px',
                    marginBottom: 12,
                    cursor: 'pointer',
                    border: `1px solid ${item.read ? 'var(--border-color)' : config.color}20`,
                    transition: 'all 0.3s ease',
                    opacity: 0,
                    animation: `slideInRight 0.3s ease ${index * 0.05}s forwards`,
                  }}
                  onClick={() => onMarkAsRead(item.id)}
                  onMouseEnter={(e) => {
                    if (!item.read) {
                      e.currentTarget.style.background = config.bgColor;
                      e.currentTarget.style.transform = 'translateX(4px)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!item.read) {
                      e.currentTarget.style.background = config.bgColor;
                      e.currentTarget.style.transform = 'translateX(0)';
                    }
                  }}
                  actions={[
                    <Tooltip key="delete" title="删除">
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(item.id);
                        }}
                        style={{ borderRadius: '6px' }}
                      />
                    </Tooltip>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={
                      <Avatar
                        size={40}
                        icon={config.icon}
                        style={{
                          background: config.color,
                          color: 'var(--text-inverse)',
                        }}
                      />
                    }
                    title={
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: 4,
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 600,
                            fontSize: '14px',
                            color: 'var(--text-primary)',
                          }}
                        >
                          {item.title}
                        </span>
                        <span
                          style={{
                            fontSize: '11px',
                            color: 'var(--text-tertiary)',
                            fontWeight: 500,
                          }}
                        >
                          {formatTime(item.timestamp)}
                        </span>
                      </div>
                    }
                    description={
                      <div>
                        <Tag
                          color={config.color}
                          style={{
                            fontSize: '10px',
                            padding: '0 6px',
                            borderRadius: '4px',
                            marginBottom: 6,
                          }}
                        >
                          {config.label}
                        </Tag>
                        <div
                          style={{
                            color: 'var(--text-secondary)',
                            fontSize: '13px',
                            lineHeight: 1.5,
                          }}
                        >
                          {item.message}
                        </div>
                      </div>
                    }
                  />
                </List.Item>
              );
            }}
          />
        )}
      </Drawer>

      <style>{`
        @keyframes slideInRight {
          from {
            opacity: 0;
            transform: translateX(20px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        
        .notification-item {
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .notification-item:hover {
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }
      `}</style>
    </>
  );
};

// 简单的通知管理 Hook
export const useNotifications = () => {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  const addNotification = useCallback(
    (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => {
      const newNotification: Notification = {
        ...notification,
        id: Date.now().toString(),
        timestamp: Date.now(),
        read: false,
      };
      setNotifications((prev) => [newNotification, ...prev].slice(0, 100));
      return newNotification.id;
    },
    []
  );

  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
  }, []);

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const deleteNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  return {
    notifications,
    addNotification,
    markAsRead,
    markAllAsRead,
    deleteNotification,
    clearAll,
  };
};
