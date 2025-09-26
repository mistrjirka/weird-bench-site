import json
import jsonschema
from typing import Dict, Any, Optional
from pathlib import Path

class JsonValidator:
    """JSON schema validator for benchmark data"""
    
    def __init__(self, schema_dir: str = None):
        if schema_dir is None:
            # Default to schemas directory relative to backend
            self.schema_dir = Path(__file__).parent.parent.parent / 'schemas'
        else:
            self.schema_dir = Path(schema_dir)
        
        self.schemas = {}
        self._load_schemas()
    
    def _load_schemas(self):
        """Load all JSON schemas from the schemas directory"""
        if not self.schema_dir.exists():
            return
            
        for schema_file in self.schema_dir.glob('*.json'):
            benchmark_type = schema_file.stem.replace('_schema', '')
            try:
                with open(schema_file, 'r') as f:
                    schema = json.load(f)
                    self.schemas[benchmark_type] = schema
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load schema {schema_file}: {e}")
    
    def validate_benchmark_data(self, benchmark_type: str, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate benchmark data against its schema and content structure
        
        Returns:
            tuple: (is_valid, error_message)
        """
        # First check basic structure validation for specific benchmark types
        structural_validation = self._validate_benchmark_structure(benchmark_type, data)
        if not structural_validation[0]:
            return structural_validation
            
        # Then check against JSON schema if available
        if benchmark_type not in self.schemas:
            # No schema available, rely on structural validation
            return True, None
        
        schema = self.schemas[benchmark_type]
        
        # Prepare data for schema validation - handle wrapper structures
        schema_data = data
        if (benchmark_type == "7zip" or benchmark_type == "blender") and "results" in data:
            # For 7zip and blender, use the inner results object for schema validation
            schema_data = data["results"]
        
        try:
            jsonschema.validate(schema_data, schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, f"Schema validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def _validate_benchmark_structure(self, benchmark_type: str, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate the structural content of benchmark data"""
        try:
            # Handle different data structures
            if benchmark_type == "7zip":
                # 7zip has data wrapped in "results"
                if "results" in data:
                    actual_data = data["results"]
                else:
                    actual_data = data
                return self._validate_7zip_structure(actual_data)
            else:
                # Other benchmarks have direct top-level structure
                if benchmark_type == "blender":
                    return self._validate_blender_structure(data)
                elif benchmark_type == "llama":
                    return self._validate_llama_structure(data)
                elif benchmark_type == "reversan":
                    return self._validate_reversan_structure(data)
            
            return True, None
            
        except Exception as e:
            return False, f"Structure validation error: {str(e)}"
    
    def _validate_blender_structure(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate Blender benchmark structure"""
        # Check for required top-level fields
        if "device_runs" not in data:
            return False, "Blender benchmark missing device_runs"
            
        device_runs = data["device_runs"]
        if not device_runs:
            return False, "Blender benchmark has empty device_runs"
        
        for run in device_runs:
            # For valid benchmarks, we expect either proper scene_results with data 
            # OR raw_json with scene data (the processing will extract scene_results)
            scene_results = run.get("scene_results", {})
            raw_json = run.get("raw_json", [])
            
            # If there's no raw_json data at all, it's definitely malformed
            if not raw_json:
                return False, "Blender benchmark missing raw_json data"
            
            # Check if raw_json contains valid scene data
            has_valid_scenes = False
            for scene_data in raw_json:
                stats = scene_data.get("stats", {})
                if stats and "samples_per_minute" in stats:
                    has_valid_scenes = True
                    break
            
            if not has_valid_scenes:
                return False, "Blender benchmark missing valid scene data in raw_json"
        
        return True, None
    
    def _validate_7zip_structure(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate 7zip benchmark structure"""
        runs = data.get("runs", [])
        
        if not runs:
            return False, "7zip benchmark missing runs data"
        
        for run in runs:
            if not run.get("success", False):
                return False, "7zip benchmark contains failed runs"
            
            # Check for required timing data
            elapsed_seconds = run.get("elapsed_seconds")
            if not isinstance(elapsed_seconds, (int, float)) or elapsed_seconds <= 0:
                return False, "7zip benchmark missing valid elapsed_seconds"
        
        return True, None
    
    def _validate_llama_structure(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate Llama benchmark structure"""
        # Check for CPU runs
        runs_cpu = data.get("runs_cpu", [])
        runs_gpu = data.get("runs_gpu", [])
        
        if not runs_cpu and not runs_gpu:
            return False, "Llama benchmark missing both CPU and GPU runs"
        
        # Validate run structure - Llama uses returncode (0 = success) instead of success field
        all_runs = runs_cpu + runs_gpu
        for run in all_runs:
            returncode = run.get("returncode")
            if returncode != 0:
                return False, "Llama benchmark contains failed runs (non-zero returncode)"
            
            # Check for tokens_per_second in metrics (at top level of metrics)
            metrics = run.get("metrics", {})
            tokens_per_second = metrics.get("tokens_per_second")
            if not isinstance(tokens_per_second, (int, float)) or tokens_per_second <= 0:
                return False, "Llama benchmark missing valid tokens_per_second in metrics"
        
        return True, None
    
    def _validate_reversan_structure(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate Reversan benchmark structure"""
        runs_depth = data.get("runs_depth", [])
        runs_threads = data.get("runs_threads", [])
        
        if not runs_depth and not runs_threads:
            return False, "Reversan benchmark missing both depth and thread runs"
        
        return True, None
    
    def validate_all_benchmarks(self, benchmark_data: Dict[str, Any]) -> Dict[str, tuple[bool, Optional[str]]]:
        """Validate all benchmark data in a collection
        
        Returns:
            dict: {benchmark_type: (is_valid, error_message)}
        """
        results = {}
        
        for benchmark_type, data in benchmark_data.items():
            results[benchmark_type] = self.validate_benchmark_data(benchmark_type, data)
        
        return results
    
    def are_all_benchmarks_valid(self, benchmark_data: Dict[str, Any]) -> tuple[bool, Dict[str, str]]:
        """Check if all benchmark data is valid (fail-fast)
        
        Returns:
            tuple: (all_valid, {benchmark_type: error_message} for failed validations)
        """
        validation_results = self.validate_all_benchmarks(benchmark_data)
        errors = {}
        all_valid = True
        
        for benchmark_type, (is_valid, error_message) in validation_results.items():
            if not is_valid:
                all_valid = False
                errors[benchmark_type] = error_message or "Unknown validation error"
        
        return all_valid, errors
    
    def get_available_schemas(self) -> list[str]:
        """Get list of available schema types"""
        return list(self.schemas.keys())
    
    def get_schema(self, benchmark_type: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific benchmark type"""
        return self.schemas.get(benchmark_type)