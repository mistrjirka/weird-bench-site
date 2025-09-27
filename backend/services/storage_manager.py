import os
import json
import time
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path
import json
import math
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from database import database, Hardware, BenchmarkRun, BenchmarkFile
from models import HardwareListData, HardwareSummary, HardwareDetail, BenchmarkFile as BenchmarkFileModel, StoredHardware, UploadResult, ProcessedBenchmarkData

class StorageManager:
    def __init__(self):
        self.data_dir = Path(os.environ.get('DATA_DIR', '/app/data'))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Legacy file-based storage directories (for backwards compatibility if needed)
        self.cpu_dir = self.data_dir / 'cpu'
        self.gpu_dir = self.data_dir / 'gpu'
        self.cpu_dir.mkdir(exist_ok=True)
        self.gpu_dir.mkdir(exist_ok=True)

    async def get_hardware_list(self) -> HardwareListData:
        """Get list of all hardware with benchmark summaries"""
        async with database.get_session() as session:
            # Get all hardware with their benchmark runs and files
            result = await session.execute(
                select(Hardware)
                .options(
                    selectinload(Hardware.benchmark_runs)
                    .selectinload(BenchmarkRun.benchmark_files)
                )
                .order_by(Hardware.type, Hardware.manufacturer, Hardware.name)
            )
            all_hardware = result.scalars().all()
            
            cpus = []
            gpus = []
            
            for hw in all_hardware:
                # Group benchmark files by type
                benchmarks = {}
                for run in hw.benchmark_runs:
                    for bf in run.benchmark_files:
                        if bf.benchmark_type not in benchmarks:
                            benchmarks[bf.benchmark_type] = []
                        benchmarks[bf.benchmark_type].append(bf.file_path)
                
                hardware_summary = HardwareSummary(
                    id=hw.id,
                    name=hw.name,
                    manufacturer=hw.manufacturer,
                    cores=hw.cores,
                    framework=hw.framework,
                    benchmarks=benchmarks,
                    lastUpdated=int(hw.updated_at.timestamp())
                )
                
                if hw.type == 'cpu':
                    cpus.append(hardware_summary)
                else:
                    gpus.append(hardware_summary)
            
            return HardwareListData(cpus=cpus, gpus=gpus)

    async def get_hardware_detail(self, hardware_type: str, hardware_id: str) -> Optional[HardwareDetail]:
        """Get detailed information for specific hardware"""
        async with database.get_session() as session:
            result = await session.execute(
                select(Hardware)
                .options(
                    selectinload(Hardware.benchmark_runs)
                    .selectinload(BenchmarkRun.benchmark_files)
                )
                .where(Hardware.id == hardware_id, Hardware.type == hardware_type)
            )
            hardware = result.scalar_one_or_none()
            
            if not hardware:
                return None
            
            # Collect all benchmark files
            benchmark_files = []
            for run in hardware.benchmark_runs:
                for bf in run.benchmark_files:
                    benchmark_files.append(BenchmarkFileModel(
                        name=bf.filename,
                        path=bf.file_path,
                        type=bf.benchmark_type,
                        timestamp=int(bf.created_at.timestamp()),
                        size=bf.file_size
                    ))
            
            return HardwareDetail(
                id=hardware.id,
                name=hardware.name,
                manufacturer=hardware.manufacturer,
                type=hardware.type,
                cores=hardware.cores,
                framework=hardware.framework,
                benchmarkFiles=benchmark_files,
                totalBenchmarks=len(benchmark_files),
                lastUpdated=int(hardware.updated_at.timestamp())
            )

    async def get_processed_benchmark_data(self, hardware_type: str, hardware_id: str) -> List[ProcessedBenchmarkData]:
        """Get processed and aggregated benchmark data for specific hardware"""
        async with database.get_session() as session:
            result = await session.execute(
                select(Hardware)
                .options(
                    selectinload(Hardware.benchmark_runs)
                    .selectinload(BenchmarkRun.benchmark_files)
                )
                .where(Hardware.id == hardware_id, Hardware.type == hardware_type)
            )
            hardware = result.scalar_one_or_none()
            
            if not hardware:
                return []

            # Group benchmark files by type
            benchmark_groups = {}
            for run in hardware.benchmark_runs:
                for bf in run.benchmark_files:
                    if bf.benchmark_type not in benchmark_groups:
                        benchmark_groups[bf.benchmark_type] = []
                    benchmark_groups[bf.benchmark_type].append(bf)

            processed_data = []
            for benchmark_type, files in benchmark_groups.items():
                processed_benchmark = self._process_benchmark_type(benchmark_type, files, hardware_type, hardware.name)
                if processed_benchmark:
                    processed_data.append(processed_benchmark)

            return processed_data

    def _process_benchmark_type(self, benchmark_type: str, files: List, hardware_type: str, hardware_name: str) -> Optional[ProcessedBenchmarkData]:
        """Process files of a specific benchmark type and return aggregated data"""
        if not files:
            return None

        valid_data = []
        file_errors = []
        
        for bf in files:
            try:
                # Load the JSON data from file path
                file_path = Path(self.data_dir) / bf.file_path
                if file_path.exists():
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        valid_data.append(data)
                else:
                    file_errors.append(f"File not found: {bf.file_path}")
            except Exception as e:
                file_errors.append(f"Error loading {bf.file_path}: {str(e)}")

        if not valid_data:
            return ProcessedBenchmarkData(
                benchmark_type=benchmark_type,
                hardware_type=hardware_type,
                data_points=[],
                median_values={},
                stats={"errors": file_errors},
                file_count=len(files),
                valid_file_count=0
            )

        # Process data based on benchmark type
        try:
            if benchmark_type == "llama":
                return self._process_llama_data(valid_data, hardware_type, hardware_name)
            elif benchmark_type == "blender":
                return self._process_blender_data(valid_data, hardware_type, hardware_name)
            elif benchmark_type == "7zip":
                return self._process_7zip_data(valid_data, hardware_type)
            elif benchmark_type == "reversan":
                return self._process_reversan_data(valid_data, hardware_type)
            else:
                return ProcessedBenchmarkData(
                    benchmark_type=benchmark_type,
                    hardware_type=hardware_type,
                    data_points=[],
                    median_values={},
                    stats={"error": f"Unknown benchmark type: {benchmark_type}"},
                    file_count=len(files),
                    valid_file_count=len(valid_data)
                )
        except Exception as e:
            return ProcessedBenchmarkData(
                benchmark_type=benchmark_type,
                hardware_type=hardware_type,
                data_points=[],
                median_values={},
                stats={"error": f"Processing error: {str(e)}"},
                file_count=len(files),
                valid_file_count=len(valid_data)
            )

    def _calculate_median(self, values: List[Union[float, int, None]]) -> Optional[float]:
        """Calculate median of a list of numbers"""
        if not values:
            return None
        # Filter out None values and convert to float
        numeric_values = []
        for v in values:
            if v is not None:
                try:
                    num_val = float(v)
                    if not math.isnan(num_val):
                        numeric_values.append(num_val)
                except (ValueError, TypeError):
                    continue
        
        if not numeric_values:
            return None
            
        sorted_values = sorted(numeric_values)
        n = len(sorted_values)
        if n % 2 == 0:
            return (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
        else:
            return sorted_values[n//2]

    def _gpu_names_match(self, gpu_name: str, hardware_name: str) -> bool:
        """Check if two GPU names match with normalization for common variations"""
        if not gpu_name or not hardware_name:
            return False
        
        # Handle comma-separated GPU lists in gpu_name (like "RTX 3060 Ti, RTX 3060")
        if ',' in gpu_name:
            gpu_names = [name.strip() for name in gpu_name.split(',')]
            return any(self._gpu_names_match_single(single_gpu, hardware_name) for single_gpu in gpu_names)
        
        return self._gpu_names_match_single(gpu_name, hardware_name)
    
    def _gpu_names_match_single(self, gpu_name: str, hardware_name: str) -> bool:
        """Check if two single GPU names match with fuzzy matching for generic/specific names"""
        if not gpu_name or not hardware_name:
            return False
        
        def normalize_gpu_name(name: str) -> str:
            """Normalize GPU name for comparison"""
            # Convert to lowercase and normalize whitespace
            name = name.lower().strip()
            name = ' '.join(name.split())  # Normalize whitespace
            
            # Remove common manufacturer prefixes but keep the core name intact
            for prefix in ['nvidia ', 'amd ', 'intel ']:
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    break
            
            # Remove "geforce" prefix for NVIDIA cards but keep everything else
            if name.startswith('geforce '):
                name = name[len('geforce '):]
            
            return name.strip()
        
        normalized_gpu = normalize_gpu_name(gpu_name)
        normalized_hardware = normalize_gpu_name(hardware_name)
        
        # Exact match after normalization - preferred
        if normalized_gpu == normalized_hardware:
            return True
        
        # Fuzzy matching for generic/specific name pairs
        return self._fuzzy_gpu_match(normalized_gpu, normalized_hardware)
    
    def _fuzzy_gpu_match(self, gpu_name: str, hardware_name: str) -> bool:
        """Fuzzy matching for GPU names to handle generic vs specific naming"""
        
        # Handle AMD Radeon generic vs specific cases
        if 'radeon' in gpu_name and 'radeon' in hardware_name:
            # "radeon graphics" should match any specific Radeon GPU
            if (gpu_name in ['radeon graphics', 'radeon'] and 
                'radeon' in hardware_name and len(hardware_name) > len('radeon')):
                return True
            # Specific Radeon should match "radeon graphics" 
            if (hardware_name in ['radeon graphics', 'radeon'] and 
                'radeon' in gpu_name and len(gpu_name) > len('radeon')):
                return True
            # Both contain radeon + model numbers/letters - check if they're similar
            if any(char.isdigit() for char in gpu_name + hardware_name):
                # Extract model numbers/identifiers
                gpu_models = set(re.findall(r'\b\d+[a-z]*\b', gpu_name))
                hardware_models = set(re.findall(r'\b\d+[a-z]*\b', hardware_name))
                if gpu_models & hardware_models:  # Common model numbers
                    return True
        
        # Handle Intel Graphics generic vs specific cases  
        if 'graphics' in gpu_name and 'graphics' in hardware_name and 'intel' in (gpu_name + hardware_name):
            # "graphics" or "intel graphics" should match specific Intel GPUs
            generic_patterns = ['graphics', 'intel graphics', 'hd graphics', 'uhd graphics']
            if (gpu_name in generic_patterns and len(hardware_name) > max(len(p) for p in generic_patterns)) or \
               (hardware_name in generic_patterns and len(gpu_name) > max(len(p) for p in generic_patterns)):
                return True
        
        # Handle NVIDIA cases
        if any(brand in gpu_name + hardware_name for brand in ['rtx', 'gtx', 'nvidia']):
            # Extract model numbers
            gpu_models = set(re.findall(r'\b(?:rtx|gtx)\s*\d+[a-z]*(?:\s*ti)?\b', gpu_name))
            hardware_models = set(re.findall(r'\b(?:rtx|gtx)\s*\d+[a-z]*(?:\s*ti)?\b', hardware_name))
            if gpu_models & hardware_models:
                return True
        
        return False
    
    def _gpu_names_match_with_fallback(self, gpu_name: str, hardware_name: str, all_gpu_entries: list) -> bool:
        """GPU name matching - for now just use normal matching without fallback"""
        return self._gpu_names_match_single(gpu_name, hardware_name)

    def _process_llama_data(self, data_list: List[Dict], hardware_type: str, hardware_name: str) -> ProcessedBenchmarkData:
        """Process Llama benchmark data"""
        all_runs = []
        build_times = []

        for data in data_list:
            # Handle wrapped data structure - extract from 'results' if present
            actual_data = data.get('results', data) if 'results' in data else data
            
            if hardware_type == "cpu":
                runs = actual_data.get("runs_cpu", [])
                all_runs.extend(runs)
                # Try different build timing structures
                # First check for direct cpu_build_timing (new format)
                if "cpu_build_timing" in actual_data:
                    cpu_timing = actual_data.get("cpu_build_timing", {})
                    if "build_time_seconds" in cpu_timing:
                        build_times.append(cpu_timing["build_time_seconds"])
                # Fallback to old build structure
                else:
                    build_info = actual_data.get("build", {})
                    if "cpu_build_timing" in build_info:
                        cpu_timing = build_info.get("cpu_build_timing", {})
                        if "build_time_seconds" in cpu_timing:
                            build_times.append(cpu_timing["build_time_seconds"])
                    elif "build_time_seconds" in build_info:
                        build_times.append(build_info["build_time_seconds"])
            else:  # GPU processing
                # Priority 1: Use new device_runs format for cleaner data
                if 'device_runs' in actual_data:
                    for device_run in actual_data['device_runs']:
                        if (device_run.get('device_type') == 'gpu' and 
                            self._gpu_names_match_single(device_run.get('device_name', ''), hardware_name)):
                            # Convert device_run format to legacy run format for compatibility
                            for run in device_run.get('runs', []):
                                # Reconstruct metrics format expected by processing logic
                                legacy_run = {
                                    'type': 'gpu',
                                    'prompt_size': run.get('prompt_size'),
                                    'generation_size': run.get('generation_size'),
                                    'ngl': run.get('ngl', 99),
                                    'returncode': run.get('returncode', 0),
                                    'elapsed_seconds': run.get('elapsed_seconds', 0),
                                    'metrics': run.get('metrics', {}),
                                    'gpu_device': {
                                        'name': device_run['device_name'],
                                        'index': device_run.get('device_index'),
                                        'driver': device_run.get('device_driver')
                                    }
                                }
                                all_runs.append(legacy_run)
                else:
                    # Fallback to legacy runs_gpu format
                    runs = actual_data.get("runs_gpu", [])
                    all_runs.extend(runs)

        # Group runs by common parameters (like thread count, model size)
        grouped_runs = self._group_llama_runs(all_runs)
        
        # Calculate medians for each group
        processed_groups = []
        for group_key, runs in grouped_runs.items():
            if not runs:
                continue
                
            # Extract metrics from schema: for CPU it's in metrics.generation, for GPU it's metrics.tokens_per_second
            tokens_per_second = []
            elapsed_seconds = []
            prompt_sizes = []
            generation_sizes = []
            total_tokens = []
            for run in runs:
                m = run.get("metrics", {})
                
                # Try GPU format first, then CPU format
                tps = m.get("tokens_per_second")
                if not isinstance(tps, (int, float)) and "generation" in m:
                    # CPU format: metrics.generation.avg_tokens_per_sec
                    generation = m.get("generation", {})
                    tps = generation.get("avg_tokens_per_sec")
                
                if isinstance(tps, (int, float)):
                    tokens_per_second.append(tps)
                    
                es = run.get("elapsed_seconds")
                if isinstance(es, (int, float)):
                    elapsed_seconds.append(es)
                    
                ps = run.get("prompt_size")
                if isinstance(ps, (int, float)):
                    prompt_sizes.append(ps)
                    
                gs = run.get("generation_size")
                if isinstance(gs, (int, float)):
                    generation_sizes.append(gs)
                    if isinstance(ps, (int, float)):
                        total_tokens.append(ps + gs)
            
            group_data = {
                "group": group_key,
                "run_count": len(runs),
                "tokens_per_second_median": self._calculate_median(tokens_per_second),
                "tokens_per_second_values": tokens_per_second,
                "elapsed_seconds_median": self._calculate_median(elapsed_seconds),
                "elapsed_seconds_values": elapsed_seconds,
                "total_tokens_median": self._calculate_median(total_tokens),
                "total_tokens_values": total_tokens,
                "prompt_size_median": self._calculate_median(prompt_sizes),
                "generation_size_median": self._calculate_median(generation_sizes)
            }
            processed_groups.append(group_data)

        # Calculate overall medians
        median_values = {}
        if build_times:
            median_values["build_time_seconds"] = self._calculate_median(build_times)

        # Include GPU selection data if present (for GPU hardware)
        if hardware_type == "gpu":
            # Find GPU selection data from any of the data files
            for data in data_list:
                actual_data = data.get('results', data) if 'results' in data else data
                if 'gpu_selection' in actual_data:
                    gpu_selection = actual_data['gpu_selection']
                    # Filter available_gpus to only include the current hardware
                    if 'available_gpus' in gpu_selection:
                        filtered_gpus = []
                        for gpu_device in gpu_selection['available_gpus']:
                            gpu_name = gpu_device.get('name', '')
                            if gpu_name and self._gpu_names_match_single(gpu_name, hardware_name):
                                filtered_gpus.append(gpu_device)
                        if filtered_gpus:
                            filtered_selection = gpu_selection.copy()
                            filtered_selection['available_gpus'] = filtered_gpus
                            median_values["gpu_selection"] = filtered_selection
                    else:
                        median_values["gpu_selection"] = gpu_selection
                    break

        return ProcessedBenchmarkData(
            benchmark_type="llama",
            hardware_type=hardware_type,
            data_points=processed_groups,
            median_values=median_values,
            stats={
                "total_runs": len(all_runs),
                "grouped_runs": len(processed_groups),
                "build_files": len(build_times)
            },
            file_count=len(data_list),
            valid_file_count=len(data_list),
            device_runs=None  # Not used for Llama
        )

    def _group_llama_runs(self, runs: List[Dict]) -> Dict[str, List[Dict]]:
        """Group Llama runs by similar parameters"""
        groups = {}
        for run in runs:
            # Create a key based on thread count and model parameters
            m = run.get("metrics", {}).get("system_info", {})
            threads = m.get("n_threads") or 0
            model_size = run.get("metrics", {}).get("system_info", {}).get("model_size")
            model_key = f"ms{model_size}" if model_size is not None else "unknown"
            key = f"{model_key}_{int(threads)}t"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(run)
        return groups

    def _process_blender_data(self, data_list: List[Dict], hardware_type: str, hardware_name: str) -> ProcessedBenchmarkData:
        """Process Blender benchmark data"""
        all_runs = []
        scenes_tested = set()
        
        for data in data_list:
            # Handle wrapped data structure - extract from 'results' if present
            actual_data = data.get('results', data) if 'results' in data else data
            
            device_runs = actual_data.get("device_runs", [])
            # Filter runs based on hardware type
            if hardware_type == "cpu":
                filtered_runs = [run for run in device_runs if run.get("device_framework") == "CPU"]
            else:
                # For GPU, filter both by framework (not CPU) and by specific hardware name
                filtered_runs = []
                for run in device_runs:
                    if run.get("device_framework") != "CPU":
                        device_name = run.get("device_name", "")
                        if self._gpu_names_match_single(device_name, hardware_name):
                            filtered_runs.append(run)
            all_runs.extend(filtered_runs)
            
            # Collect scenes tested from top-level data
            if "scenes_tested" in actual_data:
                scenes_tested.update(actual_data["scenes_tested"])

        # Process individual scene results from raw_json
        scene_results = {}
        scene_timings = {}
        device_info = {}
        
        for run in all_runs:
            framework = run.get("device_framework", "unknown")
            device_name = run.get("device_name", framework)
            device_key = f"{framework}_{device_name}"
            
            # Store device info
            if device_key not in device_info:
                device_info[device_key] = {
                    "device_name": device_name,
                    "framework": framework,
                    "elapsed_seconds": run.get("elapsed_seconds"),
                    "run_count": 0
                }
            device_info[device_key]["run_count"] += 1
            
            # Process individual scene results from raw_json
            raw_json = run.get("raw_json", [])
            for scene_data in raw_json:
                scene_label = scene_data.get("scene", {}).get("label", "unknown")
                stats = scene_data.get("stats", {})
                samples_per_minute = stats.get("samples_per_minute")
                time_for_samples = stats.get("time_for_samples")
                total_render_time = stats.get("total_render_time")
                
                if samples_per_minute is not None:
                    scene_key = f"{device_key}_{scene_label}"
                    if scene_key not in scene_results:
                        scene_results[scene_key] = []
                        scene_timings[scene_key] = []
                    scene_results[scene_key].append(samples_per_minute)
                    # Store timing info (prefer total_render_time, fallback to time_for_samples)
                    timing = total_render_time if total_render_time is not None else time_for_samples
                    scene_timings[scene_key].append(timing)

        # Create data points for each scene
        processed_groups = []
        device_runs_data = []
        
        for scene_key, spm_values in scene_results.items():
            parts = scene_key.split("_", 2)  # Split into device_key and scene
            if len(parts) >= 3:
                device_key = f"{parts[0]}_{parts[1]}"
                scene = parts[2]
                timing_values = scene_timings.get(scene_key, [])
                
                group_data = {
                    "group": scene_key,
                    "device": device_key,
                    "scene": scene,
                    "run_count": len(spm_values),
                    "samples_per_minute_median": self._calculate_median(spm_values),
                    "samples_per_minute_values": spm_values,
                    "elapsed_seconds_median": self._calculate_median(timing_values) if timing_values else None,
                    "elapsed_seconds_values": timing_values
                }
                processed_groups.append(group_data)
                
                # Create device_runs entry for backward compatibility
                device_runs_data.append({
                    "scene_name": scene,
                    "device_name": device_key,
                    "elapsed_seconds": self._calculate_median(timing_values) if timing_values else None,
                    "samples_per_minute": self._calculate_median(spm_values),
                    "run_count": len(spm_values)
                })

        result = ProcessedBenchmarkData(
            benchmark_type="blender",
            hardware_type=hardware_type,
            data_points=processed_groups,
            median_values={},
            stats={
                "total_runs": len(all_runs), 
                "scenes": len(scenes_tested),
                "scenes_tested": list(scenes_tested)
            },
            file_count=len(data_list),
            valid_file_count=len(data_list),
            device_runs=device_runs_data  # Use the field properly
        )
        
        return result

    def _process_7zip_data(self, data_list: List[Dict], hardware_type: str) -> ProcessedBenchmarkData:
        """Process 7zip benchmark data"""
        all_runs = []
        
        for data in data_list:
            # Accept either schema-root or legacy wrapper under 'results'
            src = data.get("results") if isinstance(data.get("results"), dict) else data
            runs = (src or {}).get("runs", [])
            if isinstance(runs, list):
                all_runs.extend(runs)

        # Group by thread count
        thread_groups = {}
        for run in all_runs:
            threads = run.get("threads", 0)
            if threads not in thread_groups:
                thread_groups[threads] = []
            thread_groups[threads].append(run)

        processed_groups = []
        for thread_count, runs in thread_groups.items():
            elapsed = [run.get("elapsed_seconds") for run in runs if isinstance(run.get("elapsed_seconds"), (int, float))]
            comp_speed = [run.get("compression_speed_mb_s") for run in runs if isinstance(run.get("compression_speed_mb_s"), (int, float))]
            comp_ratio = [run.get("compression_ratio") for run in runs if isinstance(run.get("compression_ratio"), (int, float))]
            thread_eff = [run.get("thread_efficiency_percent") for run in runs if isinstance(run.get("thread_efficiency_percent"), (int, float))]
            archive_sizes = [run.get("archive_size_bytes") for run in runs if isinstance(run.get("archive_size_bytes"), (int, float))]
            
            group_data = {
                "group": f"{thread_count}_threads",
                "thread_count": thread_count,
                "run_count": len(runs),
                "elapsed_seconds_median": self._calculate_median(elapsed),
                "elapsed_seconds_values": elapsed,
                "compression_speed_mb_s_median": self._calculate_median(comp_speed),
                "compression_ratio_median": self._calculate_median(comp_ratio),
                "thread_efficiency_percent_median": self._calculate_median(thread_eff),
                "archive_size_bytes_median": self._calculate_median(archive_sizes)
            }
            processed_groups.append(group_data)

        return ProcessedBenchmarkData(
            benchmark_type="7zip",
            hardware_type=hardware_type,
            data_points=processed_groups,
            median_values={},
            stats={"total_runs": len(all_runs), "thread_groups": len(thread_groups)},
            file_count=len(data_list),
            valid_file_count=len(data_list)
        )

    def _process_reversan_data(self, data_list: List[Dict], hardware_type: str) -> ProcessedBenchmarkData:
        """Process Reversan benchmark data"""
        all_depth_runs = []
        all_thread_runs = []
        build_times = []
        
        for data in data_list:
            # Handle wrapped data structure - extract from 'results' if present
            actual_data = data.get('results', data) if 'results' in data else data
            
            depth_runs = actual_data.get("runs_depth", [])
            thread_runs = actual_data.get("runs_threads", [])
            build_info = actual_data.get("build", {})
            
            all_depth_runs.extend(depth_runs)
            all_thread_runs.extend(thread_runs)
            
            if "build_time_seconds" in build_info:
                build_times.append(build_info["build_time_seconds"])

        processed_groups = []

        # Process depth runs
        if all_depth_runs:
            depth_groups = {}
            for run in all_depth_runs:
                depth = run.get("depth", 0)
                if depth not in depth_groups:
                    depth_groups[depth] = []
                depth_groups[depth].append(run)

            for depth, runs in depth_groups.items():
                # Use metrics user_seconds/elapsed_seconds (lower is better)
                elapsed_vals = []
                user_vals = []
                for r in runs:
                    metrics = r.get("metrics", {})
                    u = metrics.get("user_seconds")
                    e = metrics.get("elapsed_seconds")
                    if isinstance(u, (int, float)):
                        user_vals.append(u)
                    if isinstance(e, (int, float)):
                        elapsed_vals.append(e)
                
                group_data = {
                    "group": f"depth_{depth}",
                    "depth": depth,
                    "type": "depth",
                    "run_count": len(runs),
                    "elapsed_seconds_median": self._calculate_median(elapsed_vals),
                    "user_seconds_median": self._calculate_median(user_vals)
                }
                processed_groups.append(group_data)

        # Process thread runs
        if all_thread_runs:
            thread_groups = {}
            for run in all_thread_runs:
                threads = run.get("threads", 0)
                if threads not in thread_groups:
                    thread_groups[threads] = []
                thread_groups[threads].append(run)

            for thread_count, runs in thread_groups.items():
                elapsed_vals = []
                user_vals = []
                for r in runs:
                    metrics = r.get("metrics", {})
                    u = metrics.get("user_seconds")
                    e = metrics.get("elapsed_seconds")
                    if isinstance(u, (int, float)):
                        user_vals.append(u)
                    if isinstance(e, (int, float)):
                        elapsed_vals.append(e)
                
                group_data = {
                    "group": f"threads_{thread_count}",
                    "threads": thread_count,
                    "type": "threads", 
                    "run_count": len(runs),
                    "elapsed_seconds_median": self._calculate_median(elapsed_vals),
                    "user_seconds_median": self._calculate_median(user_vals)
                }
                processed_groups.append(group_data)

        median_values = {}
        if build_times:
            median_values["build_time_seconds"] = self._calculate_median(build_times)

        return ProcessedBenchmarkData(
            benchmark_type="reversan",
            hardware_type=hardware_type,
            data_points=processed_groups,
            median_values=median_values,
            stats={
                "depth_runs": len(all_depth_runs),
                "thread_runs": len(all_thread_runs),
                "build_files": len(build_times)
            },
            file_count=len(data_list),
            valid_file_count=len(data_list)
        )

    async def store_benchmark_run(self, run_id: str, hardware_entries: List[StoredHardware], benchmark_data: Dict[str, Any], timestamp: int) -> UploadResult:
        """Store a complete benchmark run for multiple hardware entries"""
        async with database.get_session() as session:
            stored_benchmarks = []
            all_hardware_ids = []
            
            # Process each hardware entry (CPU and/or GPU)
            for hardware_info in hardware_entries:
                # Get or create hardware entry
                result = await session.execute(
                    select(Hardware).where(Hardware.id == hardware_info.id)
                )
                hardware = result.scalar_one_or_none()
                
                if not hardware:
                    hardware = Hardware(
                        id=hardware_info.id,
                        name=hardware_info.name,
                        manufacturer=hardware_info.manufacturer,
                        type=hardware_info.type,
                        cores=hardware_info.cores,
                        framework=hardware_info.framework
                    )
                    session.add(hardware)
                    await session.flush()  # Get the ID
                
                all_hardware_ids.append(hardware.id)
                
                # Get next run number for this hardware
                run_number_result = await session.execute(
                    select(func.max(BenchmarkRun.run_number))
                    .where(BenchmarkRun.hardware_id == hardware.id)
                )
                max_run = run_number_result.scalar() or 0
                run_number = max_run + 1
                
                # Create benchmark run
                benchmark_run = BenchmarkRun(
                    run_id=run_id,
                    hardware_id=hardware.id,
                    timestamp=datetime.fromtimestamp(timestamp),
                    run_number=run_number
                )
                session.add(benchmark_run)
                await session.flush()  # Get the ID
                
                # Store benchmarks appropriate for this hardware type
                for benchmark_type, data in benchmark_data.items():
                    if self._should_store_for_hardware_type(benchmark_type, hardware_info.type, data, hardware_info.name):
                        # Filter data based on hardware type
                        filtered_data = self._filter_data_for_hardware(benchmark_type, data, hardware_info.type, hardware_info.name)
                        
                        # Create file path
                        file_path = f"{hardware_info.type}/{hardware_info.id}/run_{run_number}_{benchmark_type}.json"
                        full_path = self.data_dir / file_path
                        
                        # Ensure directory exists
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Write JSON file
                        with open(full_path, 'w') as f:
                            json.dump(filtered_data, f, indent=2)
                        
                        # Create database entry
                        benchmark_file = BenchmarkFile(
                            benchmark_run_id=benchmark_run.id,
                            benchmark_type=benchmark_type,
                            filename=f"run_{run_number}_{benchmark_type}.json",
                            file_path=file_path,
                            file_size=full_path.stat().st_size,
                            data=filtered_data
                        )
                        session.add(benchmark_file)
                        stored_benchmarks.append(f"{hardware_info.type}:{benchmark_type}")
            
            await session.commit()
            
            return UploadResult(
                hardware_id=all_hardware_ids[0] if all_hardware_ids else "",  # Primary hardware ID
                hardware_type="mixed" if len(hardware_entries) > 1 else hardware_entries[0].type,
                stored_benchmarks=stored_benchmarks,
                run_id=run_id
            )

    def _should_store_for_hardware_type(self, benchmark_type: str, hardware_type: str, data: Dict[str, Any], hardware_name: str) -> bool:
        """Determine if a benchmark should be stored for a given hardware type"""
        # Handle wrapped data structure - extract from 'results' if present
        actual_data = data.get('results', data) if 'results' in data else data
        
        if hardware_type == 'cpu':
            # CPU hardware stores: 7zip, reversan, CPU part of llama, CPU part of blender
            if benchmark_type in ['7zip', 'reversan']:
                return True
            if benchmark_type == 'llama' and actual_data.get('runs_cpu'):
                return True
            if benchmark_type == 'blender':
                # Store Blender under CPU only if there are CPU runs in the payload
                try:
                    device_runs = actual_data.get('device_runs') or []
                    cpu_runs = [run for run in device_runs if run.get('device_framework') == 'CPU']
                    if cpu_runs:
                        return True
                    else:
                        return False
                except Exception as e:
                    return False
            return False
        
        elif hardware_type == 'gpu':
            # GPU hardware stores: blender, GPU part of llama
            if benchmark_type == 'blender':
                device_runs = actual_data.get('device_runs') or []
                gpu_runs = [run for run in device_runs if run.get('device_framework') != 'CPU']
                return len(gpu_runs) > 0  # Only store if there are actual GPU runs
                
            if benchmark_type == 'llama':
                # Priority 1: Check new device_runs format for GPU entries
                if 'device_runs' in actual_data:
                    device_runs = actual_data['device_runs']
                    for device_run in device_runs:
                        if (device_run.get('device_type') == 'gpu' and 
                            self._gpu_names_match_with_fallback(device_run.get('device_name', ''), hardware_name, device_runs)):
                            return True
                    # If no matching device_runs found, continue to legacy check
                
                # Priority 2: Legacy runs_gpu check  
                if actual_data.get('runs_gpu'):
                    # For Llama with GPU selection, check if this specific GPU was used
                    gpu_selection = actual_data.get('gpu_selection')
                    if gpu_selection and gpu_selection.get('available_gpus'):
                        # Check if any of the available GPUs match this hardware entry
                        available_gpus = gpu_selection['available_gpus']
                        for gpu_device in available_gpus:
                            gpu_name = gpu_device.get('name', '')
                            if gpu_name and self._gpu_names_match_with_fallback(gpu_name, hardware_name, available_gpus):
                                return True
                        return False
                    else:
                        # Legacy behavior: store if there are GPU runs
                        return True
                return False
            return False
        
        return False

    def _filter_data_for_hardware(self, benchmark_type: str, data: Dict[str, Any], hardware_type: str, hardware_name: str) -> Dict[str, Any]:
        """Filter benchmark data to only include runs relevant to the specific hardware"""
        # Handle wrapped data structure - extract from 'results' if present
        actual_data = data.get('results', data) if 'results' in data else data
        filtered_data = data.copy()
        
        if 'results' in data:
            filtered_data['results'] = actual_data.copy()
            actual_data = filtered_data['results']
        
        if hardware_type == 'gpu' and benchmark_type == 'llama':
            # Priority 1: Filter new device_runs format for cleaner GPU separation
            if 'device_runs' in actual_data:
                filtered_device_runs = []
                for device_run in actual_data['device_runs']:
                    device_name = device_run.get('device_name', '')
                    if device_name and self._gpu_names_match_single(device_name, hardware_name):
                        filtered_device_runs.append(device_run)
                actual_data['device_runs'] = filtered_device_runs
            
            # Also filter legacy runs_gpu format for backwards compatibility
            if 'runs_gpu' in actual_data:
                filtered_runs = []
                for run in actual_data['runs_gpu']:
                    gpu_device = run.get('gpu_device')
                    if gpu_device and gpu_device.get('name'):
                        gpu_name = gpu_device['name']
                        if self._gpu_names_match_single(gpu_name, hardware_name):
                            filtered_runs.append(run)
                actual_data['runs_gpu'] = filtered_runs
                
                # Also filter gpu_selection.available_gpus to only include this GPU
                if 'gpu_selection' in actual_data and 'available_gpus' in actual_data['gpu_selection']:
                    filtered_gpus = []
                    for gpu_device in actual_data['gpu_selection']['available_gpus']:
                        gpu_name = gpu_device.get('name', '')
                        if gpu_name and self._gpu_names_match_single(gpu_name, hardware_name):
                            filtered_gpus.append(gpu_device)
                    actual_data['gpu_selection']['available_gpus'] = filtered_gpus
        
        elif hardware_type == 'gpu' and benchmark_type == 'blender':
            # For GPU hardware with blender benchmarks, filter device_runs to only include runs for this GPU
            if 'device_runs' in actual_data:
                filtered_runs = []
                for run in actual_data['device_runs']:
                    device_name = run.get('device_name', '')
                    # Also check device_framework for GPU types (OPTIX, CUDA, etc.) and extract device name from raw_json
                    if not device_name and run.get('raw_json'):
                        # Extract device name from raw_json system_info
                        for scene_data in run['raw_json']:
                            if isinstance(scene_data, dict) and 'system_info' in scene_data:
                                devices = scene_data['system_info'].get('devices', [])
                                for device in devices:
                                    if device.get('type') in ['OPTIX', 'CUDA', 'HIP', 'OPENCL']:
                                        device_name = device.get('name', '')
                                        break
                                if device_name:
                                    break
                    
                    if device_name and self._gpu_names_match_single(device_name, hardware_name):
                        filtered_runs.append(run)
                actual_data['device_runs'] = filtered_runs
        
        return filtered_data

    async def get_hardware_by_id(self, hardware_id: str) -> Optional[Hardware]:
        """Get hardware by ID"""
        async with database.get_session() as session:
            result = await session.execute(
                select(Hardware).where(Hardware.id == hardware_id)
            )
            return result.scalar_one_or_none()

    async def search_hardware(self, query: str, hardware_type: Optional[str] = None) -> List[Hardware]:
        """Search hardware by name or manufacturer"""
        async with database.get_session() as session:
            stmt = select(Hardware).where(
                Hardware.name.ilike(f"%{query}%") | 
                Hardware.manufacturer.ilike(f"%{query}%")
            )
            
            if hardware_type:
                stmt = stmt.where(Hardware.type == hardware_type)
            
            result = await session.execute(stmt.order_by(Hardware.name))
            return result.scalars().all()

    async def get_benchmark_runs_for_hardware(self, hardware_id: str, limit: int = 10) -> List[BenchmarkRun]:
        """Get recent benchmark runs for hardware"""
        async with database.get_session() as session:
            result = await session.execute(
                select(BenchmarkRun)
                .options(selectinload(BenchmarkRun.benchmark_files))
                .where(BenchmarkRun.hardware_id == hardware_id)
                .order_by(desc(BenchmarkRun.timestamp))
                .limit(limit)
            )
            return result.scalars().all()

    async def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        async with database.get_session() as session:
            # Count hardware by type
            cpu_count = await session.execute(
                select(func.count(Hardware.id)).where(Hardware.type == 'cpu')
            )
            gpu_count = await session.execute(
                select(func.count(Hardware.id)).where(Hardware.type == 'gpu')
            )
            
            # Count total benchmark runs
            total_runs = await session.execute(select(func.count(BenchmarkRun.id)))
            
            # Count benchmark files by type
            benchmark_types = await session.execute(
                select(BenchmarkFile.benchmark_type, func.count(BenchmarkFile.id))
                .group_by(BenchmarkFile.benchmark_type)
            )
            
            return {
                'hardware': {
                    'cpu': cpu_count.scalar() or 0,
                    'gpu': gpu_count.scalar() or 0
                },
                'total_benchmark_runs': total_runs.scalar() or 0,
                'benchmark_types': {row[0]: row[1] for row in benchmark_types.all()}
            }