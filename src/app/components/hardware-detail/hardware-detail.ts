import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { CommonModule } from '@angular/common';
import { NgbNavModule } from '@ng-bootstrap/ng-bootstrap';
import { HardwareDataService } from '../../services/hardware-data.service';
import { HardwareInfo, ProcessedBenchmarkData } from '../../models/benchmark.models';
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
  processedBenchmarkData = signal<ProcessedBenchmarkData[]>([]);
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
    // Load processed benchmark data
    this.hardwareService.loadProcessedBenchmarkData(type, id).subscribe({
      next: (processedData) => {
        console.log("Processed benchmark data:", processedData);
        this.processedBenchmarkData.set(processedData);
        this.isLoading.set(false);
      },
      error: (error) => {
        console.error('Failed to load processed benchmark data:', error);
        this.error.set('Failed to load benchmark data');
        this.isLoading.set(false);
      }
    });
  }

  clearError() {
    this.error.set(null);
  }

  getBenchmarkTypes(): string[] {
    const processedData = this.processedBenchmarkData();
    const types = processedData.map(d => d.benchmark_type);
    
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

  getProcessedBenchmarkData(benchmarkType: string): ProcessedBenchmarkData | null {
    const processedData = this.processedBenchmarkData();
    return processedData.find(d => d.benchmark_type === benchmarkType) || null;
  }

  // Legacy method for backward compatibility - now returns processed data
  getFilteredBenchmarkData(benchmarkType: string): any {
    const processedData = this.getProcessedBenchmarkData(benchmarkType);
    if (!processedData) {
      return null;
    }

    // Convert processed data back to a format similar to the old structure
    // for compatibility with existing templates
    const result: any = {
      benchmark_type: processedData.benchmark_type,
      data_points: processedData.data_points,
      median_values: processedData.median_values,
      stats: processedData.stats,
      file_count: processedData.file_count
    };

    // Add legacy structure mappings for specific benchmark types
    switch (benchmarkType) {
      case 'llama':
        if (this.hardwareType() === 'cpu') {
          // Map to old structure for CPU
          result.build_time_seconds = processedData.median_values['build_time_seconds'];
          result.runs_cpu = processedData.data_points.map(dp => ({
            group: dp.group,
            tokens_per_second: (dp as any).tokens_per_second_median,
            elapsed_seconds: (dp as any).elapsed_seconds_median,
            total_tokens: (dp as any).total_tokens_median,
            prompt_size: (dp as any).prompt_size_median,
            generation_size: (dp as any).generation_size_median,
            run_count: dp.run_count
          }));
        } else {
          // Map to old structure for GPU
          result.runs_gpu = processedData.data_points.map(dp => ({
            group: dp.group,
            tokens_per_second: (dp as any).tokens_per_second_median,
            elapsed_seconds: (dp as any).elapsed_seconds_median,
            total_tokens: (dp as any).total_tokens_median,
            prompt_size: (dp as any).prompt_size_median,
            generation_size: (dp as any).generation_size_median,
            run_count: dp.run_count
          }));
        }
        break;
      
      case 'blender':
        result.device_runs = processedData.data_points.map(dp => ({
          scene_name: (dp as any).scene,
          device_name: (dp as any).device,
          elapsed_seconds: null, // Not available in new structure
          samples_per_minute: (dp as any)['samples_per_minute_median'],
          run_count: dp.run_count
        }));
        break;
      
      case '7zip':
        result.runs = processedData.data_points.map(dp => ({
          threads: dp.thread_count,
          elapsed_seconds: (dp as any)['elapsed_seconds_median'],
          compression_speed_mb_s: (dp as any)['compression_speed_mb_s_median'],
          compression_ratio: (dp as any)['compression_ratio_median'],
          thread_efficiency_percent: (dp as any)['thread_efficiency_percent_median'],
          run_count: dp.run_count
        }));
        break;
      
      case 'reversan':
        const depth_runs = processedData.data_points
          .filter(dp => dp.type === 'depth')
          .map(dp => ({
            depth: dp.depth,
            // Prefer user_seconds if present (more precise), else elapsed_seconds
            user_seconds: (dp as any)['user_seconds_median'],
            elapsed_seconds: (dp as any)['elapsed_seconds_median'],
            run_count: dp.run_count
          }));
        
        const thread_runs = processedData.data_points
          .filter(dp => dp.type === 'threads')
          .map(dp => ({
            threads: dp.threads,
            user_seconds: (dp as any)['user_seconds_median'],
            elapsed_seconds: (dp as any)['elapsed_seconds_median'],
            run_count: dp.run_count
          }));
        
        result.runs_depth = depth_runs;
        result.runs_threads = thread_runs;
        result.build = { build_time_seconds: processedData.median_values['build_time_seconds'] };
        break;
    }

    return result;
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
    // Use processed data directly from data_points
    const processedData = data.data_points || [];
    if (processedData.length === 0) return null;

    // Since data_points are already medians, extract the values directly
    const tokensPerSecValues = processedData.map((r: any) => r.tokens_per_second_median).filter((v: any) => typeof v === 'number');
    const elapsedValues = processedData.map((r: any) => r.elapsed_seconds_median).filter((v: any) => typeof v === 'number');
    const totalTokensVals = processedData.map((r: any) => r.total_tokens_median).filter((v: any) => typeof v === 'number');
    const promptSizes = processedData.map((r: any) => r.prompt_size_median).filter((v: any) => typeof v === 'number');
    const genSizes = processedData.map((r: any) => r.generation_size_median).filter((v: any) => typeof v === 'number');

    return {
      type: this.hardwareType() === 'cpu' ? 'CPU' : 'GPU',
      promptSize: this.hardwareService.median(promptSizes),
      generationSize: this.hardwareService.median(genSizes),
      elapsedSeconds: this.hardwareService.median(elapsedValues),
      tokensPerSecond: this.hardwareService.median(tokensPerSecValues),
      totalTokens: this.hardwareService.median(totalTokensVals),
      compileTimeSeconds: this.hardwareType() === 'cpu' ? (data.median_values?.build_time_seconds || null) : null,
      gpuSelection: data.median_values?.gpu_selection || null
    };
  }

  private summarizeBlenderBenchmark(data: any) {
    // Use processed data_points which now contain scene-specific results
    const dataPoints = data.data_points || [];
    if (dataPoints.length === 0) return null;

    // Extract scene scores and overall info
    const sceneScores: any[] = [];
    let deviceName = null;
    let framework = null;
    let totalElapsedTime = 0;
    let hasValidTimes = false;
    
    for (const point of dataPoints) {
      const elapsedTime = point.elapsed_seconds_median;
      sceneScores.push({
        scene: point.scene,
        samplesPerMinute: point.samples_per_minute_median,
        elapsedSeconds: elapsedTime,
        runCount: point.run_count
      });
      
      // Accumulate total time if available
      if (elapsedTime && typeof elapsedTime === 'number') {
        totalElapsedTime += elapsedTime;
        hasValidTimes = true;
      }
      
      // Get device info from first point
      if (!deviceName && point.device) {
        const deviceParts = point.device.split('_', 2);
        if (deviceParts.length >= 2) {
          framework = deviceParts[0];
          deviceName = deviceParts[1];
        }
      }
    }
    
    // Get scenes count from stats
    const scenesCount = data.stats?.scenes || sceneScores.length;

    return {
      deviceName: deviceName,
      framework: framework,
      scenesCount: scenesCount,
      elapsedSeconds: hasValidTimes ? totalElapsedTime : null,
      sceneScores: sceneScores,
      // Remove totalScore - it doesn't make sense for Blender which has scene-specific scores
    };
  }

  private summarize7zipBenchmark(data: any) {
    // For processed data, use data_points directly
    if (data.data_points && Array.isArray(data.data_points)) {
      const dataPoints = data.data_points.filter((dp: any) => 
        typeof dp.elapsed_seconds_median === 'number' && 
        typeof dp.thread_count === 'number'
      );
      
      if (dataPoints.length === 0) return null;

      // Find the best time (lowest elapsed_seconds_median)
      const bestPoint = dataPoints.reduce((min: any, dp: any) => 
        (dp.elapsed_seconds_median < min.elapsed_seconds_median ? dp : min)
      );

      // Create threadData array for charts
      const threadData = dataPoints
        .map((dp: any) => ({
          threads: dp.thread_count,
          time: dp.elapsed_seconds_median,
          efficiency: dp.thread_efficiency_percent_median
        }))
        .sort((a: any, b: any) => a.threads - b.threads);

      const allTimes = dataPoints.map((dp: any) => dp.elapsed_seconds_median);

      return {
        testDataSizeMB: 200, // Standard 7zip test size
        bestTime: bestPoint.elapsed_seconds_median,
        bestThreads: bestPoint.thread_count,
        archiveSize: bestPoint.archive_size_bytes_median || 0,
        compressionRatio: null, // Removed from display
        totalRuns: dataPoints.reduce((sum: number, dp: any) => sum + dp.run_count, 0),
        averageTime: this.hardwareService.median(allTimes),
        threadData: threadData
      };
    }

    // Fallback for old data format
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
      archiveSize: runs[0]?.archive_size_bytes || 0,
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

    const pickElapsedFromRun = (run: any) => {
      // Support both raw (metrics:{...}) and processed legacy mapping (user_seconds/elapsed_seconds at top level)
      if (run && typeof run === 'object') {
        if (run.metrics) return pickElapsed(run.metrics);
        const u = (run as any).user_seconds;
        const e = (run as any).elapsed_seconds;
        if (typeof u === 'number') return u;
        if (typeof e === 'number') return e;
      }
      return null;
    };

    // Group depth runs by depth and compute median elapsed
    const depthMap = new Map<number, number[]>();
    for (const run of runsDepth) {
      const t = pickElapsedFromRun(run);
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
      const t = pickElapsedFromRun(run);
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

    // We surface depth 10 explicitly to avoid confusion; keep computing best thread below
    const bestThread = threadData.length > 0 ? threadData.reduce((min: any, d: any) => d.elapsedSeconds < min.elapsedSeconds ? d : min, threadData[0]) : null;
    const bestThreadTime = bestThread?.elapsedSeconds ?? null;
    const depth10Entry = depthData.find((d: any) => d.depth === 10);

    return {
      depthTests: runsDepth.length,
      threadTests: runsThreads.length,
      buildTime: typeof data.build?.build_time_seconds === 'number' ? data.build.build_time_seconds : null,
      bestDepthTime: depth10Entry?.elapsedSeconds ?? null,
      bestThreadTime,
      bestThreadCount: bestThread?.threads ?? null,
      depth10Time: depth10Entry?.elapsedSeconds ?? null,
      depthData,
      threadData
    };
  }
}
