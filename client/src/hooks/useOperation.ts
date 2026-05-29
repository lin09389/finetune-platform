import { useCallback, useMemo, useRef, useState } from 'react';
import { parseError } from '../utils/errorHandler';
import { appModal } from '../utils/modal';
import { notify } from '../utils/notify';

type OperationKey = string;

type ConfirmTone = 'default' | 'danger';

interface ConfirmConfig {
  title: string;
  content?: string;
  okText?: string;
  cancelText?: string;
  tone?: ConfirmTone;
}

interface OperationOptions<T> {
  key?: OperationKey;
  loadingText?: string;
  successText?: string | ((result: T) => string | undefined);
  errorText?: string;
  confirm?: ConfirmConfig;
  silent?: boolean;
}

interface OperationState {
  pending: boolean;
  activeKey?: OperationKey;
  isRunning: (key?: OperationKey) => boolean;
}

function resolveSuccessText<T>(value: OperationOptions<T>['successText'], result: T) {
  return typeof value === 'function' ? value(result) : value;
}

export function useOperation() {
  const [activeKeys, setActiveKeys] = useState<Set<OperationKey>>(new Set());
  const activeKeysRef = useRef(activeKeys);

  const updateActiveKeys = useCallback((updater: (current: Set<OperationKey>) => Set<OperationKey>) => {
    setActiveKeys((current) => {
      const next = updater(current);
      activeKeysRef.current = next;
      return next;
    });
  }, []);

  const isRunning = useCallback((key: OperationKey = 'default') => activeKeysRef.current.has(key), []);

  const run = useCallback(
    async <T,>(task: () => Promise<T>, options: OperationOptions<T> = {}): Promise<T | undefined> => {
      const key = options.key || 'default';
      if (activeKeysRef.current.has(key)) {
        return undefined;
      }

      const execute = async () => {
        updateActiveKeys((current) => new Set(current).add(key));
        if (options.loadingText && !options.silent) {
          notify.info(options.loadingText);
        }
        try {
          const result = await task();
          const successText = resolveSuccessText(options.successText, result);
          if (successText && !options.silent) {
            notify.success(successText);
          }
          return result;
        } catch (error) {
          const parsed = parseError(error, options.errorText);
          if (!options.silent) {
            notify.error(parsed.message);
          }
          return undefined;
        } finally {
          updateActiveKeys((current) => {
            const next = new Set(current);
            next.delete(key);
            return next;
          });
        }
      };

      if (!options.confirm) {
        return execute();
      }

      return new Promise<T | undefined>((resolve) => {
        appModal.confirm({
          title: options.confirm?.title,
          content: options.confirm?.content,
          okText: options.confirm?.okText || '确认',
          cancelText: options.confirm?.cancelText || '取消',
          okButtonProps: options.confirm?.tone === 'danger' ? { danger: true } : undefined,
          onOk: async () => {
            resolve(await execute());
          },
          onCancel: () => resolve(undefined),
        });
      });
    },
    [updateActiveKeys],
  );

  const state: OperationState = useMemo(
    () => ({
      pending: activeKeys.size > 0,
      activeKey: Array.from(activeKeys)[0],
      isRunning,
    }),
    [activeKeys, isRunning],
  );

  return { run, ...state };
}

