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
import re

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
    
    # Helper: slugify hardware name to produce a stable, cross-system id
    def slugify(name: str) -> str:
        if not name:
            return "unknown"
        s = name.strip().lower()
        # Replace non-alphanum with hyphens
        s = re.sub(r"[^a-z0-9]+", "-", s)
        # Collapse multiple hyphens
        s = re.sub(r"-+", "-", s).strip("-")
        return s or "unknown"

    # Helper: create per-benchmark data copies augmented with device names for easier filtering later
    def build_augmented_benchmark_payloads(meta: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        # Build a quick lookup from hw_id -> device name and slug
        hw_lookup = {}
        for k, v in (meta.get("hardware") or {}).items():
            if isinstance(v, dict):
                nm = v.get("name") or "Unknown"
                hw_lookup[k] = {
                    "name": nm,
                    "slug": slugify(nm),
                    "type": v.get("type"),
                    "manufacturer": v.get("manufacturer")
                }

        out: Dict[str, Any] = {}
        # Llama
        llama = data.get("llama")
        if llama is not None:
            llama_copy = json.loads(json.dumps(llama))  # deep copy via JSON
            # CPU name
            cpu_dev = None
            for k, v in (meta.get("hardware") or {}).items():
                if isinstance(v, dict) and v.get("type") == "cpu":
                    cpu_dev = hw_lookup.get(k)
                    break
            if isinstance(llama_copy.get("cpu_benchmark"), dict) and cpu_dev:
                llama_copy["cpu_benchmark"]["device_name"] = cpu_dev["name"]
                llama_copy["cpu_benchmark"]["device_slug"] = cpu_dev["slug"]

            # GPU runs
            if isinstance(llama_copy.get("gpu_benchmarks"), list):
                for run in llama_copy["gpu_benchmarks"]:
                    hwid = run.get("hw_id") or run.get("device") or run.get("id")
                    if hwid and hwid in hw_lookup:
                        run["device_name"] = hw_lookup[hwid]["name"]
                        run["device_slug"] = hw_lookup[hwid]["slug"]
            out["llama"] = llama_copy

        # Blender
        blender = data.get("blender")
        if blender is not None:
            blender_copy = json.loads(json.dumps(blender))
            # CPU device name
            cpu_dev = None
            for k, v in (meta.get("hardware") or {}).items():
                if isinstance(v, dict) and v.get("type") == "cpu":
                    cpu_dev = hw_lookup.get(k)
                    break
            if isinstance(blender_copy.get("cpu"), dict) and cpu_dev:
                blender_copy.setdefault("cpu", {})["device_name"] = cpu_dev["name"]
                blender_copy.setdefault("cpu", {})["device_slug"] = cpu_dev["slug"]
            # GPU devices
            if isinstance(blender_copy.get("gpus"), list):
                for gd in blender_copy["gpus"]:
                    hwid = gd.get("hw_id") or gd.get("device") or gd.get("id")
                    if hwid and hwid in hw_lookup:
                        gd["device_name"] = hw_lookup[hwid]["name"]
                        gd["device_slug"] = hw_lookup[hwid]["slug"]
            out["blender"] = blender_copy

        # 7zip and reversan are device-agnostic in our simplified views
        if data.get("sevenzip") is not None:
            out["sevenzip"] = json.loads(json.dumps(data["sevenzip"]))
        if data.get("reversan") is not None:
            out["reversan"] = json.loads(json.dumps(data["reversan"]))

        return out

    async with database.get_session() as session:
        stored_benchmarks = []
        hardware_ids = []
        
        # Process each hardware device
        # Augment the payload once per upload for all devices
        augmented_payloads = build_augmented_benchmark_payloads(meta, unified_data)

        for src_hw_id, hw_data in hardware_info.items():
            # Resolve persistent hardware id from the device name
            name = hw_data.get('name', 'Unknown')
            hw_type = hw_data.get('type', 'unknown')
            manufacturer = hw_data.get('manufacturer', 'Unknown')
            pers_id = slugify(name)

            # Try to find by persistent id (slug of name)
            result = await session.execute(select(Hardware).where(Hardware.id == pers_id))
            hardware = result.scalar_one_or_none()

            # Fallback: look for exact name+type match (in case of pre-existing db with non-slug ids)
            if not hardware:
                result = await session.execute(
                    select(Hardware).where(Hardware.name == name, Hardware.type == hw_type)
                )
                hardware = result.scalar_one_or_none()

            if not hardware:
                # Create new hardware entry using name-based id
                hardware = Hardware(
                    id=pers_id,
                    name=name,
                    type=hw_type,
                    manufacturer=manufacturer,
                    cores=hw_data.get('cores'),
                    framework=hw_data.get('framework')
                )
                session.add(hardware)
                await session.flush()
            else:
                # No legacy migration: existing records are used as-is; IDs are expected to be name slugs
                pass

            hardware_ids.append(hardware.id)

            # Get next run number for this hardware
            result = await session.execute(
                select(func.max(BenchmarkRun.run_number)).where(BenchmarkRun.hardware_id == hardware.id)
            )
            max_run_number = result.scalar() or 0
            next_run_number = max_run_number + 1

            # Create benchmark run
            run_timestamp = datetime.fromtimestamp(float(timestamp))
            benchmark_run = BenchmarkRun(
                run_id=run_id,
                hardware_id=hardware.id,
                timestamp=run_timestamp,
                run_number=next_run_number
            )
            session.add(benchmark_run)
            await session.flush()

            # Store each benchmark type directly (now with augmentation for device names)
            for bench_type_key, bench_payload in augmented_payloads.items():
                normalized_type = bench_type_key if bench_type_key != 'sevenzip' else '7zip'
                benchmark_file = BenchmarkFile(
                    benchmark_run_id=benchmark_run.id,
                    benchmark_type=normalized_type,
                    filename=f"{run_id}_{bench_type_key}.json",
                    file_path=f"unified/{run_id}_{bench_type_key}.json",
                    file_size=len(str(bench_payload)),
                    data=bench_payload
                )
                session.add(benchmark_file)
                stored_benchmarks.append(bench_type_key)
        
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
            # Get all hardware, runs, and files
            hardware_result = await session.execute(select(Hardware))
            hardware_list = hardware_result.scalars().all()
            runs_result = await session.execute(select(BenchmarkRun))
            runs_list = runs_result.scalars().all()
            files_result = await session.execute(select(BenchmarkFile))
            files_list = files_result.scalars().all()

            # Build a JSON-friendly dump
            dump = {
                "hardware": [
                    {
                        "id": hw.id,
                        "name": hw.name,
                        "type": hw.type,
                        "manufacturer": hw.manufacturer,
                        "cores": hw.cores,
                        "framework": hw.framework,
                        "created_at": hw.created_at.isoformat() if hw.created_at else None,
                        "updated_at": hw.updated_at.isoformat() if hw.updated_at else None,
                    }
                    for hw in hardware_list
                ],
                "runs": [
                    {
                        "id": r.id,
                        "run_id": r.run_id,
                        "hardware_id": r.hardware_id,
                        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                        "run_number": r.run_number,
                    }
                    for r in runs_list
                ],
                "files": [
                    {
                        "id": f.id,
                        "run_id": f.benchmark_run_id,
                        "type": f.benchmark_type,
                        "filename": f.filename,
                        "size": f.file_size,
                    }
                    for f in files_list
                ]
            }

            # Also log a compact summary
            logger.info("=== DATABASE DEBUG DUMP (summary) ===")
            for hw in dump["hardware"]:
                logger.info(f"  • {hw['id']}: {hw['name']} ({hw['type']})")
            logger.info(f"Runs: {len(dump['runs'])}, Files: {len(dump['files'])}")
            logger.info("=== END DUMP ===")

            return {
                "success": True,
                "summary": {
                    "hardware_count": len(hardware_list),
                    "benchmark_runs": len(runs_list),
                    "benchmark_files": len(files_list),
                },
                "data": dump,
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