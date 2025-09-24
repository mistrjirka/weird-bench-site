import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from database import database, Hardware, BenchmarkRun, BenchmarkFile
from models import HardwareListData, HardwareSummary, HardwareDetail, BenchmarkFile as BenchmarkFileModel, StoredHardware, UploadResult

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

    async def store_benchmark_run(self, run_id: str, hardware_info: StoredHardware, benchmark_data: Dict[str, Any], timestamp: int) -> UploadResult:
        """Store a complete benchmark run"""
        async with database.get_session() as session:
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
            
            # Separate CPU and GPU benchmarks based on hardware type and benchmark content
            stored_benchmarks = []
            
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
                    stored_benchmarks.append(benchmark_type)
            
            await session.commit()
            
            return UploadResult(
                hardware_id=hardware.id,
                hardware_type=hardware.type,
                stored_benchmarks=stored_benchmarks,
                run_id=run_id
            )

    def _should_store_for_hardware_type(self, benchmark_type: str, hardware_type: str, data: Dict[str, Any]) -> bool:
        """Determine if a benchmark should be stored for a given hardware type"""
        if hardware_type == 'cpu':
            # CPU hardware stores: 7zip, reversan, CPU part of llama
            if benchmark_type in ['7zip', 'reversan']:
                return True
            if benchmark_type == 'llama' and data.get('runs_cpu'):
                return True
            return False
        
        elif hardware_type == 'gpu':
            # GPU hardware stores: blender, GPU part of llama
            if benchmark_type == 'blender':
                return True
            if benchmark_type == 'llama' and data.get('runs_gpu'):
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