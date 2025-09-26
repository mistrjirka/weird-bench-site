import { Component, ChangeDetectionStrategy, computed, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ComparisonService } from '../../services/comparison.service';
import { HardwareDataService } from '../../services/hardware-data.service';
import { ProcessedBenchmarkData } from '../../models/benchmark.models';

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

    // Load processed benchmark data for both sides
    Promise.all([
      this.data.loadProcessedBenchmarkData(type, a).toPromise(),
      this.data.loadProcessedBenchmarkData(type, b).toPromise()
    ]).then(([la, lb]) => {
      const leftMap: Record<string, ProcessedBenchmarkData> = {};
      const rightMap: Record<string, ProcessedBenchmarkData> = {};
      (la || []).forEach(d => { leftMap[d.benchmark_type] = d; });
      (lb || []).forEach(d => { rightMap[d.benchmark_type] = d; });
      this.leftBench.set(leftMap);
      this.rightBench.set(rightMap);
    });
  }

  clearAndBack() {
    this.compare.clear();
    this.router.navigateByUrl('/hardware');
  }

  private computeDetails(): Array<{ name: string; left: number; right: number; unit: string; improvement: number; higherIsBetter: boolean }>
  {
    const result: Array<{ name: string; left: number; right: number; unit: string; improvement: number; higherIsBetter: boolean }> = [];
    const type = this.type();
    if (!type) return result;
    const left = this.leftBench();
    const right = this.rightBench();

    const candidates: BenchName[] = (Object.keys(left).filter(k => right[k]) as BenchName[]);
    for (const name of candidates) {
      if (name === 'reversan') {
        // Compare depth groups using time (lower is better)
        const leftDepth = this.reversanDepthTimeMap(left[name]);
        const rightDepth = this.reversanDepthTimeMap(right[name]);
        const depths = Array.from(new Set([...leftDepth.keys(), ...rightDepth.keys()])).sort((a, b) => a - b);
        const common = depths.filter(d => leftDepth.has(d) && rightDepth.has(d));
        for (const d of common) {
          const lv = leftDepth.get(d)!;
          const rv = rightDepth.get(d)!;
          const improvement = this.percentImprovement(lv, rv, false);
          result.push({ name: `reversan depth ${d}`, left: lv, right: rv, unit: 's', improvement, higherIsBetter: false });
        }
        // Best thread group (min seconds)
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
            higherIsBetter: false
          });
        }
        continue;
      }
      if (name === 'llama' && type === 'cpu') {
        const lc = this.llamaCompile(left[name]);
        const rc = this.llamaCompile(right[name]);
        if (lc !== null && rc !== null) {
          const improvement = this.percentImprovement(lc, rc, false);
          result.push({ name: 'llama compile', left: lc, right: rc, unit: 's', improvement, higherIsBetter: false });
        }
      }
      const leftVal = this.extractMetric(name, left[name]);
      const rightVal = this.extractMetric(name, right[name]);
      if (!leftVal || !rightVal) continue;
      const { value: lv, unit, higherIsBetter } = leftVal;
      const { value: rv } = rightVal;
      const improvement = this.percentImprovement(lv, rv, higherIsBetter);
      result.push({ name, left: lv, right: rv, unit, improvement, higherIsBetter });
    }
    return result;
  }

  private computeSummary(): { headline: string; average: number } | null {
    const rowsAll = this.details();
    const rows = rowsAll;
    if (rows.length === 0) return null;
    const avg = rows.reduce((s, r) => s + r.improvement, 0) / rows.length;
    const better = avg > 0 ? 'faster' : 'slower';
    const left = this.leftName();
    const right = this.rightName();
    const headline = `All tests delta: ${right} is ${Math.abs(avg).toFixed(1)}% ${better} than ${left} on average across ${rows.length} test(s)`;
    return { headline, average: avg };
  }
  private extractMetric(name: BenchName, data: ProcessedBenchmarkData)
    : { value: number; unit: string; higherIsBetter: boolean } | null {
    switch (name) {
      case 'llama': {
        const vals = (data.data_points || []).map(dp => dp.tokens_per_second_median).filter((v: any) => typeof v === 'number');
        const v = this.data.median(vals);
        if (typeof v !== 'number') return null;
        return { value: v, unit: 'tok/s', higherIsBetter: true };
      }
      case 'blender': {
        // Use median of all samples_per_minute values across scenes (higher is better)
        const vals = (data.data_points || []).map(dp => (dp as any)['samples_per_minute_median']).filter((v: any) => typeof v === 'number');
        const v = this.data.median(vals);
        if (typeof v !== 'number') return null;
        return { value: v, unit: 'SPM', higherIsBetter: true };
      }
      case '7zip': {
        // Use best (lowest) time across thread groups (lower is better)
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
    const t = data.median_values?.['build_time_seconds'];
    return typeof t === 'number' ? t : null;
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
