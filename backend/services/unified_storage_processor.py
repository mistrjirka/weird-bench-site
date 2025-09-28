"""
Unified Storage Processor for handling unified benchmark format uploads.
Uses Pydantic models for clean, type-safe processing.
"""

import logging
import json
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import select

from pydantic_unified_models import (
    UnifiedBenchmarkResult, SystemInfo, HardwareDevice,
    LlamaBenchmarkResult, ReversanBenchmarkResult, 
    SevenZipBenchmarkResult, BlenderBenchmarkResult
)
from database import database, Hardware, BenchmarkRun, BenchmarkFile
from essential_models import StoredHardware, UploadResult

logger = logging.getLogger(__name__)


class UnifiedStorageProcessor:
    """Processes unified benchmark format and stores in database."""
    
    def __init__(self):
        # We'll use the database directly instead of the old storage manager
        pass
    
    async def process_unified_upload(self, unified_data: Dict[str, Any], run_id: str, timestamp: str) -> UploadResult:
        """Process a unified benchmark upload - simplified version."""
        try:
            # Parse the JSON data into our Pydantic model
            unified_result = UnifiedBenchmarkResult.model_validate(unified_data)
            
            logger.info(f"Processing unified upload {run_id}: {len(unified_result.meta.hardware)} devices")
            
            # Simple storage - just save the benchmark results directly to database
            async with database.get_session() as session:
                # Store hardware info
                for hw_id, device in unified_result.meta.hardware.items():
                    # Create or update hardware entry
                    result = await session.execute(
                        select(Hardware).where(Hardware.id == hw_id)
                    )
                    hw_entry = result.scalar_one_or_none()
                    
                    if not hw_entry:
                        hw_entry = Hardware(
                            id=hw_id,
                            name=device.name,
                            type=device.type,
                            manufacturer=device.manufacturer,
                            cores=device.cores,
                            framework=device.framework
                        )
                        session.add(hw_entry)
                        logger.info(f"📝 Created hardware entry: {hw_entry.id} - {hw_entry.name} ({hw_entry.type})")
                    else:
                        hw_entry.updated_at = int(timestamp)
                
                # Create benchmark run for each hardware device
                stored_benchmarks = []
                
                for hw_id, hw_device in unified_result.meta.hardware.items():
                    # Get or create hardware entry (we already have it)
                    result = await session.execute(
                        select(Hardware).where(Hardware.id == hw_id)
                    )
                    hw_entry = result.scalar_one_or_none()
                    
                    if not hw_entry:
                        logger.warning(f"Hardware entry {hw_id} not found, skipping")
                        continue
                    
                    # Create benchmark run for this hardware
                    benchmark_run = BenchmarkRun(
                        run_id=run_id,
                        hardware_id=hw_id,
                        timestamp=datetime.fromtimestamp(int(timestamp)),
                        run_number=1  # Simple counter for now
                    )
                    session.add(benchmark_run)
                    await session.flush()  # Get the ID
                    
                    logger.info(f"📊 Created benchmark run: {benchmark_run.run_id} for {hw_entry.name}")
                
                    # Store individual benchmark files as JSON in database
                    for benchmark_type, benchmark_data in [
                        ("llama", unified_result.llama),
                        ("reversan", unified_result.reversan),
                        ("sevenzip", unified_result.sevenzip),
                        ("blender", unified_result.blender)
                    ]:
                        if benchmark_data:
                            # Convert benchmark data to legacy format for storage
                            if benchmark_type == "llama" and unified_result.llama:
                                legacy_data = self._convert_llama_unified_to_legacy(unified_result.llama, unified_result.meta.hardware)
                            elif benchmark_type == "blender" and unified_result.blender:
                                legacy_data = self._convert_blender_unified_to_legacy(unified_result.blender, unified_result.meta.hardware)
                            elif benchmark_type == "reversan" and unified_result.reversan:
                                legacy_data = {"results": self._convert_reversan_to_legacy(unified_result.reversan)}
                            elif benchmark_type == "sevenzip" and unified_result.sevenzip:
                                legacy_data = {"results": self._convert_sevenzip_to_legacy(unified_result.sevenzip)}
                            else:
                                legacy_data = {"results": {}}
                            
                            # Store benchmark file with data in database (no file system)
                            benchmark_file = BenchmarkFile(
                                benchmark_run_id=benchmark_run.id,
                                benchmark_type=benchmark_type,
                                filename=f"run_{benchmark_run.run_number}_{benchmark_type}.json",
                                file_path=f"{hw_device.type}/{hw_id}/run_{benchmark_run.run_number}_{benchmark_type}.json",  # Legacy path for compatibility
                                file_size=len(str(legacy_data).encode()),
                                data=legacy_data  # Store JSON directly in database
                            )
                            session.add(benchmark_file)
                            stored_benchmarks.append(benchmark_type)
                            
                            logger.info(f"💾 Stored {benchmark_type} benchmark data for {hw_entry.name} (size: {benchmark_file.file_size} bytes)")
                
                await session.commit()
                
                logger.info(f"✅ Upload complete: {len(stored_benchmarks)} benchmarks stored for {len(unified_result.meta.hardware)} hardware devices")
                
                return UploadResult(
                    hardware_id=list(unified_result.meta.hardware.keys())[0] if unified_result.meta.hardware else "unknown",
                    hardware_type="mixed" if len(unified_result.meta.hardware) > 1 else list(unified_result.meta.hardware.values())[0].type,
                    stored_benchmarks=stored_benchmarks,
                    run_id=run_id
                )
                
        except Exception as e:
            logger.error(f"Failed to process unified upload: {str(e)}")
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
                gpu_device_info = hardware_devices.get(gpu_run.hw_id)
                if not gpu_device_info:
                    continue
                    
                gpu_legacy_run = {
                    'type': 'gpu',
                    'metrics': {
                        'tokens_per_second': gpu_run.generation_speed,
                        'prompt_processing': {
                            'avg_tokens_per_sec': gpu_run.prompt_speed
                        }
                    },
                    'gpu_device': {
                        'name': gpu_device_info.name,
                        'index': 0,
                        'driver': gpu_device_info.driver_version or 'Unknown'
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
                gpu_device_info = hardware_devices.get(gpu_result.hw_id)
                if not gpu_device_info:
                    continue
                    
                gpu_device_run = {
                    'device_framework': gpu_device_info.framework or 'UNKNOWN',
                    'device_name': gpu_device_info.name,
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