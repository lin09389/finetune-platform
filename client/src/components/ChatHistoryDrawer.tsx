import { DeleteOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Drawer, Empty, Input, List, Space, Tag, Typography, message } from 'antd';
import { useState } from 'react';

interface Session {
  id: string;
  title: string;
  model_id?: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
  metadata?: Record<string, unknown>;
}

interface ChatHistoryDrawerProps {
  open: boolean;
  onClose: () => void;
  sessions: Session[];
  onLoadSession: (sessionId: string) => void;
  onLoadOutcome?: (sessionId: string, outcomeId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

const { Text } = Typography;

const ChatHistoryDrawer: React.FC<ChatHistoryDrawerProps> = ({
  open,
  onClose,
  sessions,
  onLoadSession,
  onLoadOutcome,
  onDeleteSession,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [selectedOutcomeIndexBySession, setSelectedOutcomeIndexBySession] = useState<
    Record<string, number>
  >({});

  const filteredSessions = sessions.filter((session) =>
    session.title.toLowerCase().includes(searchTerm.toLowerCase()),
  );
  const prioritizedSessions = [...filteredSessions].sort((left, right) => {
    const leftOutcomes = Array.isArray(left.metadata?.task_outcomes)
      ? left.metadata.task_outcomes.length
      : 0;
    const rightOutcomes = Array.isArray(right.metadata?.task_outcomes)
      ? right.metadata.task_outcomes.length
      : 0;

    if (rightOutcomes !== leftOutcomes) {
      return rightOutcomes - leftOutcomes;
    }

    return (
      new Date(right.updated_at || right.created_at || 0).getTime() -
      new Date(left.updated_at || left.created_at || 0).getTime()
    );
  });

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return '今天';
    if (days === 1) return '昨天';
    if (days < 7) return `${days}天前`;
    return date.toLocaleDateString('zh-CN');
  };

  return (
    <Drawer
      title="对话历史"
      placement="left"
      width={320}
      open={open}
      onClose={onClose}
      styles={{
        body: { padding: 0 },
      }}
    >
      <div style={{ padding: 16, borderBottom: '1px solid #f0f0f0' }}>
        <Input
          placeholder="搜索对话..."
          prefix={<SearchOutlined style={{ color: '#999' }} />}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          allowClear
        />
      </div>

      <div style={{ padding: 8 }}>
        {prioritizedSessions.length === 0 ? (
          searchTerm ? (
            <Empty description="没有找到匹配的对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <Empty description="暂无对话历史" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )
        ) : (
          <List
            dataSource={prioritizedSessions}
            renderItem={(session) => {
              const taskOutcomes = Array.isArray(session.metadata?.task_outcomes)
                ? session.metadata.task_outcomes
                : [];
              const selectedOutcomeIndex = selectedOutcomeIndexBySession[session.id] || 0;
              const selectedOutcome =
                taskOutcomes.length > 0 && typeof taskOutcomes[selectedOutcomeIndex] === 'object'
                  ? (taskOutcomes[selectedOutcomeIndex] as Record<string, unknown>)
                  : null;
              const latestOutcome =
                taskOutcomes.length > 0 && typeof taskOutcomes[0] === 'object'
                  ? (taskOutcomes[0] as Record<string, unknown>)
                  : null;

              return (
                <List.Item
                  onClick={() => onLoadSession(session.id)}
                  style={{
                    padding: '12px 16px',
                    marginBottom: 8,
                    borderRadius: 8,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    background: '#fff',
                    border: '1px solid #f0f0f0',
                  }}
                  actions={[
                    <Button
                      key="delete"
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        // 点击删除时立刻在本地状态列表中剔除，制造跟手感
                        onDeleteSession(session.id);
                        message.success('已删除对话');
                      }}
                    />,
                  ]}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = '#f5f5f5';
                    e.currentTarget.style.borderColor = '#d9d9d9';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = '#fff';
                    e.currentTarget.style.borderColor = '#f0f0f0';
                  }}
                >
                  <List.Item.Meta
                    title={
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <Text ellipsis style={{ maxWidth: 180, fontWeight: 500 }}>
                          {session.title}
                        </Text>
                        {session.message_count !== undefined && (
                          <Tag color="blue" style={{ marginLeft: 8 }}>
                            {session.message_count}条
                          </Tag>
                        )}
                      </div>
                    }
                    description={
                      <div style={{ fontSize: 12, color: '#999' }}>
                        {formatDate(session.updated_at || session.created_at)}
                        {session.model_id && (
                          <span style={{ marginLeft: 8 }}>· {session.model_id}</span>
                        )}
                        {latestOutcome ? (
                          <div style={{ marginTop: 6 }}>
                            <Space size={6} wrap>
                              <Tag color="gold">Pinned</Tag>
                              <Tag color="green">Outcome</Tag>
                              {taskOutcomes.length > 1 ? (
                                <Tag color="blue">{taskOutcomes.length} records</Tag>
                              ) : null}
                            </Space>
                            <div>
                              <Text
                                type="secondary"
                                ellipsis
                                style={{ maxWidth: 220, display: 'inline-block' }}
                              >
                                {String(
                                  latestOutcome.title ||
                                    latestOutcome.summary ||
                                    'Latest task outcome',
                                )}
                              </Text>
                            </div>
                            <Button
                              type="link"
                              size="small"
                              style={{ padding: 0, marginTop: 4 }}
                              onClick={(event) => {
                                event.stopPropagation();
                                setExpandedSessionId((current) =>
                                  current === session.id ? null : session.id,
                                );
                              }}
                            >
                              {expandedSessionId === session.id
                                ? 'Hide outcome'
                                : 'Preview outcome'}
                            </Button>
                            {expandedSessionId === session.id ? (
                              <div
                                style={{
                                  marginTop: 6,
                                  padding: 10,
                                  borderRadius: 10,
                                  background: 'rgba(82, 196, 26, 0.08)',
                                  border: '1px solid rgba(82, 196, 26, 0.18)',
                                }}
                              >
                                {taskOutcomes.length > 1 ? (
                                  <Space size={6} wrap style={{ marginBottom: 8 }}>
                                    {taskOutcomes.map((outcome, index) => {
                                      const typedOutcome =
                                        typeof outcome === 'object' && outcome
                                          ? (outcome as Record<string, unknown>)
                                          : null;
                                      return (
                                        <Button
                                          key={`${session.id}-outcome-${index}`}
                                          size="small"
                                          type={
                                            selectedOutcomeIndex === index ? 'primary' : 'default'
                                          }
                                          onClick={(event) => {
                                            event.stopPropagation();
                                            setSelectedOutcomeIndexBySession((current) => ({
                                              ...current,
                                              [session.id]: index,
                                            }));
                                          }}
                                        >
                                          {String(typedOutcome?.title || `Outcome ${index + 1}`)}
                                        </Button>
                                      );
                                    })}
                                  </Space>
                                ) : null}
                                <Text style={{ whiteSpace: 'pre-wrap' }}>
                                  {String(
                                    selectedOutcome?.summary ||
                                      selectedOutcome?.title ||
                                      latestOutcome.summary ||
                                      latestOutcome.title ||
                                      'Latest task outcome',
                                  )}
                                </Text>
                                {selectedOutcome &&
                                typeof selectedOutcome.id === 'string' &&
                                onLoadOutcome ? (
                                  <Button
                                    type="link"
                                    size="small"
                                    style={{ padding: 0, marginTop: 8 }}
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      onLoadOutcome(session.id, selectedOutcome.id as string);
                                    }}
                                  >
                                    Open this outcome
                                  </Button>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    }
                  />
                </List.Item>
              );
            }}
          />
        )}
      </div>
    </Drawer>
  );
};

export default ChatHistoryDrawer;
