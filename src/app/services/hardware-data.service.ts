import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, map, catchError, of } from 'rxjs';
import { 
  HardwareInfo, 
  HardwareSummary, 
  HardwareListResponse, 
  HardwareDetailResponse,
  ApiResponse,
  BenchmarkResult 
} from '../models/benchmark.models';

// Interface for the static index.json structure
interface HardwareIndex {
  hardware: {
    cpus: IndexHardware[];
    gpus: IndexHardware[];
  };
  metadata: {
    totalHardware: number;
    totalBenchmarks: number;
    lastUpdated: number;
    version: string;
    benchmarkTypes: string[];
  };
}

interface IndexHardware {
  id: string;
  name: string;
  manufacturer: string;
  cores?: number; // For CPUs
  framework?: string; // For GPUs
  benchmarks: {
    [key: string]: string; // benchmark type -> file path
  };
  lastUpdated: number;
}

@Injectable({
  providedIn: 'root'
})
export class HardwareDataService {
  private dataBaseUrl = '/data'; // Static JSON files
  
  // Reactive state management with signals
  private readonly _cpuList = signal<HardwareSummary[]>([]);
  private readonly _gpuList = signal<HardwareSummary[]>([]);
  private readonly _isLoading = signal<boolean>(false);
  private readonly _error = signal<string | null>(null);

  // Public readonly signals
  readonly cpuList = this._cpuList.asReadonly();
  readonly gpuList = this._gpuList.asReadonly();
  readonly isLoading = this._isLoading.asReadonly();
  readonly error = this._error.asReadonly();
  
  // Computed values
  readonly totalHardwareCount = computed(() => 
    this.cpuList().length + this.gpuList().length
  );
  
  readonly hasData = computed(() => 
    this.cpuList().length > 0 || this.gpuList().length > 0
  );

  constructor(private http: HttpClient) {
    this.loadHardwareList();
  }

  /**
   * Load the list of all hardware with benchmark summaries from static index.json
   */
  loadHardwareList(): Observable<HardwareListResponse> {
    this._isLoading.set(true);
    this._error.set(null);

    // Load static index.json file
    return this.http.get<HardwareIndex>(`${this.dataBaseUrl}/index.json`).pipe(
      map(index => {
        // Convert index format to HardwareSummary format
        const cpus: HardwareSummary[] = index.hardware.cpus.map(cpu => ({
          hardware: {
            id: cpu.id,
            name: cpu.name,
            type: 'cpu' as const,
            manufacturer: cpu.manufacturer,
            cores: cpu.cores
          },
          benchmarkCount: Object.keys(cpu.benchmarks).length,
          lastUpdated: new Date(cpu.lastUpdated * 1000),
          bestPerformance: undefined,
          averagePerformance: {}
        }));

        const gpus: HardwareSummary[] = index.hardware.gpus.map(gpu => ({
          hardware: {
            id: gpu.id,
            name: gpu.name,
            type: 'gpu' as const,
            manufacturer: gpu.manufacturer,
            framework: gpu.framework
          },
          benchmarkCount: Object.keys(gpu.benchmarks).length,
          lastUpdated: new Date(gpu.lastUpdated * 1000),
          bestPerformance: undefined,
          averagePerformance: {}
        }));

        // Update signals
        this._cpuList.set(cpus);
        this._gpuList.set(gpus);
        this._isLoading.set(false);

        return {
          cpus,
          gpus,
          totalCount: cpus.length + gpus.length
        };
      }),
      catchError(error => {
        this._error.set('Failed to load hardware index');
        this._isLoading.set(false);
        return of({
          cpus: [],
          gpus: [],
          totalCount: 0
        });
      })
    );
  }

  /**
   * Load detailed information for specific hardware from static JSON files
   */
  loadHardwareDetail(type: 'cpu' | 'gpu', id: string): Observable<HardwareDetailResponse> {
    this._isLoading.set(true);
    this._error.set(null);

    // First load the index to get file paths
    return this.http.get<HardwareIndex>(`${this.dataBaseUrl}/index.json`).pipe(
      map(index => {
        const hardware = type === 'cpu' 
          ? index.hardware.cpus.find(h => h.id === id)
          : index.hardware.gpus.find(h => h.id === id);

        if (!hardware) {
          throw new Error(`Hardware ${type}/${id} not found`);
        }

        // Create the base hardware info
        const hardwareInfo: HardwareInfo = {
          id: hardware.id,
          name: hardware.name,
          type,
          manufacturer: hardware.manufacturer,
          ...(type === 'cpu' ? { cores: hardware.cores } : { framework: hardware.framework })
        };

        // For now, return empty benchmarks - we'll implement loading individual files later
        this._isLoading.set(false);
        return {
          hardware: hardwareInfo,
          benchmarks: [],
          charts: []
        };
      }),
      catchError(error => {
        this._error.set('Failed to load hardware details');
        this._isLoading.set(false);
        return of({
          hardware: {
            id,
            name: 'Unknown Hardware',
            type
          } as HardwareInfo,
          benchmarks: [],
          charts: []
        });
      })
    );
  }

  /**
   * Load specific benchmark file for hardware
   */
  loadBenchmarkFile(type: 'cpu' | 'gpu', id: string, benchmarkType: string): Observable<any> {
    const filePath = `${this.dataBaseUrl}/${type}/${id}/${benchmarkType}.json`;
    return this.http.get(filePath).pipe(
      catchError(error => {
        console.warn(`Failed to load ${benchmarkType} benchmark for ${type}/${id}`);
        return of(null);
      })
    );
  }

  /**
   * Search hardware by name or type
   */
  searchHardware(query: string): Observable<HardwareSummary[]> {
    const searchTerm = query.toLowerCase();
    const allHardware = [...this.cpuList(), ...this.gpuList()];
    
    const filtered = allHardware.filter(hw => 
      hw.hardware.name.toLowerCase().includes(searchTerm) ||
      hw.hardware.type.toLowerCase().includes(searchTerm) ||
      hw.hardware.manufacturer?.toLowerCase().includes(searchTerm)
    );

    return of(filtered);
  }

  /**
   * Get hardware by ID
   */
  getHardwareById(id: string): HardwareSummary | null {
    const allHardware = [...this.cpuList(), ...this.gpuList()];
    return allHardware.find(hw => hw.hardware.id === id) || null;
  }

  /**
   * Clear error state
   */
  clearError(): void {
    this._error.set(null);
  }

  /**
   * Mock data for development - replace with actual API calls
   */
  private getMockHardwareList(): Observable<ApiResponse<HardwareListResponse>> {
    // Simulate API delay
    return new Observable(observer => {
      setTimeout(() => {
        observer.next({
          success: true,
          data: {
            cpus: [
              {
                hardware: {
                  id: 'cpu-amd-ryzen-7-5700x3d-8-core-processor',
                  name: 'AMD Ryzen 7 5700X3D 8-Core Processor',
                  type: 'cpu',
                  manufacturer: 'AMD',
                  cores: 8,
                  threads: 16
                },
                benchmarkCount: 4,
                lastUpdated: new Date('2025-09-23'),
                bestPerformance: {
                  benchmark: '7zip',
                  value: 3.99,
                  unit: 'speedup'
                },
                averagePerformance: {
                  '7zip': 85.2,
                  'reversan': 92.1,
                  'llama': 16.6,
                  'blender': 1142.3
                }
              }
            ],
            gpus: [
              {
                hardware: {
                  id: 'gpu-amd-radeon-rx-7800-xt',
                  name: 'AMD Radeon RX 7800 XT',
                  type: 'gpu',
                  manufacturer: 'AMD',
                  memory: 16384
                },
                benchmarkCount: 2,
                lastUpdated: new Date('2025-09-23'),
                bestPerformance: {
                  benchmark: 'blender',
                  value: 1142.3,
                  unit: 'samples/min'
                },
                averagePerformance: {
                  'llama': 160.9,
                  'blender': 892.5
                }
              }
            ],
            totalCount: 2
          },
          timestamp: Date.now()
        });
        observer.complete();
      }, 500);
    });
  }

  /**
   * Mock hardware detail data
   */
  private getMockHardwareDetail(type: 'cpu' | 'gpu', id: string): Observable<ApiResponse<HardwareDetailResponse>> {
    return new Observable(observer => {
      setTimeout(() => {
        const hardware: HardwareInfo = type === 'cpu' ? {
          id: 'cpu-amd-ryzen-7-5700x3d-8-core-processor',
          name: 'AMD Ryzen 7 5700X3D 8-Core Processor',
          type: 'cpu',
          manufacturer: 'AMD',
          cores: 8,
          threads: 16
        } : {
          id: 'gpu-amd-radeon-rx-7800-xt',
          name: 'AMD Radeon RX 7800 XT',
          type: 'gpu',
          manufacturer: 'AMD',
          memory: 16384
        };

        observer.next({
          success: true,
          data: {
            hardware,
            benchmarks: [], // Will be populated with actual benchmark data
            charts: [
              {
                type: 'line',
                title: type === 'cpu' ? 'Thread Scaling Performance' : 'GPU Performance Over Time',
                xAxis: {
                  label: type === 'cpu' ? 'Thread Count' : 'Time',
                  data: type === 'cpu' ? [1, 2, 4, 8, 16] : ['Jan', 'Feb', 'Mar', 'Apr', 'May']
                },
                yAxis: {
                  label: type === 'cpu' ? 'Speedup Factor' : 'FPS',
                  unit: type === 'cpu' ? 'x' : 'fps'
                },
                series: [{
                  name: type === 'cpu' ? '7zip Compression' : 'Blender Render',
                  data: type === 'cpu' ? [1.0, 3.85, 3.99, 3.99, 3.99] : [120, 125, 130, 128, 135],
                  color: '#007bff'
                }]
              }
            ]
          },
          timestamp: Date.now()
        });
        observer.complete();
      }, 300);
    });
  }
}