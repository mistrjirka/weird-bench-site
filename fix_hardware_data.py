#!/usr/bin/env python3
"""
Quick fix script to correct the hardware categorization and regenerate the cache
"""

import json
import os
from pathlib import Path

WEBSITE_DIR = '/home/jirka/programovani/weird-bench-site'
DATA_DIR = f'{WEBSITE_DIR}/api/data'
CACHE_DIR = f'{WEBSITE_DIR}/api/cache'

def fix_hardware_data():
    """Fix the hardware categorization issue"""
    print("🔧 Fixing hardware categorization...")
    
    # Find the hardware file
    hardware_dir = Path(f'{DATA_DIR}/hardware')
    hardware_files = list(hardware_dir.glob('*.json'))
    
    if not hardware_files:
        print("❌ No hardware files found")
        return
    
    hardware_file = hardware_files[0]  # Get the first (and likely only) file
    print(f"  Processing: {hardware_file}")
    
    # Load and fix the hardware data
    with open(hardware_file, 'r') as f:
        hardware_data = json.load(f)
    
    # Fix the categorization
    fixed_cpus = []
    fixed_gpus = []
    
    # Check both cpus and gpus arrays for misclassified items
    all_items = hardware_data.get('cpus', []) + hardware_data.get('gpus', [])
    
    for item in all_items:
        name = item.get('name', '')
        
        # Properly categorize based on name
        if any(cpu_keyword in name.lower() for cpu_keyword in ['ryzen', 'intel', 'processor', 'core processor']):
            # This is a CPU
            cpu_item = item.copy()
            cpu_item['type'] = 'cpu'
            cpu_item['id'] = generate_cpu_id(name)
            
            # Remove framework field for CPUs
            if 'framework' in cpu_item:
                del cpu_item['framework']
            
            fixed_cpus.append(cpu_item)
            print(f"    ✓ Fixed CPU: {name}")
            
        elif any(gpu_keyword in name.lower() for gpu_keyword in ['radeon', 'geforce', 'rtx', 'gtx', 'arc']):
            # This is a GPU
            gpu_item = item.copy()
            gpu_item['type'] = 'gpu'
            gpu_item['id'] = generate_gpu_id(name)
            fixed_gpus.append(gpu_item)
            print(f"    ✓ Fixed GPU: {name}")
    
    # Update hardware data
    hardware_data['cpus'] = fixed_cpus
    hardware_data['gpus'] = fixed_gpus
    
    # Generate new hardware ID
    hardware_data['id'] = generate_hardware_id(fixed_cpus, fixed_gpus)
    
    # Save the fixed data
    new_hardware_file = f'{DATA_DIR}/hardware/{hardware_data["id"]}.json'
    with open(new_hardware_file, 'w') as f:
        json.dump(hardware_data, f, indent=2)
    
    print(f"    ✓ Saved fixed hardware data: {new_hardware_file}")
    
    # Remove old file if different
    if str(hardware_file) != new_hardware_file:
        os.remove(hardware_file)
        print(f"    ✓ Removed old file: {hardware_file}")
    
    return hardware_data

def generate_cpu_id(name):
    """Generate CPU ID"""
    clean_name = name.lower().replace(' ', '-').replace('(', '').replace(')', '').replace(',', '')
    return f"cpu-{clean_name}"

def generate_gpu_id(name):
    """Generate GPU ID"""
    clean_name = name.lower().replace(' ', '-').replace('(', '').replace(')', '').replace(',', '')
    return f"gpu-{clean_name}"

def generate_hardware_id(cpus, gpus):
    """Generate overall hardware ID"""
    components = []
    for cpu in cpus:
        cpu_name = cpu['name'].lower().replace(' ', '-').replace('(', '').replace(')', '').replace(',', '')
        components.append(f"cpu-{cpu_name}")
    for gpu in gpus:
        gpu_name = gpu['name'].lower().replace(' ', '-').replace('(', '').replace(')', '').replace(',', '')
        components.append(f"gpu-{gpu_name}")
    return '-'.join(components)[:100]

def regenerate_cache(hardware_data):
    """Regenerate the hardware list cache"""
    print("📋 Regenerating hardware list cache...")
    
    import time
    
    cpus = []
    gpus = []
    
    # Create CPU summaries
    for cpu in hardware_data.get('cpus', []):
        cpu_summary = {
            'hardware': cpu,
            'benchmarkCount': 4,  # We know we have 4 benchmarks
            'lastUpdated': hardware_data.get('timestamp'),
            'bestPerformance': None,
            'averagePerformance': {}
        }
        cpus.append(cpu_summary)
    
    # Create GPU summaries
    for gpu in hardware_data.get('gpus', []):
        gpu_summary = {
            'hardware': gpu,
            'benchmarkCount': 4,  # We know we have 4 benchmarks
            'lastUpdated': hardware_data.get('timestamp'),
            'bestPerformance': None,
            'averagePerformance': {}
        }
        gpus.append(gpu_summary)
    
    hardware_list = {
        'cpus': cpus,
        'gpus': gpus,
        'totalCount': len(cpus) + len(gpus),
        'generated_at': int(time.time())
    }
    
    # Save cache
    cache_file = f'{CACHE_DIR}/hardware-list/list.json'
    Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(cache_file, 'w') as f:
        json.dump(hardware_list, f, indent=2)
    
    print(f"✓ Hardware list cache updated: {cache_file}")
    print(f"  CPUs: {len(cpus)}")
    print(f"  GPUs: {len(gpus)}")
    
    for cpu in cpus:
        print(f"    CPU: {cpu['hardware']['name']} ({cpu['hardware']['manufacturer']})")
    for gpu in gpus:
        print(f"    GPU: {gpu['hardware']['name']} ({gpu['hardware']['manufacturer']}) [{gpu['hardware'].get('framework', 'Unknown')}]")

def main():
    print("🔧 Hardware Data Fix Script")
    print("=" * 30)
    
    # Fix hardware categorization
    hardware_data = fix_hardware_data()
    
    if hardware_data:
        # Regenerate cache with fixed data
        regenerate_cache(hardware_data)
        
        print("\n✅ Hardware data fixed successfully!")
        print("🌐 You can now test the Angular frontend - it should show proper CPU/GPU categorization.")
    else:
        print("❌ Failed to fix hardware data")

if __name__ == "__main__":
    main()