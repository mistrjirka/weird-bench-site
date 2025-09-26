from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Union
from datetime import datetime

# Response Models
class HealthResponse(BaseModel):
    success: bool = True
    status: str
    timestamp: int
    version: str

class HardwareSummary(BaseModel):
    id: str
    name: str
    manufacturer: str
    cores: Optional[int] = None  # For CPUs
    framework: Optional[str] = None  # For GPUs
    benchmarks: Dict[str, List[str]]  # benchmark type -> list of file paths
    lastUpdated: int

class HardwareListData(BaseModel):
    cpus: List[HardwareSummary]
    gpus: List[HardwareSummary]
    
class HardwareListResponse(BaseModel):
    success: bool = True
    data: HardwareListData
    timestamp: int

class BenchmarkFile(BaseModel):
    name: str
    path: str
    type: str
    timestamp: int
    size: int

class HardwareDetail(BaseModel):
    id: str
    name: str
    manufacturer: str
    type: str  # "cpu" or "gpu"
    cores: Optional[int] = None
    framework: Optional[str] = None
    benchmarkFiles: List[BenchmarkFile]
    totalBenchmarks: int
    lastUpdated: int

class ProcessedBenchmarkData(BaseModel):
    benchmark_type: str
    hardware_type: str  # "cpu" or "gpu"
    data_points: List[Dict[str, Any]]
    median_values: Dict[str, Any]
    stats: Dict[str, Any]
    file_count: int
    valid_file_count: int

class HardwareDetailResponse(BaseModel):
    success: bool = True
    data: HardwareDetail
    timestamp: int

class ProcessedBenchmarkResponse(BaseModel):
    success: bool = True
    data: List[ProcessedBenchmarkData]
    timestamp: int

class UploadResult(BaseModel):
    hardware_id: str
    hardware_type: str
    stored_benchmarks: List[str]
    run_id: str

class UploadResponse(BaseModel):
    success: bool = True
    message: str
    data: UploadResult
    timestamp: int

# Input Models
class HardwareInfo(BaseModel):
    cpu: str
    gpu: str
    ram: Optional[str] = None
    os: Optional[str] = None

class BenchmarkData(BaseModel):
    """Generic benchmark data structure"""
    type: str
    data: Dict[str, Any]
    timestamp: int

# Internal Models
class StoredHardware(BaseModel):
    id: str
    name: str
    manufacturer: str
    type: str
    cores: Optional[int] = None
    framework: Optional[str] = None
    directory_path: str
    benchmark_runs: List[str]
    created_at: int
    updated_at: int

class BenchmarkRun(BaseModel):
    run_id: str
    hardware_info: HardwareInfo
    timestamp: int
    benchmarks: Dict[str, Any]  # benchmark_type -> benchmark_data
    file_paths: Dict[str, str]  # benchmark_type -> file_path