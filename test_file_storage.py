#!/usr/bin/env python3
"""
Test script to simulate uploading benchmark results to the file storage system.
This copies the real benchmark files and processes them through the PHP backend logic.
"""

import json
import os
import shutil
from pathlib import Path

# Paths to your actual benchmark result files
BENCHMARK_FILES = {
    'llama': '/home/jirka/programovani/weird-bench/results/llama_results.json',
    '7zip': '/home/jirka/programovani/weird-bench/results/7zip_results.json', 
    'reversan': '/home/jirka/programovani/weird-bench/results/reversan_results.json',
    'blender': '/home/jirka/programovani/weird-bench/results/blender_results.json'
}

# Website directories
WEBSITE_DIR = '/home/jirka/programovani/weird-bench-site'
UPLOAD_DIR = f'{WEBSITE_DIR}/api/uploads'
DATA_DIR = f'{WEBSITE_DIR}/api/data'
CACHE_DIR = f'{WEBSITE_DIR}/api/cache'

def ensure_directories():
    """Create necessary directories"""
    directories = [
        UPLOAD_DIR,
        f'{DATA_DIR}/hardware',
        f'{DATA_DIR}/benchmarks', 
        f'{DATA_DIR}/results',
        f'{CACHE_DIR}/hardware-list',
        f'{CACHE_DIR}/hardware-details'
    ]
    
    for dir_path in directories:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {dir_path}")

def copy_benchmark_files():
    """Copy actual benchmark files to upload directory"""
    print("\n📁 Copying benchmark files...")
    
    benchmark_data = {}
    
    for bench_type, file_path in BENCHMARK_FILES.items():
        if os.path.exists(file_path):
            # Copy to upload directory
            dest_path = f'{UPLOAD_DIR}/{bench_type}_results.json'
            shutil.copy2(file_path, dest_path)
            print(f"✓ Copied {bench_type}: {file_path} -> {dest_path}")
            
            # Load JSON data for processing
            with open(file_path, 'r') as f:
                benchmark_data[bench_type] = json.load(f)
        else:
            print(f"❌ File not found: {file_path}")
    
    return benchmark_data

def extract_hardware_info(benchmark_data):
    """Extract hardware information from benchmark data (Python version of PHP logic)"""
    print("\n🔧 Extracting hardware information...")
    
    hardware_info = {
        'cpus': [],
        'gpus': [],
        'memory': None,
        'os': None,
        'timestamp': int(os.path.getmtime(BENCHMARK_FILES['llama']) if os.path.exists(BENCHMARK_FILES['llama']) else 0)
    }
    
    # Extract from each benchmark type
    for bench_type, data in benchmark_data.items():
        print(f"  Processing {bench_type}...")
        
        if bench_type == 'llama':
            # Extract CPU from platform
            if 'meta' in data and 'platform' in data['meta']:
                platform = data['meta']['platform']
                # Extract CPU name from platform string (basic extraction)
                if 'AMD' in platform or 'Intel' in platform:
                    cpu_name = extract_cpu_from_platform(platform)
                    if cpu_name:
                        cpu = {
                            'id': generate_hardware_id('cpu', cpu_name),
                            'name': cpu_name,
                            'type': 'cpu',
                            'manufacturer': 'AMD' if 'AMD' in cpu_name else 'Intel' if 'Intel' in cpu_name else 'Unknown'
                        }
                        if not hardware_exists(hardware_info['cpus'], cpu):
                            hardware_info['cpus'].append(cpu)
                            print(f"    Found CPU: {cpu_name}")
            
            # Extract GPU from GPU runs
            if 'runs_gpu' in data:
                for run in data['runs_gpu']:
                    if 'device_name' in run:
                        gpu_name = run['device_name']
                        gpu = {
                            'id': generate_hardware_id('gpu', gpu_name),
                            'name': gpu_name,
                            'type': 'gpu',
                            'manufacturer': detect_gpu_manufacturer(gpu_name),
                            'framework': 'Vulkan'  # Llama uses Vulkan for GPU
                        }
                        if not hardware_exists(hardware_info['gpus'], gpu):
                            hardware_info['gpus'].append(gpu)
                            print(f"    Found GPU: {gpu_name}")
        
        elif bench_type == 'blender':
            # Extract from device runs
            if 'device_runs' in data:
                for run in data['device_runs']:
                    device_name = run.get('device_name', '')
                    device_framework = run.get('device_framework', 'UNKNOWN')
                    
                    if device_name and device_name != 'CPU':
                        # This is a GPU
                        gpu = {
                            'id': generate_hardware_id('gpu', device_name),
                            'name': device_name,
                            'type': 'gpu',
                            'manufacturer': detect_gpu_manufacturer(device_name),
                            'framework': device_framework
                        }
                        if not hardware_exists(hardware_info['gpus'], gpu):
                            hardware_info['gpus'].append(gpu)
                            print(f"    Found GPU: {device_name} ({device_framework})")
                    elif device_framework == 'CPU':
                        # This is CPU info - use device_name if available, otherwise extract from platform
                        cpu_name = device_name if device_name else extract_cpu_from_platform(data.get('meta', {}).get('platform', ''))
                        if cpu_name:
                            cpu = {
                                'id': generate_hardware_id('cpu', cpu_name),
                                'name': cpu_name,
                                'type': 'cpu',
                                'manufacturer': detect_cpu_manufacturer(cpu_name)
                            }
                            if not hardware_exists(hardware_info['cpus'], cpu):
                                hardware_info['cpus'].append(cpu)
                                print(f"    Found CPU: {cpu_name}")
        
        elif bench_type in ['7zip', 'reversan']:
            # Extract CPU from platform
            if 'meta' in data and 'platform' in data['meta']:
                platform = data['meta']['platform']
                cpu_name = extract_cpu_from_platform(platform)
                if cpu_name:
                    cpu = {
                        'id': generate_hardware_id('cpu', cpu_name),
                        'name': cpu_name,
                        'type': 'cpu',
                        'manufacturer': detect_cpu_manufacturer(cpu_name)
                    }
                    if not hardware_exists(hardware_info['cpus'], cpu):
                        hardware_info['cpus'].append(cpu)
                        print(f"    Found CPU: {cpu_name}")
    
    # Generate overall hardware ID
    hardware_info['id'] = generate_overall_hardware_id(hardware_info)
    
    return hardware_info

def extract_cpu_from_platform(platform):
    """Extract CPU name from platform string"""
    # Simple extraction - in real implementation this would be more sophisticated
    if 'AMD Ryzen' in platform:
        return 'AMD Ryzen 7 5700X3D 8-Core Processor'  # Based on your benchmark results
    elif 'Intel' in platform:
        # Extract Intel CPU name if present
        return 'Intel CPU'  # Placeholder
    return None

def detect_cpu_manufacturer(name):
    """Detect CPU manufacturer from name"""
    name_lower = name.lower()
    if 'amd' in name_lower or 'ryzen' in name_lower:
        return 'AMD'
    elif 'intel' in name_lower:
        return 'Intel'
    return 'Unknown'

def detect_gpu_manufacturer(name):
    """Detect GPU manufacturer from name"""
    name_lower = name.lower()
    if 'nvidia' in name_lower or 'geforce' in name_lower or 'rtx' in name_lower or 'gtx' in name_lower:
        return 'NVIDIA'
    elif 'amd' in name_lower or 'radeon' in name_lower or 'rx ' in name_lower:
        return 'AMD'
    elif 'intel' in name_lower or 'arc' in name_lower:
        return 'Intel'
    return 'Unknown'

def generate_hardware_id(hw_type, name):
    """Generate hardware ID"""
    clean_name = name.lower().replace(' ', '-').replace('(', '').replace(')', '')
    return f"{hw_type}-{clean_name}"

def generate_overall_hardware_id(hardware_info):
    """Generate overall hardware configuration ID"""
    components = []
    for cpu in hardware_info['cpus']:
        components.append(f"cpu-{cpu['name'].lower().replace(' ', '-')}")
    for gpu in hardware_info['gpus']:
        components.append(f"gpu-{gpu['name'].lower().replace(' ', '-')}")
    return '-'.join(components)[:100]  # Limit length

def hardware_exists(hardware_list, new_hardware):
    """Check if hardware already exists in list"""
    for existing in hardware_list:
        if existing['name'].lower() == new_hardware['name'].lower():
            return True
    return False

def store_hardware_files(hardware_info, benchmark_data):
    """Store hardware and benchmark files (simulating PHP FileStorageManager)"""
    print(f"\n💾 Storing hardware data...")
    
    hardware_id = hardware_info['id']
    
    # Store hardware info
    hardware_file = f'{DATA_DIR}/hardware/{hardware_id}.json'
    with open(hardware_file, 'w') as f:
        json.dump(hardware_info, f, indent=2)
    print(f"✓ Stored hardware info: {hardware_file}")
    
    # Store individual benchmark files
    timestamp = hardware_info['timestamp']
    benchmark_ids = {}
    
    for bench_type, data in benchmark_data.items():
        benchmark_id = f"{hardware_id}_{bench_type}_{timestamp}"
        benchmark_file = f'{DATA_DIR}/benchmarks/{benchmark_id}.json'
        
        benchmark_record = {
            'id': benchmark_id,
            'type': bench_type,
            'timestamp': timestamp,
            'data': data
        }
        
        with open(benchmark_file, 'w') as f:
            json.dump(benchmark_record, f, indent=2)
        benchmark_ids[bench_type] = benchmark_id
        print(f"✓ Stored {bench_type} benchmark: {benchmark_file}")
    
    # Store aggregated results (simplified)
    results = {
        'summary': {
            'benchmark_count': len(benchmark_data),
            'available_benchmarks': list(benchmark_data.keys()),
            'last_updated': timestamp
        }
    }
    
    results_file = f'{DATA_DIR}/results/{hardware_id}.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"✓ Stored results summary: {results_file}")
    
    return {
        'hardware_id': hardware_id,
        'benchmark_ids': benchmark_ids
    }

def generate_hardware_list():
    """Generate hardware list cache (simulating PHP FileStorageManager)"""
    print(f"\n📋 Generating hardware list...")
    
    cpus = []
    gpus = []
    
    # Scan hardware directory
    hardware_dir = Path(f'{DATA_DIR}/hardware')
    if hardware_dir.exists():
        for hardware_file in hardware_dir.glob('*.json'):
            with open(hardware_file, 'r') as f:
                hardware_data = json.load(f)
            
            hardware_id = hardware_file.stem
            
            # Load results if available
            results_file = f'{DATA_DIR}/results/{hardware_id}.json'
            results = {}
            if os.path.exists(results_file):
                with open(results_file, 'r') as f:
                    results = json.load(f)
            
            # Process CPUs and GPUs
            if 'cpus' in hardware_data:
                for cpu in hardware_data['cpus']:
                    cpu_summary = {
                        'hardware': cpu,
                        'benchmarkCount': results.get('summary', {}).get('benchmark_count', 0),
                        'lastUpdated': results.get('summary', {}).get('last_updated'),
                        'bestPerformance': None,
                        'averagePerformance': {}
                    }
                    cpus.append(cpu_summary)
            
            if 'gpus' in hardware_data:
                for gpu in hardware_data['gpus']:
                    gpu_summary = {
                        'hardware': gpu,
                        'benchmarkCount': results.get('summary', {}).get('benchmark_count', 0),
                        'lastUpdated': results.get('summary', {}).get('last_updated'),
                        'bestPerformance': None,
                        'averagePerformance': {}
                    }
                    gpus.append(gpu_summary)
    
    import time
    
    hardware_list = {
        'cpus': cpus,
        'gpus': gpus,
        'totalCount': len(cpus) + len(gpus),
        'generated_at': int(time.time())
    }
    
    # Cache the result
    cache_file = f'{CACHE_DIR}/hardware-list/list.json'
    Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(hardware_list, f, indent=2)
    
    print(f"✓ Generated hardware list cache: {cache_file}")
    print(f"  Found {len(cpus)} CPUs and {len(gpus)} GPUs")
    
    return hardware_list

def main():
    print("🚀 Testing Weird Bench file storage system...")
    print("=" * 50)
    
    # Ensure directories exist
    ensure_directories()
    
    # Copy your actual benchmark files
    benchmark_data = copy_benchmark_files()
    
    if not benchmark_data:
        print("❌ No benchmark files found!")
        return
    
    # Extract hardware information
    hardware_info = extract_hardware_info(benchmark_data)
    
    print(f"\n🔍 Hardware Detection Results:")
    print(f"  Hardware ID: {hardware_info['id']}")
    print(f"  CPUs found: {len(hardware_info['cpus'])}")
    for cpu in hardware_info['cpus']:
        print(f"    - {cpu['name']} ({cpu['manufacturer']})")
    print(f"  GPUs found: {len(hardware_info['gpus'])}")
    for gpu in hardware_info['gpus']:
        print(f"    - {gpu['name']} ({gpu['manufacturer']}) [{gpu.get('framework', 'Unknown')}]")
    
    # Store files
    storage_result = store_hardware_files(hardware_info, benchmark_data)
    
    # Generate hardware list
    hardware_list = generate_hardware_list()
    
    print(f"\n✅ Test completed successfully!")
    print(f"📊 Results:")
    print(f"  - Hardware ID: {storage_result['hardware_id']}")
    print(f"  - Benchmark files stored: {len(storage_result['benchmark_ids'])}")
    print(f"  - Hardware list generated with {hardware_list['totalCount']} items")
    
    print(f"\n📁 Files created in:")
    print(f"  - Data: {DATA_DIR}")
    print(f"  - Cache: {CACHE_DIR}")
    print(f"  - Uploads: {UPLOAD_DIR}")
    
    print(f"\n🌐 You can now start the Angular dev server and see the results!")
    print(f"   The hardware list API will read from the cached file.")

if __name__ == "__main__":
    main()