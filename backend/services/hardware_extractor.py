"""
Hardware Extractor for extracting hardware information from benchmark data.
"""

import logging
from typing import Dict, Any, List
from models import StoredHardware

logger = logging.getLogger(__name__)


class HardwareExtractor:
    """Extracts hardware information from benchmark data."""
    
    def __init__(self):
        pass
    
    async def extract_hardware_info(self, benchmark_data: Dict[str, Any], hardware_data: Dict[str, Any]) -> List[StoredHardware]:
        """Extract hardware information from benchmark data (legacy compatibility)."""
        logger.warning("HardwareExtractor.extract_hardware_info() called - this is legacy code and should not be used with unified format")
        
        # For unified format, hardware info should be extracted directly from the unified data
        # This method is kept for legacy compatibility only
        hardware_entries = []
        
        # Try to extract basic CPU info
        try:
            cpu_info = hardware_data.get('cpu', {})
            if isinstance(cpu_info, dict) and cpu_info.get('model'):
                cpu_entry = StoredHardware(
                    hardware_id="cpu-0",  # Default ID
                    name=cpu_info.get('model', 'Unknown CPU'),
                    type='cpu',
                    manufacturer=self._extract_cpu_manufacturer(cpu_info.get('model', '')),
                    cores=cpu_info.get('cores'),
                    framework=None,
                    directory_path='cpu/cpu-0',
                    benchmark_runs=[],
                    created_at=0,
                    updated_at=0
                )
                hardware_entries.append(cpu_entry)
        except Exception as e:
            logger.error(f"Failed to extract CPU info: {e}")
        
        # Try to extract basic GPU info
        try:
            gpu_info = hardware_data.get('gpu', {})
            if isinstance(gpu_info, dict) and gpu_info.get('name'):
                gpu_entry = StoredHardware(
                    hardware_id="gpu-0",  # Default ID
                    name=gpu_info.get('name', 'Unknown GPU'),
                    type='gpu',
                    manufacturer=self._extract_gpu_manufacturer(gpu_info.get('name', '')),
                    cores=None,
                    framework=gpu_info.get('framework'),
                    directory_path='gpu/gpu-0',
                    benchmark_runs=[],
                    created_at=0,
                    updated_at=0
                )
                hardware_entries.append(gpu_entry)
        except Exception as e:
            logger.error(f"Failed to extract GPU info: {e}")
        
        logger.warning(f"Legacy hardware extraction returned {len(hardware_entries)} entries")
        return hardware_entries
    
    def _extract_cpu_manufacturer(self, cpu_model: str) -> str:
        """Extract CPU manufacturer from model name."""
        model_lower = cpu_model.lower()
        if 'intel' in model_lower:
            return 'Intel'
        elif 'amd' in model_lower:
            return 'AMD'
        elif 'apple' in model_lower:
            return 'Apple'
        else:
            return 'Unknown'
    
    def _extract_gpu_manufacturer(self, gpu_name: str) -> str:
        """Extract GPU manufacturer from name."""
        name_lower = gpu_name.lower()
        if 'nvidia' in name_lower or 'geforce' in name_lower or 'rtx' in name_lower or 'gtx' in name_lower:
            return 'NVIDIA'
        elif 'amd' in name_lower or 'radeon' in name_lower:
            return 'AMD'
        elif 'intel' in name_lower:
            return 'Intel'
        else:
            return 'Unknown'