import React, { useState, useEffect } from 'react';
import { Card, Button, Input, InputNumber, Select, Slider, message, Tabs, Space, Typography, Row, Col, Statistic, Divider, Image, Alert } from 'antd';
import { DesktopOutlined, CameraOutlined, AimOutlined, KeyOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';

const { Title, Text } = Typography;

interface ScreenInfo {
  width: number;
  height: number;
  monitorCount: number;
}

interface MousePosition {
  x: number;
  y: number;
}

interface SafetyStatus {
  enabled: boolean;
  permissionLevel: string;
  failsafeEnabled: boolean;
  auditEnabled: boolean;
}

export const CUAControl: React.FC = () => {
  const [screenInfo, setScreenInfo] = useState<ScreenInfo | null>(null);
  const [mousePos, setMousePos] = useState<MousePosition>({ x: 0, y: 0 });
  const [screenshot, setScreenshot] = useState<string>('');
  const [safetyStatus, setSafetyStatus] = useState<SafetyStatus | null>(null);
  const [loading, setLoading] = useState(false);
  
  const [mouseX, setMouseX] = useState(0);
  const [mouseY, setMouseY] = useState(0);
  const [mouseButton, setMouseButton] = useState<'left' | 'right' | 'middle'>('left');
  const [clickCount, setClickCount] = useState(1);
  const [moveDuration, setMoveDuration] = useState(0);
  
  const [inputText, setInputText] = useState('');
  const [inputInterval, setInputInterval] = useState(0.05);
  const [hotkeyText, setHotkeyText] = useState('');
  
  const [screenshotMonitor, setScreenshotMonitor] = useState(0);
  const [screenshotQuality, setScreenshotQuality] = useState(85);
  
  useEffect(() => {
    fetchScreenInfo();
    fetchMousePosition();
    fetchSafetyStatus();
  }, []);
  
  const fetchScreenInfo = async () => {
    try {
      const response = await apiClient.get('/cua/screen/info');
      setScreenInfo(response.data);
    } catch (error) {
      console.error('Failed to fetch screen info:', error);
    }
  };
  
  const fetchMousePosition = async () => {
    try {
      const response = await apiClient.get('/cua/mouse/position');
      setMousePos(response.data);
    } catch (error) {
      console.error('Failed to fetch mouse position:', error);
    }
  };
  
  const fetchSafetyStatus = async () => {
    try {
      const response = await apiClient.get('/cua/safety/status');
      setSafetyStatus(response.data);
    } catch (error) {
      console.error('Failed to fetch safety status:', error);
    }
  };
  
  const handleScreenshot = async () => {
    setLoading(true);
    try {
      const response = await apiClient.post('/cua/screenshot', {
        monitor: screenshotMonitor,
        format: 'png',
        quality: screenshotQuality
      });
      setScreenshot(`data:image/png;base64,${response.data.image_base64}`);
      message.success('截图成功');
    } catch (error) {
      message.error('截图失败');
    } finally {
      setLoading(false);
    }
  };
  
  const handleMouseClick = async () => {
    try {
      await apiClient.post('/cua/mouse/click', {
        x: mouseX,
        y: mouseY,
        button: mouseButton,
        clicks: clickCount
      });
      message.success('点击成功');
    } catch (error) {
      message.error('点击失败');
    }
  };
  
  const handleMouseMove = async () => {
    try {
      await apiClient.post('/cua/mouse/move', {
        x: mouseX,
        y: mouseY,
        duration: moveDuration
      });
      message.success('移动成功');
    } catch (error) {
      message.error('移动失败');
    }
  };
  
  const handleKeyboardType = async () => {
    if (!inputText) {
      message.warning('请输入文本');
      return;
    }
    try {
      await apiClient.post('/cua/keyboard/type', {
        text: inputText,
        interval: inputInterval
      });
      message.success('输入成功');
    } catch (error) {
      message.error('输入失败');
    }
  };
  
  const handleHotkey = async () => {
    if (!hotkeyText) {
      message.warning('请输入快捷键');
      return;
    }
    try {
      const keys = hotkeyText.split('+').map(k => k.trim());
      await apiClient.post('/cua/keyboard/hotkey', { keys });
      message.success('快捷键执行成功');
    } catch (error) {
      message.error('快捷键执行失败');
    }
  };
  
  return (
    <div className="cua-control-page" style={{ padding: 24 }}>
      <Title level={2}>
        <DesktopOutlined /> Computer Use Agent 控制面板
      </Title>
      
      <Alert
        message="安全提示"
        description="CUA 功能允许 AI 直接操作您的电脑。请确保您了解每个操作的影响，敏感操作需要确认。"
        type="warning"
        showIcon
        style={{ marginBottom: 24 }}
      />
      
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="屏幕分辨率"
              value={screenInfo ? `${screenInfo.width}x${screenInfo.height}` : '-'}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="显示器数量"
              value={screenInfo?.monitorCount || 0}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="鼠标位置"
              value={mousePos ? `${mousePos.x}, ${mousePos.y}` : '-'}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="权限级别"
              value={safetyStatus?.permissionLevel || '-'}
              valueStyle={{ 
                color: safetyStatus?.permissionLevel === 'full_control' ? '#cf1322' : '#3f8600' 
              }}
            />
          </Card>
        </Col>
      </Row>
      
      <Tabs defaultActiveKey="screenshot">
        <Tabs.TabPane tab={<span><CameraOutlined /> 屏幕截图</span>} key="screenshot">
          <Card>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={16}>
                <Col span={8}>
                  <Text>显示器</Text>
                  <Select
                    value={screenshotMonitor}
                    onChange={setScreenshotMonitor}
                    style={{ width: '100%' }}
                    options={Array.from({ length: screenInfo?.monitorCount || 1 }, (_, i) => ({
                      label: `显示器 ${i + 1}`,
                      value: i
                    }))}
                  />
                </Col>
                <Col span={8}>
                  <Text>质量</Text>
                  <Slider
                    min={10}
                    max={100}
                    value={screenshotQuality}
                    onChange={setScreenshotQuality}
                  />
                </Col>
                <Col span={8}>
                  <Button
                    type="primary"
                    icon={<CameraOutlined />}
                    onClick={handleScreenshot}
                    loading={loading}
                    block
                  >
                    截图
                  </Button>
                </Col>
              </Row>
              
              {screenshot && (
                <div style={{ marginTop: 16 }}>
                  <Image
                    src={screenshot}
                    alt="Screenshot"
                    style={{ maxWidth: '100%', border: '1px solid #d9d9d9' }}
                  />
                </div>
              )}
            </Space>
          </Card>
        </Tabs.TabPane>
        
        <Tabs.TabPane tab={<span><AimOutlined /> 鼠标控制</span>} key="mouse">
          <Card>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={16}>
                <Col span={6}>
                  <Text>X 坐标</Text>
                  <InputNumber
                    value={mouseX}
                    onChange={(v: number | null) => setMouseX(v || 0)}
                    min={0}
                    max={screenInfo?.width || 1920}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col span={6}>
                  <Text>Y 坐标</Text>
                  <InputNumber
                    value={mouseY}
                    onChange={(v: number | null) => setMouseY(v || 0)}
                    min={0}
                    max={screenInfo?.height || 1080}
                    style={{ width: '100%' }}
                  />
                </Col>
                <Col span={6}>
                  <Text>按钮</Text>
                  <Select
                    value={mouseButton}
                    onChange={setMouseButton}
                    style={{ width: '100%' }}
                    options={[
                      { label: '左键', value: 'left' },
                      { label: '右键', value: 'right' },
                      { label: '中键', value: 'middle' }
                    ]}
                  />
                </Col>
                <Col span={6}>
                  <Text>点击次数</Text>
                  <InputNumber
                    value={clickCount}
                    onChange={(v: number | null) => setClickCount(v || 1)}
                    min={1}
                    max={3}
                    style={{ width: '100%' }}
                  />
                </Col>
              </Row>
              
              <Row gutter={16}>
                <Col span={12}>
                  <Text>移动持续时间 (秒)</Text>
                  <Slider
                    min={0}
                    max={2}
                    step={0.1}
                    value={moveDuration}
                    onChange={setMoveDuration}
                  />
                </Col>
              </Row>
              
              <Space>
                <Button type="primary" icon={<AimOutlined />} onClick={handleMouseClick}>
                  点击
                </Button>
                <Button icon={<PlayCircleOutlined />} onClick={handleMouseMove}>
                  移动
                </Button>
                <Button onClick={fetchMousePosition}>
                  获取当前位置
                </Button>
              </Space>
            </Space>
          </Card>
        </Tabs.TabPane>
        
        <Tabs.TabPane tab={<span><KeyOutlined /> 键盘控制</span>} key="keyboard">
          <Card>
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>
                <Text>输入文本</Text>
                <Input.TextArea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="输入要键入的文本..."
                  rows={3}
                />
              </div>
              
              <Row gutter={16}>
                <Col span={12}>
                  <Text>输入间隔 (秒)</Text>
                  <Slider
                    min={0}
                    max={0.5}
                    step={0.01}
                    value={inputInterval}
                    onChange={setInputInterval}
                  />
                </Col>
                <Col span={12}>
                  <Button type="primary" block onClick={handleKeyboardType}>
                    输入文本
                  </Button>
                </Col>
              </Row>
              
              <Divider />
              
              <div>
                <Text>快捷键 (用 + 分隔)</Text>
                <Input
                  value={hotkeyText}
                  onChange={(e) => setHotkeyText(e.target.value)}
                  placeholder="例如: ctrl+c, alt+tab, ctrl+shift+esc"
                />
              </div>
              <Button onClick={handleHotkey}>执行快捷键</Button>
            </Space>
          </Card>
        </Tabs.TabPane>
        
        <Tabs.TabPane tab={<span><ReloadOutlined /> 安全设置</span>} key="safety">
          <Card>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Text>权限级别</Text>
                  <Select
                    value={safetyStatus?.permissionLevel}
                    style={{ width: '100%' }}
                    options={[
                      { label: '只读', value: 'read_only' },
                      { label: '交互', value: 'interactive' },
                      { label: '完全控制', value: 'full_control' }
                    ]}
                    onChange={async (value) => {
                      try {
                        await apiClient.post('/cua/safety/permission', null, { params: { level: value } });
                        fetchSafetyStatus();
                        message.success('权限级别已更新');
                      } catch (error) {
                        message.error('更新失败');
                      }
                    }}
                  />
                </Col>
              </Row>
              
              <Divider />
              
              <Row gutter={16}>
                <Col span={8}>
                  <Statistic
                    title="FAILSAFE"
                    value={safetyStatus?.failsafeEnabled ? '启用' : '禁用'}
                    valueStyle={{ color: safetyStatus?.failsafeEnabled ? '#3f8600' : '#cf1322' }}
                  />
                </Col>
                <Col span={8}>
                  <Statistic
                    title="审计日志"
                    value={safetyStatus?.auditEnabled ? '启用' : '禁用'}
                    valueStyle={{ color: safetyStatus?.auditEnabled ? '#3f8600' : '#cf1322' }}
                  />
                </Col>
                <Col span={8}>
                  <Button icon={<ReloadOutlined />} onClick={fetchSafetyStatus}>
                    刷新状态
                  </Button>
                </Col>
              </Row>
            </Space>
          </Card>
        </Tabs.TabPane>
      </Tabs>
    </div>
  );
};

export default CUAControl;
