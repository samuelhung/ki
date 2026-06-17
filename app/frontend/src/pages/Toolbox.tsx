import React, { useState, useMemo, useCallback } from 'react';
import { Wrench, Calculator, ArrowRightLeft, ChevronDown, ChevronUp } from 'lucide-react';

type Mode = 'forward' | 'reverse';

interface LoanResult {
  // 正向 + 反向 共有
  monthlyPayment: number;     // 月供
  monthlyPrincipal: number;   // 月供本金
  monthlyInterest: number;    // 月供利息
  totalInterest: number;      // 总利息
  nominalAnnualRate: number;  // 名义年化 %（月利率×12）
  realAnnualRate: number;     // IRR 真实年化 %
  nominalMonthlyLi: number;   // 名义月息厘
  realMonthlyLi: number;      // 实际月息厘

  // 正向独有
  flatMonthlyRate?: number;   // 月分期利率 %
  // 反向独有
  derivedFlatRate?: number;   // 反推月分期利率 %
}

/**
 * 等本等息月供公式：
 *   月供 = 本金/期数 + 本金×月分期利率
 *   总利息 = 本金×月分期利率×期数
 */
function calcForward(principal: number, periods: number, flatMonthlyRate: number): LoanResult {
  const monthlyPrincipal = principal / periods;
  const monthlyInterest = principal * (flatMonthlyRate / 100);
  const monthlyPayment = monthlyPrincipal + monthlyInterest;
  const totalInterest = monthlyInterest * periods;
  const nominalAnnualRate = flatMonthlyRate * 12;
  const realAnnualRate = irrAnnual(principal, monthlyPayment, periods);
  const nominalMonthlyLi = flatMonthlyRate / 0.1;
  const realMonthlyLi = realAnnualRate / 12 / 0.1;

  return {
    monthlyPayment,
    monthlyPrincipal,
    monthlyInterest,
    totalInterest,
    nominalAnnualRate,
    realAnnualRate,
    nominalMonthlyLi,
    realMonthlyLi,
    flatMonthlyRate,
  };
}

/**
 * 反向：已知月供，反推月分期利率
 *   月分期利率 = (月供×期数 - 本金) / (本金×期数)
 */
function calcReverse(principal: number, periods: number, monthlyPayment: number): LoanResult {
  const derivedFlatRate = ((monthlyPayment * periods - principal) / (principal * periods)) * 100;
  const monthlyPrincipal = principal / periods;
  const monthlyInterest = monthlyPayment - monthlyPrincipal;
  const totalInterest = monthlyPayment * periods - principal;
  const nominalAnnualRate = derivedFlatRate * 12;
  const realAnnualRate = irrAnnual(principal, monthlyPayment, periods);
  const nominalMonthlyLi = derivedFlatRate / 0.1;
  const realMonthlyLi = realAnnualRate / 12 / 0.1;

  return {
    monthlyPayment,
    monthlyPrincipal,
    monthlyInterest,
    totalInterest,
    nominalAnnualRate,
    realAnnualRate,
    nominalMonthlyLi,
    realMonthlyLi,
    derivedFlatRate,
  };
}

/**
 * IRR 计算真实月利率（二分查找法，保证收敛）
 * 方程：PMT * (1 - (1+i)^-n) / i = PV
 * 年金现值随利率递增而递减 → f(i) 单调
 */
function irrMonthly(principal: number, monthlyPayment: number, periods: number): number {
  if (monthlyPayment * periods <= principal) return 0;

  // 二分查找：下限 = 名义月利率，上限 = 名义月利率 × 6（足够宽）
  const nominalRate = (monthlyPayment * periods - principal) / (principal * periods);
  let lo = nominalRate * 0.5;
  let hi = nominalRate * 8;

  // 确保区间包含根：f(lo) > 0, f(hi) < 0
  const pv = (r: number) => monthlyPayment / r * (1 - Math.pow(1 + r, -periods));
  // 扩展上界直到 f(hi) < 0
  for (let i = 0; i < 20; i++) {
    if (pv(hi) < principal) break;
    hi *= 1.5;
  }

  for (let iter = 0; iter < 80; iter++) {
    const mid = (lo + hi) / 2;
    const pvMid = pv(mid);
    if (Math.abs(pvMid - principal) < 0.01) return mid;
    if (pvMid > principal) {
      lo = mid; // 利率太低，PV 偏高，需要提高利率
    } else {
      hi = mid;
    }
  }

  return (lo + hi) / 2;
}

/** 月利率 → 年化利率 */
function irrAnnual(principal: number, monthlyPayment: number, periods: number): number {
  const monthly = irrMonthly(principal, monthlyPayment, periods);
  return (Math.pow(1 + monthly, 12) - 1) * 100;
}

/** 人话总结 */
function generateSummary(r: LoanResult): string {
  if (!r || r.totalInterest <= 0) return '';
  const ratio = r.realAnnualRate / r.nominalAnnualRate;
  if (ratio >= 1.9) return `真实年化利率是名义的 ${ratio.toFixed(1)} 倍，销售说的"低息"实际并不低。`;
  if (ratio >= 1.4) return `真实成本约为名义的 ${ratio.toFixed(1)} 倍，要注意合同上的年化利率。`;
  return '名义利率与真实成本差距较小，但仍建议核对合同年化利率。';
}

/** 格式化金额 */
function fmt(money: number): string {
  return money.toFixed(2);
}

/** 格式化利率百分比 */
function fmtPct(v: number): string {
  return v.toFixed(2) + '%';
}

/** 格式化厘 */
function fmtLi(v: number): string {
  return v.toFixed(2) + ' 厘';
}

export default function Toolbox() {
  const [mode, setMode] = useState<Mode>('forward');
  const [principal, setPrincipal] = useState('100000');
  const [years, setYears] = useState('5');
  const [flatRate, setFlatRate] = useState('0.2');     // 正向：月分期利率 %
  const [revInterest, setRevInterest] = useState('200'); // 反向：月供利息
  const [showWhy, setShowWhy] = useState(false);

  const periods = useMemo(() => {
    const y = parseFloat(years);
    return isNaN(y) || y <= 0 ? 60 : Math.round(y * 12);
  }, [years]);

  // 反向模式：月供 = 本金/期数 + 利息
  const revMonthlyPay = useMemo(() => {
    const p = parseFloat(principal);
    const i = parseFloat(revInterest);
    if (isNaN(p) || isNaN(i) || p <= 0 || periods <= 0) return NaN;
    return p / periods + i;
  }, [principal, periods, revInterest]);

  const result = useMemo((): LoanResult | null => {
    const p = parseFloat(principal);
    if (isNaN(p) || p <= 0 || periods <= 0) return null;

    if (mode === 'forward') {
      const r = parseFloat(flatRate);
      if (isNaN(r) || r < 0) return null;
      return calcForward(p, periods, r);
    } else {
      const m = revMonthlyPay;
      if (isNaN(m) || m <= 0) return null;
      // 月供不能小于本金/期数
      if (m < p / periods) return null;
      return calcReverse(p, periods, m);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [principal, periods, flatRate, revMonthlyPay, mode]);

  const summary = result ? generateSummary(result) : '';

  // 反向模式：即时展示月供拆分
  const reverseSplit = useMemo(() => {
    if (mode !== 'reverse') return null;
    const p = parseFloat(principal);
    if (isNaN(p) || p <= 0 || periods <= 0) return null;
    const monthlyPrincipal = p / periods;
    const monthlyInterest = revMonthlyPay - monthlyPrincipal;
    if (isNaN(monthlyInterest) || monthlyInterest < 0) return null;
    return { principal: monthlyPrincipal, interest: monthlyInterest };
  }, [principal, periods, revMonthlyPay, mode]);

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
            {/* Mode toggle */}
            <div className="flex bg-[#0B0C10] rounded-lg p-0.5">
              <button
                onClick={() => setMode('forward')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  mode === 'forward' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                正向
              </button>
              <button
                onClick={() => setMode('reverse')}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  mode === 'reverse' ? 'bg-purple-500/20 text-purple-400' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                反向
              </button>
            </div>
          </div>

          {/* Inputs */}
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

            {mode === 'forward' ? (
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">月分期利率（%）</label>
                <input type="number" step="0.01" value={flatRate}
                  onChange={e => setFlatRate(e.target.value)}
                  className={inputCls} placeholder="0.2" />
                <p className="text-[10px] text-gray-600 mt-1">销售常说的"每期手续费率"</p>
              </div>
            ) : (
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">月供拆分（元）</label>
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <div className="relative">
                      <input type="number" step="0.01"
                        value={fmt(parseFloat(principal) / periods)}
                        readOnly
                        className={`${inputCls} text-gray-500 cursor-default pr-10`} />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-600">本金</span>
                    </div>
                  </div>
                  <span className="text-gray-600 text-xs shrink-0">+</span>
                  <div className="flex-1">
                    <div className="relative">
                      <input type="number" step="0.01" value={revInterest}
                        onChange={e => setRevInterest(e.target.value)}
                        className={`${inputCls} text-amber-400 pr-10`} placeholder="200" />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-amber-400/60">利息</span>
                    </div>
                  </div>
                  <span className="text-gray-600 text-xs shrink-0">=</span>
                  <div className="flex-1">
                    <div className="relative">
                      <input type="text"
                        value={isNaN(revMonthlyPay) ? '—' : fmt(revMonthlyPay)}
                        readOnly
                        className={`${inputCls} text-white font-semibold cursor-default pr-10`} />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-gray-500">月供</span>
                    </div>
                  </div>
                </div>
                <p className="text-[10px] text-gray-600 mt-1">
                  {reverseSplit
                    ? <>本金固定 = 总金额 ÷ 期数，调整利息即可反推利率</>
                    : '本金固定 = 总金额 ÷ 期数，调整利息即可反推利率'}
                </p>
              </div>
            )}
          </div>

          {/* Results */}
          {result && (
            <div className="px-5 pb-5 space-y-4">
              {/* Rate info line for reverse mode */}
              {mode === 'reverse' && result.derivedFlatRate !== undefined && (
                <div className="bg-[#0B0C10] rounded-lg px-4 py-2.5 flex items-center gap-2 text-xs">
                  <ArrowRightLeft size={14} className="text-amber-400 shrink-0" />
                  <span className="text-gray-500">反推月分期利率：</span>
                  <span className="text-amber-400 font-mono font-medium">{fmtPct(result.derivedFlatRate)}</span>
                  <span className="text-gray-600">（名义 {fmtLi(result.derivedFlatRate / 0.1)}）</span>
                </div>
              )}

              {/* Comparison table */}
              <div className="overflow-hidden rounded-lg border border-[#2A2B30]">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-[#0B0C10]">
                      <th className="py-2.5 px-4 text-left text-gray-500 font-medium">项目</th>
                      <th className="py-2.5 px-4 text-right text-gray-500 font-medium">
                        {mode === 'forward' ? '销售说的' : '名义值'}
                      </th>
                      <th className="py-2.5 px-4 text-right font-medium text-red-400">真实成本</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1A1B20]">
                    <tr>
                      <td className="py-3 px-4 text-gray-400">月供（合计）</td>
                      <td className="py-3 px-4 text-right font-mono text-white font-semibold">{fmt(result.monthlyPayment)} 元</td>
                      <td className="py-3 px-4 text-right text-gray-600 text-[11px]">—</td>
                    </tr>
                    <tr className="bg-[#0B0C10]/50">
                      <td className="py-2 px-4 text-gray-600 text-[11px] pl-7">　本金</td>
                      <td className="py-2 px-4 text-right font-mono text-gray-500 text-[11px]">{fmt(result.monthlyPrincipal)} 元</td>
                      <td className="py-2 px-4 text-right text-gray-700 text-[10px]">—</td>
                    </tr>
                    <tr className="bg-[#0B0C10]/50">
                      <td className="py-2 px-4 text-gray-600 text-[11px] pl-7">　利息</td>
                      <td className="py-2 px-4 text-right font-mono text-amber-400/80 text-[11px]">{fmt(result.monthlyInterest)} 元</td>
                      <td className="py-2 px-4 text-right text-gray-700 text-[10px]">—</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">总利息</td>
                      <td className="py-3 px-4 text-right font-mono text-white">{fmt(result.totalInterest)} 元</td>
                      <td className="py-3 px-4 text-right text-gray-600 text-[11px]">—</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">年化利率</td>
                      <td className="py-3 px-4 text-right font-mono text-gray-400">{fmtPct(result.nominalAnnualRate)}</td>
                      <td className="py-3 px-4 text-right font-mono text-red-400 font-semibold">{fmtPct(result.realAnnualRate)}</td>
                    </tr>
                    <tr>
                      <td className="py-3 px-4 text-gray-400">月息</td>
                      <td className="py-3 px-4 text-right font-mono text-gray-400">{fmtLi(result.nominalMonthlyLi)}</td>
                      <td className="py-3 px-4 text-right font-mono text-red-400 font-semibold">{fmtLi(result.realMonthlyLi)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Summary */}
              {summary && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
                  <p className="text-xs text-red-300 leading-relaxed">
                    💡 {summary}
                  </p>
                </div>
              )}

              {/* Why different */}
              <button
                onClick={() => setShowWhy(!showWhy)}
                className="flex items-center gap-1.5 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
              >
                {showWhy ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                为什么「销售说的」和「真实成本」不一样？
              </button>
              {showWhy && (
                <div className="bg-[#0B0C10] border border-[#2A2B30] rounded-lg px-4 py-3 text-[11px] text-gray-400 leading-relaxed space-y-2">
                  <p>
                    <span className="text-white font-medium">等本等息的陷阱：</span>
                    每月利息按<span className="text-amber-400">最初的贷款总额</span>计算，固定不变。
                  </p>
                  <p>
                    但你每月都在还本金——实际占用的资金越来越少，利息却没有减少。
                    以 10 万 60 期为例：
                  </p>
                  <div className="bg-[#141518] rounded p-2.5 font-mono text-[10px] space-y-1">
                    <p>第 1 个月：欠 100,000，利息 200 → <span className="text-gray-400">月利率 0.20%</span></p>
                    <p>第 30 个月：欠 50,000，利息 200 → <span className="text-amber-400">月利率 0.40%</span></p>
                    <p>第 60 个月：欠 1,667，利息 200 → <span className="text-red-400">月利率 12%</span></p>
                  </div>
                  <p>
                    <span className="text-white">IRR 真实年化</span>是把 60 期不等的实际利率加权平均后换算的年化值，
                    反映了你<span className="text-red-400">真正的资金成本</span>。
                  </p>
                  <p className="text-gray-600">
                    签合同前，请认准合同上的「年化利率」或「IRR」数值，不要被「分期利率」或「几厘」迷惑。
                  </p>
                </div>
              )}

              {/* Formula note */}
              <p className="text-[10px] text-gray-600 leading-relaxed">
                IRR 采用二分查找法计算，精度 0.01，年化 = (1+月利率)¹² - 1。
                速算参考：年化 ≈ 月分期利率 × 期数 × 24 ÷ (期数 + 1)
              </p>
            </div>
          )}

          {/* Empty state */}
          {!result && (
            <div className="px-5 pb-8 text-center">
              <p className="text-xs text-gray-600">请输入参数查看计算结果</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
