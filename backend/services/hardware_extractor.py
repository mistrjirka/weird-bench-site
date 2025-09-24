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

    async def extract_hardware_info(self, benchmark_data: Dict[str, Any], provided_hardware: Dict[str, Any]) -> StoredHardware:
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
        
        # Determine which hardware type this run belongs to
        if primary_gpu and primary_gpu['name'].lower() != 'unknown':
            hardware_type = 'gpu'
            hardware_name = primary_gpu['name']
            manufacturer = primary_gpu.get('manufacturer', 'Unknown')
            framework = primary_gpu.get('framework')
            cores = None
        else:
            hardware_type = 'cpu'
            hardware_name = primary_cpu['name']
            manufacturer = primary_cpu.get('manufacturer', 'Unknown')
            framework = None
            cores = primary_cpu.get('cores')
        
        # Generate hardware ID
        hardware_id = self._generate_hardware_id(hardware_name)
        
        return StoredHardware(
            id=hardware_id,
            name=hardware_name,
            manufacturer=manufacturer,
            type=hardware_type,
            cores=cores,
            framework=framework,
            directory_path=f"{hardware_type}/{hardware_id}",
            benchmark_runs=[],
            created_at=0,  # Will be set by storage manager
            updated_at=0   # Will be set by storage manager
        )

    def _extract_from_blender(self, data: Dict[str, Any], hardware_info: Dict[str, Any]) -> None:
        """Extract hardware info from Blender benchmark data"""
        if not data.get('device_runs'):
            return
            
        for device_run in data['device_runs']:
            # Extract from device_name (old format)
            if 'device_name' in device_run:
                device_name = str(device_run['device_name'])
                framework = device_run.get('device_framework')
                
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
            
            # Extract from raw_json system_info (new format)
            if 'raw_json' in device_run and device_run['raw_json']:
                for raw_data in device_run['raw_json']:
                    if 'system_info' in raw_data and 'devices' in raw_data['system_info']:
                        for device in raw_data['system_info']['devices']:
                            if 'name' in device and 'type' in device:
                                device_name = str(device['name'])
                                device_type = str(device['type'])
                                
                                if self._is_cpu_device(device_name, device_type):
                                    cpu = {
                                        'name': device_name,
                                        'type': 'cpu',
                                        'manufacturer': self._detect_cpu_manufacturer(device_name),
                                        'cores': raw_data['system_info'].get('num_cpu_cores'),
                                        'threads': raw_data['system_info'].get('num_cpu_threads')
                                    }
                                    if not self._hardware_exists(hardware_info['cpus'], cpu):
                                        hardware_info['cpus'].append(cpu)
                                else:
                                    gpu = self._normalize_gpu_info({
                                        'name': device_name,
                                        'framework': self._detect_gpu_framework(device_name, device_type)
                                    })
                                    if not self._hardware_exists(hardware_info['gpus'], gpu):
                                        hardware_info['gpus'].append(gpu)
                    # Only process first raw_json to avoid duplicates
                    break

    def _extract_from_llama(self, data: Dict[str, Any], hardware_info: Dict[str, Any]) -> None:
        """Extract hardware info from Llama benchmark data"""
        if data.get('runs_cpu'):
            for run in data['runs_cpu']:
                cpu_info = run.get('metrics', {}).get('system_info', {}).get('cpu_info')
                if cpu_info:
                    cpu = self._normalize_cpu_info(cpu_info)
                    if not self._hardware_exists(hardware_info['cpus'], cpu):
                        hardware_info['cpus'].append(cpu)
                    break
        
        if data.get('runs_gpu'):
            for run in data['runs_gpu']:
                gpu_info = run.get('metrics', {}).get('system_info', {}).get('gpu_info')
                if gpu_info:
                    gpu = self._normalize_gpu_info(gpu_info)
                    if not self._hardware_exists(hardware_info['gpus'], gpu):
                        hardware_info['gpus'].append(gpu)
                    break

    def _extract_from_7zip(self, data: Dict[str, Any], hardware_info: Dict[str, Any]) -> None:
        """Extract hardware info from 7zip benchmark data"""
        system_info = data.get('system_info', {})
        
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
        if framework and framework.lower() == 'cpu':
            return True
        
        device_name_lower = device_name.lower()
        cpu_keywords = ['cpu', 'processor', 'intel', 'amd', 'ryzen', 'xeon']
        return any(keyword in device_name_lower for keyword in cpu_keywords)

    def _detect_cpu_manufacturer(self, cpu_name: str) -> str:
        """Detect CPU manufacturer from name"""
        cpu_name_lower = cpu_name.lower()
        
        for manufacturer, patterns in self.cpu_patterns.items():
            for pattern in patterns:
                if re.search(pattern, cpu_name_lower):
                    return manufacturer.capitalize()
        
        return 'Unknown'

    def _detect_gpu_manufacturer(self, gpu_name: str) -> str:
        """Detect GPU manufacturer from name"""
        gpu_name_lower = gpu_name.lower()
        
        for manufacturer, patterns in self.gpu_patterns.items():
            for pattern in patterns:
                if re.search(pattern, gpu_name_lower):
                    return manufacturer.upper() if manufacturer == 'amd' else manufacturer.capitalize()
        
        return 'Unknown'

    def _detect_gpu_framework(self, gpu_name: str, framework: Optional[str] = None) -> str:
        """Detect GPU framework (CUDA, OpenCL, etc.)"""
        if framework:
            framework_lower = framework.lower()
            if 'cuda' in framework_lower:
                return 'CUDA'
            elif 'opencl' in framework_lower:
                return 'OpenCL'
            elif 'vulkan' in framework_lower:
                return 'Vulkan'
        
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
            if existing.get('name', '').lower() == new_hardware.get('name', '').lower():
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
        # Convert to lowercase, replace spaces and special chars with hyphens
        hardware_id = re.sub(r'[^\w\s-]', '', hardware_name.lower())
        hardware_id = re.sub(r'[-\s]+', '-', hardware_id)
        return hardware_id.strip('-')