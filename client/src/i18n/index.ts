import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Locale = 'zh-CN' | 'en-US';

interface I18nState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

const translations = {
  'zh-CN': {
    app: {
      title: 'Finetune Platform',
      subtitle: '大模型微调平台',
    },
    nav: {
      device: '设备信息',
      models: '模型管理',
      datasets: '数据集',
      training: '模型训练',
      inference: '推理测试',
      history: '训练历史',
    },
    status: {
      connected: '已连接',
      disconnected: '未连接',
      checking: '检测中',
    },
    common: {
      loading: '加载中...',
      save: '保存',
      cancel: '取消',
      delete: '删除',
      confirm: '确认',
      refresh: '刷新',
      open: '打开',
      preview: '预览',
      success: '成功',
      error: '错误',
      warning: '警告',
    },
    device: {
      title: '设备信息',
      platform: '计算平台',
      cuda: 'NVIDIA CUDA',
      mac: 'Apple Silicon',
      unknown: '未知平台',
      vram: '显存 (VRAM)',
      memory: '系统内存 (RAM)',
      total: '总容量',
      used: '已使用',
      free: '剩余可用',
    },
  },
  'en-US': {
    app: {
      title: 'Finetune Platform',
      subtitle: 'LLM Fine-tuning Platform',
    },
    nav: {
      device: 'Device Info',
      models: 'Models',
      datasets: 'Datasets',
      training: 'Training',
      inference: 'Inference',
      history: 'History',
    },
    status: {
      connected: 'Connected',
      disconnected: 'Disconnected',
      checking: 'Checking',
    },
    common: {
      loading: 'Loading...',
      save: 'Save',
      cancel: 'Cancel',
      delete: 'Delete',
      confirm: 'Confirm',
      refresh: 'Refresh',
      open: 'Open',
      preview: 'Preview',
      success: 'Success',
      error: 'Error',
      warning: 'Warning',
    },
    device: {
      title: 'Device Information',
      platform: 'Platform',
      cuda: 'NVIDIA CUDA',
      mac: 'Apple Silicon',
      unknown: 'Unknown',
      vram: 'VRAM',
      memory: 'RAM',
      total: 'Total',
      used: 'Used',
      free: 'Free',
    },
  },
};

export const useI18n = create<I18nState>()(
  persist(
    (set) => ({
      locale: 'zh-CN',
      setLocale: (locale) => set({ locale }),
    }),
    {
      name: 'finetune-i18n',
    },
  ),
);

export function t(key: string): string {
  const { locale } = useI18n.getState();
  const keys = key.split('.');
  let value: unknown = translations[locale];

  for (const k of keys) {
    if (value && typeof value === 'object' && k in value) {
      value = (value as Record<string, unknown>)[k];
    } else {
      return key;
    }
  }

  return typeof value === 'string' ? value : key;
}

export function useTranslation() {
  const { locale, setLocale } = useI18n();
  return { t, locale, setLocale };
}
