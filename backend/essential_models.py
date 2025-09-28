"""
Essential models needed for the API - only what's actually used
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


# Models needed by UnifiedStorageProcessor
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


class UploadResult(BaseModel):
    hardware_id: str
    hardware_type: str
    stored_benchmarks: List[str]
    run_id: str


# Legacy models for backward compatibility with existing code
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