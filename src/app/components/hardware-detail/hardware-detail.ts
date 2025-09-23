import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { NgbNavModule } from '@ng-bootstrap/ng-bootstrap';
import { HardwareDataService } from '../../services/hardware-data.service';
import { HardwareInfo } from '../../models/benchmark.models';
import { BenchmarkChartComponent } from '../benchmark-chart/benchmark-chart';

@Component({
  selector: 'app-hardware-detail',
  imports: [RouterLink, CommonModule, NgbNavModule, BenchmarkChartComponent],
  templateUrl: './hardware-detail.html',
  styleUrl: './hardware-detail.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class HardwareDetail implements OnInit {
  private route = inject(ActivatedRoute);
  private hardwareService = inject(HardwareDataService);

  // Component state
  hardware = signal<HardwareInfo | null>(null);
  benchmarkData = signal<{ [benchmark: string]: any }>({});
  isLoading = signal(true);
  error = signal<string | null>(null);
  activeTab = signal('overview');

  // Route parameters
  hardwareType = signal<'cpu' | 'gpu'>('cpu');
  hardwareId = signal<string>('');

  ngOnInit() {
    // Extract route parameters
    this.route.params.subscribe(params => {
      const type = params['type'] as 'cpu' | 'gpu';
      const id = params['id'] as string;
      
      this.hardwareType.set(type);
      this.hardwareId.set(id);
      
      if (type && id) {
        this.loadHardwareDetails(type, id);
      }
    });
  }

  private loadHardwareDetails(type: 'cpu' | 'gpu', id: string) {
    this.isLoading.set(true);
    this.error.set(null);

    // Load hardware detail information
    this.hardwareService.loadHardwareDetail(type, id).subscribe({
      next: (detail) => {
        this.hardware.set(detail.hardware);
        this.loadBenchmarkFiles(type, id);
      },
      error: (error) => {
        this.error.set(`Failed to load hardware details: ${error.message}`);
        this.isLoading.set(false);
      }
    });
  }

  private loadBenchmarkFiles(type: 'cpu' | 'gpu', id: string) {
    // Load only relevant benchmarks per hardware type
    const benchmarkTypes = type === 'gpu'
      ? ['llama', 'blender']
      : ['7zip', 'reversan', 'llama', 'blender'];
    const loadPromises = benchmarkTypes.map(benchmarkType => 
      this.hardwareService.loadBenchmarkFile(type, id, benchmarkType).toPromise()
    );

    Promise.all(loadPromises).then(results => {
      const benchmarkData: { [benchmark: string]: any } = {};
      
      benchmarkTypes.forEach((benchmarkType, index) => {
        if (results[index]) {
          // Extract the actual benchmark data from the nested structure
          const rawData = results[index];
          benchmarkData[benchmarkType] = rawData.data || rawData;
        }
      });
      
      this.benchmarkData.set(benchmarkData);
      this.isLoading.set(false);
    }).catch(error => {
      this.error.set('Failed to load benchmark data');
      this.isLoading.set(false);
    });
  }

  clearError() {
    this.error.set(null);
  }

  getBenchmarkTypes(): string[] {
    const types = Object.keys(this.benchmarkData());
    if (this.hardwareType() === 'gpu') {
      // Ensure only GPU-relevant benchmarks are shown
      return types.filter(t => t === 'llama' || t === 'blender');
    }
    return types;
  }

  formatHardwareName(): string {
    const hw = this.hardware();
    return hw ? `${hw.name} (${hw.type.toUpperCase()})` : 'Loading...';
  }

  getFilteredBenchmarkData(benchmarkType: string): any {
    const data = this.benchmarkData()[benchmarkType];
    if (!data) return null;

    const hardwareType = this.hardwareType();
    
    // Filter data based on hardware type
    switch (benchmarkType) {
      case 'llama':
        return hardwareType === 'cpu' ? {
          meta: data.meta,
          build: data.build,
          runs_cpu: data.runs_cpu
        } : {
          meta: data.meta,
          build: data.build,
          runs_gpu: data.runs_gpu
        };
      
      case 'blender':
        return {
          meta: data.meta,
          build: data.build,
          device_runs: data.device_runs?.filter((run: any) => 
            hardwareType === 'cpu' ? 
              run.device_framework === 'CPU' : 
              run.device_framework !== 'CPU'
          )
        };
      
      case '7zip':
      case 'reversan':
        // These are primarily CPU benchmarks
        return hardwareType === 'cpu' ? data : {
          meta: data.meta,
          note: `${benchmarkType} is primarily a CPU benchmark. GPU performance data not available.`
        };
      
      default:
        return data;
    }
  }

  getBenchmarkSummary(benchmarkType: string): any {
    const data = this.getFilteredBenchmarkData(benchmarkType);
    if (!data) return null;

    const hardwareType = this.hardwareType();
    
    switch (benchmarkType) {
      case 'llama':
        return this.summarizeLlamaBenchmark(data);
      case 'blender':
        return this.summarizeBlenderBenchmark(data);
      case '7zip':
        return this.summarize7zipBenchmark(data);
      case 'reversan':
        return this.summarizeReversanBenchmark(data);
      default:
        return null;
    }
  }

  private summarizeLlamaBenchmark(data: any) {
    // Data structure contains either runs_cpu or runs_gpu depending on current hardware type
    const runs = Array.isArray(data.runs_cpu) ? data.runs_cpu : Array.isArray(data.runs_gpu) ? data.runs_gpu : [];
    if (!runs || runs.length === 0) {
      return null;
    }
    const first = runs[0];
    const m = first.metrics || {};
    // Try multiple possible token/sec metric keys; fall back to computed tokens/elapsed
    const promptTokensPerSecond =
      (typeof m.prompt_tokens_per_second === 'number' && m.prompt_tokens_per_second) ||
      (typeof m.tokens_per_second === 'number' && m.tokens_per_second) ||
      (typeof m.eval_tokens_per_second === 'number' && m.eval_tokens_per_second) ||
      (typeof m.decode_tokens_per_second === 'number' && m.decode_tokens_per_second) ||
      (first.generation_size && first.elapsed_seconds ? first.generation_size / first.elapsed_seconds : null);

    const totalTokens =
      (typeof m.prompt_n === 'number' && m.prompt_n) ||
      (typeof m.n_tokens_generated === 'number' && m.n_tokens_generated) ||
      (typeof first.prompt_size === 'number' && typeof first.generation_size === 'number'
        ? first.prompt_size + first.generation_size
        : null);

    return {
      type: Array.isArray(data.runs_cpu) ? 'CPU' : 'GPU',
      promptSize: first.prompt_size ?? null,
      generationSize: first.generation_size ?? null,
      elapsedSeconds: first.elapsed_seconds ?? null,
      tokensPerSecond: promptTokensPerSecond ?? null,
      totalTokens: totalTokens ?? null
    };
  }

  private summarizeBlenderBenchmark(data: any) {
    const deviceRuns = data.device_runs || [];
    if (!deviceRuns || deviceRuns.length === 0) return null;

    // Grab device details from the first run
    const firstRun = deviceRuns[0];

    // Aggregate average samples per minute across all scenes of all runs
    let totalSpm = 0;
    let spmCount = 0;
    for (const run of deviceRuns) {
      if (Array.isArray(run.raw_json)) {
        for (const entry of run.raw_json) {
          const spm = entry?.stats?.samples_per_minute;
          if (typeof spm === 'number') {
            totalSpm += spm;
            spmCount += 1;
          }
        }
      }
    }
    const avgSamplesPerMinute = spmCount > 0 ? totalSpm / spmCount : null;
    const totalElapsed = deviceRuns.reduce((sum: number, r: any) => sum + (r.elapsed_seconds || 0), 0);

    return {
      deviceName: firstRun.device_name ?? null,
      framework: firstRun.device_framework ?? null,
      scenesCount: Array.isArray(data.scenes_tested) ? data.scenes_tested.length : (firstRun.scenes?.length ?? null),
      elapsedSeconds: totalElapsed || null,
      totalScore: avgSamplesPerMinute ?? null
    };
  }

  private summarize7zipBenchmark(data: any) {
    const runs = Array.isArray(data.runs) ? data.runs : [];
    if (runs.length === 0) return null;

    // Best run is the one with minimal elapsed_seconds
    const validRuns = runs.filter((r: any) => typeof r.elapsed_seconds === 'number');
    if (validRuns.length === 0) return null;
    const bestRun = validRuns.reduce((best: any, curr: any) => (curr.elapsed_seconds < best.elapsed_seconds ? curr : best));

    const times = validRuns.map((r: any) => r.elapsed_seconds);
    const averageTime = times.reduce((sum: number, t: number) => sum + t, 0) / times.length;

    const threadData = validRuns
      .map((r: any) => ({
        threads: r.threads,
        time: r.elapsed_seconds,
        efficiency: typeof r.thread_efficiency_percent === 'number' ? r.thread_efficiency_percent : null
      }))
      .sort((a: any, b: any) => a.threads - b.threads);

    return {
      testDataSizeMB: typeof data.test_data_size_mb === 'number' ? data.test_data_size_mb : null,
      bestTime: bestRun.elapsed_seconds,
      bestThreads: bestRun.threads,
      archiveSize: bestRun.archive_size_bytes ?? null,
      compressionRatio: typeof bestRun.compression_ratio === 'number' ? bestRun.compression_ratio : null,
      totalRuns: runs.length,
      averageTime,
      threadData
    };
  }

  private summarizeReversanBenchmark(data: any) {
    const runsDepth = Array.isArray(data.runs_depth) ? data.runs_depth : [];
    const runsThreads = Array.isArray(data.runs_threads) ? data.runs_threads : [];

    const pickElapsed = (metrics: any) => {
      const e = metrics?.elapsed_seconds;
      const u = metrics?.user_seconds;
      if (typeof e === 'number') return e;
      if (typeof u === 'number') return u;
      return null;
    };

    const depthData = runsDepth
      .map((run: any) => ({
        depth: run.depth,
        elapsedSeconds: pickElapsed(run.metrics),
      }))
      .filter((d: any) => typeof d.elapsedSeconds === 'number')
      .sort((a: any, b: any) => a.depth - b.depth);

    const threadData = runsThreads
      .map((run: any) => ({
        threads: run.threads,
        elapsedSeconds: pickElapsed(run.metrics),
      }))
      .filter((d: any) => typeof d.elapsedSeconds === 'number')
      .sort((a: any, b: any) => a.threads - b.threads);

    const bestDepthTime = depthData.length > 0 ? Math.min(...depthData.map((d: any) => d.elapsedSeconds)) : null;
    const bestThreadTime = threadData.length > 0 ? Math.min(...threadData.map((d: any) => d.elapsedSeconds)) : null;

    return {
      depthTests: runsDepth.length,
      threadTests: runsThreads.length,
      buildTime: typeof data.build?.build_time_seconds === 'number' ? data.build.build_time_seconds : null,
      bestDepthTime,
      bestThreadTime,
      depthData,
      threadData
    };
  }
}
