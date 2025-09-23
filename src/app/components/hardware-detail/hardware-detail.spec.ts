import { ComponentFixture, TestBed } from '@angular/core/testing';

import { HardwareDetail } from './hardware-detail';

describe('HardwareDetail', () => {
  let component: HardwareDetail;
  let fixture: ComponentFixture<HardwareDetail>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HardwareDetail]
    })
    .compileComponents();

    fixture = TestBed.createComponent(HardwareDetail);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
