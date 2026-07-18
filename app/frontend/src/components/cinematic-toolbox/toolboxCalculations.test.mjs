import assert from 'node:assert/strict';
import test from 'node:test';
import {
  MAX_LOAN_PERIODS,
  calcAnnuity,
  calcComparison,
  calcFlatForward,
  calcFlatReverse,
  clampLoanYearsInput,
  loanPeriodsFromYears,
  pickScheduleRows,
} from './toolboxCalculations.ts';

test('loan periods preserve normal terms and cap pathological input', () => {
  assert.equal(loanPeriodsFromYears('5'), 60);
  assert.equal(loanPeriodsFromYears('999999'), MAX_LOAN_PERIODS);
  assert.equal(MAX_LOAN_PERIODS, 600);
  assert.equal(clampLoanYearsInput('999999'), '50');
  assert.equal(clampLoanYearsInput(''), '');
});

test('flat forward calculation preserves principal interest and effective rate', () => {
  const result = calcFlatForward(100000, 60, 0.2);
  assert.equal(result.monthlyPrincipal.toFixed(2), '1666.67');
  assert.equal(result.monthlyInterest.toFixed(2), '200.00');
  assert.equal(result.totalInterest.toFixed(2), '12000.00');
  assert.ok(result.realAnnualRate > result.nominalAnnualRate);
});

test('comparison calculates checkpoint ownership cost and tipping point', () => {
  const data = calcComparison(100000, 60, 0.18, 3);
  assert.equal(data.rows.map((row) => row.month).join(','), '12,24,36,48,60');
  assert.ok(data.rows.every((row) => Number.isFinite(row.diff)));
  assert.equal(data.tipping?.month, data.rows.find((row) => row.diff >= 0)?.month);
  assert.equal(data.recommendation.includes('总利息'), true);
});

test('zero-rate annuity returns principal-only payments', () => {
  const data = calcAnnuity(120000, 60, 0);
  assert.equal(data.result.monthlyPayment, 2000);
  assert.equal(data.result.totalInterest, 0);
  assert.equal(data.schedule.at(-1).balance, 0);
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
