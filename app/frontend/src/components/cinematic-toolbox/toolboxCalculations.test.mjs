import assert from 'node:assert/strict';
import test from 'node:test';
import {
  calcAnnuity,
  calcFlatForward,
  calcFlatReverse,
  pickScheduleRows,
} from './toolboxCalculations.ts';

test('flat forward calculation preserves principal interest and effective rate', () => {
  const result = calcFlatForward(100000, 60, 0.2);
  assert.equal(result.monthlyPrincipal.toFixed(2), '1666.67');
  assert.equal(result.monthlyInterest.toFixed(2), '200.00');
  assert.equal(result.totalInterest.toFixed(2), '12000.00');
  assert.ok(result.realAnnualRate > result.nominalAnnualRate);
});

test('flat reverse calculation derives the original monthly rate', () => {
  const result = calcFlatReverse(100000, 60, 1866.6666666667);
  assert.equal(result.derivedFlatRate?.toFixed(2), '0.20');
  assert.equal(result.totalInterest.toFixed(2), '12000.00');
});

test('annuity calculation creates a complete schedule and selected rows', () => {
  const data = calcAnnuity(100000, 60, 3);
  assert.equal(data.schedule.length, 60);
  assert.ok(data.schedule.at(-1).balance < 0.01);
  const selected = pickScheduleRows(data.schedule);
  assert.equal(selected[0].period, 1);
  assert.equal(selected.at(-1).period, 60);
  assert.ok(selected.length < data.schedule.length);
});
