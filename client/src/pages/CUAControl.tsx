import {
  AimOutlined,
  CameraOutlined,
  DesktopOutlined,
  KeyOutlined,
  MonitorOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Alert, Tag, message } from 'antd';
import React, { useEffect, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { apiClient } from '../services/api';
import styles from './CUAControl.module.css';

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

interface CapabilityNotice {
  kind: 'info' | 'warning' | 'error';
  message: string;
}

const TABS = [
  { key: 'screenshot', label: '屏幕截图', icon: <CameraOutlined /> },
  { key: 'mouse', label: '鼠标控制', icon: <AimOutlined /> },
  { key: 'keyboard', label: '键盘控制', icon: <KeyOutlined /> },
  { key: 'safety', label: '安全设置', icon: <ReloadOutlined /> },
];

export const CUAControl: React.FC = () => {
  const [activeTab, setActiveTab] = useState('screenshot');
  const [screenInfo, setScreenInfo] = useState<ScreenInfo | null>(null);
  const [mousePos, setMousePos] = useState<MousePosition>({ x: 0, y: 0 });
  const [screenshot, setScreenshot] = useState('');
  const [safetyStatus, setSafetyStatus] = useState<SafetyStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [capabilityNotice, setCapabilityNotice] = useState<CapabilityNotice | null>(null);

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
    void fetchScreenInfo();
    void fetchMousePosition();
    void fetchSafetyStatus();
  }, []);

  const fetchScreenInfo = async () => {
    try {
      const response = await apiClient.get('/cua/screen/info');
      const data = response.data || {};
      const monitors = Array.isArray(data.monitors) ? data.monitors : [];
      const primaryMonitor = monitors[0] || {};
      setScreenInfo({
        width: data.width ?? primaryMonitor.width ?? 0,
        height: data.height ?? primaryMonitor.height ?? 0,
        monitorCount: data.monitorCount ?? data.monitor_count ?? monitors.length ?? 0,
      });
      setCapabilityNotice(null);
    } catch {
      setCapabilityNotice({
        kind: 'warning',
        message: '当前环境无法读取屏幕能力，部分 CUA 功能可能不可用。',
      });
    }
  };

  const fetchMousePosition = async () => {
    try {
      const response = await apiClient.get('/cua/mouse/position');
      setMousePos(response.data);
    } catch {
      setMousePos({ x: 0, y: 0 });
    }
  };

  const fetchSafetyStatus = async () => {
    try {
      const response = await apiClient.get('/cua/safety/status');
      const data = response.data || {};
      setSafetyStatus({
        enabled: data.enabled ?? true,
        permissionLevel: data.permissionLevel ?? data.permission_level ?? 'unknown',
        failsafeEnabled: data.failsafeEnabled ?? data.failsafe_enabled ?? false,
        auditEnabled: data.auditEnabled ?? false,
      });
    } catch {
      setSafetyStatus(null);
    }
  };

  const handleScreenshot = async () => {
    setLoading(true);
    try {
      const response = await apiClient.post('/cua/screenshot', {
        monitor: screenshotMonitor,
        format: 'png',
        quality: screenshotQuality,
      });
      const imageBase64 = response.data.image_base64 || response.data.image;
      setScreenshot(`data:image/png;base64,${imageBase64}`);
      message.success('截图成功');
    } catch {
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
        clicks: clickCount,
      });
      message.success('点击成功');
    } catch {
      message.error('点击失败');
    }
  };

  const handleMouseMove = async () => {
    try {
      await apiClient.post('/cua/mouse/move', { x: mouseX, y: mouseY, duration: moveDuration });
      message.success('移动成功');
    } catch {
      message.error('移动失败');
    }
  };

  const handleKeyboardType = async () => {
    if (!inputText) {
      message.warning('请输入文本');
      return;
    }
    try {
      await apiClient.post('/cua/keyboard/type', { text: inputText, interval: inputInterval });
      message.success('输入成功');
    } catch {
      message.error('输入失败');
    }
  };

  const handleHotkey = async () => {
    if (!hotkeyText) {
      message.warning('请输入快捷键');
      return;
    }
    try {
      const keys = hotkeyText.split('+').map((v) => v.trim());
      await apiClient.post('/cua/keyboard/hotkey', { keys });
      message.success('快捷键执行成功');
    } catch {
      message.error('快捷键执行失败');
    }
  };

  return (
    <MotionList className={styles.page} stagger={0.08}>
      <MotionItem>
        <h2 className={styles.pageTitle}>
          <DesktopOutlined /> Computer Use Agent 控制面板（实验）
        </h2>

        <div style={{ marginBottom: 12 }}>
          <Tag color="gold">Experimental</Tag>
          {safetyStatus?.permissionLevel && (
            <Tag color={safetyStatus.permissionLevel === 'read_only' ? 'blue' : 'volcano'}>
              权限: {safetyStatus.permissionLevel}
            </Tag>
          )}
        </div>

        <div className={styles.experimentBanner}>
          <WarningOutlined style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 2 }} />
          <p>
            <strong>实验功能与安全提示</strong> — CUA 仍处于实验阶段，并且允许 AI
            直接操作本机。请只在可控环境中使用，并对敏感操作保持人工确认。
          </p>
        </div>

        {capabilityNotice && (
          <Alert
            style={{ marginBottom: 16 }}
            type={capabilityNotice.kind}
            showIcon
            message="环境能力状态"
            description={capabilityNotice.message}
          />
        )}

        {/* Stats */}
        <div className={styles.statsRow}>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <MonitorOutlined style={{ color: 'var(--primary)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>屏幕分辨率</div>
              <div className={styles.statValue} style={{ fontSize: 15 }}>
                {screenInfo ? `${screenInfo.width}×${screenInfo.height}` : '-'}
              </div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <DesktopOutlined style={{ color: 'var(--primary)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>显示器数量</div>
              <div className={styles.statValue}>{screenInfo?.monitorCount || 0}</div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <AimOutlined style={{ color: 'var(--accent-primary)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>鼠标位置</div>
              <div className={styles.statValue} style={{ fontSize: 15 }}>
                {mousePos.x}, {mousePos.y}
              </div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon} style={{ background: 'rgba(250,173,20,0.12)' }}>
              <KeyOutlined style={{ color: 'var(--warning)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>权限级别</div>
              <div className={styles.statValue} style={{ fontSize: 15 }}>
                {safetyStatus?.permissionLevel || '-'}
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className={styles.tabsWrapper}>
          <div className={styles.tabList} role="tablist" aria-label="CUA control tabs">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.key}
                aria-controls={`cua-tabpanel-${tab.key}`}
                className={`${styles.tabItem} ${activeTab === tab.key ? styles.tabItemActive : ''}`}
                onClick={() => setActiveTab(tab.key)}
                data-testid={`cua-tab-${tab.key}`}
              >
                {tab.icon} {tab.label}
              </button>
            ))}
          </div>

          <div className={styles.tabContent}>
            {/* Screenshot */}
            {activeTab === 'screenshot' && (
              <div className={styles.formSection} role="tabpanel" id="cua-tabpanel-screenshot">
                <div className={`${styles.formGrid} ${styles.formGrid3}`}>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>显示器</label>
                    <select
                      className={styles.formSelect}
                      value={screenshotMonitor}
                      onChange={(e) => setScreenshotMonitor(Number(e.target.value))}
                    >
                      {Array.from({ length: screenInfo?.monitorCount || 1 }, (_, i) => (
                        <option key={i} value={i}>
                          显示器 {i + 1}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>质量 ({screenshotQuality})</label>
                    <div className={styles.sliderWrap}>
                      <input
                        type="range"
                        min={10}
                        max={100}
                        value={screenshotQuality}
                        onChange={(e) => setScreenshotQuality(Number(e.target.value))}
                      />
                      <span className={styles.sliderValue}>{screenshotQuality}</span>
                    </div>
                  </div>
                  <div className={styles.formField} style={{ justifyContent: 'flex-end' }}>
                    <label className={styles.formLabel}>&nbsp;</label>
                    <button
                      className={`${styles.btn} ${styles.btnPrimary}`}
                      onClick={handleScreenshot}
                      disabled={loading}
                      data-testid="cua-btn-screenshot"
                    >
                      <CameraOutlined /> {loading ? '截图中...' : '截图'}
                    </button>
                  </div>
                </div>
                {screenshot && (
                  <div className={styles.screenshotPreview}>
                    <img
                      src={screenshot}
                      alt="Screenshot"
                      loading="lazy"
                      style={{ maxWidth: '100%', maxHeight: '60vh', height: 'auto', borderRadius: 8 }}
                    />
                  </div>
                )}
              </div>
            )}

            {/* Mouse */}
            {activeTab === 'mouse' && (
              <div className={styles.formSection} role="tabpanel" id="cua-tabpanel-mouse">
                <div className={`${styles.formGrid} ${styles.formGrid4}`}>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>X 坐标</label>
                    <input
                      type="number"
                      className={styles.formInput}
                      data-testid="cua-input-x"
                      value={mouseX}
                      min={0}
                      max={screenInfo?.width || 1920}
                      onChange={(e) => setMouseX(Number(e.target.value))}
                    />
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>Y 坐标</label>
                    <input
                      type="number"
                      className={styles.formInput}
                      data-testid="cua-input-y"
                      value={mouseY}
                      min={0}
                      max={screenInfo?.height || 1080}
                      onChange={(e) => setMouseY(Number(e.target.value))}
                    />
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>按键</label>
                    <select
                      className={styles.formSelect}
                      value={mouseButton}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (value === 'left' || value === 'right' || value === 'middle') {
                          setMouseButton(value);
                        }
                      }}
                    >
                      <option value="left">左键</option>
                      <option value="right">右键</option>
                      <option value="middle">中键</option>
                    </select>
                  </div>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>点击次数</label>
                    <input
                      type="number"
                      className={styles.formInput}
                      value={clickCount}
                      min={1}
                      max={3}
                      onChange={(e) => setClickCount(Number(e.target.value))}
                    />
                  </div>
                </div>
                <div className={`${styles.formGrid} ${styles.formGrid2}`}>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>移动持续时间（秒）</label>
                    <div className={styles.sliderWrap}>
                      <input
                        type="range"
                        min={0}
                        max={2}
                        step={0.1}
                        value={moveDuration}
                        onChange={(e) => setMoveDuration(Number(e.target.value))}
                      />
                      <span className={styles.sliderValue}>{moveDuration}s</span>
                    </div>
                  </div>
                </div>
                <div className={styles.btnRow}>
                  <button
                    className={`${styles.btn} ${styles.btnPrimary}`}
                    onClick={handleMouseClick}
                    data-testid="cua-btn-click"
                  >
                    <AimOutlined /> 点击
                  </button>
                  <button
                    className={`${styles.btn} ${styles.btnDefault}`}
                    onClick={handleMouseMove}
                    data-testid="cua-btn-move"
                  >
                    <PlayCircleOutlined /> 移动
                  </button>
                  <button
                    className={`${styles.btn} ${styles.btnDefault}`}
                    onClick={fetchMousePosition}
                    data-testid="cua-btn-refresh-mouse"
                  >
                    获取当前位置
                  </button>
                </div>
              </div>
            )}

            {/* Keyboard */}
            {activeTab === 'keyboard' && (
              <div className={styles.formSection} role="tabpanel" id="cua-tabpanel-keyboard">
                <div className={styles.formField}>
                  <label className={styles.formLabel}>输入文本</label>
                  <textarea
                    className={styles.formTextarea}
                    value={inputText}
                    rows={3}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="输入要键入的文本..."
                  />
                </div>
                <div className={`${styles.formGrid} ${styles.formGrid2}`}>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>输入间隔（秒）</label>
                    <div className={styles.sliderWrap}>
                      <input
                        type="range"
                        min={0}
                        max={0.5}
                        step={0.01}
                        value={inputInterval}
                        onChange={(e) => setInputInterval(Number(e.target.value))}
                      />
                      <span className={styles.sliderValue}>{inputInterval}s</span>
                    </div>
                  </div>
                  <div className={styles.formField} style={{ justifyContent: 'flex-end' }}>
                    <label className={styles.formLabel}>&nbsp;</label>
                    <button
                      className={`${styles.btn} ${styles.btnPrimary}`}
                      onClick={handleKeyboardType}
                    >
                      <KeyOutlined /> 输入文本
                    </button>
                  </div>
                </div>
                <div className={styles.formField}>
                  <label className={styles.formLabel}>快捷键（用 + 分隔）</label>
                  <input
                    className={styles.formInput}
                    value={hotkeyText}
                    onChange={(e) => setHotkeyText(e.target.value)}
                    placeholder="例如: ctrl+c, alt+tab, ctrl+shift+esc"
                  />
                </div>
                <div className={styles.btnRow}>
                  <button className={`${styles.btn} ${styles.btnDefault}`} onClick={handleHotkey}>
                    执行快捷键
                  </button>
                </div>
              </div>
            )}

            {/* Safety */}
            {activeTab === 'safety' && (
              <div className={styles.formSection} role="tabpanel" id="cua-tabpanel-safety">
                <div className={`${styles.formGrid} ${styles.formGrid2}`}>
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>权限级别</label>
                    <select
                      className={styles.formSelect}
                      value={safetyStatus?.permissionLevel || ''}
                      onChange={async (e) => {
                        try {
                          await apiClient.post('/cua/safety/permission', null, {
                            params: { level: e.target.value },
                          });
                          await fetchSafetyStatus();
                          message.success('权限级别已更新');
                        } catch {
                          message.error('更新权限级别失败');
                        }
                      }}
                    >
                      <option value="read_only">只读</option>
                      <option value="interactive">交互</option>
                      <option value="full_control">完全控制</option>
                    </select>
                  </div>
                </div>
                <div className={styles.safetyGrid}>
                  <div className={styles.safetyItem}>
                    <div className={styles.safetyItemLabel}>Failsafe</div>
                    <div
                      className={`${styles.safetyItemValue} ${safetyStatus?.failsafeEnabled ? styles.safetyValueGood : styles.safetyValueBad}`}
                    >
                      {safetyStatus?.failsafeEnabled ? '启用' : '禁用'}
                    </div>
                  </div>
                  <div className={styles.safetyItem}>
                    <div className={styles.safetyItemLabel}>审计日志</div>
                    <div
                      className={`${styles.safetyItemValue} ${safetyStatus?.auditEnabled ? styles.safetyValueGood : styles.safetyValueBad}`}
                    >
                      {safetyStatus?.auditEnabled ? '启用' : '禁用'}
                    </div>
                  </div>
                </div>
                <div className={styles.btnRow}>
                  <button
                    className={`${styles.btn} ${styles.btnDefault}`}
                    onClick={fetchSafetyStatus}
                  >
                    <ReloadOutlined /> 刷新状态
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </MotionItem>
    </MotionList>
  );
};

export default CUAControl;
