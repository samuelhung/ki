import { useMemo, useState, type CSSProperties } from 'react';
import { ArrowRightLeft, Calculator, RefreshCw, Table, Wrench } from 'lucide-react';
import { useCurtain } from '../CurtainContext';
import CinematicLaserWorkspace from '../components/cinematic/CinematicLaserWorkspace';
import CinematicTemplatePage from '../components/cinematic/CinematicTemplatePage';
import { CINEMATIC_LASER_PRESET } from '../components/cinematic/cinematicLaserPreset';
import { useCinematicTemplateLayout } from '../components/cinematic/useCinematicTemplateLayout';
import { useLaserRenderProfile } from '../components/cinematic-ingest/useLaserRenderProfile';
import {
  calcAnnuity,
  calcComparison,
  calcFlatForward,
  calcFlatReverse,
  flatSummary,
  formatLi,
  formatMoney,
  formatPercent,
  pickScheduleRows,
  type FlatMode,
  type LoanType,
} from '../components/cinematic-toolbox/toolboxCalculations';
import LaserFlow from '../components/react-bits/LaserFlow';
import '../components/cinematic/cinematic.css';
import '../components/cinematic-ingest/cinematic-ingest.css';
import '../components/cinematic-ingest/cinematic-ingest-performance.css';
import '../components/cinematic-toolbox/cinematic-toolbox.css';

const MODES = [
  { key: 'flat', label: '等本等息', meta: 'FLAT', accent: 'gold' },
  { key: 'annuity', label: '等额本息', meta: 'ANNUITY', accent: 'cyan' },
  { key: 'compare', label: '方案对比', meta: 'COMPARE', accent: 'violet' },
] as const;

export default function CinematicToolbox() {
  const { navigateWithCurtain } = useCurtain();
  const { profile, style } = useCinematicTemplateLayout('system');
  const { viewportHeight, laserRenderProfile } = useLaserRenderProfile();
  const [activeHub, setActiveHub] = useState<string | null>(null);
  const [loanType, setLoanType] = useState<LoanType>('flat');
  const [flatMode, setFlatMode] = useState<FlatMode>('forward');
  const [principal, setPrincipal] = useState('100000');
  const [years, setYears] = useState('5');
  const [flatRate, setFlatRate] = useState('0.2');
  const [reverseInterest, setReverseInterest] = useState('200');
  const [annualRate, setAnnualRate] = useState('3');
  const [compareFlatRate, setCompareFlatRate] = useState('0.18');
  const [compareAnnualRate, setCompareAnnualRate] = useState('3');
  const [showSchedule, setShowSchedule] = useState(false);

  const periods = useMemo(() => Math.max(1, Math.round((Number.parseFloat(years) || 5) * 12)), [years]);
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
    return loanType === 'annuity' && principalValue > 0 && rate > 0 ? calcAnnuity(principalValue, periods, rate) : null;
  }, [annualRate, loanType, periods, principalValue]);
  const compareData = useMemo(() => {
    if (loanType !== 'compare' || principalValue <= 0) return null;
    const flat = Number.parseFloat(compareFlatRate);
    const annual = Number.parseFloat(compareAnnualRate);
    if (!(flat > 0) || !(annual > 0)) return null;
    return calcComparison(principalValue, periods, flat, annual);
  }, [compareAnnualRate, compareFlatRate, loanType, periods, principalValue]);

  const reset = () => {
    setPrincipal('100000'); setYears('5'); setFlatRate('0.2'); setReverseInterest('200');
    setAnnualRate('3'); setCompareFlatRate('0.18'); setCompareAnnualRate('3'); setShowSchedule(false);
  };
  const activeMode = MODES.find((mode) => mode.key === loanType) || MODES[0];
  const coreBoxHeight = Math.min(Math.max(viewportHeight * 0.158, 126), 178);
  const beamVerticalOffset = (coreBoxHeight - 6) / Math.max(viewportHeight, 1) - 0.5;
  const primaryResult = flatResult?.monthlyPayment || annuityData?.result.monthlyPayment || compareData?.flatMonthly || 0;
  const totalInterest = flatResult?.totalInterest || annuityData?.result.totalInterest || compareData?.flatTotalInterest || 0;

  const status = (
    <section className="ingest-observation cinematic-observation toolbox-status" aria-label="工具状态">
      <div className="panel-status"><i className="signal-dot" /><span>计算工具</span></div>
      <span>贷款利率换算与方案成本校验</span>
      <div className="system-status-summary"><span className="is-good">引擎 就绪</span><span className="is-cyan">模式 {activeMode.label}</span></div>
      <div className="panel-detail-grid"><span>本金<b>{principal || '--'}</b></span><span>期限<b>{periods}期</b></span><span>月供<b>{primaryResult ? formatMoney(primaryResult) : '--'}</b></span><span>利息<b>{totalInterest ? formatMoney(totalInterest) : '--'}</b></span></div>
    </section>
  );
  const commands = (
    <section className="ingest-command-launcher" aria-label="工具操作">
      <div className="launcher-actions">
        <button className="launcher-action ingest-command-metric is-douyin" onClick={reset}><RefreshCw size={15} /><b>重置参数</b><span>DEFAULT</span><small>RESET</small></button>
        <button className="launcher-action ingest-command-metric is-file" onClick={() => setLoanType('compare')}><ArrowRightLeft size={15} /><b>方案对比</b><span>DUAL</span><small>COMPARE</small></button>
        <button className="launcher-action ingest-command-metric is-concept" onClick={() => { setLoanType('annuity'); setShowSchedule(true); }}><Table size={15} /><b>还款计划</b><span>{periods}期</span><small>SCHEDULE</small></button>
      </div>
    </section>
  );
  const index = (
    <>
      <div className="ingest-topic-orbit toolbox-mode-orbit" aria-label="工具分类"><button className="is-active is-gold"><Calculator size={14} /><span>金融</span></button></div>
      <div className="ingest-index-list toolbox-mode-list">{MODES.map((mode, index) => <button key={mode.key} className={`ingest-index-item${loanType === mode.key ? ' is-active' : ''}`} style={{ '--index-depth-scale': 1 - index * 0.045, '--index-depth-z': `${-index * 3}px`, '--index-depth-opacity': 1 - index * 0.1 } as CSSProperties} onClick={() => setLoanType(mode.key)}><div className="index-title"><b>{mode.label}</b><span><em className={`is-${mode.accent}`}>{mode.meta}</em></span></div></button>)}</div>
    </>
  );

  return (
    <CinematicTemplatePage
      className="cinematic-toolbox"
      profile={profile}
      topic="cyan"
      style={style}
      variant="system"
      status={status}
      commands={commands}
      workspace={<CinematicLaserWorkspace ariaLabel="工具计算舱" indexAriaLabel="工具模式" index={index} stageAriaLabel="贷款计算器" stage={<><LaserFlow {...CINEMATIC_LASER_PRESET} verticalBeamOffset={beamVerticalOffset} dpr={laserRenderProfile.dpr} maxFps={laserRenderProfile.maxFps} /><ToolDetail loanType={loanType} setLoanType={setLoanType} flatMode={flatMode} setFlatMode={setFlatMode} principal={principal} setPrincipal={setPrincipal} years={years} setYears={setYears} periods={periods} flatRate={flatRate} setFlatRate={setFlatRate} reverseInterest={reverseInterest} setReverseInterest={setReverseInterest} annualRate={annualRate} setAnnualRate={setAnnualRate} compareFlatRate={compareFlatRate} setCompareFlatRate={setCompareFlatRate} compareAnnualRate={compareAnnualRate} setCompareAnnualRate={setCompareAnnualRate} flatResult={flatResult} annuityData={annuityData} compareData={compareData} showSchedule={showSchedule} setShowSchedule={setShowSchedule} /><div className="laser-media-box toolbox-result-box"><span>CALCULATION CORE</span><b>{activeMode.label}</b><div><em>月供<strong>{primaryResult ? `${formatMoney(primaryResult)} 元` : '--'}</strong></em><em>总利息<strong>{totalInterest ? `${formatMoney(totalInterest)} 元` : '--'}</strong></em><em>期限<strong>{periods} 期</strong></em></div></div></>} />}
      activeHub={activeHub}
      onActiveHubChange={setActiveHub}
      onNavigate={(path) => path === '/docs' ? window.open('/docs', '_blank', 'noopener,noreferrer') : navigateWithCurtain(path)}
    />
  );
}

function Field({ label, value, onChange, hint }: { label: string; value: string; onChange: (value: string) => void; hint?: string }) {
  return <label className="toolbox-field"><span>{label}</span><input type="number" value={value} onChange={(event) => onChange(event.target.value)} />{hint && <small>{hint}</small>}</label>;
}

function ToolDetail(props: any) {
  return (
    <section className="ingest-detail-reader toolbox-detail-reader" aria-label="计算详情">
      <header><span>CALCULATION SURFACE</span><h2>贷款利率换算器</h2><small>旧版对比：/#/toolbox-old</small></header>
      <div className="detail-scroll-shell"><div className="detail-scroll toolbox-detail-body">
        <nav className="ingest-detail-tabs toolbox-detail-tabs">{MODES.map((mode) => <button key={mode.key} className={`ingest-tab-trigger launcher-action pixel-command${props.loanType === mode.key ? ' is-active' : ''}`} onClick={() => props.setLoanType(mode.key)}><Calculator size={14} /><b>{mode.label}</b><span>{mode.meta}</span></button>)}</nav>
        <div className={`toolbox-input-grid is-${props.loanType}`}><Field label="贷款金额（元）" value={props.principal} onChange={props.setPrincipal} /><Field label="还款年限" value={props.years} onChange={props.setYears} hint={`${props.periods} 期（月）`} />
          {props.loanType === 'flat' && <><div className="toolbox-segment"><button className={props.flatMode === 'forward' ? 'is-active' : ''} onClick={() => props.setFlatMode('forward')}>正向</button><button className={props.flatMode === 'reverse' ? 'is-active' : ''} onClick={() => props.setFlatMode('reverse')}>反向</button></div>{props.flatMode === 'forward' ? <Field label="月分期利率（%）" value={props.flatRate} onChange={props.setFlatRate} /> : <Field label="每月固定利息（元）" value={props.reverseInterest} onChange={props.setReverseInterest} />}</>}
          {props.loanType === 'annuity' && <Field label="合同年化利率（%）" value={props.annualRate} onChange={props.setAnnualRate} />}
          {props.loanType === 'compare' && <><Field label="等本等息月分期率（%）" value={props.compareFlatRate} onChange={props.setCompareFlatRate} /><Field label="等额本息年化率（%）" value={props.compareAnnualRate} onChange={props.setCompareAnnualRate} /></>}
        </div>
        {props.flatResult && <div className="toolbox-results"><Result label="月供" value={`${formatMoney(props.flatResult.monthlyPayment)} 元`} /><Result label="总利息" value={`${formatMoney(props.flatResult.totalInterest)} 元`} /><Result label="名义年化" value={formatPercent(props.flatResult.nominalAnnualRate)} /><Result label="真实年化" value={formatPercent(props.flatResult.realAnnualRate)} tone="danger" /><Result label="名义月息" value={formatLi(props.flatResult.nominalMonthlyLi)} /><Result label="真实月息" value={formatLi(props.flatResult.realMonthlyLi)} tone="danger" /><p>{flatSummary(props.flatResult)}</p></div>}
        {props.annuityData && <><div className="toolbox-results"><Result label="月供" value={`${formatMoney(props.annuityData.result.monthlyPayment)} 元`} /><Result label="还款总额" value={`${formatMoney(props.annuityData.result.totalPayment)} 元`} /><Result label="总利息" value={`${formatMoney(props.annuityData.result.totalInterest)} 元`} /><Result label="利息占比" value={formatPercent(props.annuityData.result.interestRatio)} /></div><button className="toolbox-schedule-toggle" onClick={() => props.setShowSchedule(!props.showSchedule)}><Table size={14} />还款计划明细</button>{props.showSchedule && <div className="toolbox-schedule-wrap"><div className="toolbox-schedule-head"><span>期数</span><span>当期月供</span><span>剩余本金</span></div><div className="toolbox-schedule">{pickScheduleRows(props.annuityData.schedule).map((row: any) => <span key={row.period}><b>第 {row.period} 期</b><em>{formatMoney(row.payment)}</em><small>{formatMoney(row.balance)}</small></span>)}</div></div>}</>}
        {props.compareData && <><div className="toolbox-compare"><Result label="等本等息月供" value={`${formatMoney(props.compareData.flatMonthly)} 元`} tone="danger" /><Result label="等额本息月供" value={`${formatMoney(props.compareData.annuityMonthly)} 元`} /><Result label="等本等息总利息" value={`${formatMoney(props.compareData.flatTotalInterest)} 元`} tone="danger" /><Result label="等额本息总利息" value={`${formatMoney(props.compareData.annuityTotalInterest)} 元`} /><Result label="等本等息真实年化" value={formatPercent(props.compareData.flatIrr)} tone="danger" /><Result label="等额本息年化" value={formatPercent(props.compareData.annualRate)} /></div><section className="toolbox-comparison-path"><header><span>持有节点</span><span>等本等息总成本</span><span>等额本息总成本</span><span>成本差</span></header>{props.compareData.rows.map((row: any) => <div key={row.month} className={row.winner === 'annuity' ? 'is-annuity' : row.winner === 'flat' ? 'is-flat' : ''}><b>{row.month} 期</b><span>{formatMoney(row.flatTotal)}</span><span>{formatMoney(row.annuityTotal)}</span><em>{row.diff > 0 ? '+' : ''}{formatMoney(row.diff)}</em></div>)}</section><p className="toolbox-recommendation"><ArrowRightLeft size={14} /><span>{props.compareData.recommendation}{props.compareData.tipping ? ` 成本拐点约在第 ${props.compareData.tipping.month} 期。` : ''}</span></p></>}
      </div></div>
    </section>
  );
}

function Result({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <span className={tone ? `is-${tone}` : ''}><small>{label}</small><b>{value}</b></span>;
}
