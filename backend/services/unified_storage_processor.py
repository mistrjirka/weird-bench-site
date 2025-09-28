"""
Unified Storage Processor for handling unified benchmark format uploads.
Uses Pydantic models for clean, type-safe processing.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

from pydantic_unified_models import (
    UnifiedBenchmarkResult, SystemInfo, HardwareDevice,
    LlamaBenchmarkResult, ReversanBenchmarkResult, 
    SevenZipBenchmarkResult, BlenderBenchmarkResult
)
from database import database, Hardware, BenchmarkRun, BenchmarkFile
from models import StoredHardware, UploadResult
from services.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class UnifiedStorageProcessor:
    """Processes unified benchmark format and stores in database."""
    
    def __init__(self):
        self.storage_manager = StorageManager()
    
    async def process_unified_upload(self, unified_data: Dict[str, Any], run_id: str, timestamp: str) -> UploadResult:
        """Process a unified benchmark upload using Pydantic models."""
        try:
            # Parse the JSON data directly into our Pydantic model
            unified_result = UnifiedBenchmarkResult.model_validate(unified_data)
            
            logger.info(f"Processing unified upload {run_id}: {len(unified_result.meta.hardware)} devices, {len(unified_result.get_benchmarks())} benchmarks")
            
            # Extract hardware entries from the Pydantic model
            hardware_entries = []
            for hw_id, device in unified_result.meta.hardware.items():
                hardware_entry = StoredHardware(
                    id=hw_id,
                    name=device.name,
                    type=device.type,
                    manufacturer=device.manufacturer,
                    cores=device.cores,
                    framework=device.framework,
                    directory_path=f"{device.type}/{hw_id}",
                    benchmark_runs=[],
                    created_at=int(timestamp),
                    updated_at=int(timestamp)
                )
                hardware_entries.append(hardware_entry)
            
            # Store the benchmark data directly as Pydantic models
            # We'll serialize them to JSON for storage but keep type safety
            benchmark_data = {}
            if unified_result.llama:
                benchmark_data['llama'] = self._convert_llama_to_legacy(unified_result.llama, unified_result.meta.hardware)
            if unified_result.reversan:
                benchmark_data['reversan'] = self._convert_reversan_to_legacy(unified_result.reversan)
            if unified_result.sevenzip:
                benchmark_data['7zip'] = self._convert_sevenzip_to_legacy(unified_result.sevenzip)  # Note: storage expects '7zip'
            if unified_result.blender:
                benchmark_data['blender'] = self._convert_blender_to_legacy(unified_result.blender, unified_result.meta.hardware)
            
            # Store using the existing storage manager
            result = await self.storage_manager.store_benchmark_run(
                run_id=run_id,
                hardware_entries=hardware_entries,
                benchmark_data=benchmark_data,
                timestamp=int(timestamp)
            )
            
            return UploadResult(
                hardware_id=hardware_entries[0].id if hardware_entries else "",  # Primary hardware ID
                hardware_type="mixed" if len(hardware_entries) > 1 else hardware_entries[0].type if hardware_entries else "unknown",
                stored_benchmarks=list(benchmark_data.keys()),
                run_id=run_id
            )
            
        except Exception as e:
            logger.error(f"Failed to process unified upload {run_id}: {str(e)}")
            raise ValueError(f"Processing failed: {str(e)}")
    
    def _convert_llama_to_legacy(self, llama_result: LlamaBenchmarkResult, hardware_devices: Dict[str, HardwareDevice]) -> Dict[str, Any]:
        """Convert Pydantic Llama result to legacy format."""
        legacy_format = {
            'results': {}
        }
        
        # Convert CPU benchmark
        if llama_result.cpu_benchmark:
            cpu_run = {
                'type': 'cpu',
                'metrics': {
                    'generation': {
                        'avg_tokens_per_sec': llama_result.cpu_benchmark.generation_speed
                    },
                    'prompt_processing': {
                        'avg_tokens_per_sec': llama_result.cpu_benchmark.prompt_speed
                    }
                }
            }
            legacy_format['results']['runs_cpu'] = [cpu_run]
        
        # Convert GPU benchmarks
        if llama_result.gpu_benchmarks:
            gpu_runs = []
            for gpu_run in llama_result.gpu_benchmarks:
                gpu_device = hardware_devices.get(gpu_run.hw_id)
                gpu_legacy_run = {
                    'type': 'gpu',
                    'metrics': {
                        'tokens_per_second': gpu_run.generation_speed,
                        'prompt_processing': {
                            'avg_tokens_per_sec': gpu_run.prompt_speed
                        }
                    },
                    'gpu_device': {
                        'name': gpu_device.name if gpu_device else 'Unknown GPU',
                        'index': 0,
                        'driver': gpu_device.driver_version if gpu_device else 'Unknown'
                    }
                }
                gpu_runs.append(gpu_legacy_run)
            
            legacy_format['results']['runs_gpu'] = gpu_runs
        
        # Add build timing
        if llama_result.compile_time:
            legacy_format['results']['cpu_build_timing'] = {
                'build_time_seconds': llama_result.compile_time
            }
        
        return legacy_format
    
    def _convert_llama_unified_to_legacy(self, llama_data: Any, hardware_devices: Dict[str, Any]) -> Dict[str, Any]:
        """Convert unified Llama format to legacy format."""
        legacy_format = {
            'results': {}
        }
        
        # Convert CPU benchmark
        if llama_data.cpu_benchmark:
            cpu_run = {
                'type': 'cpu',
                'metrics': {
                    'generation': {
                        'avg_tokens_per_sec': llama_data.cpu_benchmark.generation_speed
                    },
                    'prompt_processing': {
                        'avg_tokens_per_sec': llama_data.cpu_benchmark.prompt_speed
                    }
                }
            }
            legacy_format['results']['runs_cpu'] = [cpu_run]
        
        # Convert GPU benchmarks
        if llama_data.gpu_benchmarks:
            gpu_runs = []
            for gpu_run in llama_data.gpu_benchmarks:
                gpu_device_info = hardware_devices.get(gpu_run.hw_id, {})
                gpu_legacy_run = {
                    'type': 'gpu',
                    'metrics': {
                        'tokens_per_second': gpu_run.generation_speed,
                        'prompt_processing': {
                            'avg_tokens_per_sec': gpu_run.prompt_speed
                        }
                    },
                    'gpu_device': {
                        'name': gpu_device_info.get('name', 'Unknown GPU'),
                        'index': 0,
                        'driver': gpu_device_info.get('driver_version', 'Unknown')
                    }
                }
                gpu_runs.append(gpu_legacy_run)
            
            legacy_format['results']['runs_gpu'] = gpu_runs
        
        # Add build timing
        if llama_data.compile_time:
            legacy_format['results']['cpu_build_timing'] = {
                'build_time_seconds': llama_data.compile_time
            }
        
        return legacy_format
    
    def _convert_blender_unified_to_legacy(self, blender_data: Any, hardware_devices: Dict[str, Any]) -> Dict[str, Any]:
        """Convert unified Blender format to legacy format."""
        legacy_format = {
            'results': {
                'device_runs': []
            }
        }
        
        # Convert CPU results
        if blender_data.cpu:
            cpu_device_run = {
                'device_framework': 'CPU',
                'device_name': 'CPU',
                'scene_results': {},
                'raw_json': []
            }
            
            # Convert scene results
            for scene_name in ['classroom', 'junkshop', 'monster']:
                scene_value = getattr(blender_data.cpu, scene_name, None)
                if scene_value is not None:
                    cpu_device_run['scene_results'][scene_name] = {
                        'samples_per_minute': scene_value
                    }
                    # Add raw_json entry
                    cpu_device_run['raw_json'].append({
                        'scene': {'label': scene_name},
                        'stats': {'samples_per_minute': scene_value}
                    })
            
            legacy_format['results']['device_runs'].append(cpu_device_run)
        
        # Convert GPU results
        if blender_data.gpus:
            for gpu_result in blender_data.gpus:
                gpu_device_info = hardware_devices.get(gpu_result.hw_id, {})
                gpu_device_run = {
                    'device_framework': gpu_device_info.get('framework', 'UNKNOWN'),
                    'device_name': gpu_device_info.get('name', 'Unknown GPU'),
                    'scene_results': {},
                    'raw_json': []
                }
                
                # Convert scene results
                for scene_name in ['classroom', 'junkshop', 'monster']:
                    scene_value = getattr(gpu_result.scenes, scene_name, None)
                    if scene_value is not None:
                        gpu_device_run['scene_results'][scene_name] = {
                            'samples_per_minute': scene_value
                        }
                        # Add raw_json entry
                        gpu_device_run['raw_json'].append({
                            'scene': {'label': scene_name},
                            'stats': {'samples_per_minute': scene_value}
                        })
                
                legacy_format['results']['device_runs'].append(gpu_device_run)
        
        return legacy_format
    
    def _convert_reversan_to_legacy(self, reversan_result: ReversanBenchmarkResult) -> Dict[str, Any]:
        """Convert Pydantic Reversan result to legacy format."""
        legacy_format = {
            'results': {
                'runs_depth': [],
                'runs_threads': [],
                'build': {}
            }
        }
        
        # Convert depth benchmarks
        for depth_result in reversan_result.depth_benchmarks:
            depth_run = {
                'depth': depth_result.depth,
                'metrics': {
                    'elapsed_seconds': depth_result.time_seconds,
                    'max_rss_kb': depth_result.memory_kb
                }
            }
            legacy_format['results']['runs_depth'].append(depth_run)
        
        # Convert thread benchmarks
        for thread_result in reversan_result.thread_benchmarks:
            thread_run = {
                'threads': thread_result.threads,
                'metrics': {
                    'elapsed_seconds': thread_result.time_seconds,
                    'max_rss_kb': thread_result.memory_kb
                }
            }
            legacy_format['results']['runs_threads'].append(thread_run)
        
        # Add build timing
        if reversan_result.compile_time:
            legacy_format['results']['build'] = {
                'build_time_seconds': reversan_result.compile_time
            }
        
        return legacy_format

    def _convert_blender_to_legacy(self, blender_result: BlenderBenchmarkResult, hardware_devices: Dict[str, HardwareDevice]) -> Dict[str, Any]:
        """Convert Pydantic Blender result to legacy format."""
        legacy_format = {
            'results': {
                'device_runs': []
            }
        }
        
        # Convert CPU results
        if blender_result.cpu:
            cpu_device_run = {
                'device_framework': 'CPU',
                'device_name': 'CPU',
                'scene_results': {},
                'raw_json': []
            }
            
            # Convert scene results
            for scene_name in ['classroom', 'junkshop', 'monster']:
                scene_value = getattr(blender_result.cpu, scene_name, None)
                if scene_value is not None:
                    cpu_device_run['scene_results'][scene_name] = {
                        'samples_per_minute': scene_value
                    }
                    # Add raw_json entry
                    cpu_device_run['raw_json'].append({
                        'scene': {'label': scene_name},
                        'stats': {'samples_per_minute': scene_value}
                    })
            
            legacy_format['results']['device_runs'].append(cpu_device_run)
        
        # Convert GPU results
        if blender_result.gpus:
            for gpu_result in blender_result.gpus:
                gpu_device = hardware_devices.get(gpu_result.hw_id)
                gpu_device_run = {
                    'device_framework': gpu_device.framework if gpu_device else 'UNKNOWN',
                    'device_name': gpu_device.name if gpu_device else 'Unknown GPU',
                    'scene_results': {},
                    'raw_json': []
                }
                
                # Convert scene results
                for scene_name in ['classroom', 'junkshop', 'monster']:
                    scene_value = getattr(gpu_result.scenes, scene_name, None)
                    if scene_value is not None:
                        gpu_device_run['scene_results'][scene_name] = {
                            'samples_per_minute': scene_value
                        }
                        # Add raw_json entry
                        gpu_device_run['raw_json'].append({
                            'scene': {'label': scene_name},
                            'stats': {'samples_per_minute': scene_value}
                        })
                
                legacy_format['results']['device_runs'].append(gpu_device_run)
        
        return legacy_format

    def _convert_sevenzip_to_legacy(self, sevenzip_result: SevenZipBenchmarkResult) -> Dict[str, Any]:
        """Convert Pydantic 7zip result to legacy format."""
        legacy_format = {
            'results': {
                'usage_percent': sevenzip_result.usage_percent,
                'ru_mips': sevenzip_result.ru_mips,
                'total_mips': sevenzip_result.total_mips,
                'runs': [
                    {
                        'threads': 1,  # 7zip internal benchmark
                        'compression_speed_mb_s': sevenzip_result.total_mips,
                        'elapsed_seconds': 1.0,  # Placeholder
                        'compression_ratio': 1.0  # Placeholder
                    }
                ]
            }
        }
        return legacy_format