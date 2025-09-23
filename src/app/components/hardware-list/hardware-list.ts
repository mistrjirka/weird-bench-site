import { Component, inject, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { NgbNavModule } from '@ng-bootstrap/ng-bootstrap';
import { HardwareDataService } from '../../services/hardware-data.service';

@Component({
  selector: 'app-hardware-list',
  imports: [RouterLink, CommonModule, NgbNavModule],
  templateUrl: './hardware-list.html',
  styleUrl: './hardware-list.scss'
})
export class HardwareList implements OnInit {
  private hardwareService = inject(HardwareDataService);
  
  // Tab management
  activeTab = 'cpu';
  
  // Expose service signals to template
  cpuList = this.hardwareService.cpuList;
  gpuList = this.hardwareService.gpuList;
  isLoading = this.hardwareService.isLoading;
  error = this.hardwareService.error;
  totalHardwareCount = this.hardwareService.totalHardwareCount;
  hasData = this.hardwareService.hasData;

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
}
