import {
  ClockCircleOutlined,
  CopyOutlined,
  DownloadOutlined,
  EyeOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Space, Spin, Tag, Typography, message } from 'antd';
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';

const { Title, Text, Paragraph } = Typography;

interface SharedMessage {
  id: string;
  role: string;
  content: string;
  timestamp: string;
}

interface SharedChat {
  share_id: string;
  session_id: string;
  title: string;
  messages: SharedMessage[];
  created_at: string;
  expires_at: string | null;
  view_count: number;
  is_public: boolean;
}

const SharedChatPage: React.FC = () => {
  const { shareId } = useParams<{ shareId: string }>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [share, setShare] = useState<SharedChat | null>(null);

  useEffect(() => {
    if (!shareId) {
      setError('无效的分享链接');
      setLoading(false);
      return;
    }

    const fetchShare = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/chat/share/${shareId}`);
        if (!response.ok) {
          if (response.status === 404) {
            setError('分享不存在或已过期');
          } else if (response.status === 410) {
            setError('分享链接已过期');
          } else {
            setError('加载失败');
          }
          return;
        }

        const data = await response.json();
        setShare(data);
      } catch {
        setError('加载失败，请检查网络连接');
      } finally {
        setLoading(false);
      }
    };

    void fetchShare();
  }, [shareId]);

  const handleExportMarkdown = async () => {
    if (!shareId) return;

    try {
      const response = await fetch(`${API_BASE_URL}/chat/share/${shareId}/markdown`);
      if (!response.ok) {
        message.error('导出失败');
        return;
      }

      const text = await response.text();
      const blob = new Blob([text], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${share?.title || 'chat'}.md`;
      link.click();
      URL.revokeObjectURL(url);
      message.success('已导出 Markdown');
    } catch {
      message.error('导出失败');
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      message.success('链接已复制');
    } catch {
      message.error('复制失败');
    }
  };

  const renderMessage = (msg: SharedMessage, index: number) => {
    const isUser = msg.role === 'user';

    return (
      <div
        key={msg.id || index}
        style={{
          display: 'flex',
          justifyContent: isUser ? 'flex-end' : 'flex-start',
          marginBottom: 16,
        }}
      >
        <Card
          size="small"
          style={{
            maxWidth: '80%',
            background: isUser ? '#e6f7ff' : '#fff',
            borderRadius: 12,
          }}
        >
          <div style={{ marginBottom: 8 }}>
            <Tag color={isUser ? 'blue' : 'green'}>{isUser ? '用户' : '助手'}</Tag>
            {msg.timestamp && (
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                {new Date(msg.timestamp).toLocaleString('zh-CN')}
              </Text>
            )}
          </div>
          <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.content}</Paragraph>
        </Card>
      </div>
    );
  };

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          padding: 24,
        }}
      >
        <Alert
          message="加载失败"
          description={error}
          type="error"
          showIcon
          style={{ maxWidth: 400 }}
        />
      </div>
    );
  }

  if (!share) {
    return null;
  }

  return (
    <div
      style={{
        maxWidth: 900,
        margin: '0 auto',
        padding: 24,
        background: '#f5f5f5',
        minHeight: '100vh',
      }}
    >
      <Card style={{ marginBottom: 24 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <div>
            <Title level={3} style={{ margin: 0 }}>
              {share.title}
            </Title>
            <Space style={{ marginTop: 8 }} wrap>
              <Text type="secondary">
                <ClockCircleOutlined style={{ marginRight: 4 }} />
                {new Date(share.created_at).toLocaleString('zh-CN')}
              </Text>
              <Text type="secondary">
                <EyeOutlined style={{ marginRight: 4 }} />
                {share.view_count} 次浏览
              </Text>
              {share.expires_at && (
                <Tag color="orange">
                  过期时间：{new Date(share.expires_at).toLocaleString('zh-CN')}
                </Tag>
              )}
            </Space>
          </div>
          <Space wrap>
            <Button icon={<CopyOutlined />} onClick={handleCopyLink}>
              复制链接
            </Button>
            <Button icon={<DownloadOutlined />} onClick={handleExportMarkdown}>
              导出 Markdown
            </Button>
          </Space>
        </div>
      </Card>

      <Card>
        <div style={{ padding: '8px 0' }}>
          {share.messages.map((msg, index) => renderMessage(msg, index))}
        </div>
      </Card>

      <div
        style={{
          textAlign: 'center',
          marginTop: 24,
          color: 'var(--text-secondary)',
          fontSize: 12,
        }}
      >
        <ShareAltOutlined style={{ marginRight: 4 }} />由 Finetune Platform 分享
      </div>
    </div>
  );
};

export default SharedChatPage;
