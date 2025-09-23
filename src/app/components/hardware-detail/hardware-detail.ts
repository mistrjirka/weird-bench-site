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
      this.hardwareService.loadBenchmarkFiles(type, id, benchmarkType).toPromise()
    );

    Promise.all(loadPromises).then(results => {
      const benchmarkData: { [benchmark: string]: any } = {};
      console.log("benchmark data results:", results);
      benchmarkTypes.forEach((benchmarkType, index) => {
        const list = results[index] as any[];
        if (Array.isArray(list) && list.length > 0) {
          // Unwrap each entry supporting both shapes
          const contents = list
            .filter(x => !!x)
            .map(raw => (raw && (raw.data ?? raw.results)) || raw);
          benchmarkData[benchmarkType] = contents;
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
    const list = Array.isArray(data) ? data : [data];

    const hardwareType = this.hardwareType();
    
    // Filter data based on hardware type
    switch (benchmarkType) {
      case 'llama':
        if (hardwareType === 'cpu') {
          const runs = list.flatMap((d: any) => Array.isArray(d?.runs_cpu) ? d.runs_cpu : []);
          const buildTimes = list.map((d: any) => d?.build?.cpu_build_timing?.build_time_seconds).filter((v: any) => typeof v === 'number');
          return { runs_cpu: runs, build_time_seconds: this.hardwareService.median(buildTimes) };
        } else {
          const runs = list.flatMap((d: any) => Array.isArray(d?.runs_gpu) ? d.runs_gpu : []);
          // GPU compile time isn't always relevant; keep omitted for now
          return { runs_gpu: runs };
        }
      
      case 'blender':
        const device_runs = list.flatMap((d: any) => Array.isArray(d?.device_runs) ? d.device_runs : [])
          .filter((run: any) => hardwareType === 'cpu' ? run.device_framework === 'CPU' : run.device_framework !== 'CPU');
        return { device_runs };
      
      case '7zip':
      case 'reversan':
        // These are primarily CPU benchmarks
        if (hardwareType !== 'cpu') {
          return { note: `${benchmarkType} is primarily a CPU benchmark. GPU performance data not available.` };
        }
        if (benchmarkType === '7zip') {
          const runs = list.flatMap((d: any) => Array.isArray(d?.runs) ? d.runs : []);
          return { runs };
        } else {
          const runs_depth = list.flatMap((d: any) => Array.isArray(d?.runs_depth) ? d.runs_depth : []);
          const runs_threads = list.flatMap((d: any) => Array.isArray(d?.runs_threads) ? d.runs_threads : []);
          const build = list.find((d: any) => d?.build)?.build;
          return { runs_depth, runs_threads, build };
        }
      
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
    // Data may be under data or results previously; ensure correct ref already passed in
    const runs = Array.isArray(data.runs_cpu) ? data.runs_cpu : Array.isArray(data.runs_gpu) ? data.runs_gpu : [];
    if (!runs || runs.length === 0) {
      return null;
    }
    const tokensPerSecValues = runs.map((r: any) => {
      const m = r.metrics || {};
      return (
        (typeof m.prompt_tokens_per_second === 'number' && m.prompt_tokens_per_second) ||
        (typeof m.tokens_per_second === 'number' && m.tokens_per_second) ||
        (typeof m.eval_tokens_per_second === 'number' && m.eval_tokens_per_second) ||
        (typeof m.decode_tokens_per_second === 'number' && m.decode_tokens_per_second) ||
        (typeof r.generation_size === 'number' && typeof r.elapsed_seconds === 'number' ? r.generation_size / r.elapsed_seconds : null)
      );
    }).filter((v: any) => typeof v === 'number');

    const elapsedValues = runs.map((r: any) => r.elapsed_seconds).filter((v: any) => typeof v === 'number');
    const promptSizes = runs.map((r: any) => r.prompt_size).filter((v: any) => typeof v === 'number');
    const genSizes = runs.map((r: any) => r.generation_size).filter((v: any) => typeof v === 'number');
    const totalTokensVals = runs.map((r: any) => {
      const m = r.metrics || {};
      return (
        (typeof m.prompt_n === 'number' && m.prompt_n) ||
        (typeof m.n_tokens_generated === 'number' && m.n_tokens_generated) ||
        (typeof r.prompt_size === 'number' && typeof r.generation_size === 'number' ? r.prompt_size + r.generation_size : null)
      );
    }).filter((v: any) => typeof v === 'number');

    return {
      type: Array.isArray(data.runs_cpu) ? 'CPU' : 'GPU',
      promptSize: this.hardwareService.median(promptSizes),
      generationSize: this.hardwareService.median(genSizes),
      elapsedSeconds: this.hardwareService.median(elapsedValues),
      tokensPerSecond: this.hardwareService.median(tokensPerSecValues),
      totalTokens: this.hardwareService.median(totalTokensVals),
      compileTimeSeconds: typeof data.build_time_seconds === 'number' ? data.build_time_seconds : null
    };
  }

  private summarizeBlenderBenchmark(data: any) {
    const deviceRuns = data.device_runs || [];
    if (!deviceRuns || deviceRuns.length === 0) return null;

    // Grab device details from the first run
    const firstRun = deviceRuns[0];

    // Aggregate samples per minute across all scenes of all runs, then compute median
    const spmValues: number[] = [];
    for (const run of deviceRuns) {
      let entries: any[] = Array.isArray(run.raw_json) ? run.raw_json : [];
      if ((!entries || entries.length === 0) && typeof run.raw_output === 'string') {
        try {
          const parsed = JSON.parse(run.raw_output);
          if (Array.isArray(parsed)) entries = parsed;
        } catch {
          // ignore parse errors
        }
      }
      if (Array.isArray(entries)) {
        for (const entry of entries) {
          const spm = entry?.stats?.samples_per_minute;
          if (typeof spm === 'number') spmValues.push(spm);
        }
      }
    }
  const medianSpm = this.hardwareService.median(spmValues);
  const elapsedValues = deviceRuns.map((r: any) => r.elapsed_seconds).filter((v: any) => typeof v === 'number');
  const medianElapsed = this.hardwareService.median(elapsedValues);

    return {
      deviceName: firstRun.device_name ?? null,
      framework: firstRun.device_framework ?? null,
      scenesCount: Array.isArray(data.scenes_tested) ? data.scenes_tested.length : (firstRun.scenes?.length ?? null),
      elapsedSeconds: medianElapsed,
      totalScore: medianSpm
    };
  }

  private summarize7zipBenchmark(data: any) {
    const runs = Array.isArray(data.runs) ? data.runs : [];
    if (runs.length === 0) return null;

    const validRuns = runs.filter((r: any) => typeof r.elapsed_seconds === 'number' && typeof r.threads === 'number');
    if (validRuns.length === 0) return null;

    // Group by threads and compute median time/efficiency per thread count
    const groups = new Map<number, { times: number[]; effs: number[] }>();
    for (const r of validRuns) {
      const g = groups.get(r.threads) || { times: [], effs: [] };
      g.times.push(r.elapsed_seconds);
      if (typeof r.thread_efficiency_percent === 'number') g.effs.push(r.thread_efficiency_percent);
      groups.set(r.threads, g);
    }
    const threadData = Array.from(groups.entries())
      .map(([threads, g]) => ({
        threads,
        time: this.hardwareService.median(g.times),
        efficiency: this.hardwareService.median(g.effs)
      }))
      .filter(d => typeof d.time === 'number')
      .sort((a, b) => a.threads - b.threads);

    const best = threadData.reduce((min, d) => (d.time! < min.time! ? d : min));
  const allTimes = validRuns.map((r: any) => r.elapsed_seconds);

    return {
      testDataSizeMB: typeof (runs[0]?.test_data_size_mb) === 'number' ? runs[0].test_data_size_mb : null,
      bestTime: best.time,
      bestThreads: best.threads,
      archiveSize: null,
      compressionRatio: null,
      totalRuns: runs.length,
      averageTime: this.hardwareService.median(allTimes),
      threadData
    };
  }

  private summarizeReversanBenchmark(data: any) {
    const runsDepth = Array.isArray(data.runs_depth) ? data.runs_depth : [];
    const runsThreads = Array.isArray(data.runs_threads) ? data.runs_threads : [];

    const pickElapsed = (metrics: any) => {
      const u = metrics?.user_seconds;
      const e = metrics?.elapsed_seconds;
      // Prefer user_seconds as it contains more precise decimal values
      if (typeof u === 'number') return u;
      if (typeof e === 'number') return e;
      return null;
    };

    // Group depth runs by depth and compute median elapsed
    const depthMap = new Map<number, number[]>();
    for (const run of runsDepth) {
      const t = pickElapsed(run.metrics);
      if (typeof run.depth === 'number' && typeof t === 'number') {
        const arr = depthMap.get(run.depth) || [];
        arr.push(t);
        depthMap.set(run.depth, arr);
      }
    }
    
    const depthData = Array.from(depthMap.entries())
      .map(([depth, vals]) => ({ depth, elapsedSeconds: this.hardwareService.median(vals) }))
      .filter((d: any) => typeof d.elapsedSeconds === 'number')
      .sort((a: any, b: any) => a.depth - b.depth);

    const threadMap = new Map<number, number[]>();
    for (const run of runsThreads) {
      const t = pickElapsed(run.metrics);
      if (typeof run.threads === 'number' && typeof t === 'number') {
        const arr = threadMap.get(run.threads) || [];
        arr.push(t);
        threadMap.set(run.threads, arr);
      }
    }
    
    const threadData = Array.from(threadMap.entries())
      .map(([threads, vals]) => ({ threads, elapsedSeconds: this.hardwareService.median(vals) }))
      .filter((d: any) => typeof d.elapsedSeconds === 'number')
      .sort((a: any, b: any) => a.threads - b.threads);

    const bestDepthTime = depthData.length > 0 ? Math.min(...depthData.map((d: any) => d.elapsedSeconds)) : null;
    const bestThread = threadData.length > 0 ? threadData.reduce((min: any, d: any) => d.elapsedSeconds < min.elapsedSeconds ? d : min, threadData[0]) : null;
    const bestThreadTime = bestThread?.elapsedSeconds ?? null;
    const depth10Entry = depthData.find((d: any) => d.depth === 10);

    return {
      depthTests: runsDepth.length,
      threadTests: runsThreads.length,
      buildTime: typeof data.build?.build_time_seconds === 'number' ? data.build.build_time_seconds : null,
      bestDepthTime,
      bestThreadTime,
      bestThreadCount: bestThread?.threads ?? null,
      depth10Time: depth10Entry?.elapsedSeconds ?? null,
      depthData,
      threadData
    };
  }
}
