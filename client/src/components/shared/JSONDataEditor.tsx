import React from 'react';
import Editor from '@monaco-editor/react';

interface JSONDataEditorProps {
  data?: unknown;
  value?: string;
  readOnly?: boolean;
  onChange?: (value: string | undefined) => void;
  height?: string | number;
}

const JSONDataEditor: React.FC<JSONDataEditorProps> = ({ 
  data, 
  value,
  readOnly = true, 
  onChange,
  height = "100%" 
}) => {
  const displayValue = value !== undefined ? value : (data !== undefined ? JSON.stringify(data, null, 2) : '');

  return (
    <Editor
      height={height}
      defaultLanguage="json"
      theme="vs-dark"
      value={displayValue}
      onChange={onChange}
      options={{
        readOnly,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        fontSize: 14,
        fontFamily: 'var(--font-mono)',
        padding: { top: 16, bottom: 16 },
      }}
    />
  );
};

export default JSONDataEditor;
