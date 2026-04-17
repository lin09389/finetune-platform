import {
  BookOutlined,
  BugOutlined,
  QuestionCircleOutlined,
  RocketOutlined,
  SearchOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Card, Collapse, Empty, Input, List, Space, Tabs, Tag, Tooltip, Typography } from 'antd';
import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/api';

const { Search } = Input;
const { Panel } = Collapse;
const { Text, Paragraph } = Typography;

interface CommandHelp {
  command: string;
  description: string;
  examples: string[];
  parameters: Record<string, string>;
  tips: string[];
  related_commands: string[];
}

interface HelpOverview {
  categories: Record<string, string[]>;
  total_commands: number;
}

interface SearchResult {
  command: string;
  description: string;
}

const categoryIcons: Record<string, React.ReactNode> = {
  文件操作: <ToolOutlined />,
  屏幕操作: <RocketOutlined />,
  应用操作: <ToolOutlined />,
  快速入门: <BookOutlined />,
  故障排除: <BugOutlined />,
};

const categoryColors: Record<string, string> = {
  文件操作: 'blue',
  屏幕操作: 'green',
  应用操作: 'purple',
  快速入门: 'orange',
  故障排除: 'red',
};

const HelpPanel: React.FC = () => {
  const [overview, setOverview] = useState<HelpOverview | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [selectedCommand, setSelectedCommand] = useState<CommandHelp | null>(null);
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadOverview();
  }, []);

  const loadOverview = async () => {
    try {
      const response = await apiClient.get<HelpOverview>('/help');
      setOverview(response.data);
    } catch (error) {
      console.error('加载帮助概览失败:', error);
    }
  };

  const handleSearch = async (keyword: string) => {
    if (!keyword.trim()) {
      setSearchResults([]);
      return;
    }

    setLoading(true);
    try {
      const response = await apiClient.get<SearchResult[]>('/help/search', {
        params: { q: keyword, limit: 10 },
      });
      setSearchResults(response.data);
    } catch (error) {
      console.error('搜索失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadCommandHelp = async (command: string) => {
    try {
      const response = await apiClient.get<CommandHelp>(
        `/help/command/${encodeURIComponent(command)}`,
      );
      setSelectedCommand(response.data);
      setActiveTab('detail');
    } catch (error) {
      console.error('加载命令帮助失败:', error);
    }
  };

  return (
    <div style={{ padding: '24px' }}>
      <h2 style={{ marginBottom: '24px' }}>
        <QuestionCircleOutlined style={{ marginRight: '8px' }} />
        帮助中心
      </h2>

      <Card style={{ marginBottom: '24px' }}>
        <Search
          placeholder="搜索命令或关键词..."
          allowClear
          enterButton={
            <>
              <SearchOutlined /> 搜索
            </>
          }
          size="large"
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          onSearch={handleSearch}
          loading={loading}
        />
        {searchResults.length > 0 && (
          <List
            style={{ marginTop: '16px' }}
            dataSource={searchResults}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => loadCommandHelp(item.command)}
              >
                <List.Item.Meta
                  title={
                    <>
                      <Tag color="blue">{item.command}</Tag>
                    </>
                  }
                  description={item.description}
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'overview',
            label: '命令概览',
            icon: <BookOutlined />,
            children: (
              <Card>
                {overview ? (
                  <Collapse accordion>
                    {Object.entries(overview.categories).map(([name, commands]) => (
                      <Panel
                        header={
                          <span>
                            {categoryIcons[name] || <ToolOutlined />}
                            <span style={{ marginLeft: '8px' }}>{name}</span>
                            <Tag
                              color={categoryColors[name] || 'default'}
                              style={{ marginLeft: '8px' }}
                            >
                              {commands.length} 个命令
                            </Tag>
                          </span>
                        }
                        key={name}
                      >
                        <List
                          dataSource={commands}
                          renderItem={(cmd) => (
                            <List.Item
                              style={{ cursor: 'pointer', padding: '8px 0' }}
                              onClick={() => loadCommandHelp(cmd)}
                            >
                              <Text code>{cmd}</Text>
                            </List.Item>
                          )}
                        />
                      </Panel>
                    ))}
                  </Collapse>
                ) : (
                  <Empty description="加载中..." />
                )}
              </Card>
            ),
          },
          {
            key: 'detail',
            label: '命令详情',
            icon: <ToolOutlined />,
            children: selectedCommand ? (
              <Card>
                <h3 style={{ marginBottom: '16px' }}>
                  <Tag color="blue" style={{ fontSize: '16px', padding: '4px 12px' }}>
                    {selectedCommand.command}
                  </Tag>
                </h3>

                <Paragraph style={{ fontSize: '16px', marginBottom: '24px' }}>
                  {selectedCommand.description}
                </Paragraph>

                <Card title="使用示例" size="small" style={{ marginBottom: '16px' }}>
                  <List
                    dataSource={selectedCommand.examples}
                    renderItem={(example) => (
                      <List.Item>
                        <Text code style={{ fontSize: '14px' }}>
                          {example}
                        </Text>
                      </List.Item>
                    )}
                  />
                </Card>

                {Object.keys(selectedCommand.parameters).length > 0 && (
                  <Card title="参数说明" size="small" style={{ marginBottom: '16px' }}>
                    <List
                      dataSource={Object.entries(selectedCommand.parameters)}
                      renderItem={([param, desc]) => (
                        <List.Item>
                          <Text strong>{param}:</Text>
                          <Text type="secondary" style={{ marginLeft: '8px' }}>
                            {desc}
                          </Text>
                        </List.Item>
                      )}
                    />
                  </Card>
                )}

                {selectedCommand.tips.length > 0 && (
                  <Card title="使用提示" size="small" style={{ marginBottom: '16px' }}>
                    <List
                      dataSource={selectedCommand.tips}
                      renderItem={(tip) => (
                        <List.Item>
                          <Text type="success">💡 {tip}</Text>
                        </List.Item>
                      )}
                    />
                  </Card>
                )}

                {selectedCommand.related_commands.length > 0 && (
                  <Card title="相关命令" size="small">
                    <Space wrap>
                      {selectedCommand.related_commands.map((cmd) => (
                        <Tooltip key={cmd} title="点击查看详情">
                          <Tag
                            color="blue"
                            style={{ cursor: 'pointer' }}
                            onClick={() => loadCommandHelp(cmd)}
                          >
                            {cmd}
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  </Card>
                )}
              </Card>
            ) : (
              <Card>
                <Empty description="请从左侧选择一个命令查看详情" />
              </Card>
            ),
          },
          {
            key: 'quickstart',
            label: '快速入门',
            icon: <RocketOutlined />,
            children: (
              <Card>
                <Typography>
                  <h3>欢迎使用本地电脑操作助手！</h3>
                  <Paragraph>这个助手可以帮助您通过自然语言控制电脑，执行各种操作。</Paragraph>

                  <h4>基本使用</h4>
                  <ol>
                    <li>
                      <Text strong>直接说出您想做的事情</Text>
                      <br />
                      <Text type="secondary">例如："读取 test.txt"、"创建一个新文件"、"截图"</Text>
                    </li>
                    <li>
                      <Text strong>系统会自动理解您的意图</Text>
                      <br />
                      <Text type="secondary">系统会分析您的输入，识别操作类型并提取参数</Text>
                    </li>
                    <li>
                      <Text strong>确认后执行</Text>
                      <br />
                      <Text type="secondary">危险操作需要您确认，执行结果会实时反馈</Text>
                    </li>
                  </ol>

                  <h4>安全说明</h4>
                  <Paragraph>为了保护您的数据安全，系统有以下限制：</Paragraph>
                  <ul>
                    <li>只能访问安全路径（桌面、文档、下载、工作目录）</li>
                    <li>敏感文件（如 .env, .key）需要额外确认</li>
                    <li>危险操作（如删除文件）会移动到回收站</li>
                  </ul>

                  <h4>获取帮助</h4>
                  <ul>
                    <li>说 "帮助" 查看所有可用命令</li>
                    <li>说 "帮助 文件操作" 查看特定类别的帮助</li>
                    <li>说 "如何读取文件" 获取具体操作指南</li>
                  </ul>
                </Typography>
              </Card>
            ),
          },
          {
            key: 'troubleshooting',
            label: '故障排除',
            icon: <BugOutlined />,
            children: (
              <Card>
                <Typography>
                  <h3>常见问题</h3>

                  <h4>文件操作问题</h4>
                  <Collapse accordion>
                    <Panel header="文件不存在" key="file_not_found">
                      <Paragraph>
                        <strong>问题：</strong>提示"文件不存在"
                        <br />
                        <strong>解决：</strong>
                      </Paragraph>
                      <ul>
                        <li>检查文件名是否正确，注意大小写</li>
                        <li>使用"列出文件"查看目录内容</li>
                        <li>确认文件路径是否正确</li>
                      </ul>
                    </Panel>
                    <Panel header="权限不足" key="permission_denied">
                      <Paragraph>
                        <strong>问题：</strong>提示"无法访问文件"
                        <br />
                        <strong>解决：</strong>
                      </Paragraph>
                      <ul>
                        <li>检查文件是否被其他程序打开</li>
                        <li>确认您有访问该文件的权限</li>
                        <li>尝试关闭可能占用文件的应用</li>
                      </ul>
                    </Panel>
                    <Panel header="路径不安全" key="unsafe_path">
                      <Paragraph>
                        <strong>问题：</strong>提示"安全限制"
                        <br />
                        <strong>解决：</strong>
                      </Paragraph>
                      <ul>
                        <li>只能访问安全路径内的文件</li>
                        <li>将文件移动到桌面、文档或下载目录</li>
                      </ul>
                    </Panel>
                  </Collapse>

                  <h4 style={{ marginTop: '24px' }}>意图识别问题</h4>
                  <Collapse accordion>
                    <Panel header="意图识别错误" key="intent_error">
                      <Paragraph>
                        <strong>问题：</strong>系统误解了我的意思
                        <br />
                        <strong>解决：</strong>
                      </Paragraph>
                      <ul>
                        <li>使用更明确的表述</li>
                        <li>提供完整的参数信息</li>
                        <li>使用"反馈"功能报告问题</li>
                      </ul>
                    </Panel>
                  </Collapse>
                </Typography>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
};

export default HelpPanel;
