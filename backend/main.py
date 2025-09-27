from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, ValidationError
from typing import List, Dict, Optional, Any, Union
import json
import time
import logging
import os
from pathlib import Path

from models import (
    HealthResponse, 
    HardwareListResponse, 
    HardwareDetailResponse,
    ProcessedBenchmarkResponse,
    UploadResponse,
    BenchmarkData,
    HardwareInfo,
    HardwareSummary
)
from services.storage_manager import StorageManager
from services.hardware_extractor import HardwareExtractor
from services.json_validator import JsonValidator
from database import database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Weird Bench API",
    description="Backend API for benchmark data management",
    version="2.0.0"
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
hardware_extractor = HardwareExtractor()
json_validator = JsonValidator()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    await database.initialize()

# Close database on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    await database.close()

# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
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
async def http_exception_handler(request, exc):
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
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}")
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
    """Health check endpoint"""
    return HealthResponse(
        success=True,
        status="API is running",
        timestamp=int(time.time()),
        version="2.0.0"
    )

@app.get("/api/hardware", response_model=HardwareListResponse)
async def get_hardware_list():
    """Get list of all hardware with benchmark summaries"""
    try:
        hardware_data = await storage_manager.get_hardware_list()
        return HardwareListResponse(
            success=True,
            data=hardware_data,
            timestamp=int(time.time())
        )
    except Exception as e:
        logger.error(f"Error getting hardware list: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve hardware list")

@app.get("/api/hardware-detail", response_model=HardwareDetailResponse)
async def get_hardware_detail(type: str, id: str):
    """Get detailed information for specific hardware"""
    if type not in ["cpu", "gpu"]:
        raise HTTPException(status_code=400, detail="Type must be 'cpu' or 'gpu'")
    
    if not id:
        raise HTTPException(status_code=400, detail="Hardware ID is required")
    
    try:
        hardware_detail = await storage_manager.get_hardware_detail(type, id)
        if not hardware_detail:
            raise HTTPException(status_code=404, detail=f"Hardware {type}/{id} not found")
            
        return HardwareDetailResponse(
            success=True,
            data=hardware_detail,
            timestamp=int(time.time())
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting hardware detail {type}/{id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve hardware details")

@app.get("/api/hardware-processed-data", response_model=ProcessedBenchmarkResponse)
async def get_hardware_processed_data(type: str, id: str):
    """Get processed and aggregated benchmark data for specific hardware"""
    if type not in ["cpu", "gpu"]:
        raise HTTPException(status_code=400, detail="Type must be 'cpu' or 'gpu'")
    
    if not id:
        raise HTTPException(status_code=400, detail="Hardware ID is required")
    
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
        raise HTTPException(status_code=500, detail="Failed to retrieve processed benchmark data")

@app.post("/api/upload", response_model=UploadResponse)
async def upload_benchmark(request: Request):
    """Upload benchmark results from run_benchmarks.py"""
    try:
        # Parse the form data manually to handle dynamic file uploads
        form_data = await request.form()
        
        # Get metadata
        run_id = form_data.get("run_id")
        hardware_info = form_data.get("hardware_info")
        timestamp = form_data.get("timestamp")
        
        if not run_id or not hardware_info or not timestamp:
            raise HTTPException(status_code=400, detail="Missing required fields: run_id, hardware_info, timestamp")
        
        # Parse hardware info
        try:
            hardware_data = json.loads(hardware_info)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid hardware_info JSON format")
        
        # Extract uploaded files (any field that's a file)
        uploaded_files = []
        for key, value in form_data.items():
            if hasattr(value, 'filename') and hasattr(value, 'read'):  # It's a file
                uploaded_files.append(value)
        
        if not uploaded_files:
            raise HTTPException(status_code=400, detail="No benchmark files uploaded")
        
        # Process uploaded benchmark files
        benchmark_results = {}
        file_errors = []
        
        for file in uploaded_files:
            filename = getattr(file, 'filename', None)
            if not filename or not isinstance(filename, str) or not filename.endswith('.json'):
                file_errors.append(f"Invalid file: {filename}")
                continue
                
            try:
                content = await file.read()
                if not content:
                    file_errors.append(f"Empty file: {filename}")
                    continue
                    
                try:
                    benchmark_data = json.loads(content)
                    if not benchmark_data:
                        file_errors.append(f"Empty JSON in file: {filename}")
                        continue
                    
                    # Extract benchmark type from filename or form field name
                    benchmark_type = filename.replace('.json', '').replace('_results', '')
                    # Remove common prefixes like "run_1_"
                    if benchmark_type.startswith('run_'):
                        parts = benchmark_type.split('_')
                        if len(parts) >= 3:  # e.g., "run_1_blender"
                            benchmark_type = '_'.join(parts[2:])
                    
                    if benchmark_type not in ['llama', 'blender', '7zip', 'reversan']:
                        file_errors.append(f"Unknown benchmark type in filename: {filename}")
                        continue
                    
                    benchmark_results[benchmark_type] = benchmark_data
                    logger.info(f"Successfully parsed file: {filename} as {benchmark_type}")
                    
                except json.JSONDecodeError as e:
                    file_errors.append(f"Invalid JSON in file {filename}: {str(e)}")
                    continue
                    
            except Exception as e:
                file_errors.append(f"Error reading file {filename}: {str(e)}")
                continue

        # If ANY file had errors, reject the entire upload
        if file_errors:
            error_message = f"Upload failed due to file errors: {'; '.join(file_errors)}"
            logger.error(error_message)
            raise HTTPException(status_code=400, detail=error_message)

        if not benchmark_results:
            raise HTTPException(status_code=400, detail="No valid benchmark JSON files found")

        # REQUIRE ALL 4 BENCHMARK TYPES
        required_benchmarks = {'llama', 'blender', '7zip', 'reversan'}
        uploaded_benchmarks = set(benchmark_results.keys())
        missing_benchmarks = required_benchmarks - uploaded_benchmarks
        
        if missing_benchmarks:
            missing_list = ', '.join(sorted(missing_benchmarks))
            raise HTTPException(
                status_code=400, 
                detail=f"Upload incomplete: missing required benchmark files: {missing_list}. All 4 benchmark types (llama, blender, 7zip, reversan) must be provided."
            )
        
        logger.info(f"All 4 required benchmark types present: {', '.join(sorted(uploaded_benchmarks))}")

        # VALIDATE ALL BENCHMARK DATA BEFORE PROCESSING
        try:
            all_valid, validation_errors = json_validator.are_all_benchmarks_valid(benchmark_results)
            if not all_valid:
                error_details = []
                for benchmark_type, error in validation_errors.items():
                    error_details.append(f"{benchmark_type}: {error}")
                validation_error = f"Validation failed - Upload rejected. {'; '.join(error_details)}"
                logger.error(f"Validation failed for benchmark data: {'; '.join(error_details)}")
                raise HTTPException(status_code=400, detail=validation_error)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error during validation: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Validation system error: {str(e)}")

        # EXTRACT HARDWARE INFORMATION
        try:
            extracted_hardware_list = await hardware_extractor.extract_hardware_info(
                benchmark_results, hardware_data
            )
            logger.info(f"Extracted hardware info for {len(extracted_hardware_list)} hardware entries")
        except Exception as e:
            logger.error(f"Error extracting hardware info: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Hardware extraction failed: {str(e)}")
        
        # STORE THE BENCHMARK RUN
        try:
            result = await storage_manager.store_benchmark_run(
                run_id, extracted_hardware_list, benchmark_results, int(timestamp)
            )
            logger.info(f"Successfully stored benchmark run {run_id}")
        except Exception as e:
            logger.error(f"Error storing benchmark run: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Storage failed: {str(e)}")
        
        return UploadResponse(
            success=True,
            message=f"Successfully uploaded {len(benchmark_results)} benchmark(s)",
            data=result,
            timestamp=int(time.time())
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error uploading benchmark: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload benchmark data")

# Legacy endpoint compatibility (if needed)
@app.api_route("/api/api.php", methods=["GET", "POST"])
async def legacy_api_compatibility(request):
    """Legacy PHP API compatibility layer"""
    # This could redirect to appropriate new endpoints based on action parameter
    # For now, return a migration notice
    return JSONResponse(
        status_code=410,
        content={
            "success": False,
            "error": "Legacy API deprecated",
            "message": "Please use the new FastAPI endpoints",
            "migration_info": {
                "health": "/api/health",
                "hardware": "/api/hardware", 
                "hardware_detail": "/api/hardware-detail?type=<type>&id=<id>",
                "upload": "/api/upload"
            },
            "timestamp": int(time.time())
        }
    )

# Serve static files (Angular frontend) - this will be handled by nginx in production
# Only mount static files if the directory exists (for production builds)
import os
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Catch-all route for Angular SPA routing - this must be after static files mount
@app.get("/{full_path:path}")
async def catch_all(full_path: str, request: Request):
    """Catch-all route to serve Angular index.html for SPA routing"""
    # If it's an API route that wasn't matched, return 404
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # For all other routes, serve the Angular index.html
    if os.path.exists("static"):
        return FileResponse("static/index.html")
    else:
        raise HTTPException(status_code=404, detail="Frontend not built")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)