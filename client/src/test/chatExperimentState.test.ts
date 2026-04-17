import { describe, expect, it } from 'vitest';

import {
  addExperimentSnapshotRecord,
  clearActiveExperimentCandidates,
  deleteExperimentPreset,
  initialChatExperimentState,
  saveExperimentPreset,
  setActiveExperimentCandidates,
  updateExperimentSnapshotRecord,
} from '../store/chatExperimentState';

describe('chatExperimentState helpers', () => {
  it('provides a stable initial experiment state contract', () => {
    expect(initialChatExperimentState.activeCandidates).toEqual([]);
    expect(initialChatExperimentState.selectedCandidateId).toBeNull();
    expect(initialChatExperimentState.responseView).toBe('response');
    expect(initialChatExperimentState.presets).toEqual([]);
  });

  it('handles candidate activation and snapshot updates', () => {
    const candidates = [
      { id: 'cand-1', index: 0, content: 'A', status: 'completed' as const },
      { id: 'cand-2', index: 1, content: 'B', status: 'completed' as const },
    ];

    const activated = setActiveExperimentCandidates(candidates);
    const cleared = clearActiveExperimentCandidates();
    const snapshotResult = addExperimentSnapshotRecord([], {
      id: 'snap-1',
      createdAt: '2026-04-09T10:00:00.000Z',
      title: 'Experiment',
      response: 'A',
      selectedCandidateId: 'cand-1',
      candidates,
      experiment_config: {
        prompt: 'hello',
        systemPrompt: '',
        responseFormat: 'text',
        modelId: 'qwen',
        backend: 'ollama',
        temperature: 0.7,
        topP: 0.9,
        maxTokens: 1024,
        useKnowledge: false,
        useMemory: false,
        autoRetrieve: true,
        candidateCount: 2,
        attachments: [],
      },
    });
    const updated = updateExperimentSnapshotRecord(
      snapshotResult.experimentSnapshots,
      'snap-1',
      { title: 'Updated experiment' },
      snapshotResult.lastRunMetadata,
    );

    expect(activated.selectedCandidateId).toBe('cand-1');
    expect(cleared.activeCandidates).toEqual([]);
    expect(snapshotResult.selectedExperimentId).toBe('snap-1');
    expect(updated.experimentSnapshots[0]?.title).toBe('Updated experiment');
    expect(updated.lastRunMetadata?.title).toBe('Updated experiment');
  });

  it('handles preset upsert and delete consistently', () => {
    const preset = {
      id: 'preset-1',
      name: 'Default',
      createdAt: '2026-04-09T10:00:00.000Z',
      updatedAt: '2026-04-09T10:00:00.000Z',
      config: {
        prompt: 'hello',
        systemPrompt: '',
        responseFormat: 'text' as const,
        modelId: 'qwen',
        backend: 'ollama' as const,
        temperature: 0.7,
        topP: 0.9,
        maxTokens: 1024,
        useKnowledge: false,
        useMemory: false,
        autoRetrieve: true,
        candidateCount: 1,
        attachments: [],
      },
    };

    const saved = saveExperimentPreset([], preset);
    const updated = saveExperimentPreset(saved.presets, {
      ...preset,
      name: 'Updated',
    });
    const deleted = deleteExperimentPreset(updated.presets, 'preset-1', 'preset-1');

    expect(saved.presets).toHaveLength(1);
    expect(updated.presets[0]?.name).toBe('Updated');
    expect(deleted.presets).toEqual([]);
    expect(deleted.selectedPresetId).toBeNull();
  });
});
