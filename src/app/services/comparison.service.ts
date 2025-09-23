import { Injectable, signal, computed } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ComparisonService {
  // Selected type must be consistent across selections
  readonly selectedType = signal<'cpu' | 'gpu' | null>(null);
  readonly selectedIds = signal<string[]>([]);

  readonly count = computed(() => this.selectedIds().length);
  readonly isReady = computed(() => this.count() === 2 && this.selectedType() !== null);

  clear(): void {
    this.selectedType.set(null);
    this.selectedIds.set([]);
  }

  remove(id: string): void {
    this.selectedIds.set(this.selectedIds().filter(x => x !== id));
    if (this.selectedIds().length === 0) {
      this.selectedType.set(null);
    }
  }

  add(type: 'cpu' | 'gpu', id: string): boolean {
    const currentType = this.selectedType();
    if (currentType && currentType !== type) {
      // Cannot mix CPU and GPU
      return false;
    }
    const current = this.selectedIds();
    if (current.includes(id)) return true; // already selected
    if (current.length >= 2) return false; // limit to two

    if (!currentType) this.selectedType.set(type);
    this.selectedIds.set([...current, id]);
    return true;
  }
}
