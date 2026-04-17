import type { PlaygroundCandidate, PlaygroundPreset, PlaygroundSnapshot } from '../types';

export interface ChatExperimentState {
  activeCandidates: PlaygroundCandidate[];
  selectedCandidateId: string | null;
  selectedExperimentId: string | null;
  responseView: 'response' | 'patch' | 'sources' | 'metadata' | 'raw';
  lastRunMetadata: PlaygroundSnapshot | null;
  experimentSnapshots: PlaygroundSnapshot[];
  presets: PlaygroundPreset[];
  selectedPresetId: string | null;
}

export const initialChatExperimentState: ChatExperimentState = {
  activeCandidates: [],
  selectedCandidateId: null,
  selectedExperimentId: null,
  responseView: 'response',
  lastRunMetadata: null,
  experimentSnapshots: [],
  presets: [],
  selectedPresetId: null,
};

export function setActiveExperimentCandidates(activeCandidates: PlaygroundCandidate[]) {
  return {
    activeCandidates,
    selectedCandidateId: activeCandidates[0]?.id || null,
  };
}

export function clearActiveExperimentCandidates() {
  return {
    activeCandidates: [],
    selectedCandidateId: null,
  };
}

export function addExperimentSnapshotRecord(
  existingSnapshots: PlaygroundSnapshot[],
  snapshot: PlaygroundSnapshot,
  limit = 100,
) {
  return {
    experimentSnapshots: [snapshot, ...existingSnapshots].slice(0, limit),
    selectedExperimentId: snapshot.id,
    activeCandidates: snapshot.candidates,
    selectedCandidateId: snapshot.selectedCandidateId,
    lastRunMetadata: snapshot,
  };
}

export function updateExperimentSnapshotRecord(
  existingSnapshots: PlaygroundSnapshot[],
  snapshotId: string,
  updates: Partial<PlaygroundSnapshot>,
  lastRunMetadata: PlaygroundSnapshot | null,
) {
  const experimentSnapshots = existingSnapshots.map((snapshot) =>
    snapshot.id === snapshotId ? { ...snapshot, ...updates } : snapshot,
  );

  return {
    experimentSnapshots,
    lastRunMetadata:
      lastRunMetadata?.id === snapshotId ? { ...lastRunMetadata, ...updates } : lastRunMetadata,
  };
}

export function saveExperimentPreset(
  existingPresets: PlaygroundPreset[],
  preset: PlaygroundPreset,
  limit = 50,
) {
  const existing = existingPresets.find((item) => item.id === preset.id);
  if (existing) {
    return {
      presets: existingPresets.map((item) => (item.id === preset.id ? preset : item)),
    };
  }

  return {
    presets: [preset, ...existingPresets].slice(0, limit),
  };
}

export function deleteExperimentPreset(
  existingPresets: PlaygroundPreset[],
  presetId: string,
  selectedPresetId: string | null,
) {
  return {
    presets: existingPresets.filter((preset) => preset.id !== presetId),
    selectedPresetId: selectedPresetId === presetId ? null : selectedPresetId,
  };
}
