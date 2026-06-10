import { useCallback, useMemo } from 'react';

import { getSavedCloudProviderData } from '../../services/api';
import type { SavedCloudProvider } from '../../services/api';
import type { APIKeyConfig } from './chatNewUtils';

export function useCloudModelConfig(params: {
  cloudAIConfig: APIKeyConfig | null;
  cloudProviders: SavedCloudProvider[];
  setCloudAIConfig: (config: APIKeyConfig | null) => void;
  setSelectedCloudModel: (model: string) => void;
  setUseCloudAI: (value: boolean | ((previous: boolean) => boolean)) => void;
  openConfigModal: () => void;
}) {
  const {
    cloudAIConfig,
    cloudProviders,
    setCloudAIConfig,
    setSelectedCloudModel,
    setUseCloudAI,
    openConfigModal,
  } = params;

  const selectedCloudProvider = useMemo(
    () => cloudProviders.find((provider) => provider.provider === cloudAIConfig?.provider),
    [cloudAIConfig?.provider, cloudProviders],
  );

  const cloudProviderOptions = useMemo(
    () =>
      cloudProviders.map((provider) => ({
        id: provider.provider,
        name: `${provider.name || provider.provider} (${provider.provider})`,
      })),
    [cloudProviders],
  );

  const cloudModelOptions = useMemo(() => {
    const models = selectedCloudProvider?.models?.length
      ? selectedCloudProvider.models
      : selectedCloudProvider?.default_model
        ? [selectedCloudProvider.default_model]
        : [];
    return models.map((model) => ({ id: model, name: model }));
  }, [selectedCloudProvider]);

  const handleCloudProviderChange = useCallback(
    async (provider: string) => {
      const selectedProvider = cloudProviders.find((item) => item.provider === provider);
      if (!selectedProvider) return;

      const keyData = await getSavedCloudProviderData(selectedProvider.id).catch(() => ({}));
      const models = keyData.models || selectedProvider.models || [];
      const nextModel = keyData.default_model || selectedProvider.default_model || models[0] || '';
      const config: APIKeyConfig = {
        provider: selectedProvider.provider,
        api_key: '',
        key_id: selectedProvider.id,
        model: nextModel,
        group_id: keyData.group_id || '',
        base_url: keyData.base_url || '',
      };
      setCloudAIConfig(config);
      setSelectedCloudModel(nextModel);
      localStorage.setItem('cloud_ai_config', JSON.stringify(config));
    },
    [cloudProviders, setCloudAIConfig, setSelectedCloudModel],
  );

  const handleCloudModelChange = useCallback(
    (model: string) => {
      setSelectedCloudModel(model);
      if (cloudAIConfig) {
        const nextConfig = { ...cloudAIConfig, model };
        setCloudAIConfig(nextConfig);
        localStorage.setItem('cloud_ai_config', JSON.stringify(nextConfig));
      }
    },
    [cloudAIConfig, setCloudAIConfig, setSelectedCloudModel],
  );

  const handleToggleCloudAI = useCallback(() => {
    if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
      openConfigModal();
      return;
    }
    setUseCloudAI((enabled) => !enabled);
  }, [cloudAIConfig?.api_key, cloudAIConfig?.key_id, openConfigModal, setUseCloudAI]);

  return {
    cloudProviderOptions,
    cloudModelOptions,
    handleCloudProviderChange,
    handleCloudModelChange,
    handleToggleCloudAI,
  };
}
