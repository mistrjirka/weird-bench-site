import { Component, ChangeDetectionStrategy, computed, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ComparisonService } from '../../services/comparison.service';
import { HardwareDataService } from '../../services/hardware-data.service';

type BenchName = 'llama' | 'blender' | '7zip' | 'reversan';

@Component({
  selector: 'app-compare',
  standalone: true,
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

  readonly leftBench = signal<Record<string, any>>({});
  readonly rightBench = signal<Record<string, any>>({});

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

    // Load available benchmark files for both (we'll try common set)
    const benches: BenchName[] = type === 'gpu' ? ['llama', 'blender'] : ['llama', 'blender', '7zip', 'reversan'];
    Promise.all(
      benches.map(async name => {
        const [la, lb] = await Promise.all([
          this.data.loadBenchmarkFiles(type, a, name).toPromise(),
          this.data.loadBenchmarkFiles(type, b, name).toPromise()
        ]);
        if (la && lb) {
          const unwrap = (arr: any[]) => arr.filter(x => !!x).map(x => (x.data ?? x.results) ?? x);
          (this.leftBench() as any)[name] = unwrap(la);
          (this.rightBench() as any)[name] = unwrap(lb);
          this.leftBench.set({ ...this.leftBench() });
          this.rightBench.set({ ...this.rightBench() });
        }
      })
    );
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
        // Compare depths with omission of leading depths where both are 0 (immeasurable)
        const leftDepthMap = this.aggregateReversanDepths(left[name]);
        const rightDepthMap = this.aggregateReversanDepths(right[name]);
        const allDepths = Array.from(new Set([...leftDepthMap.keys(), ...rightDepthMap.keys()])).sort((a, b) => a - b);
        const commonDepths = allDepths.filter(d => leftDepthMap.has(d) && rightDepthMap.has(d));

        // Compute leading consecutive depths with both medians == 0
        let immeasurableMax = 0;
        for (const d of commonDepths) {
          const lv0 = leftDepthMap.get(d)!;
          const rv0 = rightDepthMap.get(d)!;
          if (lv0 === 0 && rv0 === 0 && (immeasurableMax === 0 ? d === 1 : d === immeasurableMax + 1)) {
            immeasurableMax = d;
          } else {
            break;
          }
        }
        if (immeasurableMax > 0) {
          result.push({ name: `reversan immeasurable depth 1–${immeasurableMax}`, left: 0, right: 0, unit: 's', improvement: 0, higherIsBetter: false });
        }
        const filteredDepths = commonDepths.filter(d => d > immeasurableMax);
        for (const depth of filteredDepths) {
          const lv = leftDepthMap.get(depth)!;
          const rv = rightDepthMap.get(depth)!;
          const improvement = this.percentImprovement(lv, rv, false);
          result.push({ name: `reversan depth ${depth}`, left: lv, right: rv, unit: 's', improvement, higherIsBetter: false });
        }

        // Add complex multithread row (best median across threads with thread count)
        const leftThreadBest = this.bestReversanThread(left[name]);
        const rightThreadBest = this.bestReversanThread(right[name]);
        if (leftThreadBest && rightThreadBest) {
          const improvement = this.percentImprovement(leftThreadBest.elapsed, rightThreadBest.elapsed, false);
          result.push({
            name: `reversan complex multithread (L: ${leftThreadBest.threads} th, R: ${rightThreadBest.threads} th)`,
            left: leftThreadBest.elapsed,
            right: rightThreadBest.elapsed,
            unit: 's',
            improvement,
            higherIsBetter: false
          });
        }
        continue;
      }
      if (name === 'llama' && type === 'cpu') {
        const lc = this.extractLlamaCompile(left[name]);
        const rc = this.extractLlamaCompile(right[name]);
        if (lc && rc) {
          const improvement = this.percentImprovement(lc.value, rc.value, false);
          result.push({ name: 'llama compile', left: lc.value, right: rc.value, unit: 's', improvement, higherIsBetter: false });
        }
      }
      const leftVal = this.extractMetric(name, left[name], type);
      const rightVal = this.extractMetric(name, right[name], type);
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
    const rows = rowsAll.filter(r => !r.name.startsWith('reversan immeasurable'));
    if (rows.length === 0) return null;
    const avg = rows.reduce((s, r) => s + r.improvement, 0) / rows.length;
    const better = avg > 0 ? 'faster' : 'slower';
    const left = this.leftName();
    const right = this.rightName();
    const headline = `All tests delta: ${right} is ${Math.abs(avg).toFixed(1)}% ${better} than ${left} on average across ${rows.length} test(s)`;
    return { headline, average: avg };
  }

  private extractMetric(name: BenchName, data: any, type: 'cpu' | 'gpu')
    : { value: number; unit: string; higherIsBetter: boolean } | null {
    switch (name) {
      case 'llama': {
        const list = Array.isArray(data) ? data : [data];
        const runs = type === 'cpu'
          ? list.flatMap((d: any) => Array.isArray(d.runs_cpu) ? d.runs_cpu : [])
          : list.flatMap((d: any) => Array.isArray(d.runs_gpu) ? d.runs_gpu : []);
        if (!runs.length) return null;
        const values = runs.map((r: any) => {
          const m = r.metrics || {};
          return m.prompt_tokens_per_second || m.tokens_per_second || m.eval_tokens_per_second || m.decode_tokens_per_second;
        }).filter((v: any) => typeof v === 'number');
        const vmed = this.data.median(values);
        if (typeof vmed !== 'number') return null;
        return { value: vmed, unit: 'tok/s', higherIsBetter: true };
      }
      case 'blender': {
        const list = Array.isArray(data) ? data : [data];
        const runs = list.flatMap((d: any) => Array.isArray(d.device_runs) ? d.device_runs : []);
        // Filter CPU/GPU according to type
        const filtered = runs.filter((r: any) => type === 'cpu' ? r.device_framework === 'CPU' : r.device_framework !== 'CPU');
        let total = 0, n = 0;
        const spms: number[] = [];
        for (const r of filtered) {
          let entries: any[] = Array.isArray(r.raw_json) ? r.raw_json : [];
          if ((!entries || entries.length === 0) && typeof r.raw_output === 'string') {
            try {
              const parsed = JSON.parse(r.raw_output);
              if (Array.isArray(parsed)) entries = parsed;
            } catch {
              // ignore parse errors
            }
          }
          if (Array.isArray(entries)) {
            for (const entry of entries) {
              const spm = entry?.stats?.samples_per_minute;
              if (typeof spm === 'number') { spms.push(spm); }
            }
          }
        }
        const vmed = this.data.median(spms);
        if (typeof vmed !== 'number') return null;
        return { value: vmed, unit: 'samples/min', higherIsBetter: true };
      }
      case '7zip': {
        const list = Array.isArray(data) ? data : [data];
        const runs = list.flatMap((d: any) => Array.isArray(d.runs) ? d.runs : []);
        const valid = runs.filter((r: any) => typeof r.elapsed_seconds === 'number');
        if (!valid.length) return null;
        const vmed = this.data.median(valid.map((r: any) => r.elapsed_seconds));
        if (typeof vmed !== 'number') return null;
        return { value: vmed, unit: 's', higherIsBetter: false };
      }
      case 'reversan': {
        const list = Array.isArray(data) ? data : [data];
        const rd = list.flatMap((d: any) => Array.isArray(d.runs_depth) ? d.runs_depth : []);
        const depthMap = new Map<number, number[]>();
        for (const r of rd) {
          // Prefer user_seconds as it contains more precise decimal values
          const t = r.metrics?.user_seconds ?? r.metrics?.elapsed_seconds;
          if (typeof r.depth === 'number' && typeof t === 'number') {
            const arr = depthMap.get(r.depth) || [];
            arr.push(t);
            depthMap.set(r.depth, arr);
          }
        }
        // Use depth 10 as representative single metric for the summary table
        const d10 = depthMap.get(10) || [];
        const vmed = this.data.median(d10);
        if (typeof vmed !== 'number') return null;
        return { value: vmed, unit: 's', higherIsBetter: false };
      }
      default:
        return null;
    }
  }

  private aggregateReversanDepths(dataList: any): Map<number, number> {
    const list = Array.isArray(dataList) ? dataList : [dataList];
    const rd = list.flatMap((d: any) => Array.isArray(d.runs_depth) ? d.runs_depth : []);
    const depthMap = new Map<number, number[]>();
    for (const r of rd) {
      // Prefer user_seconds as it contains more precise decimal values
      const t = r.metrics?.user_seconds ?? r.metrics?.elapsed_seconds;
      if (typeof r.depth === 'number' && typeof t === 'number') {
        const arr = depthMap.get(r.depth) || [];
        arr.push(t);
        depthMap.set(r.depth, arr);
      }
    }
    
    const medMap = new Map<number, number>();
    for (const [depth, vals] of depthMap.entries()) {
      const v = this.data.median(vals);
      if (typeof v === 'number') medMap.set(depth, v);
    }
    
    return medMap;
  }

  private bestReversanThread(dataList: any): { threads: number; elapsed: number } | null {
    const list = Array.isArray(dataList) ? dataList : [dataList];
    const rt = list.flatMap((d: any) => Array.isArray(d.runs_threads) ? d.runs_threads : []);
    const threadMap = new Map<number, number[]>();
    for (const r of rt) {
      // Prefer user_seconds as it contains more precise decimal values
      const t = r.metrics?.user_seconds ?? r.metrics?.elapsed_seconds;
      if (typeof r.threads === 'number' && typeof t === 'number') {
        const arr = threadMap.get(r.threads) || [];
        arr.push(t);
        threadMap.set(r.threads, arr);
      }
    }
    let best: { threads: number; elapsed: number } | null = null;
    for (const [threads, vals] of threadMap.entries()) {
      const med = this.data.median(vals);
      if (typeof med !== 'number') continue;
      if (!best || med < best.elapsed) {
        best = { threads, elapsed: med };
      }
    }
    return best;
  }

  private extractLlamaCompile(dataList: any): { value: number } | null {
    const list = Array.isArray(dataList) ? dataList : [dataList];
    const times = list.map((d: any) => d?.build?.cpu_build_timing?.build_time_seconds).filter((v: any) => typeof v === 'number');
    const v = this.data.median(times);
    if (typeof v !== 'number') return null;
    return { value: v };
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
