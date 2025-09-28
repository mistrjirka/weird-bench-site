"""
Simplified API models for clean hardware list and comparison functionality.
No legacy compatibility - unified format only.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from essential_models import UploadResult


class CleanHardwareInfo(BaseModel):
    """Clean hardware information for frontend consumption."""
    id: str = Field(..., description="Hardware identifier for URLs and comparison")
    name: str = Field(..., description="Human-readable hardware name")
    type: str = Field(..., description="Hardware type: 'cpu' or 'gpu'")
    manufacturer: str = Field(..., description="Hardware manufacturer")
    
    # Type-specific optional fields
    cores: Optional[int] = Field(None, description="CPU core count")
    threads: Optional[int] = Field(None, description="CPU thread count") 
    framework: Optional[str] = Field(None, description="GPU framework (CUDA, HIP, etc.)")
    memory_mb: Optional[int] = Field(None, description="GPU memory in MB")


class BenchmarkSummary(BaseModel):
    """Summary of benchmark results for a hardware device."""
    total_benchmarks: int = Field(..., description="Total number of benchmark runs")
    benchmark_types: List[str] = Field(..., description="Available benchmark types")
    latest_run: int = Field(..., description="Timestamp of most recent benchmark")
    
    # Best performance highlights for quick comparison
    best_performance: Optional[Dict[str, Any]] = Field(None, description="Best performance metrics")


class CleanHardwareSummary(BaseModel):
    """Simplified hardware summary for listing and comparison."""
    hardware: CleanHardwareInfo
    benchmarks: BenchmarkSummary
    comparison_url: str = Field(..., description="URL for detailed hardware view")


class SimpleHardwareListData(BaseModel):
    """Simplified hardware list without redundant path information."""
    cpus: List[CleanHardwareSummary] = Field(..., description="Available CPU hardware")
    gpus: List[CleanHardwareSummary] = Field(..., description="Available GPU hardware")
    
    # Metadata for frontend
    total_hardware: int = Field(..., description="Total number of hardware entries")
    total_benchmarks: int = Field(..., description="Total benchmark runs across all hardware")
    supported_benchmarks: List[str] = Field(..., description="All supported benchmark types")


class SimpleHardwareListResponse(BaseModel):
    """Clean API response for hardware listing."""
    success: bool = Field(True, description="Request success status")
    data: SimpleHardwareListData
    timestamp: int = Field(..., description="Response timestamp")


# Response models for other endpoints - keeping them simple
class HealthResponse(BaseModel):
    """Health check response."""
    success: bool = True
    status: str = "healthy"
    version: str = "2.0.0"
    timestamp: int


class ProcessedBenchmarkData(BaseModel):
    """Processed benchmark data for detailed views."""
    benchmark_type: str
    hardware_type: str  # "cpu" or "gpu"
    data_points: List[Dict[str, Any]]
    median_values: Dict[str, Any]
    stats: Dict[str, Any] 
    file_count: int
    valid_file_count: int


class ProcessedBenchmarkResponse(BaseModel):
    """Response for processed benchmark data."""
    success: bool = True
    data: List[ProcessedBenchmarkData]
    timestamp: int


class HardwareDetail(BaseModel):
    """Detailed hardware information with processed benchmark data."""
    hardware: CleanHardwareInfo
    benchmarks: BenchmarkSummary
    benchmark_history: List[Dict[str, Any]] = Field(default_factory=list)
    processed_benchmarks: List[ProcessedBenchmarkData] = Field(default_factory=list)


class HardwareDetailResponse(BaseModel):
    """Response for hardware detail endpoint."""
    success: bool = True  
    data: HardwareDetail
    timestamp: int


class UploadResponse(BaseModel):
    """Response for upload endpoint."""
    success: bool = Field(default=True)
    message: str
    data: UploadResult
    timestamp: int