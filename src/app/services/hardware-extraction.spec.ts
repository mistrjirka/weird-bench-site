import { TestBed } from '@angular/core/testing';

import { HardwareExtraction } from './hardware-extraction';

describe('HardwareExtraction', () => {
  let service: HardwareExtraction;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(HardwareExtraction);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
