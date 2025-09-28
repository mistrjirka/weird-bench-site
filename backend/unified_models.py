from pydantic import BaseModel, ValidationError
from typing import List, Dict, Optional, Any, Union
from datetime import datetime

# Base models for unified benchmark format
class UnifiedHardwareDevice(BaseModel):
    """Represents a single hardware device in the unified format."""
    hw_id: str  # Global hardware ID (cpu-0, gpu-0, gpu-1, etc.)
    name: str   # Full device name
    type: str   # "cpu" or "gpu"
    manufacturer: str  # "Intel", "AMD", "NVIDIA", etc.
    cores: Optional[int] = None
    threads: Optional[int] = None
    framework: Optional[str] = None  # For GPUs: "CUDA", "OPENCL", "VULKAN", etc.
    driver_version: Optional[str] = None
    memory_mb: Optional[int] = None


class UnifiedSystemInfo(BaseModel):
    """System information and hardware inventory in unified format."""
    platform: str
    host: str
    timestamp: float
    cpu_only: bool  # Whether this benchmark run was CPU-only
    hardware: Dict[str, UnifiedHardwareDevice]  # hw_id -> HardwareDevice mapping


# Llama Benchmark Results
class UnifiedLlamaRunResult(BaseModel):
    """Single Llama inference run result in unified format."""
    prompt_speed: float  # tokens per second for prompt processing
    generation_speed: float  # tokens per second for generation
    hw_id: str  # Hardware device used for this run


class UnifiedLlamaBenchmarkResult(BaseModel):
    """Llama benchmark results with CPU/GPU separation."""
    compile_time: float  # Build/compilation time in seconds
    cpu_benchmark: Optional[UnifiedLlamaRunResult] = None
    gpu_benchmarks: Optional[List[UnifiedLlamaRunResult]] = None


# Reversan Benchmark Results
class UnifiedReversanDepthResult(BaseModel):
    """Single depth benchmark result."""
    depth: int
    time_seconds: float
    memory_kb: int


class UnifiedReversanThreadResult(BaseModel):
    """Single thread benchmark result."""
    threads: int
    time_seconds: float
    memory_kb: int


class UnifiedReversanBenchmarkResult(BaseModel):
    """Reversan benchmark results with depth and thread benchmarks."""
    compile_time: float
    depth_benchmarks: List[UnifiedReversanDepthResult]
    thread_benchmarks: List[UnifiedReversanThreadResult]


# 7zip Benchmark Results
class UnifiedSevenZipBenchmarkResult(BaseModel):
    """7zip benchmark results using internal benchmark."""
    usage_percent: float  # CPU usage percentage
    ru_mips: float       # R/U MIPS (per core)
    total_mips: float    # Total MIPS


# Blender Benchmark Results
class UnifiedBlenderSceneResult(BaseModel):
    """Result for a single Blender scene."""
    classroom: Optional[float] = None  # samples per minute
    junkshop: Optional[float] = None   # samples per minute
    monster: Optional[float] = None    # samples per minute


class UnifiedBlenderDeviceResult(BaseModel):
    """Blender results for a specific device."""
    hw_id: str
    scenes: UnifiedBlenderSceneResult


class UnifiedBlenderBenchmarkResult(BaseModel):
    """Blender benchmark results with CPU/GPU separation."""
    cpu: Optional[UnifiedBlenderSceneResult] = None
    gpus: Optional[List[UnifiedBlenderDeviceResult]] = None


# Main unified benchmark result
class UnifiedBenchmarkData(BaseModel):
    """Main unified benchmark result containing all benchmark data."""
    meta: UnifiedSystemInfo
    llama: Optional[UnifiedLlamaBenchmarkResult] = None
    reversan: Optional[UnifiedReversanBenchmarkResult] = None
    sevenzip: Optional[UnifiedSevenZipBenchmarkResult] = None
    blender: Optional[UnifiedBlenderBenchmarkResult] = None


# Response models for API
class UnifiedUploadResponse(BaseModel):
    """Response for unified benchmark upload."""
    success: bool
    message: str
    timestamp: int
    run_id: Optional[str] = None
    hardware_processed: Optional[List[str]] = None  # List of hardware IDs processed
    benchmarks_processed: Optional[List[str]] = None  # List of benchmarks processed
    errors: Optional[List[str]] = None


# Legacy compatibility models (keeping existing models for backward compatibility)
class HealthResponse(BaseModel):
    success: bool
    status: str
    timestamp: int
    version: str


class HardwareSummary(BaseModel):
    hardware: Dict[str, Any]
    benchmarkCount: int


class HardwareListData(BaseModel):
    cpu: List[HardwareSummary]
    gpu: List[HardwareSummary]
    totalCount: int


class HardwareListResponse(BaseModel):
    success: bool
    data: HardwareListData
    timestamp: int


class HardwareInfo(BaseModel):
    name: str
    type: str
    manufacturer: str
    cores: Optional[int] = None
    framework: Optional[str] = None


class BenchmarkFile(BaseModel):
    filename: str
    run_number: int
    benchmark_type: str
    timestamp: int
    hardware_type: str
    hardware_name: str


class HardwareDetail(BaseModel):
    hardware: HardwareInfo
    files: List[BenchmarkFile]
    totalBenchmarks: int


class HardwareDetailResponse(BaseModel):
    success: bool
    data: HardwareDetail
    timestamp: int


class ProcessedBenchmarkData(BaseModel):
    benchmark_type: str
    data_points: List[Dict[str, Any]]
    median_values: Dict[str, Any]
    stats: Dict[str, Any]
    file_count: int


class ProcessedBenchmarkResponse(BaseModel):
    success: bool
    data: List[ProcessedBenchmarkData]
    timestamp: int


class UploadResponse(BaseModel):
    success: bool
    message: str
    timestamp: int
    run_id: Optional[str] = None
    hardware_processed: Optional[List[str]] = None
    benchmarks_processed: Optional[List[str]] = None
    errors: Optional[List[str]] = None


# Legacy models for backward compatibility
class BenchmarkData(BaseModel):
    reversan: Optional[Dict[str, Any]] = None
    llama: Optional[Dict[str, Any]] = None
    sevenzip: Optional[Dict[str, Any]] = None  # Note: kept as sevenzip for legacy
    blender: Optional[Dict[str, Any]] = None


class StoredHardware(BaseModel):
    hardware_id: str
    hardware_name: str
    hardware_type: str  # 'cpu' or 'gpu'
    manufacturer: str
    cores: Optional[int] = None
    framework: Optional[str] = None


class UploadResult(BaseModel):
    success: bool
    run_id: str
    hardware_entries: List[str]
    benchmark_files_created: int
    errors: Optional[List[str]] = None