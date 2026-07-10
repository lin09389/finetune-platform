import { describe, expect, it } from 'vitest';
import {
  isExperimentalEnabled,
  isExperimentalRoute,
  ROUTE_CAPABILITY,
  tierLabel,
} from '../capability/tiers';

describe('capability tiers helpers', () => {
  it('maps experimental SPA routes', () => {
    expect(isExperimentalRoute('/gateway')).toBe(true);
    expect(isExperimentalRoute('/heartbeat')).toBe(true);
    expect(isExperimentalRoute('/cua-control')).toBe(true);
    expect(isExperimentalRoute('/dashboard')).toBe(false);
    expect(ROUTE_CAPABILITY['/memory']?.tier).toBe('beta');
  });

  it('keeps /agent as the GA Agent Workbench entry route', () => {
    expect(ROUTE_CAPABILITY['/agent']).toEqual({ id: 'chat_sessions', tier: 'ga' });
  });

  it('treats legacy /modelhub as GA models (redirect target of unified runtime center)', () => {
    expect(ROUTE_CAPABILITY['/models']?.id).toBe('models');
    expect(ROUTE_CAPABILITY['/models']?.tier).toBe('ga');
    expect(ROUTE_CAPABILITY['/modelhub']?.id).toBe('models');
    expect(ROUTE_CAPABILITY['/modelhub']?.tier).toBe('ga');
    expect(isExperimentalRoute('/modelhub')).toBe(false);
  });

  it('does not treat cloud-api as experimental (backend cloud_chat is always-on auxiliary)', () => {
    expect(isExperimentalRoute('/cloud-api')).toBe(false);
    expect(ROUTE_CAPABILITY['/cloud-api']?.tier).toBe('beta');
    expect(ROUTE_CAPABILITY['/cloud-api']?.id).toBe('cloud_chat');
  });

  it('reads experimental_enabled from /api/info payload', () => {
    expect(isExperimentalEnabled({ experimental_enabled: false })).toBe(false);
    expect(isExperimentalEnabled({ experimental_enabled: true })).toBe(true);
    // offline optimistic default
    expect(isExperimentalEnabled(null)).toBe(true);
  });

  it('tier labels', () => {
    expect(tierLabel('ga')).toBe('GA');
    expect(tierLabel('beta')).toBe('Beta');
    expect(tierLabel('experimental')).toBe('Exp');
  });
});
