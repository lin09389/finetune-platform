import { ArrowsAltOutlined, DisconnectOutlined, PauseCircleOutlined, ShrinkOutlined } from '@ant-design/icons';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { Button, Space, Tag } from 'antd';
import React, { useEffect, useRef, useState } from 'react';
import { getAgentTerminalWebSocketUrl } from '../../services/api';
import styles from './AgentTerminal.module.css';

type TerminalState = 'connecting' | 'connected' | 'closed' | 'error';

interface AgentTerminalProps {
  terminalId: string;
  running?: boolean;
  stdout?: string;
  stderr?: string;
  exitCode?: number;
}

const AgentTerminal: React.FC<AgentTerminalProps> = ({ terminalId, running, stdout, stderr, exitCode }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<TerminalState>(running ? 'connecting' : 'closed');
  const [interactive, setInteractive] = useState<boolean>(false);
  const [expanded, setExpanded] = useState<boolean>(Boolean(running));

  useEffect(() => {
    if (!containerRef.current) return;
    const terminal = new Terminal({
      convertEol: true,
      cursorBlink: Boolean(running),
      fontFamily: 'Consolas, "Cascadia Mono", "SFMono-Regular", monospace',
      fontSize: 12,
      lineHeight: 1.25,
      scrollback: 3000,
      theme: {
        background: '#090d12',
        foreground: '#d6e2ea',
        cursor: '#73e2a7',
        selectionBackground: '#244a5f',
      },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.loadAddon(new WebLinksAddon());
    terminal.open(containerRef.current);
    fit.fit();
    terminalRef.current = terminal;
    fitRef.current = fit;

    if (!running && (stdout || stderr || exitCode !== undefined)) {
      terminal.write(`exit_code: ${exitCode ?? ''}\r\n${stdout || ''}${stderr ? `\r\n${stderr}` : ''}`);
    }

    const resizeObserver = new ResizeObserver(() => {
      fit.fit();
      const socket = socketRef.current;
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }));
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      socketRef.current?.close();
      terminal.dispose();
      terminalRef.current = null;
      fitRef.current = null;
    };
  }, [terminalId]);

  useEffect(() => {
    if (!running) return;
    const terminal = terminalRef.current;
    if (!terminal) return;
    const socket = new WebSocket(getAgentTerminalWebSocketUrl(terminalId));
    socketRef.current = socket;
    setState('connecting');

    const inputDisposable = terminal.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'input', data }));
      }
    });

    socket.onopen = () => {
      setState('connected');
      fitRef.current?.fit();
      socket.send(JSON.stringify({ type: 'resize', cols: terminal.cols, rows: terminal.rows }));
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'ready') {
          setInteractive(Boolean(message.interactive));
        } else if (message.type === 'output') {
          terminal.write(String(message.data || ''));
        } else if (message.type === 'exit') {
          terminal.write(`\r\n[process exited with code ${message.exit_code}]\r\n`);
          setState('closed');
        } else if (message.type === 'error') {
          terminal.write(`\r\n[terminal error] ${message.message || 'unknown error'}\r\n`);
          setState('error');
        }
      } catch {
        terminal.write(String(event.data || ''));
      }
    };
    socket.onerror = () => setState('error');
    socket.onclose = () => setState((current) => (current === 'error' ? 'error' : 'closed'));

    return () => {
      inputDisposable.dispose();
      socket.close();
    };
  }, [terminalId, running]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => fitRef.current?.fit());
    return () => cancelAnimationFrame(frame);
  }, [expanded]);

  const interrupt = () => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'interrupt' }));
    }
  };

  return (
    <div className={styles.terminalShell}>
      <div className={styles.toolbar}>
        <Space size={6}>
          <span className={styles.dot} />
          <span className={styles.title}>Terminal</span>
          <Tag color={state === 'connected' ? 'green' : state === 'error' ? 'red' : 'default'}>
            {state === 'connected' ? (interactive ? 'TTY' : 'stream') : state}
          </Tag>
        </Space>
        {running ? (
          <Space size={4}>
            <Button size="small" type="text" icon={expanded ? <ShrinkOutlined /> : <ArrowsAltOutlined />} onClick={() => setExpanded((value) => !value)} />
            <Button size="small" icon={<PauseCircleOutlined />} onClick={interrupt}>
              Ctrl+C
            </Button>
          </Space>
        ) : (
          <Space size={4}>
            <Button size="small" type="text" icon={expanded ? <ShrinkOutlined /> : <ArrowsAltOutlined />} onClick={() => setExpanded((value) => !value)} />
            <DisconnectOutlined className={styles.closedIcon} />
          </Space>
        )}
      </div>
      <div ref={containerRef} className={`${styles.terminalBody} ${expanded ? styles.terminalBodyExpanded : ''}`} />
    </div>
  );
};

export default AgentTerminal;
