import { useMemo } from 'react';

export function useTypewriter(content: string, isStreaming: boolean, speed: number = 45) {
  void speed;
  // Pre-process content to fix unclosed markdown and add streaming cursor
  const processedContent = useMemo(() => {
    let text = content;
    if (isStreaming) {
      const codeBlockCount = (text.match(/```/g) || []).length;
      if (codeBlockCount % 2 !== 0) {
        // Unclosed code block: put cursor inside the code block and auto-close it
        text += '<span class="gemini-cursor"></span>\n```';
      } else {
        // Normal text: just append the cursor
        text += '<span class="gemini-cursor"></span>';
      }
    }
    return text;
  }, [content, isStreaming]);

  return { displayContent: content, processedContent, isDoneTyping: !isStreaming };
}
