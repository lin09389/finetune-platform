import { Modal } from 'antd';

type ModalConfirmConfig = Parameters<typeof Modal.confirm>[0];
type ModalSuccessConfig = Parameters<typeof Modal.success>[0];

interface ModalAdapter {
  confirm: (config: ModalConfirmConfig) => void;
  success: (config: ModalSuccessConfig) => void;
}

const defaultAdapter: ModalAdapter = {
  confirm: (config) => {
    Modal.confirm(config);
  },
  success: (config) => {
    Modal.success(config);
  },
};

let activeAdapter: ModalAdapter = defaultAdapter;

export const appModal = {
  confirm: (config: ModalConfirmConfig) => activeAdapter.confirm(config),
  success: (config: ModalSuccessConfig) => activeAdapter.success(config),
};

export const setModalAdapter = (adapter: Partial<ModalAdapter> | null) => {
  if (!adapter) {
    activeAdapter = defaultAdapter;
    return;
  }

  activeAdapter = {
    ...defaultAdapter,
    ...adapter,
  };
};
