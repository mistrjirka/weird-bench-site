import { Component, inject, OnInit, ChangeDetectionStrategy, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { NgbNavModule } from '@ng-bootstrap/ng-bootstrap';
import { HardwareDataService } from '../../services/hardware-data.service';
import { ComparisonService } from '../../services/comparison.service';

@Component({
  selector: 'app-hardware-list',
  imports: [RouterLink, CommonModule, NgbNavModule],
  templateUrl: './hardware-list.html',
  styleUrl: './hardware-list.scss',
  changeDetection: ChangeDetectionStrategy.OnPush
})
export class HardwareList implements OnInit {
  private hardwareService = inject(HardwareDataService);
  protected compare = inject(ComparisonService);
  
  // Tab management
  activeTab = 'cpu';
  
  // Expose service signals to template
  cpuList = this.hardwareService.cpuList;
  gpuList = this.hardwareService.gpuList;
  isLoading = this.hardwareService.isLoading;
  error = this.hardwareService.error;
  totalHardwareCount = this.hardwareService.totalHardwareCount;
  hasData = this.hardwareService.hasData;

  // Search state
  searchQuery = signal<string>('');

  // Filtered lists based on search
  filteredCpuList = computed(() => {
    const term = this.searchQuery().trim().toLowerCase();
    const list = this.cpuList();
    if (!term) return list;
    return list.filter(item => {
      const name = item.hardware.name?.toLowerCase() ?? '';
      const manufacturer = item.hardware.manufacturer?.toLowerCase() ?? '';
      const type = item.hardware.type?.toLowerCase() ?? '';
      const benchCount = String(item.benchmarkCount ?? '').toLowerCase();
      return (
        name.includes(term) ||
        manufacturer.includes(term) ||
        type.includes(term) ||
        benchCount.includes(term)
      );
    });
  });

  filteredGpuList = computed(() => {
    const term = this.searchQuery().trim().toLowerCase();
    const list = this.gpuList();
    if (!term) return list;
    return list.filter(item => {
      const name = item.hardware.name?.toLowerCase() ?? '';
      const manufacturer = item.hardware.manufacturer?.toLowerCase() ?? '';
      const type = item.hardware.type?.toLowerCase() ?? '';
      const framework = (item.hardware as any).framework?.toLowerCase?.() ?? '';
      const benchCount = String(item.benchmarkCount ?? '').toLowerCase();
      return (
        name.includes(term) ||
        manufacturer.includes(term) ||
        type.includes(term) ||
        framework.includes(term) ||
        benchCount.includes(term)
      );
    });
  });

  ngOnInit() {
    // Data loading is automatically triggered by the service constructor
    // We can manually refresh if needed
    this.refreshData();
  }

  refreshData() {
    this.hardwareService.loadHardwareList().subscribe();
  }

  clearError() {
    this.hardwareService.clearError();
  }

  onSearchChange(value: string) {
    this.searchQuery.set(value ?? '');
  }

  // Comparison helpers
  canAddToCompare(type: 'cpu' | 'gpu'): boolean {
    const selType = this.compare.selectedType();
    const count = this.compare.count();
    return (selType === null || selType === type) && count < 2;
  }

  isSelected(id: string): boolean {
    return this.compare.selectedIds().includes(id);
  }

  addToCompare(type: 'cpu' | 'gpu', id: string): void {
    this.compare.add(type, id);
  }

  removeFromCompare(id: string): void {
    this.compare.remove(id);
  }
}
