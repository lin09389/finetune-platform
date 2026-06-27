import {
  ApiOutlined,
  CloseOutlined,
  DeleteOutlined,
  LinkOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { message } from 'antd';
import { useEffect, useState } from 'react';
import { MotionItem, MotionList } from '../components/shared/MotionWrapper';
import { apiClient } from '../services/api';
import { appModal } from '../utils/modal';
import styles from './MCPTools.module.css';

interface MCPToolItem {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  server_name?: string;
}

interface MCPServerItem {
  name: string;
  transport: 'stdio' | 'sse';
  status: 'connected' | 'disconnected';
  command?: string;
  args?: string[];
  url?: string;
  tool_count?: number;
}

interface MCPStatus {
  tier?: string;
  available?: boolean;
  runtime_status?: string;
  dependency_status?: string;
  failure_mode?: string;
  message?: string;
  total_servers?: number;
  connected_servers?: number;
  disconnected_servers?: number;
  total_tools?: number;
}

export default function MCPTools() {
  const [tools, setTools] = useState<MCPToolItem[]>([]);
  const [servers, setServers] = useState<MCPServerItem[]>([]);
  const [status, setStatus] = useState<MCPStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [callModalVisible, setCallModalVisible] = useState(false);
  const [selectedTool, setSelectedTool] = useState<MCPToolItem | null>(null);
  const [callArgs, setCallArgs] = useState('{}');
  const [addForm, setAddForm] = useState({
    name: '',
    transport: 'stdio' as 'stdio' | 'sse',
    command: '',
    args: '',
    url: '',
  });
  const [statusNotice, setStatusNotice] = useState('');

  useEffect(() => {
    fetchTools();
    fetchServers();
    fetchStatus();
  }, []);

  const fetchTools = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get('/mcp/tools');
      setTools(response.data.tools || []);
    } catch {
      setTools([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchServers = async () => {
    try {
      const response = await apiClient.get('/mcp/servers');
      setServers(response.data.servers || []);
    } catch {
      setServers([]);
    }
  };

  const fetchStatus = async () => {
    try {
      const response = await apiClient.get('/mcp/status');
      setStatus(response.data || null);
      setStatusNotice('');
    } catch {
      setStatus(null);
      setStatusNotice(
        'MCP 状态接口当前不可用，服务器列表只能反映页面请求结果，不能证明外部 MCP 服务已可调用。',
      );
    }
  };

  const handleAddServer = async () => {
    const { name, transport, command, args, url } = addForm;
    if (!name || !transport) {
      message.warning('请填写必填项');
      return;
    }
    if (transport === 'stdio' && !command) {
      message.warning('请填写命令');
      return;
    }
    if (transport === 'sse' && !url) {
      message.warning('请填写 URL');
      return;
    }

    try {
      const payload: Record<string, unknown> = { name, transport };
      if (transport === 'stdio') {
        payload['command'] = command;
        payload['args'] = args ? args.split(' ') : [];
      } else {
        payload['url'] = url;
      }
      await apiClient.post('/mcp/servers', payload);
      message.success('服务器添加成功');
      setAddModalVisible(false);
      setAddForm({ name: '', transport: 'stdio', command: '', args: '', url: '' });
      fetchServers();
      fetchTools();
      fetchStatus();
    } catch (error) {
      message.error('添加服务器失败');
    }
  };

  const handleRemoveServer = async (name: string) => {
    appModal.confirm({
      title: '确认删除',
      content: `确定要删除服务器 "${name}" 吗？`,
      onOk: async () => {
        try {
          await apiClient.delete(`/mcp/servers/${name}`);
          message.success('服务器已删除');
          fetchServers();
          fetchTools();
          fetchStatus();
        } catch (error) {
          message.error('删除失败');
        }
      },
    });
  };

  const handleReconnect = async (name: string) => {
    try {
      await apiClient.post(`/mcp/servers/${name}/reconnect`);
      message.success('重连成功');
      fetchServers();
      fetchStatus();
    } catch (error) {
      message.error('重连失败');
    }
  };

  const handleCallTool = async () => {
    if (!selectedTool) return;
    try {
      const args = JSON.parse(callArgs);
      const response = await apiClient.post('/mcp/call', {
        tool_name: selectedTool.name,
        arguments: args,
      });
      if (response.data.is_error) {
        message.error(`调用失败: ${response.data.content}`);
      } else {
        message.success('调用成功');
        appModal.success({
          title: '执行结果',
          content: (
            <pre style={{ maxHeight: 400, overflow: 'auto' }}>
              {JSON.stringify(response.data.content, null, 2)}
            </pre>
          ),
        });
      }
    } catch (error) {
      message.error('参数格式错误或调用失败');
    }
  };

  const connectedCount = servers.filter((s) => s.status === 'connected').length;

  return (
    <MotionList className={styles.page} stagger={0.08}>
      <MotionItem>
        <div className={styles.experimentBanner}>
          <WarningOutlined style={{ color: 'var(--warning)', flexShrink: 0, marginTop: 2 }} />
          <p>
            <strong>实验功能</strong> — MCP
            服务器接入与工具调用当前仍处于实验阶段，配置和调用结果应以实际服务状态为准。
          </p>
        </div>
        <div
          data-testid="mcp-runtime-status"
          className={styles.experimentBanner}
          style={{
            marginTop: 12,
            background:
              status?.runtime_status === 'ready'
                ? 'rgba(74, 222, 128, 0.12)'
                : 'rgba(250, 173, 20, 0.14)',
            borderColor:
              status?.runtime_status === 'ready'
                ? 'rgba(74, 222, 128, 0.28)'
                : 'rgba(250, 173, 20, 0.28)',
          }}
        >
          <WarningOutlined
            style={{
              color: status?.runtime_status === 'ready' ? '#4ade80' : '#faad14',
              flexShrink: 0,
              marginTop: 2,
            }}
          />
          <p>
            <strong>
              {status?.runtime_status === 'ready' ? '已检测到可用 MCP 连接' : '当前能力受限'}
            </strong>
            {' — '}
            {statusNotice || status?.message || '尚未拿到 MCP 运行状态。'}
            {status?.dependency_status ? ` 依赖状态：${status.dependency_status}。` : ''}
          </p>
        </div>

        <h2 className={styles.pageTitle}>
          <ApiOutlined /> MCP 工具集成（实验）
        </h2>

        {/* Stats */}
        <div className={styles.statsRow}>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <LinkOutlined style={{ color: 'var(--primary)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>已连接服务器</div>
              <div className={styles.statValue}>
                {connectedCount}
                <span className={styles.statSuffix}>/ {servers.length}</span>
              </div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <ApiOutlined style={{ color: 'var(--primary)' }} />
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>可用工具</div>
              <div className={styles.statValue}>{tools.length}</div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon} style={{ background: 'rgba(34,197,94,0.12)' }}>
              <span style={{ color: 'var(--success)', fontSize: 13, fontWeight: 700 }}>stdio</span>
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>stdio 连接</div>
              <div className={styles.statValue}>
                {servers.filter((s) => s.transport === 'stdio').length}
              </div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon} style={{ background: 'rgba(250,173,20,0.12)' }}>
              <span style={{ color: 'var(--warning)', fontSize: 13, fontWeight: 700 }}>SSE</span>
            </div>
            <div className={styles.statInfo}>
              <div className={styles.statLabel}>SSE 连接</div>
              <div className={styles.statValue}>
                {servers.filter((s) => s.transport === 'sse').length}
              </div>
            </div>
          </div>
        </div>

        {/* Servers card */}
        <div className={styles.glassCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardTitle}>
              <ApiOutlined /> MCP 服务器
            </span>
            <div className={styles.cardActions}>
              <button
                className={`${styles.btn} ${styles.btnDefault}`}
                onClick={() => {
                  fetchServers();
                  fetchTools();
                  fetchStatus();
                }}
              >
                <ReloadOutlined /> 刷新
              </button>
              <button
                className={`${styles.btn} ${styles.btnPrimary}`}
                onClick={() => setAddModalVisible(true)}
              >
                <PlusOutlined /> 添加服务器
              </button>
            </div>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th>服务器名称</th>
                  <th>传输类型</th>
                  <th>状态</th>
                  <th>工具数量</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {servers.length === 0 ? (
                  <tr>
                    <td colSpan={5} className={styles.emptyCell}>
                      暂无服务器
                    </td>
                  </tr>
                ) : (
                  servers.map((server) => (
                    <tr key={server.name}>
                      <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                        {server.name}
                      </td>
                      <td>
                        <span
                          className={`${styles.tag} ${server.transport === 'stdio' ? styles.tagGreen : styles.tagOrange}`}
                        >
                          {server.transport}
                        </span>
                      </td>
                      <td>
                        <span className={styles.statusDot}>
                          <span
                            className={`${styles.dot} ${server.status === 'connected' ? styles.dotGreen : styles.dotRed}`}
                          />
                          {server.status === 'connected' ? '已连接' : '未连接'}
                        </span>
                      </td>
                      <td>{server.tool_count || 0}</td>
                      <td>
                        <button
                          className={`${styles.linkBtn} ${styles.linkBtnDefault}`}
                          onClick={() => handleReconnect(server.name)}
                        >
                          <LinkOutlined /> 重连
                        </button>
                        <button
                          className={`${styles.linkBtn} ${styles.linkBtnDanger}`}
                          onClick={() => handleRemoveServer(server.name)}
                        >
                          <DeleteOutlined /> 删除
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Tools card */}
        <div className={styles.glassCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardTitle}>可用工具</span>
            <div className={styles.cardActions}>
              <button
                className={`${styles.btn} ${styles.btnDefault}`}
                onClick={() => {
                  fetchTools();
                  fetchStatus();
                }}
              >
                <ReloadOutlined /> 刷新
              </button>
            </div>
          </div>
          {loading ? (
            <div className={styles.spinnerWrap}>
              <div className={styles.spinner} />
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>工具名称</th>
                    <th>描述</th>
                    <th>服务器</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {tools.length === 0 ? (
                    <tr>
                      <td colSpan={4} className={styles.emptyCell}>
                        暂无工具，请先添加 MCP 服务器
                      </td>
                    </tr>
                  ) : (
                    tools.map((tool) => (
                      <tr key={tool.name}>
                        <td>
                          <span className={`${styles.tag} ${styles.tagBlue}`}>{tool.name}</span>
                        </td>
                        <td
                          style={{
                            maxWidth: 300,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {tool.description}
                        </td>
                        <td>
                          {tool.server_name ? (
                            <span className={`${styles.tag} ${styles.tagGray}`}>
                              {tool.server_name}
                            </span>
                          ) : (
                            '-'
                          )}
                        </td>
                        <td>
                          <button
                            className={`${styles.linkBtn} ${styles.linkBtnDefault}`}
                            onClick={() => {
                              setSelectedTool(tool);
                              setCallArgs('{}');
                              setCallModalVisible(true);
                            }}
                          >
                            <PlayCircleOutlined /> 调用
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Add server modal */}
        {addModalVisible && (
          <div className={styles.modalOverlay} onClick={() => setAddModalVisible(false)}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
              <div className={styles.modalHeader}>
                <span className={styles.modalTitle}>添加 MCP 服务器</span>
                <button className={styles.closeBtn} onClick={() => setAddModalVisible(false)}>
                  <CloseOutlined />
                </button>
              </div>
              <div className={styles.modalBody}>
                <div className={styles.formField}>
                  <label className={styles.formLabel}>服务器名称 *</label>
                  <input
                    className={styles.formInput}
                    placeholder="例如: filesystem"
                    value={addForm.name}
                    onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                  />
                </div>
                <div className={styles.formField}>
                  <label className={styles.formLabel}>传输类型 *</label>
                  <select
                    className={styles.formSelect}
                    value={addForm.transport}
                    onChange={(e) =>
                      setAddForm({ ...addForm, transport: e.target.value as 'stdio' | 'sse' })
                    }
                  >
                    <option value="stdio">stdio (本地进程)</option>
                    <option value="sse">sse (HTTP/SSE)</option>
                  </select>
                </div>
                {addForm.transport === 'stdio' ? (
                  <>
                    <div className={styles.formField}>
                      <label className={styles.formLabel}>命令 *</label>
                      <input
                        className={styles.formInput}
                        placeholder="例如: npx"
                        value={addForm.command}
                        onChange={(e) => setAddForm({ ...addForm, command: e.target.value })}
                      />
                    </div>
                    <div className={styles.formField}>
                      <label className={styles.formLabel}>参数 (空格分隔)</label>
                      <input
                        className={styles.formInput}
                        placeholder="例如: -y @modelcontextprotocol/server-filesystem /path"
                        value={addForm.args}
                        onChange={(e) => setAddForm({ ...addForm, args: e.target.value })}
                      />
                    </div>
                  </>
                ) : (
                  <div className={styles.formField}>
                    <label className={styles.formLabel}>URL *</label>
                    <input
                      className={styles.formInput}
                      placeholder="例如: http://localhost:8080/sse"
                      value={addForm.url}
                      onChange={(e) => setAddForm({ ...addForm, url: e.target.value })}
                    />
                  </div>
                )}
              </div>
              <div className={styles.modalFooter}>
                <button
                  className={`${styles.btn} ${styles.btnDefault}`}
                  onClick={() => setAddModalVisible(false)}
                >
                  取消
                </button>
                <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleAddServer}>
                  添加
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Call tool modal */}
        {callModalVisible && selectedTool && (
          <div className={styles.modalOverlay} onClick={() => setCallModalVisible(false)}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
              <div className={styles.modalHeader}>
                <span className={styles.modalTitle}>调用工具: {selectedTool.name}</span>
                <button className={styles.closeBtn} onClick={() => setCallModalVisible(false)}>
                  <CloseOutlined />
                </button>
              </div>
              <div className={styles.modalBody}>
                <p className={styles.schemaDesc}>{selectedTool.description}</p>
                <hr className={styles.divider} />
                <div className={styles.formField}>
                  <label className={styles.formLabel}>参数 (JSON 格式)</label>
                  <textarea
                    className={styles.codeTextarea}
                    rows={8}
                    value={callArgs}
                    onChange={(e) => setCallArgs(e.target.value)}
                  />
                </div>
                {selectedTool.input_schema && (
                  <>
                    <hr className={styles.divider} />
                    <p className={styles.schemaTitle}>参数 Schema:</p>
                    <pre className={styles.schemaPre}>
                      {JSON.stringify(selectedTool.input_schema, null, 2)}
                    </pre>
                  </>
                )}
              </div>
              <div className={styles.modalFooter}>
                <button
                  className={`${styles.btn} ${styles.btnDefault}`}
                  onClick={() => setCallModalVisible(false)}
                >
                  取消
                </button>
                <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleCallTool}>
                  调用
                </button>
              </div>
            </div>
          </div>
        )}
      </MotionItem>
    </MotionList>
  );
}
