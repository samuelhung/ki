export type LoanType = 'flat' | 'annuity' | 'compare';
export type FlatMode = 'forward' | 'reverse';

export interface FlatResult {
  monthlyPayment: number;
  monthlyPrincipal: number;
  monthlyInterest: number;
  totalInterest: number;
  nominalAnnualRate: number;
  realAnnualRate: number;
  nominalMonthlyLi: number;
  realMonthlyLi: number;
  flatMonthlyRate?: number;
  derivedFlatRate?: number;
}

export interface AnnuityResult {
  monthlyPayment: number;
  totalPayment: number;
  totalInterest: number;
  interestRatio: number;
}

export interface RepaymentRow {
  period: number;
  payment: number;
  principal: number;
  interest: number;
  balance: number;
}

export interface ComparisonRow {
  month: number;
  flatTotal: number;
  annuityTotal: number;
  diff: number;
  winner: 'flat' | 'annuity' | 'tie';
}

export function calcFlatForward(principal: number, periods: number, flatMonthlyRate: number): FlatResult {
  const monthlyPrincipal = principal / periods;
  const monthlyInterest = principal * (flatMonthlyRate / 100);
  const monthlyPayment = monthlyPrincipal + monthlyInterest;
  const totalInterest = monthlyInterest * periods;
  const nominalAnnualRate = flatMonthlyRate * 12;
  const realAnnualRate = irrAnnual(principal, monthlyPayment, periods);
  return {
    monthlyPayment,
    monthlyPrincipal,
    monthlyInterest,
    totalInterest,
    nominalAnnualRate,
    realAnnualRate,
    nominalMonthlyLi: flatMonthlyRate / 0.1,
    realMonthlyLi: realAnnualRate / 12 / 0.1,
    flatMonthlyRate,
  };
}

export function calcFlatReverse(principal: number, periods: number, monthlyPayment: number): FlatResult {
  const derivedFlatRate = ((monthlyPayment * periods - principal) / (principal * periods)) * 100;
  const monthlyPrincipal = principal / periods;
  const monthlyInterest = monthlyPayment - monthlyPrincipal;
  const totalInterest = monthlyPayment * periods - principal;
  const nominalAnnualRate = derivedFlatRate * 12;
  const realAnnualRate = irrAnnual(principal, monthlyPayment, periods);
  return {
    monthlyPayment,
    monthlyPrincipal,
    monthlyInterest,
    totalInterest,
    nominalAnnualRate,
    realAnnualRate,
    nominalMonthlyLi: derivedFlatRate / 0.1,
    realMonthlyLi: realAnnualRate / 12 / 0.1,
    derivedFlatRate,
  };
}

export function irrMonthly(principal: number, monthlyPayment: number, periods: number): number {
  if (monthlyPayment * periods <= principal) return 0;
  const nominalRate = (monthlyPayment * periods - principal) / (principal * periods);
  let lo = nominalRate * 0.5;
  let hi = nominalRate * 8;
  const presentValue = (rate: number) => monthlyPayment / rate * (1 - Math.pow(1 + rate, -periods));
  for (let index = 0; index < 20; index += 1) {
    if (presentValue(hi) < principal) break;
    hi *= 1.5;
  }
  for (let index = 0; index < 80; index += 1) {
    const mid = (lo + hi) / 2;
    const value = presentValue(mid);
    if (Math.abs(value - principal) < 0.01) return mid;
    if (value > principal) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

export function irrAnnual(principal: number, monthlyPayment: number, periods: number): number {
  return (Math.pow(1 + irrMonthly(principal, monthlyPayment, periods), 12) - 1) * 100;
}

export function calcAnnuity(principal: number, periods: number, annualRate: number): { result: AnnuityResult; schedule: RepaymentRow[] } {
  const monthlyRate = annualRate / 100 / 12;
  if (monthlyRate === 0) {
    const monthlyPayment = principal / periods;
    return {
      result: { monthlyPayment, totalPayment: principal, totalInterest: 0, interestRatio: 0 },
      schedule: Array.from({ length: periods }, (_, index) => ({
        period: index + 1,
        payment: monthlyPayment,
        principal: monthlyPayment,
        interest: 0,
        balance: Math.max(principal - monthlyPayment * (index + 1), 0),
      })),
    };
  }
  const monthlyPayment = principal * monthlyRate * Math.pow(1 + monthlyRate, periods) / (Math.pow(1 + monthlyRate, periods) - 1);
  const totalPayment = monthlyPayment * periods;
  const totalInterest = totalPayment - principal;
  const schedule: RepaymentRow[] = [];
  let balance = principal;
  for (let period = 1; period <= periods; period += 1) {
    const interest = balance * monthlyRate;
    const principalPart = monthlyPayment - interest;
    balance -= principalPart;
    schedule.push({ period, payment: monthlyPayment, principal: principalPart, interest, balance: Math.max(balance, 0) });
  }
  return {
    result: { monthlyPayment, totalPayment, totalInterest, interestRatio: (totalInterest / totalPayment) * 100 },
    schedule,
  };
}

export function calcComparison(principal: number, periods: number, flatMonthlyRate: number, annualRate: number) {
  const flatMonthly = principal / periods + principal * flatMonthlyRate / 100;
  const flatPrincipal = principal / periods;
  const flatInterest = principal * flatMonthlyRate / 100;
  const flatTotalInterest = flatInterest * periods;
  const flatIrr = irrAnnual(principal, flatMonthly, periods);
  const annuity = calcAnnuity(principal, periods, annualRate);
  const checkpoints = [12, 24, 36, 48, 60].filter((month) => month <= periods);
  if (!checkpoints.includes(periods)) checkpoints.push(periods);
  const rows: ComparisonRow[] = [...new Set(checkpoints)].map((month) => {
    const flatTotal = month * flatMonthly + Math.max(principal - month * flatPrincipal, 0);
    const annuityRow = annuity.schedule[month - 1];
    const annuityTotal = month * annuity.result.monthlyPayment + (annuityRow?.balance || 0);
    const diff = flatTotal - annuityTotal;
    return { month, flatTotal, annuityTotal, diff, winner: diff < 0 ? 'flat' : diff > 0 ? 'annuity' : 'tie' };
  });
  const tipping = rows.find((row) => row.diff >= 0);
  const saving = Math.abs(flatTotalInterest - annuity.result.totalInterest);
  const recommendation = flatTotalInterest > annuity.result.totalInterest
    ? `等额本息总利息少 ${formatMoney(saving)} 元，长期持有成本更低。`
    : `等本等息总利息少 ${formatMoney(saving)} 元，需同时核对真实年化。`;
  return {
    flatMonthly,
    flatPrincipal,
    flatInterest,
    flatTotalInterest,
    flatIrr,
    annuityMonthly: annuity.result.monthlyPayment,
    annuityTotalInterest: annuity.result.totalInterest,
    annualRate,
    rows,
    tipping,
    recommendation,
  };
}

export function formatMoney(value: number): string { return value.toFixed(2); }
export function formatPercent(value: number): string { return `${value.toFixed(2)}%`; }
export function formatLi(value: number): string { return `${value.toFixed(2)} 厘`; }

export function flatSummary(result: FlatResult): string {
  if (!result || result.totalInterest <= 0) return '';
  const ratio = result.realAnnualRate / result.nominalAnnualRate;
  if (ratio >= 1.9) return `真实年化利率是名义的 ${ratio.toFixed(1)} 倍，销售说的"低息"实际并不低。`;
  if (ratio >= 1.4) return `真实成本约为名义的 ${ratio.toFixed(1)} 倍，要注意合同上的年化利率。`;
  return '名义利率与真实成本差距较小，但仍建议核对合同年化利率。';
}

export function pickScheduleRows(schedule: RepaymentRow[]): RepaymentRow[] {
  if (schedule.length <= 12) return schedule;
  const rows = schedule.slice(0, 3);
  for (let index = 11; index < schedule.length - 3; index += 12) {
    if (index > 2) rows.push(schedule[index]);
  }
  rows.push(...schedule.slice(-3));
  return rows;
}
