/**
 * Soft-block experimental SPA routes when /api/info reports experimental disabled.
 */
import { Result, Button } from 'antd';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../services/api';
import { useAppStore } from '../store/appStore';
import {
  ApiInfoCapabilityPayload,
  isExperimentalEnabled,
  isExperimentalRoute,
} from './tiers';

export default function ExperimentalRouteGuard({
  path,
  children,
}: {
  path: string;
  children: React.ReactNode;
}) {
  const backendStatus = useAppStore(s => s.backendStatus);
  const [info, setInfo] = useState<ApiInfoCapabilityPayload | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!isExperimentalRoute(path)) {
      setLoaded(true);
      return;
    }
    if (backendStatus !== 'connected') {
      setLoaded(true);
      return;
    }
    let cancelled = false;
    apiClient
      .get('/api/info')
      .then(res => {
        if (!cancelled) {
          setInfo(res.data as ApiInfoCapabilityPayload);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setInfo(null);
          setLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [path, backendStatus]);

  if (!isExperimentalRoute(path)) {
    return <>{children}</>;
  }

  if (!loaded) {
    return null;
  }

  if (!isExperimentalEnabled(info)) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '50vh',
        }}
        data-testid="experimental-disabled-guard"
      >
        <Result
          status="403"
          title="实验能力未启用"
          subTitle="当前后端已关闭 ENABLE_EXPERIMENTAL_CAPABILITIES。核心 GA 功能不受影响。"
          extra={
            <Link to="/dashboard">
              <Button type="primary">返回仪表盘</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return <>{children}</>;
}
