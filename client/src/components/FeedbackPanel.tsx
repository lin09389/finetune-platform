import {
  BarChartOutlined,
  BugOutlined,
  BulbOutlined,
  CommentOutlined,
  DislikeOutlined,
  LikeOutlined,
  SendOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  message,
  Rate,
  Row,
  Select,
  Statistic,
  Tabs,
  Tag,
} from 'antd';
import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/api';

const { TextArea } = Input;
const { Option } = Select;

interface FeedbackStats {
  total_feedback: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  avg_rating: number;
  intent_accuracy: number;
  execution_success_rate: number;
  category_breakdown: Record<string, number>;
  common_issues: string[];
}

interface FeedbackItem {
  feedback_id: string;
  feedback_type: string;
  category: string;
  rating: number;
  comment: string;
  action: string;
  timestamp: string;
}

interface IntentCorrection {
  feedback_id: string;
  detected_intent: string;
  correct_intent: string;
  action: string;
  comment: string;
  timestamp: string;
}

interface ImprovementSuggestion {
  feedback_id: string;
  action: string;
  suggestion: string;
  timestamp: string;
}

const FeedbackPanel: React.FC = () => {
  const [feedbackType, setFeedbackType] = useState<string>('positive');
  const [category, setCategory] = useState<string>('execution_result');
  const [rating, setRating] = useState<number>(5);
  const [comment, setComment] = useState<string>('');
  const [action, setAction] = useState<string>('');
  const [intentDetected, setIntentDetected] = useState<string>('');
  const [intentCorrect, setIntentCorrect] = useState<boolean | undefined>(undefined);
  const [suggestedIntent, setSuggestedIntent] = useState<string>('');
  const [suggestedImprovement, setSuggestedImprovement] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [recentFeedbacks, setRecentFeedbacks] = useState<FeedbackItem[]>([]);
  const [corrections, setCorrections] = useState<IntentCorrection[]>([]);
  const [suggestions, setSuggestions] = useState<ImprovementSuggestion[]>([]);
  const [activeTab, setActiveTab] = useState<string>('submit');

  useEffect(() => {
    loadStats();
    loadRecentFeedbacks();
    loadCorrections();
    loadSuggestions();
  }, []);

  const loadStats = async () => {
    try {
      const response = await apiClient.get<FeedbackStats>('/feedback/stats');
      setStats(response.data);
    } catch {
      setStats(null);
    }
  };

  const loadRecentFeedbacks = async () => {
    try {
      const response = await apiClient.get<{ feedbacks: FeedbackItem[] }>(
        '/feedback/recent?limit=20',
      );
      setRecentFeedbacks(response.data.feedbacks || []);
    } catch {
      setRecentFeedbacks([]);
    }
  };

  const loadCorrections = async () => {
    try {
      const response = await apiClient.get<IntentCorrection[]>('/feedback/corrections');
      setCorrections(response.data);
    } catch {
      setCorrections([]);
    }
  };

  const loadSuggestions = async () => {
    try {
      const response = await apiClient.get<ImprovementSuggestion[]>('/feedback/suggestions');
      setSuggestions(response.data);
    } catch {
      setSuggestions([]);
    }
  };

  const handleSubmit = async () => {
    if (!comment.trim() && !suggestedImprovement.trim()) {
      message.warning('请填写反馈内容或改进建议');
      return;
    }

    setSubmitting(true);
    try {
      await apiClient.post('/feedback/submit', {
        feedback_type: feedbackType,
        category: category,
        rating: rating,
        comment: comment,
        action: action,
        intent_detected: intentDetected,
        intent_correct: intentCorrect,
        suggested_intent: suggestedIntent,
        suggested_improvement: suggestedImprovement,
      });

      message.success('感谢您的反馈！');

      setComment('');
      setAction('');
      setIntentDetected('');
      setIntentCorrect(undefined);
      setSuggestedIntent('');
      setSuggestedImprovement('');
      setRating(5);

      loadStats();
      loadRecentFeedbacks();
    } catch (error) {
      message.error('提交失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const feedbackTypeOptions = [
    { value: 'positive', label: '正面反馈', icon: <LikeOutlined style={{ color: 'var(--success)' }} /> },
    {
      value: 'negative',
      label: '负面反馈',
      icon: <DislikeOutlined style={{ color: 'var(--error)' }} />,
    },
    { value: 'neutral', label: '中性反馈', icon: <CommentOutlined /> },
    { value: 'bug_report', label: '错误报告', icon: <BugOutlined style={{ color: 'var(--warning)' }} /> },
    {
      value: 'feature_request',
      label: '功能请求',
      icon: <BulbOutlined style={{ color: 'var(--accent-primary)' }} />,
    },
    {
      value: 'improvement',
      label: '改进建议',
      icon: <BulbOutlined style={{ color: 'var(--accent-tertiary)' }} />,
    },
  ];

  const categoryOptions = [
    { value: 'intent_detection', label: '意图检测' },
    { value: 'execution_result', label: '执行结果' },
    { value: 'error_message', label: '错误信息' },
    { value: 'user_experience', label: '用户体验' },
    { value: 'performance', label: '性能表现' },
    { value: 'safety', label: '安全性' },
    { value: 'other', label: '其他' },
  ];

  const getFeedbackTypeTag = (type: string) => {
    const colors: Record<string, string> = {
      positive: 'success',
      negative: 'error',
      neutral: 'default',
      bug_report: 'warning',
      feature_request: 'processing',
      improvement: 'purple',
    };
    return (
      <Tag color={colors[type] || 'default'}>
        {feedbackTypeOptions.find((o) => o.value === type)?.label || type}
      </Tag>
    );
  };

  return (
    <div style={{ padding: '24px' }}>
      <h2 style={{ marginBottom: '24px' }}>用户反馈</h2>

      {stats && (
        <Card style={{ marginBottom: '24px' }}>
          <Row gutter={16}>
            <Col span={4}>
              <Statistic title="总反馈数" value={stats.total_feedback} />
            </Col>
            <Col span={4}>
              <Statistic
                title="正面反馈"
                value={stats.positive_count}
                valueStyle={{ color: 'var(--success)' }}
              />
            </Col>
            <Col span={4}>
              <Statistic
                title="负面反馈"
                value={stats.negative_count}
                valueStyle={{ color: 'var(--error)' }}
              />
            </Col>
            <Col span={4}>
              <Statistic title="平均评分" value={stats.avg_rating} suffix="/ 5" />
            </Col>
            <Col span={4}>
              <Statistic title="意图准确率" value={stats.intent_accuracy} suffix="%" />
            </Col>
            <Col span={4}>
              <Statistic title="执行成功率" value={stats.execution_success_rate} suffix="%" />
            </Col>
          </Row>
        </Card>
      )}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'submit',
            label: '提交反馈',
            icon: <SendOutlined />,
            children: (
              <Card>
                <div style={{ maxWidth: '600px' }}>
                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', marginBottom: '8px' }}>反馈类型</label>
                    <Select
                      value={feedbackType}
                      onChange={setFeedbackType}
                      style={{ width: '100%' }}
                    >
                      {feedbackTypeOptions.map((opt) => (
                        <Option key={opt.value} value={opt.value}>
                          {opt.icon} {opt.label}
                        </Option>
                      ))}
                    </Select>
                  </div>

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', marginBottom: '8px' }}>反馈类别</label>
                    <Select value={category} onChange={setCategory} style={{ width: '100%' }}>
                      {categoryOptions.map((opt) => (
                        <Option key={opt.value} value={opt.value}>
                          {opt.label}
                        </Option>
                      ))}
                    </Select>
                  </div>

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', marginBottom: '8px' }}>评分</label>
                    <Rate value={rating} onChange={setRating} />
                  </div>

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', marginBottom: '8px' }}>
                      相关操作（可选）
                    </label>
                    <Input
                      placeholder="例如：读取文件、截图等"
                      value={action}
                      onChange={(e) => setAction(e.target.value)}
                    />
                  </div>

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', marginBottom: '8px' }}>反馈内容</label>
                    <TextArea
                      rows={4}
                      placeholder="请详细描述您的反馈..."
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                    />
                  </div>

                  {category === 'intent_detection' && (
                    <>
                      <div style={{ marginBottom: '16px' }}>
                        <label style={{ display: 'block', marginBottom: '8px' }}>
                          检测到的意图
                        </label>
                        <Input
                          placeholder="系统检测到的意图"
                          value={intentDetected}
                          onChange={(e) => setIntentDetected(e.target.value)}
                        />
                      </div>
                      <div style={{ marginBottom: '16px' }}>
                        <label style={{ display: 'block', marginBottom: '8px' }}>
                          意图是否正确？
                        </label>
                        <Select
                          value={intentCorrect}
                          onChange={setIntentCorrect}
                          style={{ width: '100%' }}
                          allowClear
                        >
                          <Option value={true}>正确</Option>
                          <Option value={false}>错误</Option>
                        </Select>
                      </div>
                      {intentCorrect === false && (
                        <div style={{ marginBottom: '16px' }}>
                          <label style={{ display: 'block', marginBottom: '8px' }}>
                            正确的意图应该是
                          </label>
                          <Input
                            placeholder="请输入正确的意图"
                            value={suggestedIntent}
                            onChange={(e) => setSuggestedIntent(e.target.value)}
                          />
                        </div>
                      )}
                    </>
                  )}

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', marginBottom: '8px' }}>
                      改进建议（可选）
                    </label>
                    <TextArea
                      rows={2}
                      placeholder="您有什么改进建议？"
                      value={suggestedImprovement}
                      onChange={(e) => setSuggestedImprovement(e.target.value)}
                    />
                  </div>

                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSubmit}
                    loading={submitting}
                  >
                    提交反馈
                  </Button>
                </div>
              </Card>
            ),
          },
          {
            key: 'recent',
            label: '最近反馈',
            icon: <CommentOutlined />,
            children: (
              <Card>
                <List
                  dataSource={recentFeedbacks}
                  locale={{ emptyText: <Empty description="暂无反馈记录" /> }}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        avatar={getFeedbackTypeTag(item.feedback_type)}
                        title={`${item.action || '通用反馈'} - ${item.rating} 星`}
                        description={item.comment || '无详细内容'}
                      />
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {new Date(item.timestamp).toLocaleString()}
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            ),
          },
          {
            key: 'corrections',
            label: '意图纠正',
            icon: <BarChartOutlined />,
            children: (
              <Card>
                <List
                  dataSource={corrections}
                  locale={{ emptyText: <Empty description="暂无纠正记录" /> }}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        title={
                          <span>
                            <Tag color="error">{item.detected_intent}</Tag>→
                            <Tag color="success">{item.correct_intent}</Tag>
                          </span>
                        }
                        description={item.comment || `操作: ${item.action}`}
                      />
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {new Date(item.timestamp).toLocaleString()}
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            ),
          },
          {
            key: 'suggestions',
            label: '改进建议',
            icon: <BulbOutlined />,
            children: (
              <Card>
                <List
                  dataSource={suggestions}
                  locale={{ emptyText: <Empty description="暂无改进建议" /> }}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta
                        title={item.suggestion}
                        description={`相关操作: ${item.action || '无'}`}
                      />
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {new Date(item.timestamp).toLocaleString()}
                      </div>
                    </List.Item>
                  )}
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
};

export default FeedbackPanel;
