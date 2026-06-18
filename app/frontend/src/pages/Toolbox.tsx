import React, { useState, useMemo } from 'react';
import { Wrench, Calculator, ArrowRightLeft, ChevronDown, ChevronUp, Table } from 'lucide-react';

type LoanType = 'flat' | 'annuity';      // 等本等息 | 等额本息
type FlatMode = 'forward' | 'reverse';   // 等本等息子模式

interface FlatResult {
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

interface AnnuityResult {
  monthlyPayment: number;
  totalPayment: number;
  totalInterest: number;
  interestRatio: number;    // 利息占比 %
}

interface RepaymentRow {
  period: number;
  payment: number;
  principal: number;
  interest: number;
  balance: number;
}

/* ═══════════════════════════════════════════
   等本等息
   ═══════════════════════════════════════════ */

function calcFlatForward(principal: number, periods: number, flatMonthlyRate: number): FlatResult {
  const monthlyPrincipal = principal / periods;
  const monthlyInterest = principal * (flatMonthlyRate / 100);
  const monthlyPayment = monthlyPrincipal + monthlyInterest;
  const totalInterest = monthlyInterest * periods;
  const nominalAnnualRate = flatMonthlyRate * 12;
  const realAnnualRate = irrAnnual(principal, monthlyPayment, periods);
  const nominalMonthlyLi = flatMonthlyRate / 0.1;
  const realMonthlyLi = realAnnualRate / 12 / 0.1;
  return { monthlyPayment, monthlyPrincipal, monthlyInterest, totalInterest,
    nominalAnnualRate, realAnnualRate, nominalMonthlyLi, realMonthlyLi, flatMonthlyRate };
}

function calcFlatReverse(principal: number, periods: number, monthlyPayment: number): FlatResult {
  const derivedFlatRate = ((monthlyPayment * periods - principal) / (principal * periods)) * 100;
  const monthlyPrincipal = principal / periods;
  const monthlyInterest = monthlyPayment - monthlyPrincipal;
  const totalInterest = monthlyPayment * periods - principal;
  const nominalAnnualRate = derivedFlatRate * 12;
  const realAnnualRate = irrAnnual(principal, monthlyPayment, periods);
  const nominalMonthlyLi = derivedFlatRate / 0.1;
  const realMonthlyLi = realAnnualRate / 12 / 0.1;
  return { monthlyPayment, monthlyPrincipal, monthlyInterest, totalInterest,
    nominalAnnualRate, realAnnualRate, nominalMonthlyLi, realMonthlyLi, derivedFlatRate };
}

function irrMonthly(principal: number, monthlyPayment: number, periods: number): number {
  if (monthlyPayment * periods <= principal) return 0;
  const nominalRate = (monthlyPayment * periods - principal) / (principal * periods);
  let lo = nominalRate * 0.5, hi = nominalRate * 8;
  const pv = (r: number) => monthlyPayment / r * (1 - Math.pow(1 + r, -periods));
  for (let i = 0; i < 20; i++) { if (pv(hi) < principal) break; hi *= 1.5; }
  for (let iter = 0; iter < 80; iter++) {
    const mid = (lo + hi) / 2, pvMid = pv(mid);
    if (Math.abs(pvMid - principal) < 0.01) return mid;
    if (pvMid > principal) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

function irrAnnual(principal: number, monthlyPayment: number, periods: number): number {
  return (Math.pow(1 + irrMonthly(principal, monthlyPayment, periods), 12) - 1) * 100;
}

/* ═══════════════════════════════════════════
   等额本息
   ═══════════════════════════════════════════ */

function calcAnnuity(principal: number, periods: number, annualRate: number): { result: AnnuityResult; schedule: RepaymentRow[] } {
  const monthlyRate = annualRate / 100 / 12;
  const monthlyPayment = principal * monthlyRate * Math.pow(1 + monthlyRate, periods) / (Math.pow(1 + monthlyRate, periods) - 1);
  const totalPayment = monthlyPayment * periods;
  const totalInterest = totalPayment - principal;
  const interestRatio = (totalInterest / totalPayment) * 100;

  // 生成还款计划（全量，前端只展示精选行）
  const schedule: RepaymentRow[] = [];
  let balance = principal;
  for (let i = 1; i <= periods; i++) {
    const interest = balance * monthlyRate;
    const principalPart = monthlyPayment - interest;
    balance -= principalPart;
    schedule.push({
      period: i,
      payment: monthlyPayment,
      principal: principalPart,
      interest,
      balance: Math.max(balance, 0),
    });
  }

  return { result: { monthlyPayment, totalPayment, totalInterest, interestRatio }, schedule };
}

/* ═══════════════════════════════════════════
   工具函数
   ═══════════════════════════════════════════ */

function fmt(money: number): string { return money.toFixed(2); }
function fmtPct(v: number): string { return v.toFixed(2) + '%'; }
function fmtLi(v: number): string { return v.toFixed(2) + ' 厘'; }

function flatSummary(r: FlatResult): string {
  if (!r || r.totalInterest <= 0) return '';
  const ratio = r.realAnnualRate / r.nominalAnnualRate;
  if (ratio >= 1.9) return `真实年化利率是名义的 ${ratio.toFixed(1)} 倍，销售说的"低息"实际并不低。`;
  if (ratio >= 1.4) return `真实成本约为名义的 ${ratio.toFixed(1)} 倍，要注意合同上的年化利率。`;
  return '名义利率与真实成本差距较小，但仍建议核对合同年化利率。';
}

/** 精选还款计划行：首3 + 中段每12期 + 末3 */
function pickScheduleRows(schedule: RepaymentRow[]): RepaymentRow[] {
  if (schedule.length <= 12) return schedule;
  const n = schedule.length;
  const rows: RepaymentRow[] = [];
  // 首 3
  for (let i = 0; i < 3; i++) rows.push(schedule[i]);
  // 中间每隔 12 期
  for (let i = 11; i < n - 3; i += 12) {
    if (i > 2 && i < n - 3) rows.push(schedule[i]);
  }
  // 末 3
  for (let i = n - 3; i < n; i++) rows.push(schedule[i]);
  return rows;
}

/* ═══════════════════════════════════════════
   组件
   ═══════════════════════════════════════════ */

export default function Toolbox() {
  const [loanType, setLoanType] = useState<LoanType>('flat');
  const [flatMode, setFlatMode] = useState<FlatMode>('forward');
  const [principal, setPrincipal] = useState('100000');
  const [years, setYears] = useState('5');
  const [flatRate, setFlatRate] = useState('0.2');        // 等本等息 正向
  const [revInterest, setRevInterest] = useState('200');  // 等本等息 反向
  const [annualRate, setAnnualRate] = useState('3');      // 等额本息 年化利率
  const [showWhy, setShowWhy] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);

  const periods = useMemo(() => {
    const y = parseFloat(years);
    return isNaN(y) || y <= 0 ? 60 : Math.round(y * 12);
  }, [years]);

  // 等本等息 反向：月供
  const revMonthlyPay = useMemo(() => {
    const p = parseFloat(principal);
    const i = parseFloat(revInterest);
    if (isNaN(p) || isNaN(i) || p <= 0 || periods <= 0) return NaN;
    return p / periods + i;
  }, [principal, periods, revInterest]);

  // 等本等息 结果
  const flatResult = useMemo((): FlatResult | null => {
    if (loanType !== 'flat') return null;
    const p = parseFloat(principal);
    if (isNaN(p) || p <= 0 || periods <= 0) return null;
    if (flatMode === 'forward') {
      const r = parseFloat(flatRate);
      if (isNaN(r) || r < 0) return null;
      return calcFlatForward(p, periods, r);
    } else {
      const m = revMonthlyPay;
      if (isNaN(m) || m <= 0 || m < p / periods) return null;
      return calcFlatReverse(p, periods, m);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loanType, principal, periods, flatRate, revMonthlyPay, flatMode]);

  // 等额本息 结果
  const annuityData = useMemo(() => {
    if (loanType !== 'annuity') return null;
    const p = parseFloat(principal);
    const r = parseFloat(annualRate);
    if (isNaN(p) || isNaN(r) || p <= 0 || r <= 0 || periods <= 0) return null;
    return calcAnnuity(p, periods, r);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loanType, principal, periods, annualRate]);

  const inputCls = "w-full bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 font-mono";

  return (
    <div className="flex flex-col h-full overflow-auto bg-[#0B0C10] text-white">
      <div className="max-w-2xl mx-auto w-full px-4 md:px-8 pt-4 md:pt-8 pb-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Wrench size={28} className="text-orange-400 shrink-0" />
          <div>
            <h1 className="text-xl font-bold text-white">工具箱</h1>
            <p className="text-xs text-gray-500 mt-0.5">实用计算工具</p>
          </div>
        </div>

        {/* Tool card */}
        <div className="bg-[#141518] border border-[#2A2B30] rounded-xl overflow-hidden">
          {/* Card header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-[#2A2B30]">
            <div className="flex items-center gap-2.5">
              <Calculator size={18} className="text-purple-400" />
              <span className="text-sm font-semibold">贷款利率换算器</span>
            </div>
            <div className="flex items-center gap-2">
              {/* Loan type switch */}
              <div className="flex bg-[#0B0C10] rounded-lg p-0.5">
                <button
                  onClick={() => setLoanType('flat')}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    loanType === 'flat' ? 'bg-red-500/20 text-red-400' : 'text-gray-500 hover:text-gray-300'
                  }`}
                >等本等息</button>
                <button
                  onClick={() => setLoanType('annuity')}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    loanType === 'annuity' ? 'bg-emerald-500/20 text-emerald-400' : 'text-gray-500 hover:text-gray-300'
                  }`}
                >等额本息</button>
              </div>
              {/* Forward/reverse only for flat */}
              {loanType === 'flat' && (
                <div className="flex bg-[#0B0C10] rounded-lg p-0.5">
                  <button onClick={() => setFlatMode('forward')}
                    className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                      flatMode === 'forward' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'
                    }`}>正向</button>
                  <button onClick={() => setFlatMode('reverse')}
                    className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                      flatMode === 'reverse' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'
                    }`}>反向</button>
                </div>
              )}
            </div>
          </div>

          {/* ═══════════ Inputs ═══════════ */}
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">贷款金额（元）</label>
                <input type="number" value={principal}
                  onChange={e => setPrincipal(e.target.value)}
                  className={inputCls} placeholder="100000" />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">还款年限</label>
                <input type="number" value={years}
                  onChange={e => setYears(e.target.value)}
                  className={inputCls} placeholder="5" />
                <p className="text-[10px] text-gray-600 mt-1">{periods} 期（月）</p>
              </div>
            </div>

            {/* 等本等息 inputs */}
            {loanType === 'flat' && flatMode === 'forward' && (
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">月分期利率（%）</label>
                <input type="number" step="0.01" value={flatRate}
                  onChange={e => setFlatRate(e.target.value)}
                  className={inputCls} placeholder="0.2" />
                <p className="text-[10px] text-gray-600 mt-1">销售常说的"每期手续费率"</p>
              </div>
            )}

            {loanType === 'flat' && flatMode === 'reverse' && (
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">月供拆分（元）</label>
                <div className="flex items-center gap-2">
                  <div className="flex-1"><div className="relative">
                    <input type="number" step="0.01" readOnly
                      value={fmt(parseFloat(principal) / periods)}
                      className={`${inputCls} text-gray-500 cursor-default pr-10`} />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-600">本金</span>
                  </div></div>
                  <span className="text-gray-600 text-xs shrink-0">+</span>
                  <div className="flex-1"><div className="relative">
                    <input type="number" step="0.01" value={revInterest}
                      onChange={e => setRevInterest(e.target.value)}
                      className={`${inputCls} text-amber-400 pr-10`} placeholder="200" />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-amber-400/60">利息</span>
                  </div></div>
                  <span className="text-gray-600 text-xs shrink-0">=</span>
                  <div className="flex-1"><div className="relative">
                    <input type="text" readOnly
                      value={isNaN(revMonthlyPay) ? '—' : fmt(revMonthlyPay)}
                      className={`${inputCls} text-white font-semibold cursor-default pr-10`} />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-500">月供</span>
                  </div></div>
                </div>
                <p className="text-[10px] text-gray-600 mt-1">本金固定 = 总金额 ÷ 期数，调整利息即可反推利率</p>
              </div>
            )}

            {/* 等额本息 input */}
            {loanType === 'annuity' && (
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">年化利率（%）</label>
                <input type="number" step="0.01" value={annualRate}
                  onChange={e => setAnnualRate(e.target.value)}
                  className={inputCls} placeholder="3" />
                <p className="text-[10px] text-gray-600 mt-1">银行合同上的年化利率，利息按剩余本金计算</p>
              </div>
            )}
          </div>

          {/* ═══════════ Results: 等本等息 ═══════════ */}
          {loanType === 'flat' && flatResult && (
            <div className="px-5 pb-5 space-y-4">
              {flatMode === 'reverse' && flatResult.derivedFlatRate !== undefined && (
                <div className="bg-[#0B0C10] rounded-lg px-4 py-2.5 flex items-center gap-2 text-xs">
                  <ArrowRightLeft size={14} className="text-amber-400 shrink-0" />
                  <span className="text-gray-500">反推月分期利率：</span>
                  <span className="text-amber-400 font-mono font-medium">{fmtPct(flatResult.derivedFlatRate)}</span>
                  <span className="text-gray-600">（名义 {fmtLi(flatResult.derivedFlatRate / 0.1)}）</span>
                </div>
              )}

              <div className="overflow-hidden rounded-lg border border-[#2A2B30]">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-[#0B0C10]">
                      <th className="py-2.5 px-4 text-left text-gray-500 font-medium">项目</th>
                      <th className="py-2.5 px-4 text-right text-gray-500 font-medium">
                        {flatMode === 'forward' ? '销售说的' : '名义值'}
                      </th>
                      <th className="py-2.5 px-4 text-right font-medium text-red-400">真实成本</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1A1B20]">
                    <tr>
                      <td className="py-3 px-4 text-gray-400">月供（合计）</td>
                      <td className="py-3 px-4 text-right font-mono text-white font-semibold">{fmt(flatResult.monthlyPayment)} 元</td>
                      <td className="py-3 px-4 text-right text-gray-600 text-[11px]">—</td>
                    </tr>
                    <tr className="bg-[#0B0C10]/50">
                      <td className="py-2 px-4 text-gray-600 text-[11px] pl-7">　本金</td>
                      <td className="py-2 px-4 text-right font-mono text-gray-500 text-[11px]">{fmt(flatResult.monthlyPrincipal)} 元</td>
                      <td className="py-2 px-4 text-right text-gray-700 text-[10px]">—</td>
                    </tr>
                    <tr className="bg-[#0B0C10]/50">
                      <td className="py-2 px-4 text-gray-600 text-[11px] pl-7">　利息</td>
                      <td className="py-2 px-4 text-right font-mono text-amber-400/80 text-[11px]">{fmt(flatResult.monthlyInterest)} 元</td>
                      <td className="py-2 px-4 text-right text-gray-700 text-[10px]">—</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">总利息</td>
                      <td className="py-3 px-4 text-right font-mono text-white">{fmt(flatResult.totalInterest)} 元</td>
                      <td className="py-3 px-4 text-right text-gray-600 text-[11px]">—</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">年化利率</td>
                      <td className="py-3 px-4 text-right font-mono text-gray-400">{fmtPct(flatResult.nominalAnnualRate)}</td>
                      <td className="py-3 px-4 text-right font-mono text-red-400 font-semibold">{fmtPct(flatResult.realAnnualRate)}</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">月息</td>
                      <td className="py-3 px-4 text-right font-mono text-gray-400">{fmtLi(flatResult.nominalMonthlyLi)}</td>
                      <td className="py-3 px-4 text-right font-mono text-red-400 font-semibold">{fmtLi(flatResult.realMonthlyLi)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {flatSummary(flatResult) && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
                  <p className="text-xs text-red-300 leading-relaxed">💡 {flatSummary(flatResult)}</p>
                </div>
              )}

              <button onClick={() => setShowWhy(!showWhy)}
                className="flex items-center gap-1.5 text-[10px] text-gray-500 hover:text-gray-300 transition-colors">
                {showWhy ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                为什么「销售说的」和「真实成本」不一样？
              </button>
              {showWhy && (
                <div className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-4 py-3 text-[11px] text-gray-400 leading-relaxed space-y-2">
                  <p><span className="text-white font-medium">等本等息的陷阱：</span>每月利息按<span className="text-amber-400">最初的贷款总额</span>计算，固定不变。</p>
                  <p>但你每月都在还本金——实际占用资金越来越少，利息却没有减少。以 10 万 60 期为例：</p>
                  <div className="bg-[#141518] rounded p-2.5 font-mono text-[10px] space-y-1">
                    <p>第 1 个月：欠 100,000，利息 200 → <span className="text-gray-400">月利率 0.20%</span></p>
                    <p>第 30 个月：欠 50,000，利息 200 → <span className="text-amber-400">月利率 0.40%</span></p>
                    <p>第 60 个月：欠 1,667，利息 200 → <span className="text-red-400">月利率 12%</span></p>
                  </div>
                  <p><span className="text-white">IRR 真实年化</span>是把 60 期不等的实际利率加权平均后换算的年化值，反映了你<span className="text-red-400">真正的资金成本</span>。</p>
                  <p className="text-gray-600">签合同前，请认准合同上的「年化利率」或「IRR」数值，不要被「分期利率」或「几厘」迷惑。</p>
                </div>
              )}
              <p className="text-[10px] text-gray-600 leading-relaxed">
                IRR 采用二分查找法计算，精度 0.01，年化 = (1+月利率)¹² - 1。<br/>
                速算参考：年化 ≈ 月分期利率 × 期数 × 24 ÷ (期数 + 1)
              </p>
            </div>
          )}

          {/* ═══════════ Results: 等额本息 ═══════════ */}
          {loanType === 'annuity' && annuityData && (
            <div className="px-5 pb-5 space-y-4">
              <div className="overflow-hidden rounded-lg border border-[#2A2B30]">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-[#0B0C10]">
                      <th className="py-2.5 px-4 text-left text-gray-500 font-medium">项目</th>
                      <th className="py-2.5 px-4 text-right text-gray-500 font-medium">数值</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1A1B20]">
                    <tr>
                      <td className="py-3 px-4 text-gray-400">月供</td>
                      <td className="py-3 px-4 text-right font-mono text-white font-semibold">{fmt(annuityData.result.monthlyPayment)} 元</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">还款总额</td>
                      <td className="py-3 px-4 text-right font-mono text-white">{fmt(annuityData.result.totalPayment)} 元</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">利息总额</td>
                      <td className="py-3 px-4 text-right font-mono text-amber-400/80">{fmt(annuityData.result.totalInterest)} 元</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">月息</td>
                      <td className="py-3 px-4 text-right font-mono text-gray-400">{fmtLi(parseFloat(annualRate) / 12 / 0.1)}</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">利息占比</td>
                      <td className="py-3 px-4 text-right font-mono text-gray-400">{fmtPct(annuityData.result.interestRatio)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-4 py-3">
                <p className="text-xs text-emerald-300 leading-relaxed">
                  💡 等额本息按<span className="text-white font-medium">剩余本金</span>计息，IRR = 名义年化 = {fmtPct(parseFloat(annualRate))}，不存在「低息陷阱」。
                </p>
              </div>

              {/* 还款计划表 */}
              <button onClick={() => setShowSchedule(!showSchedule)}
                className="flex items-center gap-1.5 text-[10px] text-gray-500 hover:text-gray-300 transition-colors">
                {showSchedule ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                <Table size={12} />
                还款计划明细
              </button>
              {showSchedule && (
                <div className="overflow-hidden rounded-lg border border-[#2A2B30]">
                  <table className="w-full text-[11px] font-mono">
                    <thead>
                      <tr className="bg-[#0B0C10]">
                        <th className="py-2 px-3 text-left text-gray-500 font-medium">期数</th>
                        <th className="py-2 px-3 text-right text-gray-500 font-medium">月供</th>
                        <th className="py-2 px-3 text-right text-gray-500 font-medium">本金</th>
                        <th className="py-2 px-3 text-right text-gray-500 font-medium">利息</th>
                        <th className="py-2 px-3 text-right text-gray-500 font-medium">剩余本金</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1A1B20]">
                      {pickScheduleRows(annuityData.schedule).map((row, i, arr) => (
                        <tr key={row.period}
                          className={i > 0 && arr[i-1].period + 1 !== row.period
                            ? 'border-t-2 border-dashed border-[#2A2B30]' : ''}>
                          <td className="py-1.5 px-3 text-gray-500">{row.period}</td>
                          <td className="py-1.5 px-3 text-right text-gray-300">{fmt(row.payment)}</td>
                          <td className="py-1.5 px-3 text-right text-gray-400">{fmt(row.principal)}</td>
                          <td className="py-1.5 px-3 text-right text-amber-400/70">{fmt(row.interest)}</td>
                          <td className="py-1.5 px-3 text-right text-gray-600">{fmt(row.balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="bg-[#0B0C10] px-3 py-1.5 text-[10px] text-gray-600">
                    显示首3期 + 中段每12期 + 末3期（共{annuityData.schedule.length}期，省略中间行）
                  </div>
                </div>
              )}

              <p className="text-[10px] text-gray-600 leading-relaxed">
                月供 = 本金 × 月利率 × (1+月利率)ⁿ ÷ ((1+月利率)ⁿ − 1)，每月利息按剩余本金重新计算。
              </p>
            </div>
          )}

          {/* Empty state */}
          {loanType === 'flat' && !flatResult && (
            <div className="px-5 pb-8 text-center">
              <p className="text-xs text-gray-600">请输入参数查看计算结果</p>
            </div>
          )}
          {loanType === 'annuity' && !annuityData && (
            <div className="px-5 pb-8 text-center">
              <p className="text-xs text-gray-600">请输入参数查看计算结果</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
