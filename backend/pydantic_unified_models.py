"""
Unified benchmark Pydantic models for the backend API.
Based on unified_models.py from the benchmark runner but using Pydantic for JSON parsing.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Union
import time
from datetime import datetime


class HardwareDevice(BaseModel):
    """Represents a single hardware device (CPU or GPU)."""
    hw_id: str  # Global hardware ID (cpu-0, gpu-0, gpu-1, etc.)
    name: str   # Full device name
    type: str   # "cpu" or "gpu"
    manufacturer: str  # "Intel", "AMD", "NVIDIA", etc.
    # Additional optional fields
    cores: Optional[int] = None
    threads: Optional[int] = None
    framework: Optional[str] = None  # For GPUs: "CUDA", "OPENCL", "VULKAN", etc.
    driver_version: Optional[str] = None
    memory_mb: Optional[int] = None


class SystemInfo(BaseModel):
    """System information and hardware inventory."""
    platform: str
    host: str
    timestamp: float
    cpu_only: bool  # Whether this benchmark run was CPU-only
    hardware: Dict[str, HardwareDevice]  # hw_id -> HardwareDevice mapping
    
    def get_cpu_device(self) -> Optional[HardwareDevice]:
        """Get the primary CPU device."""
        for device in self.hardware.values():
            if device.type == "cpu":
                return device
        return None
    
    def get_gpu_devices(self) -> List[HardwareDevice]:
        """Get all GPU devices."""
        return [device for device in self.hardware.values() if device.type == "gpu"]


# Llama Benchmark Results
class LlamaRunResult(BaseModel):
    """Single Llama inference run result."""
    prompt_speed: float  # tokens per second for prompt processing
    generation_speed: float  # tokens per second for generation
    hw_id: str  # Hardware device used for this run


class LlamaBenchmarkResult(BaseModel):
    """Llama benchmark results with CPU/GPU separation."""
    compile_time: float  # Build/compilation time in seconds
    cpu_benchmark: Optional[LlamaRunResult] = None
    gpu_benchmarks: Optional[List[LlamaRunResult]] = None


# Reversan Benchmark Results
class ReversanDepthResult(BaseModel):
    """Single depth benchmark result."""
    depth: int
    time_seconds: float
    memory_kb: int


class ReversanThreadResult(BaseModel):
    """Single thread benchmark result."""
    threads: int
    time_seconds: float
    memory_kb: int


class ReversanBenchmarkResult(BaseModel):
    """Reversan benchmark results with depth and thread benchmarks."""
    compile_time: float
    depth_benchmarks: List[ReversanDepthResult]
    thread_benchmarks: List[ReversanThreadResult]


# 7zip Benchmark Results
class SevenZipBenchmarkResult(BaseModel):
    """7zip benchmark results using internal benchmark."""
    usage_percent: float  # CPU usage percentage
    ru_mips: float       # R/U MIPS (per core)
    total_mips: float    # Total MIPS


# Blender Benchmark Results
class BlenderSceneResult(BaseModel):
    """Result for a single Blender scene."""
    classroom: Optional[float] = None  # samples per minute
    junkshop: Optional[float] = None   # samples per minute
    monster: Optional[float] = None    # samples per minute


class BlenderDeviceResult(BaseModel):
    """Blender results for a specific device."""
    hw_id: str
    scenes: BlenderSceneResult


class BlenderBenchmarkResult(BaseModel):
    """Blender benchmark results with CPU/GPU separation."""
    cpu: Optional[BlenderSceneResult] = None
    gpus: Optional[List[BlenderDeviceResult]] = None


# Main unified benchmark result
class UnifiedBenchmarkResult(BaseModel):
    """Main unified benchmark result containing all benchmark data and system info."""
    meta: SystemInfo
    llama: Optional[LlamaBenchmarkResult] = None
    reversan: Optional[ReversanBenchmarkResult] = None
    sevenzip: Optional[SevenZipBenchmarkResult] = None
    blender: Optional[BlenderBenchmarkResult] = None
    
    def get_benchmarks(self) -> Dict[str, Any]:
        """Get all non-None benchmark results."""
        benchmarks = {}
        if self.llama is not None:
            benchmarks['llama'] = self.llama
        if self.reversan is not None:
            benchmarks['reversan'] = self.reversan
        if self.sevenzip is not None:
            benchmarks['sevenzip'] = self.sevenzip
        if self.blender is not None:
            benchmarks['blender'] = self.blender
        return benchmarks


# Utility functions for hardware detection and ID generation
def generate_hardware_id(device_type: str, index: int) -> str:
    """Generate consistent hardware ID."""
    return f"{device_type}-{index}"


def normalize_hardware_name(name: str) -> str:
    """Normalize hardware names for consistent identification."""
    # Remove extra spaces and standardize format
    normalized = " ".join(name.split())
    
    # Common GPU name normalizations
    normalized = normalized.replace("(R)", "").replace("(TM)", "").replace("(C)", "")
    normalized = normalized.replace(" Graphics", "")
    
    return normalized.strip()


# Response models for the API
class UnifiedUploadResponse(BaseModel):
    """Response for unified benchmark upload."""
    success: bool
    message: str
    timestamp: int
    run_id: Optional[str] = None
    hardware_processed: Optional[List[str]] = None  # List of hardware IDs processed
    benchmarks_processed: Optional[List[str]] = None  # List of benchmarks processed
    errors: Optional[List[str]] = None