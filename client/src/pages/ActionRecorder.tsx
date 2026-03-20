import React, { useState, useEffect } from 'react';
import { Card, Button, Table, Space, Typography, Tag, message, Modal, Input, Slider, Row, Col, Statistic, Divider, List, Select, Alert } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined, StopOutlined, SaveOutlined, FolderOpenOutlined, DeleteOutlined, ClockCircleOutlined, AimOutlined, KeyOutlined, EyeOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import type { RecordedAction } from '../types';

const { Title } = Typography;

export const ActionRecorder: React.FC = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [actions, setActions] = useState<RecordedAction[]>([]);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [selectedActions, setSelectedActions] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [loadModalVisible, setLoadModalVisible] = useState(false);
  const [filename, setFilename] = useState('');
  const [savedFiles, setSavedFiles] = useState<string[]>([]);
  const [playbackMode, setPlaybackMode] = useState<'realtime' | 'fast'>('realtime');
  
  useEffect(() => {
    fetchActions();
    fetchSavedFiles();
  }, []);
  
  const fetchActions = async () => {
    try {
      const response = await apiClient.get('/cua/record/actions');
      setActions(response.data.actions || []);
    } catch (error) {
      console.error('Failed to fetch actions:', error);
    }
  };
  
  const fetchSavedFiles = async () => {
    try {
      const response = await apiClient.get('/cua/record/files');
      setSavedFiles(response.data.files || []);
    } catch (error) {
      console.error('Failed to fetch saved files:', error);
    }
  };
  
  const handleStartRecording = async () => {
    try {
      await apiClient.post('/cua/record/action', { action: 'start' });
      setIsRecording(true);
      setIsPaused(false);
      message.success('开始录制');
    } catch (error) {
      message.error('启动录制失败');
    }
  };
  
  const handlePauseRecording = async () => {
    try {
      await apiClient.post('/cua/record/action', { action: isPaused ? 'resume' : 'pause' });
      setIsPaused(!isPaused);
      message.success(isPaused ? '继续录制' : '暂停录制');
    } catch (error) {
      message.error('操作失败');
    }
  };
  
  const handleStopRecording = async () => {
    try {
      await apiClient.post('/cua/record/action', { action: 'stop' });
      setIsRecording(false);
      setIsPaused(false);
      fetchActions();
      message.success('录制已停止');
    } catch (error) {
      message.error('停止录制失败');
    }
  };
  
  const handlePlayback = async () => {
    if (actions.length === 0) {
      message.warning('没有可回放的操作');
      return;
    }
    setLoading(true);
    try {
      await apiClient.post('/cua/record/play', {
        actions: selectedActions.length > 0 
          ? actions.filter((_, i) => selectedActions.includes(i))
          : undefined,
        speed: playbackSpeed,
        mode: playbackMode
      });
      message.success('回放完成');
    } catch (error) {
      message.error('回放失败');
    } finally {
      setLoading(false);
    }
  };
  
  const handleSave = async () => {
    if (!filename) {
      message.warning('请输入文件名');
      return;
    }
    try {
      await apiClient.post('/cua/record/save', { filename });
      setSaveModalVisible(false);
      setFilename('');
      fetchSavedFiles();
      message.success('保存成功');
    } catch (error) {
      message.error('保存失败');
    }
  };
  
  const handleLoad = async (file: string) => {
    try {
      await apiClient.post('/cua/record/load', { filepath: file });
      fetchActions();
      setLoadModalVisible(false);
      message.success('加载成功');
    } catch (error) {
      message.error('加载失败');
    }
  };
  
  const handleClear = async () => {
    Modal.confirm({
      title: '确认清除',
      content: '确定要清除所有录制的操作吗？',
      onOk: async () => {
        try {
          await apiClient.delete('/cua/record/actions');
          setActions([]);
          setSelectedActions([]);
          message.success('已清除');
        } catch (error) {
          message.error('清除失败');
        }
      }
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
      render: (_: unknown, __: unknown, index: number) => index + 1
    },
    {
      title: '类型',
      dataIndex: 'action_type',
      key: 'type',
      width: 150,
      render: (type: string) => (
        <Tag icon={getActionIcon(type)} color={getActionColor(type)}>
          {type}
        </Tag>
      )
    },
    {
      title: '数据',
      dataIndex: 'data',
      key: 'data',
      ellipsis: true,
      render: (data: object) => JSON.stringify(data)
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 150,
      render: (ts: number) => new Date(ts * 1000).toLocaleTimeString()
    }
  ];
  
  const rowSelection = {
    selectedRowKeys: selectedActions,
    onChange: (keys: React.Key[]) => setSelectedActions(keys as number[])
  };
  
  return (
    <div className="action-recorder-page" style={{ padding: 24 }}>
      <Title level={2}>
        <ClockCircleOutlined /> 操作录制与回放
      </Title>
      
      <Alert
        message="录制说明"
        description="点击开始录制后，您的鼠标和键盘操作将被记录。可以随时暂停、继续或停止录制。录制完成后可以回放或保存。"
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />
      
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card>
            <Statistic
              title="录制状态"
              value={isRecording ? (isPaused ? '暂停' : '录制中') : '停止'}
              valueStyle={{ 
                color: isRecording ? (isPaused ? '#faad14' : '#52c41a') : '#8c8c8c' 
              }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="操作数量" value={actions.length} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title="已选择" value={selectedActions.length} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic
              title="回放速度"
              value={playbackSpeed}
              suffix="x"
            />
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
              开始录制
            </Button>
          ) : (
            <>
              <Button
                icon={isPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
                onClick={handlePauseRecording}
                size="large"
              >
                {isPaused ? '继续' : '暂停'}
              </Button>
              <Button
                danger
                icon={<StopOutlined />}
                onClick={handleStopRecording}
                size="large"
              >
                停止录制
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
            回放
          </Button>
          
          <Select
            value={playbackMode}
            onChange={setPlaybackMode}
            style={{ width: 120 }}
            options={[
              { label: '实时模式', value: 'realtime' },
              { label: '快速模式', value: 'fast' }
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
            保存
          </Button>
          <Button icon={<FolderOpenOutlined />} onClick={() => setLoadModalVisible(true)}>
            加载
          </Button>
          <Button icon={<DeleteOutlined />} danger onClick={handleClear}>
            清除
          </Button>
        </Space>
      </Card>
      
      <Card title="操作列表">
        <Table
          columns={columns}
          dataSource={actions}
          rowKey={(_, index) => index?.toString() || '0'}
          rowSelection={rowSelection}
          pagination={{ pageSize: 20 }}
          size="small"
        />
      </Card>
      
      <Modal
        title="保存录制"
        open={saveModalVisible}
        onOk={handleSave}
        onCancel={() => setSaveModalVisible(false)}
      >
        <Input
          placeholder="输入文件名"
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          suffix=".json"
        />
      </Modal>
      
      <Modal
        title="加载录制"
        open={loadModalVisible}
        onCancel={() => setLoadModalVisible(false)}
        footer={null}
      >
        <List
          dataSource={savedFiles}
          renderItem={(file) => (
            <List.Item
              actions={[<Button onClick={() => handleLoad(file)}>加载</Button>]}
            >
              {file}
            </List.Item>
          )}
        />
      </Modal>
    </div>
  );
};

export default ActionRecorder;
