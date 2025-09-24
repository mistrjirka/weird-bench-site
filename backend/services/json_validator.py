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
        """Validate benchmark data against its schema
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if benchmark_type not in self.schemas:
            # No schema available, consider valid
            return True, None
        
        schema = self.schemas[benchmark_type]
        
        try:
            jsonschema.validate(data, schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, f"Schema validation failed: {e.message}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def validate_all_benchmarks(self, benchmark_data: Dict[str, Any]) -> Dict[str, tuple[bool, Optional[str]]]:
        """Validate all benchmark data in a collection
        
        Returns:
            dict: {benchmark_type: (is_valid, error_message)}
        """
        results = {}
        
        for benchmark_type, data in benchmark_data.items():
            results[benchmark_type] = self.validate_benchmark_data(benchmark_type, data)
        
        return results
    
    def get_available_schemas(self) -> list[str]:
        """Get list of available schema types"""
        return list(self.schemas.keys())
    
    def get_schema(self, benchmark_type: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific benchmark type"""
        return self.schemas.get(benchmark_type)