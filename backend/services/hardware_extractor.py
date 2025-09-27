import re
from typing import Dict, List, Any, Optional
from models import HardwareInfo, StoredHardware

class HardwareExtractor:
    """Extract hardware information from benchmark data"""
    
    def __init__(self):
        self.cpu_patterns = {
            'intel': [r'intel', r'i\d-\d+', r'xeon', r'celeron', r'pentium'],
            'amd': [r'amd', r'ryzen', r'epyc', r'threadripper', r'athlon']
        }
        
        self.gpu_patterns = {
            'nvidia': [r'nvidia', r'geforce', r'gtx', r'rtx', r'titan', r'quadro', r'tesla'],
            'amd': [r'radeon', r'rx\s?\d+', r'vega', r'fury', r'r9', r'r7'],
            'intel': [r'intel.*graphics', r'iris', r'uhd.*graphics']
        }

    async def extract_hardware_info(self, benchmark_data: Dict[str, Any], provided_hardware: Dict[str, Any]) -> List[StoredHardware]:
        """Extract hardware information from benchmark data and provided hardware info"""
        hardware_info = {
            'cpus': [],
            'gpus': [],
            'memory': None,
            'os': None
        }
        
        # Process each benchmark type
        for benchmark_type, data in benchmark_data.items():
            if not data:
                continue
                
            if benchmark_type == 'blender':
                self._extract_from_blender(data, hardware_info)
            elif benchmark_type == 'llama':
                self._extract_from_llama(data, hardware_info)
            elif benchmark_type == '7zip':
                self._extract_from_7zip(data, hardware_info)
            elif benchmark_type == 'reversan':
                self._extract_from_reversan(data, hardware_info)
        
        # Use the most detailed hardware info available
        primary_cpu = self._get_primary_hardware(hardware_info['cpus'], provided_hardware.get('cpu'))
        primary_gpu = self._get_primary_hardware(hardware_info['gpus'], provided_hardware.get('gpu'))
        
        hardware_entries = []

        # Create CPU hardware entry if we have CPU benchmarks (include Blender CPU device runs)
        cpu_benchmarks = []
        for bt in benchmark_data.keys():
            if bt in ['7zip', 'reversan']:
                cpu_benchmarks.append(bt)
            elif bt == 'llama':
                # Handle wrapped data structure
                data = benchmark_data[bt]
                actual_data = data.get('results', data) if 'results' in data else data
                if actual_data.get('runs_cpu'):
                    cpu_benchmarks.append(bt)
            elif bt == 'blender':
                # Handle wrapped data structure
                data = benchmark_data[bt]
                actual_data = data.get('results', data) if 'results' in data else data
                device_runs = actual_data.get('device_runs') or []
                if any((dr or {}).get('device_framework') == 'CPU' for dr in device_runs):
                    cpu_benchmarks.append(bt)
        if cpu_benchmarks and primary_cpu:
            cpu_id = self._generate_hardware_id(primary_cpu['name'])
            hardware_entries.append(StoredHardware(
                id=cpu_id,
                name=primary_cpu['name'],
                manufacturer=primary_cpu.get('manufacturer', 'Unknown'),
                type='cpu',
                cores=primary_cpu.get('cores'),
                framework=None,
                directory_path=f"cpu/{cpu_id}",
                benchmark_runs=[],
                created_at=0,  # Will be set by storage manager
                updated_at=0   # Will be set by storage manager
            ))
        
        # Create GPU hardware entries - one for each GPU found
        gpu_benchmarks = []
        for bt in benchmark_data.keys():
            if bt == 'blender':
                gpu_benchmarks.append(bt)  # Blender always has potential for GPU
            elif bt == 'llama':
                # Handle wrapped data structure
                data = benchmark_data[bt]
                actual_data = data.get('results', data) if 'results' in data else data
                if actual_data.get('runs_gpu'):
                    gpu_benchmarks.append(bt)
        
        # Create separate hardware entry for each GPU
        for gpu_info in hardware_info['gpus']:
            if isinstance(gpu_info.get('name'), str) and gpu_info['name'].lower() != 'unknown':
                gpu_id = self._generate_hardware_id(gpu_info['name'])
                hardware_entries.append(StoredHardware(
                    id=gpu_id,
                    name=gpu_info['name'],
                    manufacturer=gpu_info.get('manufacturer', 'Unknown'),
                    type='gpu',
                    cores=None,
                    framework=gpu_info.get('framework'),
                    directory_path=f"gpu/{gpu_id}",
                    benchmark_runs=[],
                    created_at=0,  # Will be set by storage manager
                    updated_at=0   # Will be set by storage manager
                ))
        
        # Fallback: if no specific benchmarks found, create based on detected hardware
        if not hardware_entries:
            # Create entries for all detected GPUs
            for gpu_info in hardware_info['gpus']:
                if isinstance(gpu_info.get('name'), str) and gpu_info['name'].lower() != 'unknown':
                    gpu_id = self._generate_hardware_id(gpu_info['name'])
                    hardware_entries.append(StoredHardware(
                        id=gpu_id,
                        name=gpu_info['name'],
                        manufacturer=gpu_info.get('manufacturer', 'Unknown'),
                        type='gpu',
                        cores=None,
                        framework=gpu_info.get('framework'),
                        directory_path=f"gpu/{gpu_id}",
                        benchmark_runs=[],
                        created_at=0,
                        updated_at=0
                    ))
            
            # If no GPUs, create CPU entry
            if not hardware_entries and primary_cpu:
                cpu_id = self._generate_hardware_id(primary_cpu['name'])
                hardware_entries.append(StoredHardware(
                    id=cpu_id,
                    name=primary_cpu['name'],
                    manufacturer=primary_cpu.get('manufacturer', 'Unknown'),
                    type='cpu',
                    cores=primary_cpu.get('cores'),
                    framework=None,
                    directory_path=f"cpu/{cpu_id}",
                    benchmark_runs=[],
                    created_at=0,
                    updated_at=0
                ))
        
        return hardware_entries

    def _extract_from_blender(self, data: Dict[str, Any], hardware_info: Dict[str, Any]) -> None:
        """Extract hardware info from Blender benchmark data"""
        # Handle wrapped data structure - extract from 'results' if present
        actual_data = data.get('results', data) if 'results' in data else data
        
        if not actual_data.get('device_runs'):
            return
            
        for device_run in actual_data['device_runs']:
            # Extract from device_name (individual device per run)
            if 'device_name' in device_run:
                device_name = str(device_run['device_name'])
                framework = device_run.get('device_framework')
                
                # Skip combined GPU names (e.g. "GPU1, GPU2") - only process individual GPUs
                if ',' in device_name and len(device_name.split(',')) > 1:
                    print(f"Skipping combined GPU name: {device_name}")
                    continue
                
                if self._is_cpu_device(device_name, framework):
                    cpu = {
                        'name': device_name,
                        'type': 'cpu',
                        'manufacturer': self._detect_cpu_manufacturer(device_name),
                        'cores': None,
                        'threads': None
                    }
                    if not self._hardware_exists(hardware_info['cpus'], cpu):
                        hardware_info['cpus'].append(cpu)
                else:
                    gpu = self._normalize_gpu_info({
                        'name': device_name,
                        'framework': self._detect_gpu_framework(device_name, framework)
                    })
                    if not self._hardware_exists(hardware_info['gpus'], gpu):
                        hardware_info['gpus'].append(gpu)
        
        # Note: We intentionally skip raw_json system_info processing to avoid
        # duplicates and mixed hardware entries. Device-specific runs should
        # already provide the correct individual device names.

    def _extract_from_llama(self, data: Dict[str, Any], hardware_info: Dict[str, Any]) -> None:
        """Extract hardware info from Llama benchmark data"""
        # Handle wrapped data structure - extract from 'results' if present
        actual_data = data.get('results', data) if 'results' in data else data
        
        # Priority 1: Check new device_runs format for cleaner GPU separation
        if actual_data.get('device_runs'):
            for device_run in actual_data['device_runs']:
                if device_run.get('device_type') == 'gpu':
                    gpu = {
                        'name': device_run['device_name'],
                        'type': 'gpu',
                        'manufacturer': self._detect_gpu_manufacturer(device_run['device_name']),
                        'framework': 'Vulkan',  # Llama uses Vulkan for GPU benchmarks
                        'device_index': device_run.get('device_index'),
                        'driver': device_run.get('device_driver', 'unknown')
                    }
                    if not self._hardware_exists(hardware_info['gpus'], gpu):
                        hardware_info['gpus'].append(gpu)
        
        # Priority 2: Check CPU runs for CPU info
        if actual_data.get('runs_cpu'):
            for run in actual_data['runs_cpu']:
                cpu_info = run.get('metrics', {}).get('system_info', {}).get('cpu_info')
                if cpu_info:
                    cpu = self._normalize_cpu_info(cpu_info)
                    if not self._hardware_exists(hardware_info['cpus'], cpu):
                        hardware_info['cpus'].append(cpu)
                    break
        
        # Priority 3: Check if GPU selection is specified (fallback for older format)
        if not hardware_info['gpus']:  # Only if no GPUs found from device_runs
            gpu_selection = actual_data.get('gpu_selection')
            if gpu_selection and gpu_selection.get('available_gpus'):
                # Use GPU selection info to create separate entries for each GPU
                for gpu_device in gpu_selection['available_gpus']:
                    gpu = {
                        'name': gpu_device['name'],
                        'type': 'gpu',
                        'manufacturer': self._detect_gpu_manufacturer(gpu_device['name']),
                        'framework': 'Vulkan',  # Llama uses Vulkan for GPU benchmarks
                        'device_index': gpu_device['index'],
                        'icd_path': gpu_device.get('icd_path')
                    }
                    if not self._hardware_exists(hardware_info['gpus'], gpu):
                        hardware_info['gpus'].append(gpu)
            elif actual_data.get('runs_gpu'):
                # Last fallback: extract from GPU runs (legacy behavior)
                for run in actual_data['runs_gpu']:
                    gpu_info = run.get('metrics', {}).get('system_info', {}).get('gpu_info')
                    if gpu_info:
                        gpu = self._normalize_gpu_info(gpu_info)
                        if not self._hardware_exists(hardware_info['gpus'], gpu):
                            hardware_info['gpus'].append(gpu)
                        break

    def _extract_from_7zip(self, data: Dict[str, Any], hardware_info: Dict[str, Any]) -> None:
        """Extract hardware info from 7zip benchmark data"""
        # Handle wrapped data structure - extract from 'results' if present
        actual_data = data.get('results', data) if 'results' in data else data
        
        system_info = actual_data.get('system_info', {})
        
        if 'cpu' in system_info:
            cpu = self._normalize_cpu_info(system_info['cpu'])
            if not self._hardware_exists(hardware_info['cpus'], cpu):
                hardware_info['cpus'].append(cpu)
        
        if 'memory' in system_info and hardware_info['memory'] is None:
            hardware_info['memory'] = system_info['memory']
        
        if 'os' in system_info and hardware_info['os'] is None:
            hardware_info['os'] = system_info['os']

    def _extract_from_reversan(self, data: Dict[str, Any], hardware_info: Dict[str, Any]) -> None:
        """Extract hardware info from Reversan benchmark data"""
        # Handle wrapped data structure - extract from 'results' if present
        actual_data = data.get('results', data) if 'results' in data else data
        # Reversan typically doesn't contain hardware info
        pass

    def _normalize_cpu_info(self, cpu_data) -> Dict[str, Any]:
        """Normalize CPU info to consistent format"""
        if isinstance(cpu_data, str):
            return {
                'name': cpu_data,
                'type': 'cpu',
                'manufacturer': self._detect_cpu_manufacturer(cpu_data),
                'cores': None,
                'threads': None
            }
        
        name = cpu_data.get('name') or cpu_data.get('model') or 'Unknown CPU'
        
        return {
            'name': name,
            'type': 'cpu',
            'manufacturer': self._detect_cpu_manufacturer(name),
            'cores': int(cpu_data.get('cores', 0)) if cpu_data.get('cores') else None,
            'threads': int(cpu_data.get('threads', 0)) if cpu_data.get('threads') else None
        }

    def _normalize_gpu_info(self, gpu_data) -> Dict[str, Any]:
        """Normalize GPU info to consistent format"""
        if isinstance(gpu_data, str):
            return {
                'name': gpu_data,
                'type': 'gpu',
                'manufacturer': self._detect_gpu_manufacturer(gpu_data),
                'framework': self._detect_gpu_framework(gpu_data)
            }
        
        name = gpu_data.get('name') or 'Unknown GPU'
        
        return {
            'name': name,
            'type': 'gpu',
            'manufacturer': self._detect_gpu_manufacturer(name),
            'framework': gpu_data.get('framework') or self._detect_gpu_framework(name)
        }

    def _is_cpu_device(self, device_name: str, framework: Optional[str]) -> bool:
        """Check if device is a CPU"""
        if framework and isinstance(framework, str) and framework.lower() == 'cpu':
            return True
        
        if not isinstance(device_name, str):
            return False
        
        device_name_lower = device_name.lower()
        
        # Strong CPU indicators (these override GPU keywords)
        strong_cpu_keywords = ['ryzen', 'xeon', 'celeron', 'pentium', 'threadripper', 'epyc']
        if any(keyword in device_name_lower for keyword in strong_cpu_keywords):
            return True
        
        # Strong GPU indicators
        gpu_keywords = ['radeon graphics', 'geforce', 'gtx', 'rtx', 'quadro', 'tesla']
        if any(keyword in device_name_lower for keyword in gpu_keywords):
            return False
        
        # Generic keywords that could be either - use context
        if 'graphics' in device_name_lower or 'gpu' in device_name_lower:
            return False
        
        # Fallback CPU keywords
        cpu_keywords = ['cpu', 'processor', 'intel', 'amd']
        return any(keyword in device_name_lower for keyword in cpu_keywords)

    def _detect_cpu_manufacturer(self, cpu_name: str) -> str:
        """Detect CPU manufacturer from name"""
        if not isinstance(cpu_name, str):
            return 'Unknown'
        
        cpu_name_lower = cpu_name.lower()
        
        for manufacturer, patterns in self.cpu_patterns.items():
            for pattern in patterns:
                if re.search(pattern, cpu_name_lower):
                    return manufacturer.capitalize()
        
        return 'Unknown'

    def _detect_gpu_manufacturer(self, gpu_name: str) -> str:
        """Detect GPU manufacturer from name"""
        if not isinstance(gpu_name, str):
            return 'Unknown'
        
        gpu_name_lower = gpu_name.lower()
        
        for manufacturer, patterns in self.gpu_patterns.items():
            for pattern in patterns:
                if re.search(pattern, gpu_name_lower):
                    return manufacturer.upper() if manufacturer == 'amd' else manufacturer.capitalize()
        
        return 'Unknown'

    def _detect_gpu_framework(self, gpu_name: str, framework: Optional[str] = None) -> str:
        """Detect GPU framework (CUDA, OpenCL, etc.)"""
        if framework and isinstance(framework, str):
            framework_lower = framework.lower()
            if 'cuda' in framework_lower:
                return 'CUDA'
            elif 'opencl' in framework_lower:
                return 'OpenCL'
            elif 'vulkan' in framework_lower:
                return 'Vulkan'
        
        if not isinstance(gpu_name, str):
            return 'Unknown'
        
        gpu_name_lower = gpu_name.lower()
        
        if any(pattern in gpu_name_lower for pattern in ['nvidia', 'geforce', 'gtx', 'rtx']):
            return 'CUDA'
        elif any(pattern in gpu_name_lower for pattern in ['radeon', 'amd']):
            return 'OpenCL'
        elif 'intel' in gpu_name_lower:
            return 'OpenCL'
        
        return 'Unknown'

    def _hardware_exists(self, hardware_list: List[Dict], new_hardware: Dict) -> bool:
        """Check if hardware already exists in list"""
        for existing in hardware_list:
            existing_name = existing.get('name', '')
            new_name = new_hardware.get('name', '')
            if isinstance(existing_name, str) and isinstance(new_name, str):
                if existing_name.lower() == new_name.lower():
                    return True
        return False

    def _get_primary_hardware(self, extracted_hardware: List[Dict], provided_name: Optional[str]) -> Dict:
        """Get the most relevant hardware info"""
        if not extracted_hardware:
            return {
                'name': provided_name or 'Unknown',
                'manufacturer': 'Unknown',
                'type': 'unknown'
            }
        
        # If we have extracted hardware, use the first (most detailed) one
        return extracted_hardware[0]

    def _generate_hardware_id(self, hardware_name: str) -> str:
        """Generate a consistent hardware ID from name"""
        if not isinstance(hardware_name, str):
            return 'unknown-hardware'
        
        # Convert to lowercase, replace spaces and special chars with hyphens
        hardware_id = re.sub(r'[^\w\s-]', '', hardware_name.lower())
        hardware_id = re.sub(r'[-\s]+', '-', hardware_id)
        return hardware_id.strip('-')