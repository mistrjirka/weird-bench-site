import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: '/hardware',
    pathMatch: 'full'
  },
  {
    path: 'hardware',
    loadComponent: () => import('./components/hardware-list/hardware-list').then(m => m.HardwareList)
  },
  {
    path: 'hardware/:type/:id',
    loadComponent: () => import('./components/hardware-detail/hardware-detail').then(m => m.HardwareDetail)
  }
  ,
  {
    path: 'compare',
    loadComponent: () => import('./components/compare/compare').then(m => m.CompareComponent)
  }
];
