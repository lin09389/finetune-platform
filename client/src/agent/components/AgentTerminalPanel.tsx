import { CopyOutlined, PauseCircleOutlined } from '@ant-design/icons';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { Button, Empty, Input, Select, Tag, message } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { getAgentTerminalWebSocketUrl, type AgentSessionUiTimelineItem } from '../../services/api';
import { useTheme } from '../../theme';
import styles from './AgentTerminalPanel.module.css';

type TerminalState = 'snapshot' | 'connecting' | 'connected' | 'closed' | 'error';

interface TerminalRecord {
  id: string;
  title: string;
  command: string;
  stdout: string;
  stderr: string;
  exitCode?: number;
  running: boolean;
}

function terminalRecords(timeline: AgentSessionUiTimelineItem[]): TerminalRecord[] {
  const records = new Map<string, TerminalRecord>();
  for (const item of timeline) {
    if (item.type !== 'command') continue;
    const payload = item.payload || {};
    const terminalId = String(payload.terminal_id || item.part_id || item.id);
    records.set(terminalId, {
      id: terminalId,
      title: item.title || String(payload.command || '终端'),
      command: String(payload.command || ''),
      stdout: String(payload.stdout || item.content || ''),
      stderr: String(payload.stderr || ''),
      exitCode: typeof payload.exit_code === 'number' ? payload.exit_code : undefined,
      running: item.status === 'running' || item.status === 'pending',
    });
  }
  return Array.from(records.values()).reverse();
}

const stateLabels: Record<TerminalState, string> = {
  snapshot: '历史快照',
  connecting: '连接中',
  connected: '实时连接',
  closed: '已结束',
  error: '连接错误',
};

function readTerminalFontFamily(): string {
  if (typeof window === 'undefined') return 'ui-monospace, monospace';
  const token = getComputedStyle(document.documentElement).getPropertyValue('--font-mono').trim();
  return token || 'ui-monospace, monospace';
}

function readTerminalTheme() {
  const root = typeof document !== 'undefined' ? document.documentElement : null;
  const read = (name: string, fallback: string) => {
    if (!root) return fallback;
    const value = getComputedStyle(root).getPropertyValue(name).trim();
    return value || fallback;
  };
  return {
    background: read('--terminal-bg', '#1b1b19'),
    foreground: read('--terminal-fg', '#e8e6df'),
    cursor: read('--terminal-cursor', '#e8e6df'),
    selectionBackground: read('--terminal-selection', 'rgba(232,230,223,0.22)'),
  };
}

interface AgentTerminalPanelProps {
  timeline: AgentSessionUiTimelineItem[];
}

export default function AgentTerminalPanel({ timeline }: AgentTerminalPanelProps) {
  const { theme } = useTheme();
  const records = useMemo(() => terminalRecords(timeline), [timeline]);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const [state, setState] = useState<TerminalState>('snapshot');
  const [searchQuery, setSearchQuery] = useState('');
  const selected = records.find((record) => record.id === selectedId) || records[0];
  const terminalText = selected
    ? [selected.command, selected.stdout, selected.stderr].filter(Boolean).join('\n')
    : '';
  const matchCount = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return 0;
    return terminalText.toLowerCase().split(query).length - 1;
  }, [searchQuery, terminalText]);

  useEffect(() => {
    if (!selectedId && records[0]) setSelectedId(records[0].id);
  }, [records, selectedId]);

  useEffect(() => {
    if (!containerRef.current || !selected) return;
    const terminal = new Terminal({
      convertEol: true,
      cursorBlink: selected.running,
      fontFamily: readTerminalFontFamily(),
      fontSize: 12,
      lineHeight: 1.35,
      scrollback: 5000,
      theme: readTerminalTheme(),
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.loadAddon(new WebLinksAddon());
    terminal.open(containerRef.current);
    terminalRef.current = terminal;
    fitRef.current = fit;
    terminal.write(selected.command ? `$ ${selected.command}\r\n` : '');
    terminal.write(selected.stdout);
    if (selected.stderr) terminal.write(`\r\n${selected.stderr}`);
    if (!selected.running && selected.exitCode !== undefined) {
      terminal.write(`\r\n[process exited with code ${selected.exitCode}]\r\n`);
    }
    fit.fit();

    const resizeObserver = new ResizeObserver(() => {
      fit.fit();
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }));
      }
    });
    resizeObserver.observe(containerRef.current);

    if (selected.running && selected.id.startsWith('agt_')) {
      setState('connecting');
      const socket = new WebSocket(getAgentTerminalWebSocketUrl(selected.id));
      socketRef.current = socket;
      const input = terminal.onData((data) => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'input', data }));
        }
      });
      socket.onopen = () => {
        setState('connected');
        socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }));
      };
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(String(event.data));
          if (message.type === 'output') terminal.write(String(message.data || ''));
          if (message.type === 'exit') {
            terminal.write(`\r\n[process exited with code ${message.exit_code}]\r\n`);
            setState('closed');
          }
          if (message.type === 'error') {
            terminal.write(`\r\n[terminal error] ${message.message || 'unknown error'}\r\n`);
            setState('error');
          }
        } catch {
          terminal.write(String(event.data || ''));
        }
      };
      socket.onerror = () => setState('error');
      socket.onclose = () => setState((current) => current === 'error' ? 'error' : 'closed');
      return () => {
        input.dispose();
        resizeObserver.disconnect();
        socket.close();
        terminal.dispose();
        socketRef.current = null;
        terminalRef.current = null;
        fitRef.current = null;
      };
    }

    setState('snapshot');
    return () => {
      resizeObserver.disconnect();
      terminal.dispose();
      terminalRef.current = null;
      fitRef.current = null;
    };
  }, [selected]);

  // xterm stores a copy of its palette. Apply the CSS-token palette whenever
  // the application theme changes instead of requiring a terminal switch.
  useEffect(() => {
    const terminal = terminalRef.current;
    if (!terminal) return;
    terminal.options.theme = readTerminalTheme();
    terminal.options.fontFamily = readTerminalFontFamily();
  }, [theme]);

  if (!selected) {
    return <div className={styles.empty}><Empty description="运行命令后，终端输出会显示在这里" /></div>;
  }

  return (
    <section className={styles.shell} aria-label="Agent 终端">
      <header className={styles.toolbar}>
        <Select
          size="small"
          variant="borderless"
          value={selected.id}
          onChange={setSelectedId}
          options={records.map((record) => ({ value: record.id, label: record.title }))}
          aria-label="选择终端"
        />
        <Input
          className={styles.search}
          size="small"
          allowClear
          value={searchQuery}
          placeholder="搜索输出"
          aria-label="搜索终端输出"
          onChange={(event) => setSearchQuery(event.target.value)}
        />
        {searchQuery ? <Tag>{matchCount} 处</Tag> : null}
        <Tag color={state === 'error' ? 'red' : state === 'connected' ? 'green' : undefined}>
          {stateLabels[state]}
        </Tag>
        <Button
          size="small"
          icon={<CopyOutlined />}
          aria-label="复制终端输出"
          onClick={() => {
            const content = [
              selected.command ? `$ ${selected.command}` : '',
              selected.stdout,
              selected.stderr,
              selected.exitCode === undefined ? '' : `[process exited with code ${selected.exitCode}]`,
            ].filter(Boolean).join('\n');
            void navigator.clipboard.writeText(content)
              .then(() => message.success('终端输出已复制'))
              .catch(() => message.error('复制失败'));
          }}
        />
        {selected.running ? (
          <Button
            size="small"
            icon={<PauseCircleOutlined />}
            onClick={() => socketRef.current?.send(JSON.stringify({ type: 'interrupt' }))}
          >
            Ctrl+C
          </Button>
        ) : null}
      </header>
      <div ref={containerRef} className={styles.terminal} />
    </section>
  );
}
