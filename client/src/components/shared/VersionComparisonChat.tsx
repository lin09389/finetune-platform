import React, { useState } from 'react';
import { SendOutlined, LoadingOutlined, SwapOutlined } from '@ant-design/icons';
import { Select } from 'antd';
import styles from './VersionComparisonChat.module.css';
import { streamInference } from '../../services/api';

interface VersionComparisonChatProps {
  modelOptions: { value: string; label: string }[];
  currentBackend: string;
}

const VersionComparisonChat: React.FC<VersionComparisonChatProps> = ({ modelOptions, currentBackend }) => {
  const [modelA, setModelA] = useState<string>();
  const [modelB, setModelB] = useState<string>();
  const [prompt, setPrompt] = useState('');
  
  const [responseA, setResponseA] = useState('');
  const [responseB, setResponseB] = useState('');
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);

  const handleSend = async () => {
    if (!prompt.trim() || (!modelA && !modelB)) return;

    if (modelA) {
      setLoadingA(true);
      setResponseA('');
      streamInference({
        modelId: modelA,
        prompt,
        maxTokens: 1024,
        temperature: 0.7,
        backend: currentBackend
      }, (text) => setResponseA(prev => prev + text))
      .catch(e => setResponseA('Error: ' + e.message))
      .finally(() => setLoadingA(false));
    }

    if (modelB) {
      setLoadingB(true);
      setResponseB('');
      streamInference({
        modelId: modelB,
        prompt,
        maxTokens: 1024,
        temperature: 0.7,
        backend: currentBackend
      }, (text) => setResponseB(prev => prev + text))
      .catch(e => setResponseB('Error: ' + e.message))
      .finally(() => setLoadingB(false));
    }
  };

  return (
    <div className={`deep-tech-panel ${styles.comparisonContainer}`}>
      <div className={styles.splitView}>
        {/* Model A */}
        <div className={styles.modelPane}>
          <div className={styles.paneHeader}>
            <span className={styles.modelTag}>Model A</span>
            <Select 
              className="deepSelect"
              placeholder="Select Baseline Model"
              options={modelOptions}
              value={modelA}
              onChange={setModelA}
              style={{ width: '100%', maxWidth: '200px' }}
            />
          </div>
          <div className={`${styles.chatOutput} ${loadingA ? styles.glowA : ''}`}>
             {responseA || 'Awaiting input...'}
             {loadingA && <LoadingOutlined style={{ marginLeft: 8 }} spin />}
          </div>
        </div>

        <div className={styles.vsDivider}>
          <SwapOutlined /> VS
        </div>

        {/* Model B */}
        <div className={styles.modelPane}>
          <div className={styles.paneHeader}>
            <span className={styles.modelTag} style={{color: 'var(--accent-neon-cyan)', borderColor: 'var(--accent-neon-cyan)'}}>Model B</span>
            <Select 
              className="deepSelect"
              placeholder="Select Fine-tuned Model"
              options={modelOptions}
              value={modelB}
              onChange={setModelB}
              style={{ width: '100%', maxWidth: '200px' }}
            />
          </div>
          <div className={`${styles.chatOutput} ${loadingB ? styles.glowB : ''}`}>
             {responseB || 'Awaiting input...'}
             {loadingB && <LoadingOutlined style={{ marginLeft: 8 }} spin />}
          </div>
        </div>
      </div>

      <div className={styles.inputArea}>
        <textarea
          className={styles.promptInput}
          placeholder="Enter prompt for A/B testing..."
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button 
          className={styles.sendButton}
          disabled={!prompt.trim() || (!modelA && !modelB) || (loadingA || loadingB)}
          onClick={handleSend}
        >
          <SendOutlined /> <span>Run Comparison</span>
        </button>
      </div>
    </div>
  );
};

export default VersionComparisonChat;
