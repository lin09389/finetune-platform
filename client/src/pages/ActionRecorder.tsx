import {
  AimOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  KeyOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SaveOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Input,
  List,
  Modal,
  Row,
  Select,
  Slider,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../services/api';
import type { RecordedAction } from '../types';
import { appModal } from '../utils/modal';

const { Title } = Typography;

type TableAction = RecordedAction & {
  _rowKey: string;
};

type SavedRecording = {
  filename: string;
  filepath?: string;
  size?: number;
  modified?: number;
};

export const ActionRecorder: React.FC = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [actions, setActions] = useState<RecordedAction[]>([]);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [selectedActionKeys, setSelectedActionKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [loadModalVisible, setLoadModalVisible] = useState(false);
  const [filename, setFilename] = useState('');
  const [savedFiles, setSavedFiles] = useState<SavedRecording[]>([]);
  const [playbackMode, setPlaybackMode] = useState<'realtime' | 'fast'>('realtime');
  const [capabilityMessage, setCapabilityMessage] = useState<string | null>(null);

  useEffect(() => {
    void fetchActions();
    void fetchSavedFiles();
  }, []);

  const tableData = useMemo<TableAction[]>(
    () =>
      actions.map((action, index) => ({
        ...action,
        _rowKey: `${action.action_type}-${action.timestamp}-${index}`,
      })),
    [actions],
  );

  const fetchActions = async () => {
    try {
      const response = await apiClient.get('/cua/record/actions');
      setActions(response.data.actions || []);
      setIsRecording(Boolean(response.data.is_recording));
      setIsPaused(Boolean(response.data.is_paused));
      setCapabilityMessage(null);
    } catch {
      setCapabilityMessage('当前环境无法读取录制器状态，请确认本机交互能力已启用。');
    }
  };

  const fetchSavedFiles = async () => {
    try {
      const response = await apiClient.get('/cua/record/files');
      const files = Array.isArray(response.data.files) ? response.data.files : [];
      setSavedFiles(
        files
          .map((file: string | SavedRecording) =>
            typeof file === 'string' ? { filename: file, filepath: file } : file,
          )
          .filter((file: SavedRecording) => Boolean(file.filename)),
      );
    } catch {
      setSavedFiles([]);
    }
  };

  const handleStartRecording = async () => {
    setIsRecording(true);
    setIsPaused(false);
    try {
      await apiClient.post('/cua/record/action', { action: 'start' });
      message.success('Recording started');
    } catch (error) {
      setIsRecording(false);
      message.error('Failed to start recording');
    }
  };

  const handlePauseRecording = async () => {
    const nextPaused = !isPaused;
    setIsPaused(nextPaused);
    try {
      await apiClient.post('/cua/record/action', { action: isPaused ? 'resume' : 'pause' });
      message.success(isPaused ? 'Recording resumed' : 'Recording paused');
    } catch (error) {
      setIsPaused(!nextPaused);
      message.error('Recording action failed');
    }
  };

  const handleStopRecording = async () => {
    setIsRecording(false);
    setIsPaused(false);
    try {
      await apiClient.post('/cua/record/action', { action: 'stop' });
      await fetchActions();
      message.success('Recording stopped');
    } catch (error) {
      setIsRecording(true);
      message.error('Failed to stop recording');
    }
  };

  const handlePlayback = async () => {
    if (actions.length === 0) {
      message.warning('No recorded actions to play');
      return;
    }

    setLoading(true);
    try {
      await apiClient.post('/cua/record/play', {
        actions:
          selectedActionKeys.length > 0
            ? tableData
                .filter((action) => selectedActionKeys.includes(action._rowKey))
                .map(({ _rowKey, ...action }) => action)
            : undefined,
        speed: playbackSpeed,
        mode: playbackMode,
      });
      message.success('Playback finished');
    } catch (error) {
      message.error('Playback failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!filename) {
      message.warning('Please enter a filename');
      return;
    }

    try {
      await apiClient.post('/cua/record/save', { filename });
      setSaveModalVisible(false);
      setFilename('');
      await fetchSavedFiles();
      message.success('Recording saved');
    } catch (error) {
      message.error('Failed to save recording');
    }
  };

  const handleLoad = async (file: SavedRecording) => {
    try {
      await apiClient.post('/cua/record/load', { filepath: file.filepath || file.filename });
      await fetchActions();
      setLoadModalVisible(false);
      message.success('Recording loaded');
    } catch (error) {
      message.error('Failed to load recording');
    }
  };

  const handleClear = async () => {
    appModal.confirm({
      title: 'Clear recordings',
      content: 'Remove all recorded actions?',
      onOk: async () => {
        try {
          await apiClient.delete('/cua/record/actions');
          setActions([]);
          setSelectedActionKeys([]);
          message.success('Actions cleared');
        } catch (error) {
          message.error('Failed to clear actions');
        }
      },
    });
  };

  const getActionIcon = (type: string) => {
    switch (type) {
      case 'mouse_move':
      case 'mouse_click':
      case 'mouse_scroll':
      case 'mouse_drag':
        return <AimOutlined />;
      case 'key_press':
      case 'key_release':
        return <KeyOutlined />;
      default:
        return <EyeOutlined />;
    }
  };

  const getActionColor = (type: string) => {
    switch (type) {
      case 'mouse_click':
        return 'blue';
      case 'mouse_move':
        return 'green';
      case 'key_press':
        return 'orange';
      case 'key_release':
        return 'red';
      default:
        return 'default';
    }
  };

  const columns = [
    {
      title: '#',
      dataIndex: 'index',
      key: 'index',
      width: 50,
      render: (_: unknown, __: unknown, index: number) => index + 1,
    },
    {
      title: 'Type',
      dataIndex: 'action_type',
      key: 'type',
      width: 150,
      render: (type: string) => (
        <Tag icon={getActionIcon(type)} color={getActionColor(type)}>
          {type}
        </Tag>
      ),
    },
    {
      title: 'Data',
      dataIndex: 'data',
      key: 'data',
      ellipsis: true,
      render: (data: object) => JSON.stringify(data),
    },
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 150,
      render: (ts: number) => new Date(ts * 1000).toLocaleTimeString(),
    },
  ];

  const rowSelection = {
    selectedRowKeys: selectedActionKeys,
    onChange: (keys: React.Key[]) => setSelectedActionKeys(keys.map(String)),
  };

  return (
    <div className="action-recorder-page" style={{ padding: 24 }}>
      <Title level={2}>
        <ClockCircleOutlined /> Action Recorder（实验）
      </Title>

      <Alert
        message="Experimental recording guide"
        description="This recorder is still experimental. Use it in a controlled environment and verify saved or replayed actions before relying on them."
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      {capabilityMessage && (
        <Alert
          message="Recorder capability status"
          description={capabilityMessage}
          type="warning"
          showIcon
          style={{ marginBottom: 24 }}
        />
      )}

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card>
            <Statistic
              title="Status"
              value={isRecording ? (isPaused ? 'Paused' : 'Recording') : 'Stopped'}
              valueStyle={{
                color: isRecording ? (isPaused ? '#faad14' : '#52c41a') : '#8c8c8c',
              }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="Action Count" value={actions.length} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="Selected" value={selectedActionKeys.length} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="Playback Speed" value={playbackSpeed} suffix="x" />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginBottom: 24 }}>
        <Space size="middle">
          {!isRecording ? (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleStartRecording}
              size="large"
            >
              Start Recording
            </Button>
          ) : (
            <>
              <Button
                icon={isPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
                onClick={handlePauseRecording}
                size="large"
              >
                {isPaused ? 'Resume' : 'Pause'}
              </Button>
              <Button danger icon={<StopOutlined />} onClick={handleStopRecording} size="large">
                Stop Recording
              </Button>
            </>
          )}

          <Divider type="vertical" style={{ height: 40 }} />

          <Button
            icon={<PlayCircleOutlined />}
            onClick={handlePlayback}
            disabled={actions.length === 0 || isRecording}
            loading={loading}
            size="large"
          >
            Playback
          </Button>

          <Select
            value={playbackMode}
            onChange={setPlaybackMode}
            style={{ width: 120 }}
            options={[
              { label: 'Realtime', value: 'realtime' },
              { label: 'Fast', value: 'fast' },
            ]}
          />

          <Slider
            min={0.1}
            max={5}
            step={0.1}
            value={playbackSpeed}
            onChange={setPlaybackSpeed}
            style={{ width: 150 }}
            tooltip={{ formatter: (v) => `${v}x` }}
          />

          <Divider type="vertical" style={{ height: 40 }} />

          <Button icon={<SaveOutlined />} onClick={() => setSaveModalVisible(true)}>
            Save
          </Button>
          <Button icon={<FolderOpenOutlined />} onClick={() => setLoadModalVisible(true)}>
            Load
          </Button>
          <Button icon={<DeleteOutlined />} danger onClick={handleClear}>
            Clear
          </Button>
        </Space>
      </Card>

      <Card title="Recorded Actions">
        <Table
          columns={columns}
          dataSource={tableData}
          rowKey="_rowKey"
          rowSelection={rowSelection}
          pagination={{ pageSize: 20 }}
          size="small"
        />
      </Card>

      <Modal
        title="Save Recording"
        open={saveModalVisible}
        onOk={handleSave}
        onCancel={() => setSaveModalVisible(false)}
      >
        <Input
          placeholder="Enter filename"
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          suffix=".json"
        />
      </Modal>

      <Modal
        title="Load Recording"
        open={loadModalVisible}
        onCancel={() => setLoadModalVisible(false)}
        footer={null}
      >
        <List
          dataSource={savedFiles}
          renderItem={(file) => (
            <List.Item
              actions={[
                <Button key={file.filepath || file.filename} onClick={() => handleLoad(file)}>
                  Load
                </Button>,
              ]}
            >
              {file.filename}
            </List.Item>
          )}
        />
      </Modal>
    </div>
  );
};

export default ActionRecorder;
