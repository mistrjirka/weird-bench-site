"""
Clean FastAPI application for Weird Bench - Unified Format Only
Version 2.0.0 - No legacy format support
"""

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import json
import time
import logging
import os
from pathlib import Path
from typing import Dict, Any

# Import models and services
from models import (
    HealthResponse, 
    HardwareListResponse, 
    HardwareDetailResponse,
    ProcessedBenchmarkResponse,
    UploadResponse,
    UploadResult
)
from unified_models import UnifiedBenchmarkData
from services.storage_manager import StorageManager
from services.unified_storage_processor import UnifiedStorageProcessor
from services.json_validator import JsonValidator
from database import database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Weird Bench API",
    description="Backend API for unified benchmark data management",
    version="2.0.0",
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

# Initialize services
storage_manager = StorageManager()
unified_processor = UnifiedStorageProcessor()
json_validator = JsonValidator()


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
        success=True,
        status="API is running",
        timestamp=int(time.time()),
        version="2.0.0"
    )


@app.get("/api/hardware", response_model=HardwareListResponse)
async def get_hardware_list():
    """Get list of all hardware with benchmark summaries."""
    try:
        hardware_data = await storage_manager.get_hardware_list()
        return HardwareListResponse(
            success=True,
            data=hardware_data,
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"Error getting hardware list: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve hardware list"
        )


@app.get("/api/hardware-detail", response_model=HardwareDetailResponse)
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
            
        return HardwareDetailResponse(
            success=True,
            data=hardware_detail,
            timestamp=int(time.time())
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting hardware detail {type}/{id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve hardware details"
        )


@app.get("/api/hardware-processed-data", response_model=ProcessedBenchmarkResponse)
async def get_hardware_processed_data(type: str, id: str):
    """Get processed and aggregated benchmark data for specific hardware."""
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
        processed_data = await storage_manager.get_processed_benchmark_data(type, id)
        return ProcessedBenchmarkResponse(
            success=True,
            data=processed_data,
            timestamp=int(time.time())
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting processed data for {type}/{id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Failed to retrieve processed benchmark data"
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
        
        # Validate unified format structure
        is_valid, validation_errors = json_validator.validate_unified_format(unified_data)
        if not is_valid:
            error_message = f"Invalid unified format: {'; '.join(validation_errors)}"
            logger.error(f"Validation failed for {filename}: {error_message}")
            raise HTTPException(
                status_code=400, 
                detail=f"{error_message}. Use unified_runner.py to generate the correct format."
            )
        
        # Process the unified upload
        try:
            result = await unified_processor.process_unified_upload(
                unified_data, 
                run_id,
                timestamp
            )
            
            logger.info(f"Successfully processed unified benchmark upload: {filename}")
            return UploadResponse(
                success=True,
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