import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, map, catchError, of, forkJoin, switchMap } from 'rxjs';
import { 
  HardwareInfo, 
  HardwareSummary, 
  HardwareListResponse, 
  HardwareDetailResponse
} from '../models/benchmark.models';
import { environment } from '../../environments/environment';

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
    [key: string]: string[]; // benchmark type -> list of file paths
  };
  lastUpdated: number;
}

@Injectable({
  providedIn: 'root'
})
export class HardwareDataService {
  private apiBaseUrl = environment.apiUrl;
  
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

  // Shared metrics helpers
  public median(values: number[]): number | null {
    const arr = values.filter(v => typeof v === 'number' && !isNaN(v)).sort((a, b) => a - b);
    if (!arr.length) return null;
    const mid = Math.floor(arr.length / 2);
    return arr.length % 2 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
  }

  /**
   * Load the list of all hardware with benchmark summaries from API
   */
  loadHardwareList(): Observable<HardwareListResponse> {
    this._isLoading.set(true);
    this._error.set(null);

    return this.http.get<any>(`${this.apiBaseUrl}/hardware`).pipe(
      map(response => {
        // Convert API response to HardwareSummary format
        const hardwareData = response.data || {};
        
        // Process CPUs
        const cpus: HardwareSummary[] = (hardwareData.cpus || []).map((hw: any) => ({
          hardware: {
            id: hw.id,
            name: hw.name,
            type: 'cpu' as const,
            manufacturer: hw.manufacturer,
            ...(hw.cores ? { cores: hw.cores } : {})
          },
          benchmarkCount: Object.values(hw.benchmarks || {}).reduce((sum: number, arr: any) => 
            sum + (Array.isArray(arr) ? arr.length : 0), 0),
          lastUpdated: new Date(hw.lastUpdated * 1000),
          bestPerformance: undefined,
          averagePerformance: {}
        }));

        // Process GPUs
        const gpus: HardwareSummary[] = (hardwareData.gpus || []).map((hw: any) => ({
          hardware: {
            id: hw.id,
            name: hw.name,
            type: 'gpu' as const,
            manufacturer: hw.manufacturer,
            ...(hw.framework ? { framework: hw.framework } : {})
          },
          benchmarkCount: Object.values(hw.benchmarks || {}).reduce((sum: number, arr: any) => 
            sum + (Array.isArray(arr) ? arr.length : 0), 0),
          lastUpdated: new Date(hw.lastUpdated * 1000),
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
        console.error('Failed to load hardware list:', error);
        this._error.set('Failed to load hardware list');
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
   * Load detailed information for specific hardware from API
   */
  loadHardwareDetail(type: 'cpu' | 'gpu', id: string): Observable<HardwareDetailResponse> {
    this._isLoading.set(true);
    this._error.set(null);

    return this.http.get<any>(`${this.apiBaseUrl}/hardware-detail?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`).pipe(
      map(response => {
        const hardwareData = response.data;
        if (!hardwareData) {
          console.log('Hardware detail response:', response);
          throw new Error(`Hardware ${type}/${id} not found`);
        }

        // Create the base hardware info
        const hardwareInfo: HardwareInfo = {
          id: hardwareData.id,
          name: hardwareData.name,
          type: hardwareData.type || type,
          manufacturer: hardwareData.manufacturer,
          ...(hardwareData.cores ? { cores: hardwareData.cores } : {}),
          ...(hardwareData.framework ? { framework: hardwareData.framework } : {})
        };

        this._isLoading.set(false);
        return {
          hardware: hardwareInfo,
          benchmarks: hardwareData.benchmarkFiles || [],
          charts: []
        };
      }),
      catchError(error => {
        console.error('Failed to load hardware details:', error);
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
   * Load specific benchmark file for hardware - gets data directly from API
   */
  loadBenchmarkFile(type: 'cpu' | 'gpu', id: string, benchmarkType: string): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/hardware-detail?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`).pipe(
      map(response => {
        const benchmarkFiles = response.data?.benchmarkFiles || [];
        if (!benchmarkFiles || !Array.isArray(benchmarkFiles)) return null;
        
        // Find the first benchmark of the specific type
        const benchmark = benchmarkFiles.find((b: any) => b.type === benchmarkType);
        return benchmark ? benchmark.data : null;
      }),
      catchError(error => {
        console.error(`Failed to load ${benchmarkType} benchmark for ${id}:`, error);
        return of(null);
      })
    );
  }

  loadBenchmarkFiles(type: 'cpu' | 'gpu', id: string, benchmarkType: string): Observable<any[]> {
    return this.http.get<any>(`${this.apiBaseUrl}/hardware-detail?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`).pipe(
      map(response => {
        const benchmarkFiles = response.data?.benchmarkFiles || [];
        if (!benchmarkFiles || !Array.isArray(benchmarkFiles)) return [];
        
        // Find all benchmarks of the specific type
        const benchmarks = benchmarkFiles
          .filter((b: any) => b.type === benchmarkType)
          .map((b: any) => b.data)
          .filter((data: any) => data !== null);
        
        return benchmarks;
      }),
      catchError(error => {
        console.error(`Failed to load ${benchmarkType} benchmarks for ${id}:`, error);
        return of([]);
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

  // Removed legacy mock methods to avoid confusion
}