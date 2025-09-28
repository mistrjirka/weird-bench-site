"""
Simplified FastAPI application for Weird Bench - Unified Format Only
Version 2.1.0 - Clean API without legacy support
"""

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select, func
import json
import time
import logging
import traceback
import os
from pathlib import Path
from typing import Dict, Any

# Import simplified models and services
from simplified_models import (
    HealthResponse,
    SimpleHardwareListResponse,
    HardwareDetailResponse, 
    UploadResponse,
    UploadResult
)
from simplified_storage_manager import SimplifiedStorageManager
# Simple direct upload processing - no legacy conversion
from database import database, Hardware, BenchmarkRun, BenchmarkFile
from database import database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Weird Bench API",
    description="Simplified backend API for unified benchmark data management", 
    version="2.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize simplified services
storage_manager = SimplifiedStorageManager()


async def process_unified_upload_direct(unified_data: Dict[str, Any], run_id: str, timestamp: str) -> UploadResult:
    """Process unified upload directly without legacy conversion."""
    from datetime import datetime
    
    # Extract hardware info from meta
    meta = unified_data.get('meta', {})
    hardware_info = meta.get('hardware', {})
    
    if not hardware_info:
        raise HTTPException(status_code=400, detail="No hardware information found in upload")
    
    async with database.get_session() as session:
        stored_benchmarks = []
        hardware_ids = []
        
        # Process each hardware device
        for hw_id, hw_data in hardware_info.items():
            # Create or get hardware entry
            result = await session.execute(
                select(Hardware).where(Hardware.id == hw_id)
            )
            hardware = result.scalar_one_or_none()
            
            if not hardware:
                # Create new hardware entry
                hardware = Hardware(
                    id=hw_id,
                    name=hw_data.get('name', 'Unknown'),
                    type=hw_data.get('type', 'unknown'),
                    manufacturer=hw_data.get('manufacturer', 'Unknown'),
                    cores=hw_data.get('cores'),
                    framework=hw_data.get('framework')
                )
                session.add(hardware)
                await session.flush()  # Get the ID
            
            hardware_ids.append(hw_id)
            
            # Get next run number for this hardware
            result = await session.execute(
                select(func.max(BenchmarkRun.run_number)).where(BenchmarkRun.hardware_id == hw_id)
            )
            max_run_number = result.scalar() or 0
            next_run_number = max_run_number + 1
            
            # Create benchmark run
            run_timestamp = datetime.fromtimestamp(float(timestamp))
            benchmark_run = BenchmarkRun(
                run_id=run_id,
                hardware_id=hw_id,
                timestamp=run_timestamp,
                run_number=next_run_number
            )
            session.add(benchmark_run)
            await session.flush()  # Get the ID
            
            # Store each benchmark type directly (no legacy conversion)
            benchmark_types = ['llama', 'reversan', 'sevenzip', 'blender']
            for bench_type in benchmark_types:
                if bench_type in unified_data and unified_data[bench_type] is not None:
                    # Store the benchmark data directly from unified format
                    benchmark_file = BenchmarkFile(
                        benchmark_run_id=benchmark_run.id,
                        benchmark_type=bench_type if bench_type != 'sevenzip' else '7zip',  # Normalize name
                        filename=f"{run_id}_{bench_type}.json",  # Generate filename
                        file_path=f"unified/{run_id}_{bench_type}.json",  # Generate path
                        file_size=len(str(unified_data[bench_type])),
                        data=unified_data[bench_type]  # Store unified format directly
                    )
                    session.add(benchmark_file)
                    stored_benchmarks.append(bench_type)
        
        await session.commit()
        
        return UploadResult(
            hardware_id=','.join(hardware_ids),
            hardware_type='mixed',
            stored_benchmarks=stored_benchmarks,
            run_id=run_id
        )


# Application lifecycle events
@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup."""
    try:
        await database.initialize()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    try:
        await database.close()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.error(f"❌ Error closing database: {e}")


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": "Validation error",
            "message": str(exc),
            "timestamp": int(time.time())
        }
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": "HTTP error",
            "message": exc.detail,
            "timestamp": int(time.time())
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "timestamp": int(time.time())
        }
    )


# API Endpoints
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="2.1.0",
        timestamp=int(time.time())
    )


@app.get("/api/debug/database")
async def debug_database():
    """DEBUG: Dump all database contents to logs."""
    try:
        async with database.get_session() as session:
            # Get all hardware
            hardware_result = await session.execute(select(Hardware))
            hardware_list = hardware_result.scalars().all()
            
            logger.info("=== DATABASE DEBUG DUMP ===")
            logger.info(f"🖥️  HARDWARE ENTRIES: {len(hardware_list)}")
            
            for hw in hardware_list:
                logger.info(f"  • {hw.id}: {hw.name} ({hw.type}) - {hw.manufacturer}")
            
            # Get all benchmark runs
            runs_result = await session.execute(select(BenchmarkRun))
            runs_list = runs_result.scalars().all()
            
            logger.info(f"🏃 BENCHMARK RUNS: {len(runs_list)}")
            
            for run in runs_list:
                logger.info(f"  • {run.run_id}: Hardware {run.hardware_id} at {run.timestamp}")
            
            # Get all benchmark files
            files_result = await session.execute(select(BenchmarkFile))
            files_list = files_result.scalars().all()
            
            logger.info(f"📁 BENCHMARK FILES: {len(files_list)}")
            
            for bf in files_list:
                data_preview = str(bf.data)[:100] + "..." if bf.data and len(str(bf.data)) > 100 else str(bf.data)
                logger.info(f"  • {bf.benchmark_type}: Run {bf.benchmark_run_id}, Size {bf.file_size}b")
                logger.info(f"    Data: {data_preview}")
            
            logger.info("=== END DATABASE DUMP ===")
            
            return {
                "success": True,
                "hardware_count": len(hardware_list),
                "benchmark_runs": len(runs_list), 
                "benchmark_files": len(files_list),
                "message": "Database contents dumped to logs",
                "timestamp": int(time.time())
            }
            
    except Exception as e:
        logger.error(f"Debug database dump failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": int(time.time())
        }


@app.get("/api/hardware", response_model=SimpleHardwareListResponse)
async def get_hardware_list():
    """Get simplified list of all hardware with clean comparison data."""
    try:
        hardware_data = await storage_manager.get_hardware_list()
        return SimpleHardwareListResponse(
            data=hardware_data,
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"Error getting hardware list: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve hardware list"
        )


@app.get("/api/hardware-detail")
async def get_hardware_detail(type: str, id: str):
    """Get detailed information for specific hardware."""
    if type not in ["cpu", "gpu"]:
        raise HTTPException(
            status_code=400, 
            detail="Type must be 'cpu' or 'gpu'"
        )
    
    if not id:
        raise HTTPException(
            status_code=400, 
            detail="Hardware ID is required"
        )
    
    try:
        hardware_detail = await storage_manager.get_hardware_detail(type, id)
        if not hardware_detail:
            raise HTTPException(
                status_code=404,
                detail=f"Hardware {type}/{id} not found"
            )
        return hardware_detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting hardware detail {type}/{id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve hardware details"
        )


@app.post("/api/upload", response_model=UploadResponse)
async def upload_unified_benchmark(request: Request):
    """Upload unified benchmark results from unified_runner.py."""
    try:
        # Parse form data
        form_data = await request.form()
        
        # Get metadata fields
        run_id = form_data.get("run_id")
        timestamp = form_data.get("timestamp")
        
        if not run_id or not timestamp:
            raise HTTPException(
                status_code=400, 
                detail="Missing required fields: run_id, timestamp"
            )
        
        # Extract uploaded file
        uploaded_files = [
            value for key, value in form_data.items() 
            if hasattr(value, 'filename') and hasattr(value, 'read')
        ]
        
        if not uploaded_files:
            raise HTTPException(
                status_code=400, 
                detail="No benchmark file uploaded"
            )
        
        if len(uploaded_files) != 1:
            raise HTTPException(
                status_code=400, 
                detail=f"Expected exactly 1 unified benchmark file, got {len(uploaded_files)} files. Use unified_runner.py to generate the correct format."
            )
        
        file = uploaded_files[0]
        filename = getattr(file, 'filename', None) or "unknown"
        
        logger.info(f"Processing unified benchmark file: {filename}")
        
        # Read and parse file content
        try:
            content = await file.read()
            if not content:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Empty file: {filename}"
                )
            
            unified_data = json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {filename}: {str(e)}")
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid JSON in file: {str(e)}"
            )
        
        # Process the unified upload directly
        try:
            result = await process_unified_upload_direct(
                unified_data, 
                run_id,
                timestamp
            )
            
            logger.info(f"Successfully processed unified benchmark upload: {filename}")
            return UploadResponse(
                message=f"Successfully uploaded {len(result.stored_benchmarks)} benchmark(s) for hardware {result.hardware_id}",
                data=result,
                timestamp=int(time.time())
            )
            
        except Exception as e:
            logger.error(f"Failed to process unified format: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Processing error: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error uploading unified benchmark: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to upload unified benchmark data"
        )


# Static file serving and SPA routing
# Serve static files (Angular frontend) if directory exists
static_dir = Path("static")
if static_dir.exists():
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
    logger.info("✅ Static files mounted from static/ directory")
else:
    logger.warning("⚠️  Static files directory not found - frontend not available")


# Catch-all route for Angular SPA routing
@app.get("/{full_path:path}")
async def spa_catchall(full_path: str):
    """Catch-all route to serve Angular index.html for SPA routing."""
    # If it's an API route that wasn't matched, return 404
    if full_path.startswith("api/"):
        raise HTTPException(
            status_code=404, 
            detail="API endpoint not found"
        )
    
    # For all other routes, serve the Angular index.html
    if static_dir.exists():
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
    
    raise HTTPException(
        status_code=404, 
        detail="Frontend not available"
    )


# Development server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info"
    )