import { message } from 'antd';

type NotifyLevel = 'success' | 'warning' | 'error' | 'info';

interface NotifyAdapter {
  success: (content: string) => void;
  warning: (content: string) => void;
  error: (content: string) => void;
  info: (content: string) => void;
}

const defaultAdapter: NotifyAdapter = {
  success: (content) => {
    message.success(content);
  },
  warning: (content) => {
    message.warning(content);
  },
  error: (content) => {
    message.error(content);
  },
  info: (content) => {
    message.info(content);
  },
};

let activeAdapter: NotifyAdapter = defaultAdapter;

export const notify = {
  success: (content: string) => activeAdapter.success(content),
  warning: (content: string) => activeAdapter.warning(content),
  error: (content: string) => activeAdapter.error(content),
  info: (content: string) => activeAdapter.info(content),
  emit: (level: NotifyLevel, content: string) => activeAdapter[level](content),
};

export const setNotifyAdapter = (adapter: Partial<NotifyAdapter> | null) => {
  if (!adapter) {
    activeAdapter = defaultAdapter;
    return;
  }

  activeAdapter = {
    ...defaultAdapter,
    ...adapter,
  };
};
