import {
  CheckCircleOutlined,
  ClearOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CodeOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Input,
  InputNumber,
  message,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { API_BASE_URL, apiClient } from '../services/api';
import CodeBlock from './CodeBlock';

const { Text } = Typography;
const { TextArea } = Input;

interface Language {
  id: string;
  name: string;
  extension: string;
  description: string;
  available: boolean;
  version: string | null;
}

interface ExecuteResult {
  success: boolean;
  stdout: string;
  stderr: string;
  exit_code: number;
  execution_time: number;
  memory_used_mb: number;
  error: string | null;
  language: string;
  timestamp: string;
}

const DEFAULT_CODE: Record<string, string> = {
  python: `# Python 示例代码
import sys

print("Hello, World!")
print(f"Python 版本: {sys.version}")

# 计算斐波那契数列
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

for i in range(10):
    print(f"F({i}) = {fibonacci(i)}")
`,
  javascript: `// JavaScript 示例代码
console.log("Hello, World!");
console.log("Node.js 版本:", process.version);

// 计算斐波那契数列
function fibonacci(n) {
  if (n <= 1) return n;
  return fibonacci(n-1) + fibonacci(n-2);
}

for (let i = 0; i < 10; i++) {
  console.log(\`F(\${i}) = \${fibonacci(i)}\`);
}
`,
  typescript: `// TypeScript 示例代码
function greet(name: string): string {
  return \`Hello, \${name}!\`;
}

console.log(greet("World"));

// 计算斐波那契数列
function fibonacci(n: number): number {
  if (n <= 1) return n;
  return fibonacci(n-1) + fibonacci(n-2);
}

for (let i = 0; i < 10; i++) {
  console.log(\`F(\${i}) = \${fibonacci(i)}\`);
}
`,
};

const CodeExecutor: React.FC = () => {
  const [code, setCode] = useState<string>(DEFAULT_CODE['python'] || '');
  const [language, setLanguage] = useState<string>('python');
  const [timeout, setTimeout] = useState<number>(30);
  const [memoryLimit, setMemoryLimit] = useState<number>(256);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [languages, setLanguages] = useState<Language[]>([]);
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [stdin, setStdin] = useState<string>('');
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchLanguages = useCallback(async () => {
    try {
      const response = await apiClient.get('/code/languages');
      setLanguages(response.data.languages || []);
    } catch {
      setLanguages([]);
    }
  }, []);

  useEffect(() => {
    fetchLanguages();
  }, [fetchLanguages]);

  const handleLanguageChange = (newLanguage: string) => {
    setLanguage(newLanguage);
    if (!code || code === DEFAULT_CODE[language]) {
      setCode(DEFAULT_CODE[newLanguage] || '');
    }
    setResult(null);
  };

  const handleExecute = useCallback(async () => {
    if (!code.trim()) {
      message.warning('请输入要执行的代码');
      return;
    }

    const selectedLang = languages.find((l) => l.id === language);
    if (selectedLang && !selectedLang.available) {
      message.error(`${selectedLang.name} 环境不可用`);
      return;
    }

    setLoading(true);
    setResult(null);
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_BASE_URL}/code/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          code,
          language,
          timeout,
          memory_limit_mb: memoryLimit,
          stdin: stdin || null,
        }),
        signal: abortControllerRef.current.signal,
      });

      const data = await response.json();
      setResult(data);

      if (data.success) {
        message.success('代码执行成功');
      } else {
        message.warning('代码执行完成，但有错误');
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        message.info('执行已取消');
      } else {
        const errorMessage = error instanceof Error && error.message ? error.message : '未知错误';
        message.error(`执行失败: ${errorMessage}`);
      }
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }, [code, language, timeout, memoryLimit, stdin, languages]);

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  const handleClear = useCallback(() => {
    setCode('');
    setResult(null);
    setStdin('');
  }, []);

  const handleClearResult = useCallback(() => {
    setResult(null);
  }, []);

  const formatExecutionTime = (seconds: number): string => {
    if (seconds < 1) {
      return `${(seconds * 1000).toFixed(0)}ms`;
    }
    return `${seconds.toFixed(2)}s`;
  };

  const currentLanguageInfo = languages.find((l) => l.id === language);

  return (
    <div
      className="code-executor"
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
    >
      <Card
        title={
          <Space>
            <CodeOutlined />
            <span>代码执行沙箱</span>
          </Space>
        }
        extra={
          <Space>
            <Select
              value={language}
              onChange={handleLanguageChange}
              style={{ width: 150 }}
              options={languages.map((l) => ({
                value: l.id,
                label: (
                  <Space>
                    <span>{l.name}</span>
                    {!l.available && <Tag color="red">不可用</Tag>}
                  </Space>
                ),
                disabled: !l.available,
              }))}
            />
            <Tooltip title="设置">
              <Button
                type={showSettings ? 'primary' : 'text'}
                icon={<SettingOutlined />}
                onClick={() => setShowSettings(!showSettings)}
              />
            </Tooltip>
          </Space>
        }
        style={{ height: '100%', display: 'flex', flexDirection: 'column' }}
        styles={{
          body: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
        }}
      >
        <div
          style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden' }}
        >
          {showSettings && (
            <Card size="small" style={{ background: 'var(--bg-secondary)' }}>
              <Space wrap>
                <Space>
                  <Text type="secondary">超时时间:</Text>
                  <InputNumber
                    value={timeout}
                    onChange={(v) => setTimeout(v || 30)}
                    min={1}
                    max={300}
                    step={5}
                    addonAfter="秒"
                    style={{ width: 100 }}
                  />
                </Space>
                <Space>
                  <Text type="secondary">内存限制:</Text>
                  <InputNumber
                    value={memoryLimit}
                    onChange={(v) => setMemoryLimit(v || 256)}
                    min={64}
                    max={2048}
                    step={64}
                    addonAfter="MB"
                    style={{ width: 120 }}
                  />
                </Space>
                {currentLanguageInfo?.version && (
                  <Tag color="blue">{currentLanguageInfo.version}</Tag>
                )}
              </Space>
            </Card>
          )}

          <div
            style={{ flex: '1 1 50%', display: 'flex', flexDirection: 'column', minHeight: 200 }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <Text strong>代码编辑器</Text>
              <Space>
                <Button size="small" onClick={() => setCode(DEFAULT_CODE[language] || '')}>
                  重置示例
                </Button>
                <Button size="small" icon={<ClearOutlined />} onClick={handleClear}>
                  清空
                </Button>
              </Space>
            </div>
            <TextArea
              value={code}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setCode(e.target.value)}
              placeholder={`输入 ${language} 代码...`}
              style={{
                flex: 1,
                fontFamily: 'var(--font-mono)',
                fontSize: 13,
                lineHeight: 1.6,
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 8,
                resize: 'none',
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                标准输入 (可选)
              </Text>
              <TextArea
                value={stdin}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setStdin(e.target.value)}
                placeholder="输入标准输入数据..."
                rows={2}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 8,
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'center', gap: 12, padding: '8px 0' }}>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleExecute}
              loading={loading}
              disabled={!code.trim()}
              size="large"
            >
              执行代码
            </Button>
            {loading && (
              <Button icon={<StopOutlined />} onClick={handleStop} danger size="large">
                停止
              </Button>
            )}
          </div>

          {loading && (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <Spin size="large" />
              <div style={{ marginTop: 12, color: 'var(--text-secondary)' }}>正在执行代码...</div>
            </div>
          )}

          {result && !loading && (
            <div
              style={{ flex: '1 1 50%', display: 'flex', flexDirection: 'column', minHeight: 200 }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 8,
                }}
              >
                <Space>
                  {result.success ? (
                    <Tag icon={<CheckCircleOutlined />} color="success">
                      执行成功
                    </Tag>
                  ) : (
                    <Tag icon={<CloseCircleOutlined />} color="error">
                      执行失败
                    </Tag>
                  )}
                  <Tag icon={<ClockCircleOutlined />}>
                    {formatExecutionTime(result.execution_time)}
                  </Tag>
                  {result.exit_code !== 0 && <Tag color="warning">退出码: {result.exit_code}</Tag>}
                </Space>
                <Button size="small" icon={<ClearOutlined />} onClick={handleClearResult}>
                  清除结果
                </Button>
              </div>

              {result.error && (
                <Alert
                  message="执行错误"
                  description={result.error}
                  type="error"
                  showIcon
                  style={{ marginBottom: 12 }}
                />
              )}

              {result.stdout && (
                <div style={{ marginBottom: 12 }}>
                  <Text strong style={{ marginBottom: 8, display: 'block' }}>
                    标准输出
                  </Text>
                  <CodeBlock
                    code={result.stdout}
                    language="text"
                    showLineNumbers={false}
                    maxHeight={200}
                  />
                </div>
              )}

              {result.stderr && (
                <div>
                  <Text strong style={{ marginBottom: 8, display: 'block', color: 'var(--error)' }}>
                    标准错误
                  </Text>
                  <CodeBlock
                    code={result.stderr}
                    language="text"
                    showLineNumbers={false}
                    maxHeight={150}
                  />
                </div>
              )}

              {!result.stdout && !result.stderr && !result.error && result.success && (
                <Alert message="代码执行成功，但没有输出" type="info" showIcon />
              )}
            </div>
          )}
        </div>
      </Card>

      <style>{`
        .code-executor .ant-input:focus,
        .code-executor .ant-input-focused {
          border-color: var(--accent-primary);
          box-shadow: 0 0 0 2px rgba(59, 91, 219, 0.1);
        }
        
        .code-executor .ant-input:hover {
          border-color: var(--accent-primary);
        }
      `}</style>
    </div>
  );
};

export default CodeExecutor;
