// Simplified models matching the new API - no legacy support

// Common benchmark metadata (kept for compatibility)
export interface BenchmarkMeta {
  benchmark_name: string;
  host: string;
  platform: string;
  timestamp: number;
}

// Performance metrics (kept for compatibility)
export interface PerformanceMetrics {
  elapsed_seconds: number;
  throughput?: number;
  memory_usage_mb?: number;
  [key: string]: any; // Allow additional metrics
}

// Build timing information (kept for compatibility)
export interface BuildTiming {
  config_time_seconds: number;
  build_time_seconds: number;
  total_time_seconds: number;
}

// Clean hardware information from the simplified API
export interface CleanHardwareInfo {
  id: string;
  name: string;
  type: 'cpu' | 'gpu';
  manufacturer: string;
  cores?: number;
  threads?: number;
  framework?: string;
  memory_mb?: number;
}

// Benchmark summary from the API
export interface BenchmarkSummary {
  total_benchmarks: number;
  benchmark_types: string[];
  latest_run: number;
  best_performance?: { [key: string]: any };
}

// Clean hardware summary from the simplified API
export interface CleanHardwareSummary {
  hardware: CleanHardwareInfo;
  benchmarks: BenchmarkSummary;
  comparison_url: string;
}

// Simplified hardware list response
export interface SimpleHardwareListData {
  cpus: CleanHardwareSummary[];
  gpus: CleanHardwareSummary[];
  total_hardware: number;
  total_benchmarks: number;
  supported_benchmarks: string[];
}

export interface SimpleHardwareListResponse {
  data: SimpleHardwareListData;
  timestamp: number;
}

// For backward compatibility with existing components
export interface HardwareInfo extends CleanHardwareInfo {
  // Kept for compatibility
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
  memory_mb: number; // Memory in MB
  framework?: string; // CUDA, HIP, OPENCL, etc.
}

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

// Hardware detail response
export interface HardwareDetail {
  hardware: CleanHardwareInfo;
  benchmarks: BenchmarkSummary;
  benchmark_history: Array<{ benchmark_type: string; timestamp: number; run_id: string }>;
  processed_benchmarks: ProcessedBenchmarkData[];
}

export interface HardwareDetailResponse {
  data: HardwareDetail;
  timestamp: number;
}

// API response types - simplified without success field
export interface ProcessedBenchmarkData {
  benchmark_type: string;
  hardware_type: 'cpu' | 'gpu';
  data_points: ProcessedDataPoint[];
  median_values: { [key: string]: any };
  stats: { [key: string]: any };
  file_count: number;
  valid_file_count: number;
}

export interface ProcessedDataPoint {
  group?: string;
  run_count?: number;
  // Type-specific properties
  type?: string; // For reversan (depth/threads)
  depth?: number; // For reversan depth tests
  threads?: number; // For reversan thread tests
  thread_count?: number; // For 7zip
  tokens_per_second_median?: number; // For llama
  tokens_per_second?: number; // For llama
  nodes_per_second_median?: number; // For reversan
  render_time_median?: number; // For blender
  render_time?: number; // For blender
  compression_mips_median?: number; // For 7zip
  decompression_mips_median?: number; // For 7zip
  total_mips_median?: number; // For 7zip
  total_mips?: number; // For 7zip
  elapsed_seconds?: number; // For reversan
  scene?: string; // For blender
  run_data?: any; // Additional run data
  [key: string]: any; // For additional benchmark-specific metrics
}

export interface ProcessedBenchmarkResponse {
  data: ProcessedBenchmarkData[];
  timestamp: number;
}

// For backward compatibility - old response format
export interface HardwareListResponse {
  data: {
    cpus: HardwareSummary[];
    gpus: HardwareSummary[];
  };
  timestamp: number;
}

export interface OldHardwareDetailResponse {
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