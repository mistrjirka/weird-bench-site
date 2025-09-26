import os
import json
import time
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
                processed_benchmark = self._process_benchmark_type(benchmark_type, files, hardware_type)
                if processed_benchmark:
                    processed_data.append(processed_benchmark)

            return processed_data

    def _process_benchmark_type(self, benchmark_type: str, files: List, hardware_type: str) -> Optional[ProcessedBenchmarkData]:
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
                return self._process_llama_data(valid_data, hardware_type)
            elif benchmark_type == "blender":
                return self._process_blender_data(valid_data, hardware_type)
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

    def _process_llama_data(self, data_list: List[Dict], hardware_type: str) -> ProcessedBenchmarkData:
        """Process Llama benchmark data"""
        all_runs = []
        build_times = []

        for data in data_list:
            # Handle wrapped data structure - extract from 'results' if present
            actual_data = data.get('results', data) if 'results' in data else data
            
            if hardware_type == "cpu":
                runs = actual_data.get("runs_cpu", [])
                build_info = actual_data.get("build", {}).get("cpu_build_timing", {})
                if "build_time_seconds" in build_info:
                    build_times.append(build_info["build_time_seconds"])
            else:
                runs = actual_data.get("runs_gpu", [])
            
            all_runs.extend(runs)

        # Group runs by common parameters (like thread count, model size)
        grouped_runs = self._group_llama_runs(all_runs)
        
        # Calculate medians for each group
        processed_groups = []
        for group_key, runs in grouped_runs.items():
            if not runs:
                continue
                
            # Extract metrics from schema: metrics.tokens_per_second; sizes at top-level
            tokens_per_second = []
            elapsed_seconds = []
            prompt_sizes = []
            generation_sizes = []
            total_tokens = []
            for run in runs:
                m = run.get("metrics", {})
                tps = m.get("tokens_per_second")
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
            valid_file_count=len(data_list)
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

    def _process_blender_data(self, data_list: List[Dict], hardware_type: str) -> ProcessedBenchmarkData:
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
                filtered_runs = [run for run in device_runs if run.get("device_framework") != "CPU"]
            all_runs.extend(filtered_runs)
            
            # Collect scenes tested from top-level data
            if "scenes_tested" in actual_data:
                scenes_tested.update(actual_data["scenes_tested"])

        # Process individual scene results from raw_json
        scene_results = {}
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
                
                if samples_per_minute is not None:
                    scene_key = f"{device_key}_{scene_label}"
                    if scene_key not in scene_results:
                        scene_results[scene_key] = []
                    scene_results[scene_key].append(samples_per_minute)

        # Create data points for each scene
        processed_groups = []
        for scene_key, spm_values in scene_results.items():
            parts = scene_key.split("_", 2)  # Split into device_key and scene
            if len(parts) >= 3:
                device_key = f"{parts[0]}_{parts[1]}"
                scene = parts[2]
                
                group_data = {
                    "group": scene_key,
                    "device": device_key,
                    "scene": scene,
                    "run_count": len(spm_values),
                    "samples_per_minute_median": self._calculate_median(spm_values),
                    "samples_per_minute_values": spm_values
                }
                processed_groups.append(group_data)

        return ProcessedBenchmarkData(
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
            valid_file_count=len(data_list)
        )

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
                    if self._should_store_for_hardware_type(benchmark_type, hardware_info.type, data):
                        # Create file path
                        file_path = f"{hardware_info.type}/{hardware_info.id}/run_{run_number}_{benchmark_type}.json"
                        full_path = self.data_dir / file_path
                        
                        # Ensure directory exists
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Write JSON file
                        with open(full_path, 'w') as f:
                            json.dump(data, f, indent=2)
                        
                        # Create database entry
                        benchmark_file = BenchmarkFile(
                            benchmark_run_id=benchmark_run.id,
                            benchmark_type=benchmark_type,
                            filename=f"run_{run_number}_{benchmark_type}.json",
                            file_path=file_path,
                            file_size=full_path.stat().st_size,
                            data=data
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

    def _should_store_for_hardware_type(self, benchmark_type: str, hardware_type: str, data: Dict[str, Any]) -> bool:
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
            if benchmark_type == 'llama' and actual_data.get('runs_gpu'):
                return True
            return False
        
        return False

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