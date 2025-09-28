import { Component, ChangeDetectionStrategy, computed, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ComparisonService } from '../../services/comparison.service';
import { HardwareDataService } from '../../services/hardware-data.service';
import { ProcessedBenchmarkData } from '../../models/benchmark.models';
import { forkJoin } from 'rxjs';

type BenchName = 'llama' | 'blender' | '7zip' | 'reversan';

@Component({
  selector: 'app-compare',
  imports: [CommonModule],
  templateUrl: './compare.html',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class CompareComponent implements OnInit {
  private compare = inject(ComparisonService);
  private data = inject(HardwareDataService);
  private router = inject(Router);

  readonly type = computed(() => this.compare.selectedType());
  readonly ids = computed(() => this.compare.selectedIds());

  readonly leftId = computed(() => this.ids()[0] ?? '');
  readonly rightId = computed(() => this.ids()[1] ?? '');

  readonly leftName = signal<string>('');
  readonly rightName = signal<string>('');

  // Map of benchmark_type -> processed data
  readonly leftBench = signal<Record<string, ProcessedBenchmarkData>>({});
  readonly rightBench = signal<Record<string, ProcessedBenchmarkData>>({});

  readonly details = computed(() => this.computeDetails());
  readonly summary = computed(() => this.computeSummary());

  ngOnInit(): void {
    if (!this.compare.isReady()) return;
    const type = this.type()!;
    const [a, b] = this.ids();

    // Load names from index
    const leftSummary = this.data.getHardwareById(a);
    const rightSummary = this.data.getHardwareById(b);
    this.leftName.set(leftSummary?.hardware.name ?? a);
    this.rightName.set(rightSummary?.hardware.name ?? b);

    // Load processed benchmark data for both sides using hardware-detail API
    forkJoin([
      this.data.loadHardwareDetail(type, a),
      this.data.loadHardwareDetail(type, b)
  ]).subscribe(([leftDetail, rightDetail]: any[]) => {
      const leftMap: Record<string, ProcessedBenchmarkData> = {};
      const rightMap: Record<string, ProcessedBenchmarkData> = {};
      const leftPb = (leftDetail?.processed_benchmarks ?? []) as ProcessedBenchmarkData[];
      const rightPb = (rightDetail?.processed_benchmarks ?? []) as ProcessedBenchmarkData[];
      leftPb.forEach(d => { if (d && d.benchmark_type) leftMap[d.benchmark_type] = d; });
      rightPb.forEach(d => { if (d && d.benchmark_type) rightMap[d.benchmark_type] = d; });
      this.leftBench.set(leftMap);
      this.rightBench.set(rightMap);
    });
  }

  clearAndBack() {
    this.compare.clear();
    this.router.navigateByUrl('/hardware');
  }

  private computeDetails(): Array<{ name: string; left: number; right: number; unit: string; improvement: number; higherIsBetter: boolean; weight?: number }>
  {
    const result: Array<{ name: string; left: number; right: number; unit: string; improvement: number; higherIsBetter: boolean; weight?: number }> = [];
    const type = this.type();
    if (!type) return result;
    const left = this.leftBench();
    const right = this.rightBench();

    const candidates: BenchName[] = (Object.keys(left).filter(k => right[k]) as BenchName[]);
    for (const name of candidates) {
      if (name === 'reversan') {
        // Compare depth groups using time (lower is better)
        // Only include depths where both CPUs have results > 0.1s
        const leftDepth = this.reversanDepthTimeMap(left[name]);
        const rightDepth = this.reversanDepthTimeMap(right[name]);
        const depths = Array.from(new Set([...leftDepth.keys(), ...rightDepth.keys()])).sort((a, b) => a - b);
        const validDepths = depths.filter(d => {
          const lv = leftDepth.get(d);
          const rv = rightDepth.get(d);
          return lv && rv && lv > 0.1 && rv > 0.1;
        });
        
        const weightPerDepth = validDepths.length > 0 ? 1 / validDepths.length : 0;
        for (const d of validDepths) {
          const lv = leftDepth.get(d)!;
          const rv = rightDepth.get(d)!;
          const improvement = this.percentImprovement(lv, rv, false);
          result.push({ 
            name: `reversan depth ${d}`, 
            left: lv, 
            right: rv, 
            unit: 's', 
            improvement, 
            higherIsBetter: false,
            weight: weightPerDepth
          });
        }
        // Best thread group (min seconds) - weight 1
        const lbest = this.reversanBestThreadsTime(left[name]);
        const rbest = this.reversanBestThreadsTime(right[name]);
        if (lbest && rbest) {
          const improvement = this.percentImprovement(lbest.value, rbest.value, false);
          result.push({
            name: `reversan best threads (L: ${lbest.threads}, R: ${rbest.threads})`,
            left: lbest.value,
            right: rbest.value,
            unit: 's',
            improvement,
            higherIsBetter: false,
            weight: 1
          });
        }
        continue;
      }
      
      // Add individual scene comparisons for Blender (both CPU and GPU)
      if (name === 'blender') {
        const leftScenes = this.blenderSceneMap(left[name]);
        const rightScenes = this.blenderSceneMap(right[name]);
        const commonScenes = Array.from(leftScenes.keys()).filter(s => rightScenes.has(s));
        
        const weightPerScene = commonScenes.length > 0 ? 1 / commonScenes.length : 0;
        for (const scene of commonScenes) {
          const lv = leftScenes.get(scene)!;
          const rv = rightScenes.get(scene)!;
          const improvement = this.percentImprovement(lv, rv, true);
          result.push({ 
            name: `blender ${scene}`, 
            left: lv, 
            right: rv, 
            unit: 'SPM', 
            improvement, 
            higherIsBetter: true,
            weight: weightPerScene
          });
        }
        continue;
      }
      if (name === 'llama') {
        if (type === 'cpu') {
          // CPU: token speed and compile time
          const leftTps = this.llamaTokenSpeed(left[name]);
          const rightTps = this.llamaTokenSpeed(right[name]);
          if (leftTps !== null && rightTps !== null) {
            const improvement = this.percentImprovement(leftTps, rightTps, true);
            result.push({ name: 'llama token speed', left: leftTps, right: rightTps, unit: 'tok/s', improvement, higherIsBetter: true, weight: 1 });
          }
          
          const lc = this.llamaCompile(left[name]);
          const rc = this.llamaCompile(right[name]);
          if (lc !== null && rc !== null) {
            const improvement = this.percentImprovement(lc, rc, false);
            result.push({ name: 'llama compile', left: lc, right: rc, unit: 's', improvement, higherIsBetter: false, weight: 1 });
          }
        } else {
          // GPU: prompt speed and generation speed
          const leftPrompt = this.llamaPromptSpeed(left[name]);
          const rightPrompt = this.llamaPromptSpeed(right[name]);
          if (leftPrompt !== null && rightPrompt !== null) {
            const improvement = this.percentImprovement(leftPrompt, rightPrompt, true);
            result.push({ name: 'llama prompt speed', left: leftPrompt, right: rightPrompt, unit: 'tok/s', improvement, higherIsBetter: true, weight: 1 });
          }
          
          const leftGen = this.llamaGenerationSpeed(left[name]);
          const rightGen = this.llamaGenerationSpeed(right[name]);
          if (leftGen !== null && rightGen !== null) {
            const improvement = this.percentImprovement(leftGen, rightGen, true);
            result.push({ name: 'llama generation speed', left: leftGen, right: rightGen, unit: 'tok/s', improvement, higherIsBetter: true, weight: 1 });
          }
        }
        continue;
      }
      const leftVal = this.extractMetric(name, left[name]);
      const rightVal = this.extractMetric(name, right[name]);
      if (!leftVal || !rightVal) continue;
      const { value: lv, unit, higherIsBetter } = leftVal;
      const { value: rv } = rightVal;
      const improvement = this.percentImprovement(lv, rv, higherIsBetter);
      result.push({ name, left: lv, right: rv, unit, improvement, higherIsBetter, weight: 1 });
    }
    return result;
  }

  private computeSummary(): { headline: string; average: number } | null {
    const rowsAll = this.details();
    const rows = rowsAll;
    if (rows.length === 0) return null;
    
    // Calculate weighted average if weights are provided, otherwise equal weights
    let totalImprovement = 0;
    let totalWeight = 0;
    
    for (const row of rows) {
      const weight = row.weight ?? 1; // Default weight of 1 if not specified
      totalImprovement += row.improvement * weight;
      totalWeight += weight;
    }
    
    const avg = totalWeight > 0 ? totalImprovement / totalWeight : 0;
    const better = avg > 0 ? 'faster' : 'slower';
    const left = this.leftName();
    const right = this.rightName();
    const headline = `All tests delta: ${right} is ${Math.abs(avg).toFixed(1)}% ${better} than ${left} on average across ${rows.length} test(s)`;
    return { headline, average: avg };
  }
  private extractMetric(name: BenchName, data: ProcessedBenchmarkData)
    : { value: number; unit: string; higherIsBetter: boolean } | null {
    switch (name) {
      case 'blender': {
        // Compare each scene individually with weight 1/number_of_scenes
        const rightData = this.rightBench()[name];
        if (!rightData) return null;
        
        const leftScenes = this.blenderSceneMap(data);
        const rightScenes = this.blenderSceneMap(rightData);
        if (leftScenes.size === 0 || rightScenes.size === 0) return null;
        
        const commonScenes = Array.from(leftScenes.keys()).filter(s => rightScenes.has(s));
        if (commonScenes.length === 0) return null;
        
        // For overall metric, use median across common scenes
        const leftVals = commonScenes.map(s => leftScenes.get(s)!);
        const rightVals = commonScenes.map(s => rightScenes.get(s)!);
        const leftMedian = this.data.median(leftVals);
        const rightMedian = this.data.median(rightVals);
        if (typeof leftMedian !== 'number' || typeof rightMedian !== 'number') return null;
        
        return { value: leftMedian, unit: 'SPM', higherIsBetter: true };
      }
      case '7zip': {
        // Use best (lowest) compression time across thread groups (lower is better)
        // This compares the fastest compression time each CPU can achieve
        const vals = (data.data_points || []).map(dp => (dp as any)['elapsed_seconds_median']).filter((v: any) => typeof v === 'number');
        if (!vals.length) return null;
        const v = Math.min(...vals);
        return { value: v, unit: 's', higherIsBetter: false };
      }
      case 'reversan': {
        // Use depth 10 time as representative metric if present, else median time across depths (lower is better)
        const depthMap = this.reversanDepthTimeMap(data);
        if (depthMap.size === 0) return null;
        const d10 = depthMap.get(10);
        if (typeof d10 === 'number') return { value: d10, unit: 's', higherIsBetter: false };
        const vals = Array.from(depthMap.values()).filter(v => typeof v === 'number') as number[];
        const v = this.data.median(vals);
        if (typeof v !== 'number') return null;
        return { value: v, unit: 's', higherIsBetter: false };
      }
      default:
        return null;
    }
  }

  private reversanDepthTimeMap(data: ProcessedBenchmarkData): Map<number, number> {
    const depthMap = new Map<number, number>();
    for (const dp of data.data_points || []) {
      if (dp.type === 'depth' && typeof (dp as any).depth === 'number') {
        const u = (dp as any)['user_seconds_median'];
        const e = (dp as any)['elapsed_seconds_median'];
        const t = typeof u === 'number' ? u : (typeof e === 'number' ? e : null);
        if (typeof t === 'number') depthMap.set((dp as any).depth, t);
      }
    }
    return depthMap;
  }

  private reversanBestThreadsTime(data: ProcessedBenchmarkData): { threads: number; value: number } | null {
    let best: { threads: number; value: number } | null = null;
    for (const dp of data.data_points || []) {
      if (dp.type === 'threads' && typeof (dp as any).threads === 'number') {
        const u = (dp as any)['user_seconds_median'];
        const e = (dp as any)['elapsed_seconds_median'];
        const t = typeof u === 'number' ? u : (typeof e === 'number' ? e : null);
        if (typeof t === 'number') {
          if (!best || t < best.value) {
            best = { threads: (dp as any).threads, value: t };
          }
        }
      }
    }
    return best;
  }

  private llamaCompile(data: ProcessedBenchmarkData): number | null {
    const t = data.median_values?.['compilation_time'];
    return typeof t === 'number' ? t : null;
  }

  private llamaTokenSpeed(data: ProcessedBenchmarkData): number | null {
    const vals = (data.data_points || []).map(dp => dp.tokens_per_second_median).filter((v: any) => typeof v === 'number');
    const v = this.data.median(vals);
    return typeof v === 'number' ? v : null;
  }

  private llamaPromptSpeed(data: ProcessedBenchmarkData): number | null {
    const t = data.median_values?.['prompt_token_speed'];
    return typeof t === 'number' ? t : null;
  }

  private llamaGenerationSpeed(data: ProcessedBenchmarkData): number | null {
    const t = data.median_values?.['generation_token_speed'];
    return typeof t === 'number' ? t : null;
  }

  private blenderSceneMap(data: ProcessedBenchmarkData): Map<string, number> {
    const sceneMap = new Map<string, number>();
    for (const dp of data.data_points || []) {
      const scene = (dp as any).scene;
      const spm = (dp as any).samples_per_minute_median;
      if (typeof scene === 'string' && typeof spm === 'number') {
        sceneMap.set(scene, spm);
      }
    }
    return sceneMap;
  }

  private percentImprovement(left: number, right: number, higherIsBetter: boolean): number {
    if (higherIsBetter) {
      // percent change from left to right where higher is better
      return ((right - left) / left) * 100;
    } else {
      // lower is better: invert
      return ((left - right) / left) * 100;
    }
  }
}
