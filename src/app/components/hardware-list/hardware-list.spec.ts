import { ComponentFixture, TestBed } from '@angular/core/testing';

import { HardwareList } from './hardware-list';

describe('HardwareList', () => {
  let component: HardwareList;
  let fixture: ComponentFixture<HardwareList>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HardwareList]
    })
    .compileComponents();

    fixture = TestBed.createComponent(HardwareList);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
