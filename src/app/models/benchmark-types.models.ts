// 7zip specific models
export interface SevenZipResult {
  meta: {
    benchmark_name: '7zip';
    host: string;
    platform: string;
    timestamp: number;
  };
  build: {
    sevenzip_command: string;
    build_time_seconds: number;
    notes?: string;
  };
  runs: SevenZipRun[];
  test_data_size_mb?: number;
}

export interface SevenZipRun {
  success: boolean;
  threads: number;
  elapsed_seconds: number;
  archive_size_bytes: number;
  compression_ratio: number;
  compression_speed_mb_s: number;
  raw_output: string;
  speedup?: number;
  thread_efficiency_percent?: number;
}

// Reversan specific models
export interface ReversanResult {
  meta: {
    benchmark_name: 'reversan';
    host: string;
    platform: string;
    timestamp: number;
    gnu_time?: boolean;
    repo?: string;
    test_runs_per_config?: number;
  };
  build: {
    binary: string;
    compile_time_seconds: number;
    config_time_seconds: number;
    build_time_seconds: number;
    time_measurer?: string;
    threads_supported?: boolean;
    help_snippet?: string;
  };
  runs_depth?: ReversanDepthRun[];
  runs_threads?: ReversanThreadRun[];
}

export interface ReversanDepthRun {
  depth: number;
  returncode: number;
  metrics: ReversanMetrics;
  stderr_tail?: string;
  average_metrics?: ReversanMetrics;
}

export interface ReversanThreadRun {
  threads: number;
  returncode: number;
  metrics: ReversanMetrics;
  stderr_tail?: string;
  average_metrics?: ReversanMetrics;
}

export interface ReversanMetrics {
  max_rss_kb: number;
  user_seconds: number;
  sys_seconds: number;
  elapsed_seconds: number;
}

// Llama specific models
export interface LlamaResult {
  meta: {
    benchmark_name: 'llama';
    host: string;
    platform: string;
    timestamp: number;
    repo?: string;
    model_url?: string;
  };
  build: {
    cpu_build_timing?: {
      config_time_seconds: number;
      build_time_seconds: number;
      total_time_seconds: number;
    };
    cpu_bench_binary?: string;
    vulkan_bench_binary?: string;
    gpu_bench_binary?: string;
    vulkan_devices?: string[];
    vulkan_supported?: boolean;
  };
  runs_cpu?: LlamaCpuRun[];
  runs_gpu?: LlamaGpuRun[];
  gpu_selection?: LlamaGpuSelection;
}

export interface LlamaCpuRun {
  type: 'cpu';
  prompt_size: number;
  generation_size: number;
  ngl: number;
  returncode: number;
  elapsed_seconds: number;
  metrics: LlamaMetrics;
  raw_json?: any[];
}

export interface LlamaGpuRun {
  type: 'gpu';
  prompt_size: number;
  generation_size: number;
  ngl: number;
  returncode: number;
  elapsed_seconds: number;
  metrics: LlamaGpuMetrics;
  raw_json?: any[];
}

export interface LlamaMetrics {
  system_info: {
    cpu_info: string;
    gpu_info: string;
    backends: string;
    model_type: string;
    model_size: number;
    model_n_params: number;
    n_threads: number;
    n_gpu_layers: number;
  };
  prompt_processing: LlamaProcessingMetrics;
  generation: LlamaProcessingMetrics;
  tokens_per_second: number;
  total_time_ms: number;
}

export interface LlamaGpuMetrics {
  system_info: {
    cpu_info: string;
    gpu_info: string;
    backends: string;
    model_type: string;
    model_size: number;
    model_n_params: number;
    n_threads: number;
    n_gpu_layers: number;
  };
  prompt_processing?: LlamaProcessingMetrics;
  generation?: LlamaProcessingMetrics;
  tokens_per_second: number;
  total_time_ms: number;
}

export interface LlamaProcessingMetrics {
  avg_time_ns: number;
  avg_tokens_per_sec: number;
  stddev_time_ns: number;
  stddev_tokens_per_sec: number;
  avg_time_ms: number;
  samples_ns: number[];
  samples_ts: number[];
}

export interface LlamaGpuSelection {
  device_index?: number | null;
  vk_driver_files?: string | null;
  available_gpus?: LlamaGpuDevice[];
}

export interface LlamaGpuDevice {
  index: number;
  name: string;
  driver: string;
  icd_path?: string | null;
}

// Blender specific models
export interface BlenderResult {
  meta: {
    benchmark_name: 'blender';
    host: string;
    platform: string;
    timestamp: number;
    benchmark_url?: string;
  };
  build: {
    launcher_path: string;
    build_time_seconds: number;
    notes?: string;
  };
  device_runs: BlenderDeviceRun[];
  scenes_tested?: string[];
  successful_runs?: number;
  total_devices_tested?: number;
}

export interface BlenderDeviceRun {
  device_framework: 'CPU' | 'CUDA' | 'HIP' | 'OPENCL' | 'OPTIX' | 'METAL';
  scenes: string[];
  success: boolean;
  elapsed_seconds: number;
  scene_results?: any;
  total_score?: number;
  raw_json?: BlenderRawResult[];
  device_name?: string;
}

export interface BlenderRawResult {
  timestamp?: string;
  blender_version?: any;
  benchmark_launcher?: any;
  benchmark_script?: any;
  scene?: any;
  system_info?: {
    bitness?: string;
    machine?: string;
    system?: string;
    dist_name?: string;
    dist_version?: string;
    devices?: BlenderDevice[];
    num_cpu_sockets?: number;
    num_cpu_cores?: number;
    num_cpu_threads?: number;
  };
  device_info?: {
    device_type?: string;
    compute_devices?: BlenderDevice[];
    num_cpu_threads?: number;
  };
  stats?: {
    device_peak_memory?: number;
    number_of_samples?: number;
    time_for_samples?: number;
    samples_per_minute?: number;
    total_render_time?: number;
    render_time_no_sync?: number;
    time_limit?: number;
  };
}

export interface BlenderDevice {
  type: string;
  name: string;
  is_display?: boolean;
}