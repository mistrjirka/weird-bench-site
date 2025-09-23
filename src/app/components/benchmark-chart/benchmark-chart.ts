import { Component, input, computed, ChangeDetectionStrategy } from '@angular/core';
import { NgApexchartsModule } from 'ng-apexcharts';
import {
  ApexAxisChartSeries,
  ApexChart,
  ApexXAxis,
  ApexYAxis,
  ApexDataLabels,
  ApexTooltip,
  ApexStroke,
  ApexGrid,
  ApexMarkers,
  ApexTheme
} from 'ng-apexcharts';

export interface ChartOptions {
  series: ApexAxisChartSeries;
  chart: ApexChart;
  xaxis: ApexXAxis;
  yaxis: ApexYAxis;
  dataLabels: ApexDataLabels;
  grid: ApexGrid;
  stroke: ApexStroke;
  tooltip: ApexTooltip;
  markers: ApexMarkers;
  theme: ApexTheme;
}

@Component({
  selector: 'app-benchmark-chart',
  template: `
    <div class="chart-container">
      <apx-chart
        [series]="chartOptions().series"
        [chart]="chartOptions().chart"
        [xaxis]="chartOptions().xaxis"
        [yaxis]="chartOptions().yaxis"
        [dataLabels]="chartOptions().dataLabels"
        [grid]="chartOptions().grid"
        [stroke]="chartOptions().stroke"
        [tooltip]="chartOptions().tooltip"
        [markers]="chartOptions().markers"
        [theme]="chartOptions().theme">
      </apx-chart>
    </div>
  `,
  styles: [`
    .chart-container {
      width: 100%;
      height: 400px;
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgApexchartsModule]
})
export class BenchmarkChartComponent {
  data = input.required<any[]>();
  chartType = input<'line' | 'bar'>('line');
  title = input<string>('Benchmark Chart');
  xAxisLabel = input<string>('X Axis');
  yAxisLabel = input<string>('Y Axis');
  xAxisKey = input<string>('x');
  yAxisKey = input<string>('y');

  chartOptions = computed<ChartOptions>(() => {
    const data = this.data();
    const series = [{
      name: this.yAxisLabel(),
      data: data.map(item => ({
        x: item[this.xAxisKey()],
        y: item[this.yAxisKey()]
      }))
    }];

    return {
      series: series,
      chart: {
        height: 350,
        type: this.chartType(),
        toolbar: {
          show: true
        }
      },
      dataLabels: {
        enabled: false
      },
      stroke: {
        curve: 'smooth'
      },
      xaxis: {
        type: 'numeric',
        title: {
          text: this.xAxisLabel()
        }
      },
      yaxis: {
        title: {
          text: this.yAxisLabel()
        }
      },
      tooltip: {
        x: {
          formatter: function (val: number) {
            return val.toString();
          }
        }
      },
      grid: {
        borderColor: '#e7e7e7',
        row: {
          colors: ['#f3f3f3', 'transparent'],
          opacity: 0.5
        }
      },
      markers: {
        size: 4
      },
      theme: {
        mode: 'light'
      }
    };
  });
}