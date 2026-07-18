import { memo, useCallback, useMemo, useState } from 'react';
import {
  ArrowRightLeft,
  Calculator,
  Landmark,
  RefreshCw,
  Search,
} from 'lucide-react';
import {
  MAX_LOAN_YEARS,
  calcAnnuity,
  calcComparison,
  calcFlatForward,
  calcFlatReverse,
  clampLoanYearsInput,
  flatSummary,
  formatLi,
  formatMoney,
  formatPercent,
  loanPeriodsFromYears,
  pickScheduleRows,
  type FlatMode,
  type LoanType,
} from '../components/cinematic-toolbox/toolboxCalculations';
import SpotlightListRow from '../components/react-bits/SpotlightListRow';
import KiNavigationShell from './KiNavigationShell';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-toolbox/cinematic-toolbox.css';

const MODES = [
  { key: 'flat', label: '等本等息', meta: '真实资金成本', icon: Calculator },
  { key: 'annuity', label: '等额本息', meta: '标准银行还款', icon: Landmark },
  { key: 'compare', label: '方案对比', meta: '双方案持有成本', icon: ArrowRightLeft },
] as const;

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  max?: number;
}

export default function CinematicToolbox() {
  const [query, setQuery] = useState('');

  return (
    <KiNavigationShell
      className="ki-shell-ingest-preview ki-shell-toolbox"
      sceneVariant="ingest"
      laserPrimary
      topAccessory={(
        <label className="ki-ingest-list-search" aria-label="搜索工具">
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索工具" />
        </label>
      )}
    >
      <ToolboxWorkspace query={query} />
    </KiNavigationShell>
  );
}

const ToolboxWorkspace = memo(function ToolboxWorkspace({ query }: { query: string }) {
  const [loanType, setLoanType] = useState<LoanType>('flat');
  const [flatMode, setFlatMode] = useState<FlatMode>('forward');
  const [principal, setPrincipal] = useState('100000');
  const [years, setYears] = useState('5');
  const [flatRate, setFlatRate] = useState('0.2');
  const [reverseInterest, setReverseInterest] = useState('200');
  const [annualRate, setAnnualRate] = useState('3');
  const [compareFlatRate, setCompareFlatRate] = useState('0.18');
  const [compareAnnualRate, setCompareAnnualRate] = useState('3');
  const handleYearsChange = useCallback((value: string) => setYears(clampLoanYearsInput(value)), []);

  const periods = useMemo(() => loanPeriodsFromYears(years), [years]);
  const principalValue = Number.parseFloat(principal);
  const reverseMonthlyPayment = principalValue / periods + Number.parseFloat(reverseInterest || '0');
  const flatResult = useMemo(() => {
    if (loanType !== 'flat' || !Number.isFinite(principalValue) || principalValue <= 0) return null;
    if (flatMode === 'forward') {
      const rate = Number.parseFloat(flatRate);
      return Number.isFinite(rate) && rate >= 0 ? calcFlatForward(principalValue, periods, rate) : null;
    }
    return Number.isFinite(reverseMonthlyPayment) && reverseMonthlyPayment >= principalValue / periods
      ? calcFlatReverse(principalValue, periods, reverseMonthlyPayment)
      : null;
  }, [flatMode, flatRate, loanType, periods, principalValue, reverseMonthlyPayment]);
  const annuityData = useMemo(() => {
    const rate = Number.parseFloat(annualRate);
    return loanType === 'annuity' && principalValue > 0 && rate >= 0
      ? calcAnnuity(principalValue, periods, rate)
      : null;
  }, [annualRate, loanType, periods, principalValue]);
  const compareData = useMemo(() => {
    if (loanType !== 'compare' || principalValue <= 0) return null;
    const flat = Number.parseFloat(compareFlatRate);
    const annual = Number.parseFloat(compareAnnualRate);
    return flat > 0 && annual >= 0 ? calcComparison(principalValue, periods, flat, annual) : null;
  }, [compareAnnualRate, compareFlatRate, loanType, periods, principalValue]);
  const visibleScheduleRows = useMemo(
    () => annuityData ? pickScheduleRows(annuityData.schedule) : [],
    [annuityData],
  );

  const activeMode = MODES.find((mode) => mode.key === loanType) || MODES[0];
  const toolVisible = '贷款利率换算器 金融 等本等息 等额本息 方案对比'.includes(query.trim());

  function reset() {
    setLoanType('flat');
    setFlatMode('forward');
    setPrincipal('100000');
    setYears('5');
    setFlatRate('0.2');
    setReverseInterest('200');
    setAnnualRate('3');
    setCompareFlatRate('0.18');
    setCompareAnnualRate('3');
  }

  return (
    <section className="ki-shell-content" aria-label="工具箱工作区">
        <div className="ki-shell-legacy-ingest">
          <div className="legacy-ingest-root is-shell-embedded cinematic-ingest ki-toolbox-embedded-root flex-1 bg-[#0B0C10] text-white flex flex-col h-full overflow-hidden">
            <div className="flex-1 overflow-y-auto custom-scrollbar px-4 md:px-8 pb-4 md:pb-8">
              <div className="max-w-[1500px] mx-auto pt-4">
                <div className="ki-ingest-split-stage">
                  <section className="ki-ingest-list-pane" aria-label="工具列表">
                    <nav className="ingest-topic-orbit ki-ingest-topic-orbit toolbox-category-tabs" aria-label="工具分类">
                      <button type="button" className="is-active is-gold"><Landmark size={17} /><span>金融</span></button>
                    </nav>
                    <div className="ki-ingest-event-list toolbox-tool-list">
                      {toolVisible ? (
                        <SpotlightListRow active>
                          <button type="button" className="ki-ingest-list-row toolbox-tool-row">
                            <span className="ki-ingest-list-topic is-gold">
                              <span className="ki-ingest-list-type-icon"><Calculator size={14} /></span>
                              <em>金融</em>
                            </span>
                            <strong>贷款利率换算器</strong>
                            <small className="ki-ingest-list-meta">名义利率、真实年化与持有成本</small>
                          </button>
                        </SpotlightListRow>
                      ) : <p className="toolbox-empty">没有匹配工具</p>}
                    </div>
                  </section>

                  <section className="ki-ingest-detail-pane" aria-label="贷款利率换算器">
                    <section className="ingest-detail-reader toolbox-detail-reader" aria-label="贷款利率换算器">
                      <header className="toolbox-detail-header">
                        <span>FINANCE TOOL · {activeMode.label}</span>
                        <h2>贷款利率换算器</h2>
                        <small><a href="/#/toolbox-old">旧版对比：/#/toolbox-old</a></small>
                        <button type="button" onClick={reset} title="重置参数" aria-label="重置参数"><RefreshCw size={17} /></button>
                      </header>

                      <nav className="ingest-detail-tabs toolbox-detail-tabs" aria-label="计算模式">
                        {MODES.map((mode) => {
                          const Icon = mode.icon;
                          return (
                            <button
                              key={mode.key}
                              type="button"
                              className={`ingest-tab-trigger launcher-action pixel-command is-${mode.key}${loanType === mode.key ? ' is-active' : ''}`}
                              onClick={() => setLoanType(mode.key)}
                            >
                              <Icon size={16} /><b>{mode.label}</b><span>{mode.meta}</span>
                            </button>
                          );
                        })}
                      </nav>

                      <div className="detail-scroll-shell">
                        <div className="detail-scroll toolbox-detail-scroll">
                          <section className="toolbox-reading-section toolbox-parameter-section">
                            <div className="toolbox-section-heading">
                              <span className="toolbox-section-label">计算参数</span>
                              {loanType === 'flat' && (
                                <div className="toolbox-segment" aria-label="等本等息计算方向">
                                  <button type="button" className={flatMode === 'forward' ? 'is-active' : ''} onClick={() => setFlatMode('forward')}>正向</button>
                                  <button type="button" className={flatMode === 'reverse' ? 'is-active' : ''} onClick={() => setFlatMode('reverse')}>反向</button>
                                </div>
                              )}
                            </div>
                            <div className={`toolbox-input-grid is-${loanType}`}>
                              <Field label="贷款金额（元）" value={principal} onChange={setPrincipal} />
                              <Field label="还款年限" value={years} onChange={handleYearsChange} hint={`${periods} 期（月）`} max={MAX_LOAN_YEARS} />
                              {loanType === 'flat' && (
                                flatMode === 'forward'
                                  ? <Field label="月分期利率（%）" value={flatRate} onChange={setFlatRate} hint="每期手续费率" />
                                  : <Field label="每月固定利息（元）" value={reverseInterest} onChange={setReverseInterest} hint={`月供 ${Number.isFinite(reverseMonthlyPayment) ? formatMoney(reverseMonthlyPayment) : '--'} 元`} />
                              )}
                              {loanType === 'annuity' && <Field label="合同年化利率（%）" value={annualRate} onChange={setAnnualRate} hint="利息按剩余本金计算" />}
                              {loanType === 'compare' && (
                                <>
                                  <Field label="等本等息月分期率（%）" value={compareFlatRate} onChange={setCompareFlatRate} />
                                  <Field label="等额本息年化率（%）" value={compareAnnualRate} onChange={setCompareAnnualRate} />
                                </>
                              )}
                            </div>
                          </section>

                          {flatResult && (
                            <>
                              <section className="toolbox-reading-section toolbox-result-section">
                                <span className="toolbox-section-label">核心结果</span>
                                {flatMode === 'reverse' && flatResult.derivedFlatRate !== undefined && (
                                  <p className="toolbox-derived-rate"><ArrowRightLeft size={14} />反推月分期利率 <b>{formatPercent(flatResult.derivedFlatRate)}</b>，名义月息 {formatLi(flatResult.derivedFlatRate / .1)}</p>
                                )}
                                <div className="toolbox-primary-results">
                                  <Result label="月供" value={`${formatMoney(flatResult.monthlyPayment)} 元`} />
                                  <Result label="真实年化" value={formatPercent(flatResult.realAnnualRate)} tone="danger" />
                                </div>
                                <div className="toolbox-metric-list">
                                  <Result label="总利息" value={`${formatMoney(flatResult.totalInterest)} 元`} />
                                  <Result label="名义年化" value={formatPercent(flatResult.nominalAnnualRate)} />
                                  <Result label="名义月息" value={formatLi(flatResult.nominalMonthlyLi)} />
                                  <Result label="真实月息" value={formatLi(flatResult.realMonthlyLi)} tone="danger" />
                                </div>
                                <p className="toolbox-result-summary">{flatSummary(flatResult)}</p>
                              </section>
                              <section className="toolbox-reading-section toolbox-cost-section">
                                <span className="toolbox-section-label">每期成本拆解</span>
                                <div className="toolbox-cost-anatomy">
                                  <span><small>每期本金</small><b>{formatMoney(flatResult.monthlyPrincipal)}</b></span><i>+</i>
                                  <span><small>固定利息</small><b>{formatMoney(flatResult.monthlyInterest)}</b></span><i>=</i>
                                  <span className="is-total"><small>每期月供</small><b>{formatMoney(flatResult.monthlyPayment)}</b></span>
                                </div>
                              </section>
                              <section className="toolbox-reading-section toolbox-explanation">
                                <span className="toolbox-section-label">成本说明</span>
                                <h3>为什么“销售说的”和“真实成本”不一样？</h3>
                                <p>等本等息每期利息始终按初始本金计算，但本金会逐月归还。实际占用的资金越来越少，因此真实年化通常高于简单相乘得到的名义年化。</p>
                                <p>比较不同方案时，应以合同披露的综合年化利率和提前结清成本为准。</p>
                              </section>
                            </>
                          )}

                          {annuityData && (
                            <>
                              <section className="toolbox-reading-section toolbox-result-section">
                                <span className="toolbox-section-label">核心结果</span>
                                <div className="toolbox-primary-results">
                                  <Result label="月供" value={`${formatMoney(annuityData.result.monthlyPayment)} 元`} />
                                  <Result label="还款总额" value={`${formatMoney(annuityData.result.totalPayment)} 元`} />
                                </div>
                                <div className="toolbox-metric-list">
                                  <Result label="总利息" value={`${formatMoney(annuityData.result.totalInterest)} 元`} />
                                  <Result label="利息占比" value={formatPercent(annuityData.result.interestRatio)} />
                                </div>
                              </section>
                              <section className="toolbox-reading-section toolbox-schedule-wrap">
                                <span className="toolbox-section-label">还款计划明细</span>
                                <div className="toolbox-schedule-head"><span>期数</span><span>当期月供</span><span>当期本金</span><span>当期利息</span><span>剩余本金</span></div>
                                <div className="toolbox-schedule">
                                  {visibleScheduleRows.map((row) => (
                                    <span key={row.period}><b>第 {row.period} 期</b><em>{formatMoney(row.payment)}</em><em>{formatMoney(row.principal)}</em><em>{formatMoney(row.interest)}</em><small>{formatMoney(row.balance)}</small></span>
                                  ))}
                                </div>
                              </section>
                            </>
                          )}

                          {compareData && (
                            <>
                              <section className="toolbox-reading-section toolbox-result-section">
                                <span className="toolbox-section-label">方案核心对比</span>
                                <div className="toolbox-primary-results">
                                  <Result label="等本等息月供" value={`${formatMoney(compareData.flatMonthly)} 元`} tone="danger" />
                                  <Result label="等额本息月供" value={`${formatMoney(compareData.annuityMonthly)} 元`} />
                                </div>
                                <div className="toolbox-metric-list">
                                  <Result label="等本等息总利息" value={`${formatMoney(compareData.flatTotalInterest)} 元`} tone="danger" />
                                  <Result label="等额本息总利息" value={`${formatMoney(compareData.annuityTotalInterest)} 元`} />
                                  <Result label="等本等息真实年化" value={formatPercent(compareData.flatIrr)} tone="danger" />
                                  <Result label="等额本息年化" value={formatPercent(compareData.annualRate)} />
                                </div>
                                <p className="toolbox-recommendation"><ArrowRightLeft size={15} /><span>{compareData.recommendation}{compareData.tipping ? ` 成本拐点约在第 ${compareData.tipping.month} 期。` : ''}</span></p>
                              </section>
                              <section className="toolbox-reading-section toolbox-comparison-path">
                                <span className="toolbox-section-label">持有节点</span>
                                <header><span>期数</span><span>等本等息总成本</span><span>等额本息总成本</span><span>成本差</span></header>
                                {compareData.rows.map((row) => (
                                  <div key={row.month} className={`is-${row.winner}`}><b>{row.month} 期</b><span>{formatMoney(row.flatTotal)}</span><span>{formatMoney(row.annuityTotal)}</span><em>{row.diff > 0 ? '+' : ''}{formatMoney(row.diff)}</em></div>
                                ))}
                              </section>
                            </>
                          )}
                        </div>
                      </div>
                    </section>
                  </section>
                </div>
              </div>
            </div>
          </div>
        </div>
    </section>
  );
});

const Field = memo(function Field({ label, value, onChange, hint, max }: FieldProps) {
  return (
    <label className="toolbox-field">
      <span className="toolbox-field-head">
        <span>{label}</span>
        {hint && <small>{hint}</small>}
      </span>
      <input type="number" value={value} max={max} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
});

function Result({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <span className={tone ? `is-${tone}` : ''}><small>{label}</small><b>{value}</b></span>;
}
