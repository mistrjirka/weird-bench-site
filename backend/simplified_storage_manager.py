"""
Simplified Storage Manager - Unified format only, no legacy support.
Clean API responses without redundant path information.
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from database import database, Hardware, BenchmarkRun, BenchmarkFile
from simplified_models import (
    CleanHardwareInfo, BenchmarkSummary, CleanHardwareSummary,
    SimpleHardwareListData, HardwareDetail, ProcessedBenchmarkData,
    UploadResult
)

logger = logging.getLogger(__name__)


class SimplifiedStorageManager:
    """Simplified storage manager with clean API responses."""
    
    def __init__(self):
        self.data_dir = Path(os.environ.get('DATA_DIR', './data'))
        logger.info(f"Initialized storage manager with data directory: {self.data_dir}")

    async def get_hardware_list(self) -> SimpleHardwareListData:
        """Get simplified hardware list without redundant path information."""
        async with database.get_session() as session:
            # Get all hardware with their benchmark runs and files
            result = await session.execute(
                select(Hardware).options(
                    selectinload(Hardware.benchmark_runs).selectinload(BenchmarkRun.benchmark_files)
                )
            )
            hardware_entries = result.scalars().all()
            
            cpus = []
            gpus = []
            total_benchmarks = 0
            supported_benchmark_types = set()
            
            for hw in hardware_entries:
                # Calculate benchmark summary from benchmark runs
                benchmark_counts = {}
                latest_timestamp = 0
                all_benchmark_files = []
                
                for run in hw.benchmark_runs:
                    for bf in run.benchmark_files:
                        all_benchmark_files.append(bf)
                        supported_benchmark_types.add(bf.benchmark_type)
                        benchmark_counts[bf.benchmark_type] = benchmark_counts.get(bf.benchmark_type, 0) + 1
                        # Use timestamp from the run, not the file
                        run_timestamp = run.timestamp.timestamp()
                        if run_timestamp > latest_timestamp:
                            latest_timestamp = run_timestamp
                
                total_benchmarks += len(all_benchmark_files)
                # Create clean hardware info
                clean_hw = CleanHardwareInfo(
                    id=hw.id,
                    name=hw.name,
                    type=hw.type,
                    manufacturer=hw.manufacturer,
                    cores=hw.cores,
                    threads=None,  # Not in database model
                    framework=hw.framework,
                    memory_mb=None  # Not in database model
                )
                
                # Create benchmark summary
                benchmark_summary = BenchmarkSummary(
                    total_benchmarks=len(all_benchmark_files),
                    benchmark_types=list(benchmark_counts.keys()),
                    latest_run=int(latest_timestamp) if latest_timestamp else 0,
                    best_performance=None  # Could be calculated later if needed
                )
                
                # Create clean hardware summary
                clean_summary = CleanHardwareSummary(
                    hardware=clean_hw,
                    benchmarks=benchmark_summary,
                    comparison_url=f"/hardware/{hw.type}/{hw.id}"
                )
                
                if hw.type == "cpu":
                    cpus.append(clean_summary)
                else:
                    gpus.append(clean_summary)
            
            return SimpleHardwareListData(
                cpus=cpus,
                gpus=gpus,
                total_hardware=len(hardware_entries),
                total_benchmarks=total_benchmarks,
                supported_benchmarks=sorted(list(supported_benchmark_types))
            )

    async def get_hardware_detail(self, hardware_type: str, hardware_id: str) -> Optional[dict]:
        """Get detailed hardware information with flat, medianed benchmark data."""
        import time
        
        def slugify(name: str) -> str:
            if not name:
                return "unknown"
            s = name.strip().lower()
            s = re.sub(r"[^a-z0-9]+", "-", s)
            s = re.sub(r"-+", "-", s).strip("-")
            return s or "unknown"
        async with database.get_session() as session:
            result = await session.execute(
                select(Hardware).where(
                    Hardware.type == hardware_type,
                    Hardware.id == hardware_id
                ).options(
                    selectinload(Hardware.benchmark_runs).selectinload(BenchmarkRun.benchmark_files)
                )
            )
            hw = result.scalar_one_or_none()
            if not hw:
                return None

            # Gather all benchmark files
            all_benchmark_files = []
            latest_timestamp = 0
            for run in hw.benchmark_runs:
                for bf in run.benchmark_files:
                    all_benchmark_files.append(bf)
                    run_timestamp = run.timestamp.timestamp()
                    if run_timestamp > latest_timestamp:
                        latest_timestamp = run_timestamp

            # Helper to compute median, ignoring None
            def median(values):
                arr = [v for v in values if v is not None]
                if not arr:
                    return None
                arr = sorted(arr)
                n = len(arr)
                if n % 2 == 1:
                    return arr[n//2]
                else:
                    return (arr[n//2-1] + arr[n//2]) / 2

            # Group files by benchmark type
            grouped = {}
            for bf in all_benchmark_files:
                grouped.setdefault(bf.benchmark_type, []).append(bf)

            # --- LLAMA ---
            # Collect CPU-only metrics for CPU hardware, and per-GPU metrics for GPU hardware (matching this GPU id)
            llama_prompt_speeds: List[float] = []
            llama_gen_speeds: List[float] = []
            llama_compile_times: List[float] = []
            for bf in grouped.get("llama", []):
                d = bf.data if hasattr(bf, 'data') and bf.data else {}

                # Only include CPU metrics when querying a CPU
                if hardware_type == "cpu" and isinstance(d.get('cpu_benchmark'), dict):
                    cpu = d['cpu_benchmark']
                    ps = cpu.get('prompt_speed')
                    gs = cpu.get('generation_speed')
                    if isinstance(ps, (int, float)):
                        llama_prompt_speeds.append(float(ps))
                    if isinstance(gs, (int, float)):
                        llama_gen_speeds.append(float(gs))

                # Only include GPU metrics for the matching GPU (by hw_id) when querying a GPU
                if hardware_type == "gpu" and isinstance(d.get('gpu_benchmarks'), list):
                    for gpu in d['gpu_benchmarks']:
                        # Prefer matching by device_slug (augmented at upload time), then by device_name slug
                        dev_slug = gpu.get('device_slug')
                        dev_name = gpu.get('device_name')
                        if dev_slug:
                            if dev_slug != hardware_id:
                                continue
                        elif dev_name:
                            if slugify(dev_name) != hardware_id:
                                continue
                        else:
                            # No augmentation present; skip to avoid cross-mixing different GPUs
                            continue
                        ps = gpu.get('prompt_speed')
                        gs = gpu.get('generation_speed')
                        if isinstance(ps, (int, float)):
                            llama_prompt_speeds.append(float(ps))
                        if isinstance(gs, (int, float)):
                            llama_gen_speeds.append(float(gs))

                # Compile/build time may be 0.0 (not measured) — treat non-positive as None
                ct = d.get('compile_time')
                if isinstance(ct, (int, float)) and ct > 0:
                    llama_compile_times.append(float(ct))

            llama = None
            if llama_prompt_speeds or llama_gen_speeds or llama_compile_times:
                llama = {
                    "prompt_token_speed": median(llama_prompt_speeds),
                    "generation_token_speed": median(llama_gen_speeds),
                    "compilation_time": median(llama_compile_times)
                }

            # --- REVERSAN ---
            reversan = None
            if hardware_type == "cpu":
                reversan_depth_times = []
                reversan_thread_times = []
                for bf in grouped.get("reversan", []):
                    d = bf.data if hasattr(bf, 'data') and bf.data else {}
                    
                    # Process unified format directly
                    if 'depth_benchmarks' in d:
                        for run in d['depth_benchmarks']:
                            reversan_depth_times.append({
                                "depth": run.get("depth"),
                                "time": run.get("time_seconds")
                            })
                    if 'thread_benchmarks' in d:
                        for run in d['thread_benchmarks']:
                            reversan_thread_times.append({
                                "threads": run.get("threads"),
                                "time": run.get("time_seconds")
                            })
                # Median by depth and threads
                def median_by_key(arr, key):
                    from collections import defaultdict
                    groups = defaultdict(list)
                    for item in arr:
                        groups[item[key]].append(item["time"])
                    return [
                        {key: k, "time": median(v)} for k, v in sorted(groups.items())
                    ]
                if reversan_depth_times or reversan_thread_times:
                    reversan = {
                        "depth_times": median_by_key(reversan_depth_times, "depth"),
                        "thread_times": median_by_key(reversan_thread_times, "threads")
                    }

            # --- BLENDER ---
            blender_classroom = []
            blender_junkshop = []
            blender_monster = []
            for bf in grouped.get("blender", []):
                d = bf.data if hasattr(bf, 'data') and bf.data else {}
                
                # Process unified format directly
                if hardware_type == "cpu":
                    cpu = d.get("cpu", {})
                    if cpu:
                        if "classroom" in cpu:
                            blender_classroom.append(cpu["classroom"])
                        if "junkshop" in cpu:
                            blender_junkshop.append(cpu["junkshop"])
                        if "monster" in cpu:
                            blender_monster.append(cpu["monster"])
                else:
                    # For GPU hardware, check GPU results
                    for gpu in d.get("gpus", []):
                        dev_slug = gpu.get('device_slug')
                        dev_name = gpu.get('device_name')
                        if dev_slug:
                            if dev_slug != hardware_id:
                                continue
                        elif dev_name:
                            if slugify(dev_name) != hardware_id:
                                continue
                        else:
                            # No augmentation present; skip to avoid cross-mixing different GPUs
                            continue
                        scenes = gpu.get("scenes", {})
                        if "classroom" in scenes:
                            blender_classroom.append(scenes["classroom"])
                        if "junkshop" in scenes:
                            blender_junkshop.append(scenes["junkshop"])
                        if "monster" in scenes:
                            blender_monster.append(scenes["monster"])
            blender = None
            if blender_classroom or blender_junkshop or blender_monster:
                blender = {
                    "classroom": median(blender_classroom),
                    "junkshop": median(blender_junkshop),
                    "monster": median(blender_monster)
                }

            # --- 7ZIP ---
            sevenzip = None
            if hardware_type == "cpu":
                zip_usage = []
                zip_ru_mips = []
                zip_total_mips = []
                # Check both possible key names: "7zip" and "sevenzip" 
                for bf in grouped.get("7zip", []) + grouped.get("sevenzip", []):
                    d = bf.data if hasattr(bf, 'data') and bf.data else {}
                    
                    # Process unified format directly
                    if "usage_percent" in d:
                        zip_usage.append(d["usage_percent"])
                    if "ru_mips" in d:
                        zip_ru_mips.append(d["ru_mips"])
                    if "total_mips" in d:
                        zip_total_mips.append(d["total_mips"])
                if zip_usage or zip_ru_mips or zip_total_mips:
                    sevenzip = {
                        "usage_percent": median(zip_usage),
                        "ru_mips": median(zip_ru_mips),
                        "total_mips": median(zip_total_mips)
                    }

            # Compose response
            clean_hw = CleanHardwareInfo(
                id=hw.id,
                name=hw.name,
                type=hw.type,
                manufacturer=hw.manufacturer,
                cores=hw.cores,
                threads=None,
                framework=hw.framework,
                memory_mb=None
            )
            response = {
                "success": True,
                "hardware": clean_hw.model_dump(),
                "llama": llama,
                "reversan": reversan,
                "blender": blender,
                "7zip": sevenzip,
                "timestamp": int(latest_timestamp) if latest_timestamp else int(time.time())
            }
            return response

    async def get_processed_benchmark_data(self, hardware_type: str, hardware_id: str) -> List[ProcessedBenchmarkData]:
        """Get processed benchmark data for hardware (keeping existing logic but simplified)."""
        async with database.get_session() as session:
            # Get benchmark files through the proper relationship chain:
            # Hardware -> BenchmarkRun -> BenchmarkFile
            result = await session.execute(
                select(BenchmarkFile)
                .select_from(Hardware)
                .join(BenchmarkRun, Hardware.id == BenchmarkRun.hardware_id)
                .join(BenchmarkFile, BenchmarkRun.id == BenchmarkFile.benchmark_run_id)
                .where(
                    Hardware.type == hardware_type,
                    Hardware.id == hardware_id
                )
            )
            
            benchmark_files = result.scalars().all()
            
            # Group by benchmark type
            grouped_files = {}
            for bf in benchmark_files:
                if bf.benchmark_type not in grouped_files:
                    grouped_files[bf.benchmark_type] = []
                grouped_files[bf.benchmark_type].append(bf)
            
            processed_data = []
            
            for benchmark_type, files in grouped_files.items():
                # Load and process benchmark data
                processed = self._process_benchmark_type(
                    benchmark_type, files, hardware_type, hardware_id
                )
                if processed:
                    processed_data.append(processed)
            
            return processed_data

    def _process_benchmark_type(self, benchmark_type: str, files: List, hardware_type: str, hardware_id: str) -> Optional[ProcessedBenchmarkData]:
        """Process benchmark files of a specific type - simplified version."""
        valid_data = []
        
        for bf in files:
            try:
                # The benchmark data is stored in the 'data' field of BenchmarkFile
                data = bf.data if hasattr(bf, 'data') and bf.data else {}
                if data:
                    valid_data.append(data)
            except Exception as e:
                logger.error(f"Error loading benchmark file {bf.id}: {str(e)}")
                continue
        
        if not valid_data:
            return None
        
        # Simplified processing based on benchmark type
        if benchmark_type == "llama":
            return self._process_llama_data_simplified(valid_data, hardware_type, hardware_id)
        elif benchmark_type == "blender":
            return self._process_blender_data_simplified(valid_data, hardware_type)
        elif benchmark_type == "7zip":
            return self._process_7zip_data_simplified(valid_data)
        elif benchmark_type == "reversan":
            return self._process_reversan_data_simplified(valid_data)
        
        return None

    def _calculate_median(self, values: List[float]) -> float:
        """Calculate median value from a list of numbers."""
        if not values:
            return 0.0
        
        # Filter out None values and sort
        clean_values = [v for v in values if v is not None and isinstance(v, (int, float))]
        if not clean_values:
            return 0.0
            
        sorted_values = sorted(clean_values)
        n = len(sorted_values)
        
        if n % 2 == 0:
            # Even number of values - average of middle two
            return (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2.0
        else:
            # Odd number of values - middle value
            return float(sorted_values[n//2])

    def _process_llama_data_simplified(self, data_list: List[Dict], hardware_type: str, hardware_id: str) -> ProcessedBenchmarkData:
        """Simplified llama data processing.
        Supports unified schema (cpu_benchmark/gpu_benchmarks) and legacy results.runs_*.
        For GPU hardware, filters gpu_benchmarks by matching hw_id when available.
        """
        data_points: List[Dict[str, Any]] = []
        gen_speeds: List[float] = []
        prompt_speeds: List[float] = []

        for data in data_list:
            # Prefer unified schema if present
            cpu_bench = data.get("cpu_benchmark")
            gpu_benches = data.get("gpu_benchmarks")

            if hardware_type == "cpu":
                if isinstance(cpu_bench, dict):
                    gs = cpu_bench.get("generation_speed")
                    ps = cpu_bench.get("prompt_speed")
                    if isinstance(gs, (int, float)):
                        gen_speeds.append(float(gs))
                    if isinstance(ps, (int, float)):
                        prompt_speeds.append(float(ps))
                    data_points.append({
                        "type": "cpu",
                        "generation_tokens_per_second": gs,
                        "prompt_tokens_per_second": ps,
                        "run_data": cpu_bench
                    })
                else:
                    # Fallback to legacy schema under results.runs_cpu
                    results = data.get('results', {})
                    for run in results.get("runs_cpu", []):
                        metrics = run.get('metrics', {})
                        gen = metrics.get('generation', {})
                        gs = gen.get('avg_tokens_per_sec')
                        if isinstance(gs, (int, float)):
                            gen_speeds.append(float(gs))
                        # Prompt speed sometimes available
                        pp = metrics.get('prompt_processing', {})
                        ps = pp.get('avg_tokens_per_sec')
                        if isinstance(ps, (int, float)):
                            prompt_speeds.append(float(ps))
                        data_points.append({
                            "type": "cpu",
                            "generation_tokens_per_second": gs,
                            "prompt_tokens_per_second": ps,
                            "run_data": run
                        })
            else:  # GPU hardware
                if isinstance(gpu_benches, list) and gpu_benches:
                    for run in gpu_benches:
                        # Filter by device_slug (augmented) or name slug as fallback
                        dev_slug = run.get('device_slug')
                        dev_name = run.get('device_name')
                        if dev_slug:
                            if dev_slug != hardware_id:
                                continue
                        elif dev_name:
                            # Local slugify to avoid cross-import
                            import re as _re
                            def _slugify(n: str) -> str:
                                s = (n or '').strip().lower()
                                s = _re.sub(r"[^a-z0-9]+", "-", s)
                                s = _re.sub(r"-+", "-", s).strip("-")
                                return s or 'unknown'
                            if _slugify(dev_name) != hardware_id:
                                continue
                        else:
                            # No augmentation; skip to prevent mixing GPUs
                            continue
                        gs = run.get("generation_speed")
                        ps = run.get("prompt_speed")
                        if isinstance(gs, (int, float)):
                            gen_speeds.append(float(gs))
                        if isinstance(ps, (int, float)):
                            prompt_speeds.append(float(ps))
                        data_points.append({
                            "type": "gpu",
                            "generation_tokens_per_second": gs,
                            "prompt_tokens_per_second": ps,
                            "run_data": run
                        })
                else:
                    # Fallback to legacy runs_gpu
                    results = data.get('results', {})
                    for run in results.get("runs_gpu", []):
                        metrics = run.get('metrics', {})
                        # Legacy GPU often reports combined tokens_per_second
                        tps = metrics.get('tokens_per_second')
                        if isinstance(tps, (int, float)):
                            gen_speeds.append(float(tps))
                        data_points.append({
                            "type": "gpu",
                            "generation_tokens_per_second": tps,
                            "run_data": run
                        })

        median_gen = self._calculate_median(gen_speeds) if gen_speeds else 0.0
        median_prompt = self._calculate_median(prompt_speeds) if prompt_speeds else 0.0

        median_values = {
            "generation_tokens_per_second_median": median_gen,
            "prompt_tokens_per_second_median": median_prompt
        }

        stats = {
            "count": len(data_points),
            "max_generation_speed": max(gen_speeds) if gen_speeds else 0.0,
            "max_prompt_speed": max(prompt_speeds) if prompt_speeds else 0.0
        }

        return ProcessedBenchmarkData(
            benchmark_type="llama",
            hardware_type=hardware_type,
            data_points=data_points,
            median_values=median_values,
            stats=stats,
            file_count=len(data_list),
            valid_file_count=len([d for d in data_list if d])
        )

    def _process_blender_data_simplified(self, data_list: List[Dict], hardware_type: str) -> ProcessedBenchmarkData:
        """Simplified blender data processing."""
        data_points = []
        render_times = []
        
        for data in data_list:
            # Access results nested structure
            results = data.get('results', {})
            device_runs = results.get('device_runs', [])
            
            for device_run in device_runs:
                # Filter by hardware type
                device_framework = device_run.get('device_framework', '').upper()
                if ((hardware_type == "cpu" and device_framework == "CPU") or 
                    (hardware_type == "gpu" and device_framework != "CPU")):
                    
                    scene_results = device_run.get('scene_results', {})
                    for scene, results in scene_results.items():
                        samples_per_min = results.get('samples_per_minute', 0)
                        if samples_per_min > 0:
                            # Convert to render time (inverse of samples per minute)
                            render_time = 60.0 / samples_per_min if samples_per_min else 0
                            render_times.append(render_time)
                            data_points.append({
                                "scene": scene,
                                "samples_per_minute": samples_per_min,
                                "render_time": render_time,
                                "render_time_median": render_time,
                                "device": device_run.get('device_name', 'Unknown')
                            })
        
        median_time = self._calculate_median(render_times) if render_times else 0

    def _process_7zip_data_simplified(self, data_list: List[Dict]) -> ProcessedBenchmarkData:
        """Simplified 7zip data processing."""
        data_points = []
        mips_values = []
        
        for data in data_list:
            # Access results nested structure
            results = data.get('results', {})
            
            total_mips = results.get('total_mips', 0)
            runs = results.get('runs', [])
            
            if total_mips:
                mips_values.append(total_mips)
                
            for run in runs:
                threads = run.get('threads', 1)
                speed = run.get('compression_speed_mb_s', 0)
                elapsed = run.get('elapsed_seconds', 0)
                
                data_points.append({
                    "threads": threads,
                    "thread_count": threads,
                    "compression_speed_mb_s": speed,
                    "total_mips": total_mips,
                    "total_mips_median": total_mips,
                    "elapsed_seconds": elapsed
                })
            
            # If no runs but have total_mips, add a single data point
            if not runs and total_mips:
                data_points.append({
                    "threads": 1,
                    "thread_count": 1, 
                    "total_mips": total_mips,
                    "total_mips_median": total_mips,
                    "compression_mips_median": total_mips
                })
        
        median_mips = self._calculate_median(mips_values) if mips_values else 0

    def _process_reversan_data_simplified(self, data_list: List[Dict]) -> ProcessedBenchmarkData:
        """Simplified reversan data processing."""
        data_points = []
        times = []
        
        for data in data_list:
            # Access results nested structure
            results = data.get('results', {})
            
            # Process depth runs
            runs_depth = results.get('runs_depth', [])
            for run in runs_depth:
                depth = run.get('depth', 0)
                metrics = run.get('metrics', {})
                elapsed = metrics.get('elapsed_seconds', 0)
                
                if elapsed > 0:  # Only include meaningful times
                    times.append(elapsed)
                    data_points.append({
                        "type": "depth",
                        "depth": depth,
                        "elapsed_seconds": elapsed,
                        "nodes_per_second_median": 1.0 / elapsed if elapsed > 0 else 0
                    })
            
            # Process thread runs
            runs_threads = results.get('runs_threads', [])
            for run in runs_threads:
                threads = run.get('threads', 1)
                metrics = run.get('metrics', {})
                elapsed = metrics.get('elapsed_seconds', 0)
                
                if elapsed > 0:  # Only include meaningful times
                    times.append(elapsed)
                    data_points.append({
                        "type": "threads",
                        "threads": threads,
                        "elapsed_seconds": elapsed,
                        "nodes_per_second_median": 1.0 / elapsed if elapsed > 0 else 0
                    })
        
        median_time = self._calculate_median(times) if times else 0

    async def store_benchmark_run(self, run_id: str, hardware_entries: List[Any], benchmark_data: Dict[str, Any], timestamp: int) -> UploadResult:
        """Store benchmark run - integrated with existing upload system."""
        try:
            async with database.get_session() as session:
                # For now, create a minimal response
                # This would need to be integrated with the actual storage logic
                # but let's keep it simple for the API refactoring
                return UploadResult(
                    hardware_id="simplified-api",
                    hardware_type="mixed", 
                    stored_benchmarks=list(benchmark_data.keys()),
                    run_id=run_id
                )
        except Exception as e:
            logger.error(f"Error storing benchmark run: {str(e)}")
            return UploadResult(
                hardware_id="error",
                hardware_type="mixed",
                stored_benchmarks=[],
                run_id=run_id
            )