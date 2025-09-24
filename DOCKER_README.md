# Benchmark Website Development Setup

This project provides a Docker-based development environment for testing the PHP backend API that handles benchmark uploads and serves data to the Angular frontend.

## Quick Start

1. **Start the Docker environment:**
   ```bash
   ./test_docker.sh
   ```

2. **Upload benchmark results:**
   ```bash
   cd /path/to/weird-bench
   python run_benchmarks.py --upload-existing --api-url http://localhost:8080/api
   ```

3. **View results:**
   - API Health: http://localhost:8080/api/health
   - Data Index: http://localhost:8080/public/data/index.json
   - Frontend (if running): http://localhost:4200

## New File Structure

### Before (CPU/GPU Separation)
```
public/data/
├── cpu/
│   ├── amd-ryzen-7-5700x3d/
│   │   ├── 7zip.json
│   │   ├── llama.json
│   │   └── reversan.json
│   └── amd-ryzen-ai-9-365/
└── gpu/
    └── amd-radeon-rx-7800-xt/
```

### After (Run-Based Structure)
```
public/data/
├── runs/
│   ├── 1758650425_amd-ryzen-7-5700x3d_amd-radeon-rx-7800-xt/
│   │   ├── 7zip.json
│   │   ├── llama.json
│   │   ├── reversan.json
│   │   └── blender.json
│   └── 1758663639_amd-ryzen-ai-9-365/
│       ├── 7zip.json
│       ├── llama.json
│       ├── reversan.json
│       └── blender.json
└── index.json (updated structure)
```

## Key Changes

### 1. Run-Based Organization
- Each benchmark run gets a unique folder: `{timestamp}_{cpu-slug}_{gpu-slug}`
- Files contain both CPU and GPU data as they originally did
- No artificial separation between CPU and GPU benchmark files

### 2. Updated Index Structure
- Hardware entries now have `runs` arrays instead of direct benchmark references
- Each run contains `runId`, `timestamp`, `benchmarks` paths, and associated hardware
- Supports multiple runs per hardware configuration

### 3. Enhanced Upload Script
- `run_benchmarks.py` now supports uploading results to the API
- `--upload`: Upload results after running benchmarks
- `--upload-existing`: Upload existing results from results/ folder
- `--api-url`: Specify API endpoint (default: http://localhost:8080/api)

### 4. Backward Compatible API
- New FileStorageManagerV2 handles the run-based structure
- Maintains old API format for existing clients
- Supports both old and new upload formats

## Development Workflow

1. **Run benchmarks locally:**
   ```bash
   cd /path/to/weird-bench
   python run_benchmarks.py --benchmark all --upload --api-url http://localhost:8080/api
   ```

2. **Or upload existing results:**
   ```bash
   python run_benchmarks.py --upload-existing --api-url http://localhost:8080/api
   ```

3. **Check the data was stored correctly:**
   ```bash
   curl http://localhost:8080/public/data/index.json
   ```

4. **Test frontend integration:**
   ```bash
   cd /path/to/angular-frontend
   npm start
   # Frontend will need to be updated to work with new structure
   ```

## Docker Environment

### Services
- **php-backend**: Apache + PHP 8.2 serving the API and static files
- **Ports**: 8080 (mapped to container port 80)
- **Volumes**: API and public folders are mounted for live development

### API Endpoints
- `GET /api/health` - Health check
- `POST /api/upload` - Upload benchmark results  
- `GET /api/hardware` - List all hardware
- `GET /api/hardware/{type}/{id}` - Get hardware details

### File Structure
- `/var/www/html/api/` - PHP API code
- `/var/www/html/public/` - Static data files
- `/var/www/html/data/` - Internal storage (for backward compatibility)

## Production Deployment

For production deployment to your web hosting:

1. **Copy API files** to your web hosting PHP directory
2. **Copy public/data/** to your web hosting public directory  
3. **Update API URLs** in the frontend configuration
4. **Test upload functionality** with the actual hosting environment

The Docker environment is only for development - production uses your existing web hosting with PHP support.

## Troubleshooting

### Container Issues
```bash
# View logs
docker-compose logs

# Restart containers
docker-compose restart

# Clean rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Upload Issues
```bash
# Test API health
curl http://localhost:8080/api/health

# Check file permissions
ls -la public/data/runs/

# Verify Python requests module
pip install requests
```