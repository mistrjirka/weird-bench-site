from sqlalchemy import Column, Integer, String, JSON, DateTime, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
import os

Base = declarative_base()

class Hardware(Base):
    __tablename__ = "hardware"
    
    id = Column(String, primary_key=True)  # e.g., "amd-ryzen-7-5700x3d"
    name = Column(String, nullable=False)  # e.g., "AMD Ryzen 7 5700X3D"
    manufacturer = Column(String, nullable=False)  # "AMD", "NVIDIA", "Intel"
    type = Column(String, nullable=False)  # "cpu" or "gpu"
    cores = Column(Integer, nullable=True)  # For CPUs
    framework = Column(String, nullable=True)  # For GPUs: "CUDA", "OpenCL"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    benchmark_runs = relationship("BenchmarkRun", back_populates="hardware", cascade="all, delete-orphan")
    
    # Indexes for faster queries
    __table_args__ = (
        Index('idx_hardware_type', 'type'),
        Index('idx_hardware_manufacturer', 'manufacturer'),
    )

class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False)  # User-provided run ID
    hardware_id = Column(String, ForeignKey("hardware.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    run_number = Column(Integer, nullable=False)  # Sequential number for this hardware
    
    # Foreign key relationship
    hardware = relationship("Hardware", back_populates="benchmark_runs")
    
    # Benchmark results
    benchmark_files = relationship("BenchmarkFile", back_populates="benchmark_run", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_benchmark_runs_hardware', 'hardware_id'),
        Index('idx_benchmark_runs_timestamp', 'timestamp'),
        Index('idx_benchmark_runs_run_id', 'run_id'),
    )

class BenchmarkFile(Base):
    __tablename__ = "benchmark_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    benchmark_run_id = Column(Integer, ForeignKey("benchmark_runs.id"), nullable=False)
    benchmark_type = Column(String, nullable=False)  # "7zip", "blender", "llama", "reversan"
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)  # Relative path from data directory
    file_size = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)  # The actual benchmark JSON data
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Foreign key relationship
    benchmark_run = relationship("BenchmarkRun", back_populates="benchmark_files")
    
    # Indexes
    __table_args__ = (
        Index('idx_benchmark_files_run', 'benchmark_run_id'),
        Index('idx_benchmark_files_type', 'benchmark_type'),
    )

class Database:
    def __init__(self, database_url: str = None):
        if database_url is None:
            # Default to SQLite in the data directory
            data_dir = os.environ.get('DATA_DIR', '/app/data')
            os.makedirs(data_dir, exist_ok=True)
            database_url = f"sqlite+aiosqlite:///{data_dir}/benchmarks.db"
        
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None
    
    async def initialize(self):
        """Initialize database connection and create tables"""
        # For SQLite, we need to handle async properly
        if "sqlite+aiosqlite" in self.database_url:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            self.engine = create_async_engine(
                self.database_url,
                echo=False,  # Set to True for SQL debugging
                future=True
            )
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        else:
            # For other databases, use synchronous version
            self.engine = create_engine(self.database_url, echo=False)
            self.SessionLocal = sessionmaker(bind=self.engine)
            Base.metadata.create_all(bind=self.engine)
    
    def get_session(self):
        """Get database session context manager"""
        if "sqlite+aiosqlite" in self.database_url:
            return AsyncSessionContext(self.SessionLocal)
        else:
            return SyncSessionContext(self.SessionLocal)

    async def close(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()

class AsyncSessionContext:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = None
    
    async def __aenter__(self):
        self.session = self.session_factory()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

class SyncSessionContext:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = None
    
    async def __aenter__(self):
        self.session = self.session_factory()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()

# Global database instance
database = Database()