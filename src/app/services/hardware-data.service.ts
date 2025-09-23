import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, map, catchError, of, forkJoin, switchMap } from 'rxjs';
import { 
  HardwareInfo, 
  HardwareSummary, 
  HardwareListResponse, 
  HardwareDetailResponse
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
    [key: string]: string[]; // benchmark type -> list of file paths
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

  // Shared metrics helpers
  public median(values: number[]): number | null {
    const arr = values.filter(v => typeof v === 'number' && !isNaN(v)).sort((a, b) => a - b);
    if (!arr.length) return null;
    const mid = Math.floor(arr.length / 2);
    return arr.length % 2 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
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
          benchmarkCount: Object.values(cpu.benchmarks).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0),
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
          benchmarkCount: Object.values(gpu.benchmarks).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0),
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

        // For now, return empty benchmarks - detailed files are loaded lazily per component
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
    return this.http.get<HardwareIndex>(`${this.dataBaseUrl}/index.json`).pipe(
      map(index => {
        const hardware = type === 'cpu'
          ? index.hardware.cpus.find(h => h.id === id)
          : index.hardware.gpus.find(h => h.id === id);
        if (!hardware) throw new Error('Hardware not found');
        const paths = hardware.benchmarks[benchmarkType] || [];
        return Array.isArray(paths) ? paths[0] : undefined;
      }),
      catchError(() => of(undefined)),
      switchMap((path?: string) => {
        if (!path) return of(null);
        const fullPath = `${this.dataBaseUrl}/${path}`;
        return this.http.get(fullPath).pipe(catchError(() => of(null)));
      })
    );
  }

  loadBenchmarkFiles(type: 'cpu' | 'gpu', id: string, benchmarkType: string): Observable<any[]> {
    return this.http.get<HardwareIndex>(`${this.dataBaseUrl}/index.json`).pipe(
      map(index => {
        const hardware = type === 'cpu'
          ? index.hardware.cpus.find(h => h.id === id)
          : index.hardware.gpus.find(h => h.id === id);
        if (!hardware) throw new Error('Hardware not found');
        const paths = hardware.benchmarks[benchmarkType] || [];
        return Array.isArray(paths) ? paths : [];
      }),
      catchError(() => of([] as string[])),
      switchMap((paths: string[]) => {
        if (!paths.length) return of([]);
        return forkJoin(
          paths.map(p => this.http.get(`${this.dataBaseUrl}/${p}`).pipe(catchError(() => of(null))))
        );
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