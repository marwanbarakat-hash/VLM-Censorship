export interface EngineMetrics {
  fps: number;
  latencyMs: number;
  gpuMemoryMb: number;
  isCensoringActive: boolean;
  activeTargetsCount: number;
}

export interface TargetPrototype {
  id: string;
  label: string;
  promptText: string;
  threshold: number;
  createdAt: string;
}

export interface DetectionBox {
  id: string;
  label: string;
  confidence: number;
  x: number;      // 0.0 to 1.0 (relative percentage)
  y: number;
  width: number;
  height: number;
}