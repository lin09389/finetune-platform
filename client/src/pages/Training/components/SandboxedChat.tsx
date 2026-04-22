import React, { useState, useRef, useEffect } from 'react';
import { MessageOutlined, SendOutlined } from '@ant-design/icons';
import styles from './SandboxedChat.module.css';

const SandboxedChat: React.FC = () => {
  const [messages, setMessages] = useState<{role: string, content: string}[]>([
    { role: 'system', content: '↯ sandbox initialized — ready for inference' }
  ]);
  const [input, setInput] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;
    setMessages(prev => [...prev, { role: 'user', content: input }]);
    setInput('');
    setTimeout(() => {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Mock response from fine-tuned model. Connect a real checkpoint to see live output.' }]);
    }, 800);
  };

  return (
    <div className={`deep-tech-panel ${styles.chatContainer}`}>
      <div className={styles.chatHeader}>
        <MessageOutlined className={styles.iconPurple} />
        <h2>Sandbox</h2>
        <span className={styles.chatSubtitle}>Playground</span>
      </div>
      
      <div className={styles.messageList} ref={listRef}>
        {messages.map((m, i) => (
          <div key={i} className={`${styles.message} ${styles[m.role]}`}>
            <div className={styles.bubble}>{m.content}</div>
          </div>
        ))}
      </div>

      <div className={styles.inputArea}>
        <input 
          className={styles.chatInput} 
          value={input} 
          onChange={e => setInput(e.target.value)} 
          placeholder="Test your model..."
          onKeyDown={e => e.key === 'Enter' && handleSend()}
        />
        <button className={styles.sendBtn} onClick={handleSend}>
          <SendOutlined />
        </button>
      </div>
    </div>
  );
};

export default SandboxedChat;
