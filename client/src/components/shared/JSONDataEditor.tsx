import React from 'react';
import Editor from '@monaco-editor/react';

interface JSONDataEditorProps {
  data: any;
  readOnly?: boolean;
}

const JSONDataEditor: React.FC<JSONDataEditorProps> = ({ data, readOnly = true }) => {
  return (
    <Editor
      height="100%"
      defaultLanguage="json"
      theme="vs-dark"
      value={JSON.stringify(data, null, 2)}
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
