"""
JSON Validator for validating unified benchmark data with comprehensive validation.
"""

import logging
from typing import Dict, Any, Tuple, List
from pydantic import ValidationError

from pydantic_unified_models import UnifiedBenchmarkResult

logger = logging.getLogger(__name__)


class JsonValidator:
    """Validates unified benchmark data with comprehensive business logic."""
    
    def __init__(self):
        pass
    
    def validate_unified_format(self, unified_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate unified benchmark format with comprehensive validation."""
        error_messages = []
        
        try:
            # First, validate basic Pydantic structure
            validated_data = UnifiedBenchmarkResult.model_validate(unified_data)
            
            # Now perform business logic validation
            business_errors = self._validate_business_logic(validated_data)
            error_messages.extend(business_errors)
            
            return len(error_messages) == 0, error_messages
            
        except ValidationError as e:
            # Extract error messages from Pydantic validation
            for error in e.errors():
                loc = " -> ".join(str(x) for x in error['loc'])
                msg = error['msg']
                error_messages.append(f"{loc}: {msg}")
            return False, error_messages
        except Exception as e:
            return False, [f"Unexpected validation error: {str(e)}"]
    
    def _validate_business_logic(self, data: UnifiedBenchmarkResult) -> List[str]:
        """Validate business logic rules for benchmark completeness."""
        errors = []
        
        # Check if any benchmarks are present
        has_any_benchmark = any([
            data.llama is not None,
            data.reversan is not None, 
            data.sevenzip is not None,
            data.blender is not None
        ])
        
        if not has_any_benchmark:
            errors.append("No benchmark results found - at least one benchmark must be present")
            return errors  # No point in further validation
        
        # Get hardware info
        cpu_device = data.meta.get_cpu_device()
        gpu_devices = data.meta.get_gpu_devices()
        
        if not cpu_device:
            errors.append("No CPU device found in hardware list")
        
        # CPU-only mode validation
        if data.meta.cpu_only:
            logger.info("Validating CPU-only benchmark")
            # In CPU-only mode, GPU benchmarks should not be present
            gpu_benchmark_errors = self._check_gpu_benchmarks_absent(data)
            errors.extend(gpu_benchmark_errors)
            # But CPU benchmarks should still be present
            cpu_benchmark_errors = self._check_cpu_benchmarks_present(data, cpu_device, is_cpu_only=True)
            errors.extend(cpu_benchmark_errors)
        else:
            logger.info(f"Validating full benchmark with {len(gpu_devices)} GPU(s)")
            # Full mode - validate GPU benchmarks
            if not gpu_devices:
                errors.append("cpu_only is false but no GPU devices found in hardware list")
            else:
                # For GPU-capable benchmarks, require complete results
                gpu_benchmark_errors = self._check_gpu_benchmarks_complete(data, gpu_devices)
                errors.extend(gpu_benchmark_errors)
            
            # Always validate CPU benchmarks are present for CPU-compatible tests
            cpu_benchmark_errors = self._check_cpu_benchmarks_present(data, cpu_device, is_cpu_only=False)
            errors.extend(cpu_benchmark_errors)
        
        return errors
    
    def _check_gpu_benchmarks_absent(self, data: UnifiedBenchmarkResult) -> List[str]:
        """Check that GPU benchmarks are not present in CPU-only mode."""
        errors = []
        
        if data.llama and data.llama.gpu_benchmarks:
            errors.append("CPU-only mode but Llama GPU benchmarks are present")
        
        if data.blender and data.blender.gpus:
            errors.append("CPU-only mode but Blender GPU benchmarks are present")
        
        return errors
    
    def _check_gpu_benchmarks_complete(self, data: UnifiedBenchmarkResult, gpu_devices: List) -> List[str]:
        """Check that GPU benchmarks are complete for all available GPUs."""
        errors = []
        gpu_hw_ids = {device.hw_id for device in gpu_devices}
        
        # For GPU-capable benchmarks, they must exist and have GPU results
        gpu_capable_benchmarks = []
        
        # Check Llama - GPU-capable benchmark
        if data.llama is None:
            errors.append("Llama benchmark is missing but GPUs are available (cpu_only is false)")
        else:
            gpu_capable_benchmarks.append("llama")
            if not data.llama.gpu_benchmarks:
                errors.append("Llama benchmark missing GPU results despite available GPUs")
            else:
                llama_gpu_ids = {run.hw_id for run in data.llama.gpu_benchmarks}
                missing_llama_gpus = gpu_hw_ids - llama_gpu_ids
                if missing_llama_gpus:
                    errors.append(f"Llama benchmark missing GPU results for: {', '.join(missing_llama_gpus)}")
        
        # Check Blender - GPU-capable benchmark 
        if data.blender is None:
            errors.append("Blender benchmark is missing but GPUs are available (cpu_only is false)")
        else:
            gpu_capable_benchmarks.append("blender")
            if not data.blender.gpus:
                errors.append("Blender benchmark missing GPU results despite available GPUs")
            else:
                blender_gpu_ids = {gpu.hw_id for gpu in data.blender.gpus}
                missing_blender_gpus = gpu_hw_ids - blender_gpu_ids
                if missing_blender_gpus:
                    errors.append(f"Blender benchmark missing GPU results for: {', '.join(missing_blender_gpus)}")
        
        logger.info(f"GPU-capable benchmarks validated: {gpu_capable_benchmarks}")
        return errors
    
    def _check_cpu_benchmarks_present(self, data: UnifiedBenchmarkResult, cpu_device, is_cpu_only: bool = False) -> List[str]:
        """Check that CPU benchmarks are present for CPU-compatible tests."""
        errors = []
        
        if not cpu_device:
            return errors  # Already reported missing CPU device
        
        # For CPU-capable benchmarks, check they exist and have CPU results
        cpu_capable_benchmarks = []
        
        # Check Llama CPU benchmark - required in both modes
        if data.llama is None:
            if is_cpu_only:
                errors.append("Llama benchmark is missing in CPU-only mode")
            # In full mode, we already report this in GPU validation
        else:
            cpu_capable_benchmarks.append("llama")
            if not data.llama.cpu_benchmark:
                errors.append("Llama benchmark missing CPU results")
        
        # Check Blender CPU benchmark - required in both modes
        if data.blender is None:
            if is_cpu_only:
                errors.append("Blender benchmark is missing in CPU-only mode")
            # In full mode, we already report this in GPU validation
        else:
            cpu_capable_benchmarks.append("blender")
            if not data.blender.cpu:
                errors.append("Blender benchmark missing CPU results")
        
        # Reversan and 7zip are CPU-only, just check they exist if present
        # (their presence is already validated by the "has_any_benchmark" check)
        if data.reversan:
            cpu_capable_benchmarks.append("reversan")
        if data.sevenzip:
            cpu_capable_benchmarks.append("sevenzip")
        
        logger.info(f"CPU-capable benchmarks validated: {cpu_capable_benchmarks}")
        return errors