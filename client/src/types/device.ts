/**
 * 设备相关类型定义
 */

export interface DeviceInfo {
  platform: string;
  device_name: string;
  vram_total: number;
  vram_used: number;
  vram_free: number;
  memory_total: number;
  memory_used: number;
  memory_free: number;
  cuda_available: boolean;
  mps_available: boolean;
  cpu_count: number;
  cpu_percent: number;
}

export interface VRAMInfo {
  cuda_available: boolean;
  device_name: string;
  total_gb: number;
  allocated_gb: number;
  reserved_gb: number;
  free_gb: number;
}

export interface MemoryInfo {
  virtual: {
    total_gb: number;
    used_gb: number;
    available_gb: number;
    percent: number;
  };
  swap: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    percent: number;
  };
}

export interface DiskInfo {
  device: string;
  mountpoint: string;
  fstype: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  percent: number;
}
