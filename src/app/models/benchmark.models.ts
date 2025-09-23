// Common benchmark metadata
export interface BenchmarkMeta {
  benchmark_name: string;
  host: string;
  platform: string;
  timestamp: number;
}

// Hardware information extracted from benchmarks
export interface HardwareInfo {
  id: string;
  name: string;
  type: 'cpu' | 'gpu';
  manufacturer?: string;
  architecture?: string;
  cores?: number;
  threads?: number;
  clockSpeed?: number;
  memory?: number; // In MB for GPU, GB for system
  framework?: string; // For GPUs: CUDA, HIP, OPENCL, etc.
  deviceFramework?: string; // Alternative name for framework
}

// CPU specific information
export interface CpuInfo extends HardwareInfo {
  type: 'cpu';
  cores: number;
  threads: number;
  clockSpeed?: number; // MHz
  cacheSize?: number; // KB
}

// GPU specific information
export interface GpuInfo extends HardwareInfo {
  type: 'gpu';
  memory: number; // Memory in MB
  framework?: string; // CUDA, HIP, OPENCL, etc.
  deviceFramework?: string; // Alternative name for framework
}

// Build timing information (for compile-time benchmarks)
export interface BuildTiming {
  config_time_seconds: number;
  build_time_seconds: number;
  total_time_seconds: number;
}

// Performance metrics for different benchmark types
export interface PerformanceMetrics {
  elapsed_seconds: number;
  throughput?: number;
  memory_usage_mb?: number;
  [key: string]: any; // Allow additional metrics
}

// Benchmark result summary for hardware listing
export interface HardwareSummary {
  hardware: HardwareInfo;
  benchmarkCount: number;
  lastUpdated: Date;
  bestPerformance?: {
    benchmark: string;
    value: number;
    unit: string;
  };
  averagePerformance?: {
    [benchmarkType: string]: number;
  };
}

// API response types
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: number;
}

export interface HardwareListResponse {
  cpus: HardwareSummary[];
  gpus: HardwareSummary[];
  totalCount: number;
}

export interface HardwareDetailResponse {
  hardware: HardwareInfo;
  benchmarks: BenchmarkResult[];
  charts?: ChartData[];
}

// Chart configuration for visualization
export interface ChartData {
  type: 'line' | 'bar' | 'scatter';
  title: string;
  xAxis: {
    label: string;
    data: (string | number)[];
  };
  yAxis: {
    label: string;
    unit?: string;
  };
  series: ChartSeries[];
}

export interface ChartSeries {
  name: string;
  data: number[];
  color?: string;
  type?: 'line' | 'bar';
}

// Individual benchmark result
export interface BenchmarkResult {
  id: string;
  meta: BenchmarkMeta;
  hardware: HardwareInfo;
  benchmarkType: '7zip' | 'reversan' | 'llama' | 'blender';
  results: any; // Raw benchmark data
  performance: PerformanceMetrics;
  buildTiming?: BuildTiming;
  uploadedAt: Date;
}