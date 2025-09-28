import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map, catchError, of } from 'rxjs';
import { 
  HardwareInfo, 
  HardwareSummary, 
  SimpleHardwareListResponse,
  CleanHardwareSummary,
  HardwareListResponse,
  ProcessedBenchmarkData
} from '../models/benchmark.models';
import { environment } from '../../environments/environment';

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

  // Public computed signals
  readonly cpuList = computed(() => this._cpuList());
  readonly gpuList = computed(() => this._gpuList());
  readonly isLoading = computed(() => this._isLoading());
  readonly error = computed(() => this._error());
  
  // Computed values
  readonly totalHardwareCount = computed(() => 
    this.cpuList().length + this.gpuList().length
  );
  
  readonly hasData = computed(() => 
    this.cpuList().length > 0 || this.gpuList().length > 0
  );
  
  // Computed combined list for easier access
  readonly allHardware = computed(() => [...this.cpuList(), ...this.gpuList()]);
  readonly totalCount = computed(() => this.allHardware().length);

  constructor(private http: HttpClient) {
    // Auto-load on initialization
    this.loadHardwareList().subscribe();
  }

  public median(values: number[]): number | null {
    const arr = values.filter(v => typeof v === 'number' && !isNaN(v)).sort((a, b) => a - b);
    if (!arr.length) return null;
    const mid = Math.floor(arr.length / 2);
    return arr.length % 2 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
  }

  /**
   * Load hardware list from the simplified API
   */
  loadHardwareList(): Observable<HardwareListResponse> {
    this._isLoading.set(true);
    this._error.set(null);

    return this.http.get<SimpleHardwareListResponse>(`${this.apiBaseUrl}/hardware`).pipe(
      map(response => {
        // Convert new API response to legacy format for backward compatibility
        const hardwareData = response.data;
        
        // Convert clean summaries to legacy HardwareSummary format
        const cpus: HardwareSummary[] = hardwareData.cpus.map((cleanSummary: CleanHardwareSummary) => ({
          hardware: {
            id: cleanSummary.hardware.id,
            name: cleanSummary.hardware.name,
            type: cleanSummary.hardware.type,
            manufacturer: cleanSummary.hardware.manufacturer,
            cores: cleanSummary.hardware.cores,
            threads: cleanSummary.hardware.threads,
            framework: cleanSummary.hardware.framework,
            memory_mb: cleanSummary.hardware.memory_mb
          } as HardwareInfo,
          benchmarkCount: cleanSummary.benchmarks.total_benchmarks,
          lastUpdated: new Date(cleanSummary.benchmarks.latest_run * 1000),
          bestPerformance: cleanSummary.benchmarks.best_performance ? {
            benchmark: 'mixed',
            value: 0,
            unit: 'mixed'
          } : undefined,
          averagePerformance: {}
        }));

        const gpus: HardwareSummary[] = hardwareData.gpus.map((cleanSummary: CleanHardwareSummary) => ({
          hardware: {
            id: cleanSummary.hardware.id,
            name: cleanSummary.hardware.name,
            type: cleanSummary.hardware.type,
            manufacturer: cleanSummary.hardware.manufacturer,
            cores: cleanSummary.hardware.cores,
            threads: cleanSummary.hardware.threads,
            framework: cleanSummary.hardware.framework,
            memory_mb: cleanSummary.hardware.memory_mb
          } as HardwareInfo,
          benchmarkCount: cleanSummary.benchmarks.total_benchmarks,
          lastUpdated: new Date(cleanSummary.benchmarks.latest_run * 1000),
          bestPerformance: cleanSummary.benchmarks.best_performance ? {
            benchmark: 'mixed',
            value: 0,
            unit: 'mixed'
          } : undefined,
          averagePerformance: {}
        }));

        // Update reactive state
        this._cpuList.set(cpus);
        this._gpuList.set(gpus);
        this._isLoading.set(false);

        // Return in legacy format
        return {
          data: { cpus, gpus },
          timestamp: response.timestamp
        } as HardwareListResponse;
      }),
      catchError(error => {
        console.error('Failed to load hardware list:', error);
        this._error.set('Failed to load hardware list');
        this._isLoading.set(false);
        return of({
          data: { cpus: [], gpus: [] },
          timestamp: Date.now()
        } as HardwareListResponse);
      })
    );
  }

  /**
   * Load detailed information for specific hardware
   */
  loadHardwareDetail(type: 'cpu' | 'gpu', id: string): Observable<any> {
    return this.http.get<any>(`${this.apiBaseUrl}/hardware-detail?type=${type}&id=${id}`).pipe(
      map(response => {
        // Handle new flat API response format
        if (response && response.success && response.hardware) {
          // Convert the new flat format to expected structure
          const convertedResponse: any = {
            hardware: response.hardware,
            // Convert flat benchmark data to processed_benchmarks format for compatibility
            processed_benchmarks: [] as any[]
          };
          
          // Add benchmark data if present
          if (response.llama) {
            const mv = response.llama;
            // Create a synthetic data point so compare views have a concrete value
            const dp: any = { group: 'median' };
            if (typeof mv['generation_token_speed'] === 'number') {
              dp.tokens_per_second_median = mv['generation_token_speed'];
            }
            if (typeof mv['prompt_token_speed'] === 'number') {
              dp.prompt_tokens_per_second_median = mv['prompt_token_speed'];
            }
            const data_points = (dp.tokens_per_second_median || dp.prompt_tokens_per_second_median) ? [dp] : [];

            convertedResponse.processed_benchmarks.push({
              benchmark_type: 'llama',
              hardware_type: type,
              data_points,
              median_values: mv,
              stats: {},
              file_count: 1,
              valid_file_count: 1
            });
          }
          
          if (response.reversan) {
            // Map depth/thread arrays into typed data_points for UI/compare
            const depth = (response.reversan.depth_times || []).map((d: any) => ({
              group: `depth_${d.depth}`,
              type: 'depth',
              depth: d.depth,
              elapsed_seconds_median: d.time,
              run_count: d.run_count ?? 1
            }));
            const threads = (response.reversan.thread_times || []).map((t: any) => ({
              group: `threads_${t.threads}`,
              type: 'threads',
              threads: t.threads,
              elapsed_seconds_median: t.time,
              run_count: t.run_count ?? 1
            }));
            convertedResponse.processed_benchmarks.push({
              benchmark_type: 'reversan',
              hardware_type: type,
              data_points: [...depth, ...threads],
              median_values: response.reversan,
              stats: {},
              file_count: 1,
              valid_file_count: 1
            });
          }
          
          if (response.blender) {
            // Map simplified per-scene medians into data_points for compare view
            const mv = response.blender;
            const scenes = ['classroom', 'junkshop', 'monster'];
            const data_points = scenes
              .filter((key: string) => typeof mv[key] === 'number')
              .map((key: string) => ({
                scene: key,
                samples_per_minute_median: mv[key],
                elapsed_seconds_median: null,
                run_count: 1
              }));

            const stats = { scenes: data_points.length } as any;

            convertedResponse.processed_benchmarks.push({
              benchmark_type: 'blender',
              hardware_type: type,
              data_points,
              median_values: mv,
              stats,
              file_count: 1,
              valid_file_count: 1
            });
          }
          
          if (response['7zip']) {
            convertedResponse.processed_benchmarks.push({
              benchmark_type: '7zip',
              hardware_type: type,
              data_points: [],
              median_values: response['7zip'],
              stats: {},
              file_count: 1,
              valid_file_count: 1
            });
          }
          
          return convertedResponse;
        }
        return null;
      }),
      catchError((error: any) => {
        console.error(`Failed to load hardware detail for ${type}/${id}:`, error);
        this._error.set(`Failed to load hardware detail for ${type}/${id}`);
        return of(null);
      })
    );
  }

  // Removed loadProcessedBenchmarkData - no longer needed

  /**
   * Get hardware by ID from the loaded data
   */
  getHardwareById(id: string): HardwareSummary | null {
    return this.allHardware().find((hw: HardwareSummary) => hw.hardware.id === id) || null;
  }

  // Removed loadBenchmarkData - no longer needed

  // Removed loadChartData - no longer needed

  /**
   * Clear error state
   */
  clearError(): void {
    this._error.set(null);
  }

  /**
   * Force reload of hardware list
   */
  reload(): void {
    this.loadHardwareList().subscribe();
  }
}