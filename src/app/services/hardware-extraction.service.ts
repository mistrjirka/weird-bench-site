import { Injectable } from '@angular/core';
import { HardwareInfo, CpuInfo, GpuInfo } from '../models/benchmark.models';
import { 
  SevenZipResult, 
  ReversanResult, 
  LlamaResult, 
  BlenderResult 
} from '../models/benchmark-types.models';

@Injectable({
  providedIn: 'root'
})
export class HardwareExtractionService {

  constructor() { }

  /**
   * Extract hardware information from any benchmark result
   */
  extractHardwareInfo(benchmarkData: any): HardwareInfo[] {
    const hardware: HardwareInfo[] = [];
    
    if (!benchmarkData?.meta?.benchmark_name) {
      return hardware;
    }

    switch (benchmarkData.meta.benchmark_name) {
      case '7zip':
        hardware.push(...this.extractFrom7zip(benchmarkData as SevenZipResult));
        break;
      case 'reversan':
        hardware.push(...this.extractFromReversan(benchmarkData as ReversanResult));
        break;
      case 'llama':
        hardware.push(...this.extractFromLlama(benchmarkData as LlamaResult));
        break;
      case 'blender':
        hardware.push(...this.extractFromBlender(benchmarkData as BlenderResult));
        break;
    }

    return hardware;
  }

  /**
   * Extract CPU information from 7zip results
   * 7zip doesn't provide detailed CPU info, so we extract from platform string
   */
  private extractFrom7zip(data: SevenZipResult): HardwareInfo[] {
    const cpuName = this.extractCpuFromPlatform(data.meta.platform);
    if (!cpuName) return [];

    const cpu: CpuInfo = {
      id: this.generateHardwareId('cpu', cpuName),
      name: cpuName,
      type: 'cpu',
      cores: 0, // Not available from 7zip
      threads: Math.max(...data.runs.map(r => r.threads)) // Max threads used
    };

    return [cpu];
  }

  /**
   * Extract CPU information from Reversan results
   * Reversan provides compile times but limited CPU details
   */
  private extractFromReversan(data: ReversanResult): HardwareInfo[] {
    const cpuName = this.extractCpuFromPlatform(data.meta.platform);
    if (!cpuName) return [];

    const cpu: CpuInfo = {
      id: this.generateHardwareId('cpu', cpuName),
      name: cpuName,
      type: 'cpu',
      cores: 0, // Not directly available
      threads: data.runs_threads ? Math.max(...data.runs_threads.map(r => r.threads)) : 1
    };

    return [cpu];
  }

  /**
   * Extract hardware information from Llama results
   * Llama provides detailed CPU info and GPU info for GPU runs
   */
  private extractFromLlama(data: LlamaResult): HardwareInfo[] {
    const hardware: HardwareInfo[] = [];

    // Extract CPU info from CPU runs
    if (data.runs_cpu && data.runs_cpu.length > 0) {
      const cpuRun = data.runs_cpu[0];
      const cpuInfo = cpuRun.metrics.system_info.cpu_info;
      
      const cpu: CpuInfo = {
        id: this.generateHardwareId('cpu', cpuInfo),
        name: cpuInfo,
        type: 'cpu',
        cores: 0, // Could be extracted from name parsing
        threads: cpuRun.metrics.system_info.n_threads
      };
      
      hardware.push(cpu);
    }

    // Extract GPU info from GPU runs
    if (data.runs_gpu && data.runs_gpu.length > 0) {
      const gpuRun = data.runs_gpu[0];
      const gpuInfo = gpuRun.metrics.system_info.gpu_info;
      
      if (gpuInfo && gpuInfo.trim()) {
        const gpu: GpuInfo = {
          id: this.generateHardwareId('gpu', gpuInfo),
          name: gpuInfo,
          type: 'gpu',
          memory: 0, // Not directly available
          deviceFramework: this.mapBackendToFramework(gpuRun.metrics.system_info.backends)
        };
        
        hardware.push(gpu);
      }
    }

    return hardware;
  }

  /**
   * Extract hardware information from Blender results
   * Blender provides the most detailed hardware information
   */
  private extractFromBlender(data: BlenderResult): HardwareInfo[] {
    const hardware: HardwareInfo[] = [];

    for (const deviceRun of data.device_runs) {
      if (deviceRun.raw_json && deviceRun.raw_json.length > 0) {
        const rawResult = deviceRun.raw_json[0];
        
        if (rawResult.system_info?.devices) {
          for (const device of rawResult.system_info.devices) {
            if (device.type === 'CPU') {
              const cpu: CpuInfo = {
                id: this.generateHardwareId('cpu', device.name),
                name: device.name,
                type: 'cpu',
                cores: rawResult.system_info.num_cpu_cores || 0,
                threads: rawResult.system_info.num_cpu_threads || 0
              };
              hardware.push(cpu);
            } else if (['CUDA', 'HIP', 'OPENCL', 'OPTIX', 'METAL'].includes(device.type)) {
              const gpu: GpuInfo = {
                id: this.generateHardwareId('gpu', device.name),
                name: device.name,
                type: 'gpu',
                memory: 0, // Could be extracted from device memory info if available
                deviceFramework: device.type as any
              };
              hardware.push(gpu);
            }
          }
        }
      }
    }

    return hardware;
  }

  /**
   * Extract CPU name from platform string
   */
  private extractCpuFromPlatform(platform: string): string | null {
    // Platform example: "Linux-6.16.7-arch1-1-x86_64-with-glibc2.42"
    // This doesn't contain CPU info, so we return null
    return null;
  }

  /**
   * Map Llama backend to GPU framework
   */
  private mapBackendToFramework(backend: string): 'CUDA' | 'HIP' | 'OPENCL' | 'OPTIX' | 'METAL' {
    const backendLower = backend.toLowerCase();
    
    if (backendLower.includes('cuda')) return 'CUDA';
    if (backendLower.includes('hip')) return 'HIP';
    if (backendLower.includes('opencl')) return 'OPENCL';
    if (backendLower.includes('optix')) return 'OPTIX';
    if (backendLower.includes('metal')) return 'METAL';
    
    return 'CUDA'; // Default fallback
  }

  /**
   * Generate a consistent hardware ID
   */
  private generateHardwareId(type: 'cpu' | 'gpu', name: string): string {
    // Clean and normalize the name
    const cleanName = name.toLowerCase()
      .replace(/[^a-z0-9\s]/g, '')
      .replace(/\s+/g, '-')
      .trim();
    
    return `${type}-${cleanName}`;
  }

  /**
   * Normalize hardware name for consistent display
   */
  normalizeHardwareName(name: string): string {
    return name
      .replace(/\s+/g, ' ')
      .replace(/\s*-\s*/g, '-')
      .trim();
  }

  /**
   * Check if two hardware entries represent the same hardware
   */
  isSameHardware(hw1: HardwareInfo, hw2: HardwareInfo): boolean {
    return hw1.type === hw2.type && 
           hw1.id === hw2.id;
  }
}