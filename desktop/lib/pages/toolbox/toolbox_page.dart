import 'dart:math';
import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

// ═══════════════════════════════════════════
// Types
// ═══════════════════════════════════════════
enum LoanType { flat, annuity, compare }
enum FlatMode { forward, reverse }

class FlatResult {
  final double monthlyPayment, monthlyPrincipal, monthlyInterest;
  final double totalInterest, nominalAnnualRate, realAnnualRate;
  final double nominalMonthlyLi, realMonthlyLi;
  final double? flatMonthlyRate, derivedFlatRate;
  FlatResult(this.monthlyPayment, this.monthlyPrincipal, this.monthlyInterest,
      this.totalInterest, this.nominalAnnualRate, this.realAnnualRate,
      this.nominalMonthlyLi, this.realMonthlyLi,
      {this.flatMonthlyRate, this.derivedFlatRate});
}

class AnnuityResult {
  final double monthlyPayment, totalPayment, totalInterest, interestRatio;
  AnnuityResult(this.monthlyPayment, this.totalPayment, this.totalInterest, this.interestRatio);
}

class RepaymentRow {
  final int period;
  final double payment, principal, interest, balance;
  RepaymentRow(this.period, this.payment, this.principal, this.interest, this.balance);
}

class CompareRow {
  final int month;
  final double fTotal, aTotal, diff;
  final String winner; // 'flat' | 'annuity' | 'tie'
  CompareRow(this.month, this.fTotal, this.aTotal, this.diff, this.winner);
}

class CompareData {
  final double fMonthly, fPrincipal, fInterest, fTotalInt, fIrr;
  final double aMonthly, aTotalInt;
  final List<CompareRow> rows;
  final CompareRow? tipping;
  CompareData(this.fMonthly, this.fPrincipal, this.fInterest, this.fTotalInt,
      this.fIrr, this.aMonthly, this.aTotalInt, this.rows, this.tipping);
}

// ═══════════════════════════════════════════
// Math helpers
// ═══════════════════════════════════════════
String fmt(double v) => v.toStringAsFixed(2);
String fmtPct(double v) => '${v.toStringAsFixed(2)}%';
String fmtLi(double v) => '${v.toStringAsFixed(2)} 厘';

double irrMonthly(double principal, double monthlyPayment, int periods) {
  if (monthlyPayment * periods <= principal) return 0;
  final nominalRate = (monthlyPayment * periods - principal) / (principal * periods);
  double lo = nominalRate * 0.5, hi = nominalRate * 8;
  double pv(double r) => monthlyPayment / r * (1 - pow(1 + r, -periods));
  for (int i = 0; i < 20; i++) { if (pv(hi) < principal) break; hi *= 1.5; }
  for (int iter = 0; iter < 80; iter++) {
    final mid = (lo + hi) / 2, pvMid = pv(mid);
    if ((pvMid - principal).abs() < 0.01) return mid;
    if (pvMid > principal) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

double irrAnnual(double principal, double monthlyPayment, int periods) =>
    (pow(1 + irrMonthly(principal, monthlyPayment, periods), 12) - 1) * 100;

FlatResult calcFlatForward(double principal, int periods, double flatMonthlyRate) {
  final mp = principal / periods;
  final mi = principal * (flatMonthlyRate / 100);
  final mpmt = mp + mi;
  final ti = mi * periods;
  final nar = flatMonthlyRate * 12;
  final rar = irrAnnual(principal, mpmt, periods);
  return FlatResult(mpmt, mp, mi, ti, nar, rar,
      flatMonthlyRate / 0.1, rar / 12 / 0.1, flatMonthlyRate: flatMonthlyRate);
}

FlatResult calcFlatReverse(double principal, int periods, double monthlyPayment) {
  final dfr = ((monthlyPayment * periods - principal) / (principal * periods)) * 100;
  final mp = principal / periods;
  final mi = monthlyPayment - mp;
  final ti = monthlyPayment * periods - principal;
  final nar = dfr * 12;
  final rar = irrAnnual(principal, monthlyPayment, periods);
  return FlatResult(monthlyPayment, mp, mi, ti, nar, rar,
      dfr / 0.1, rar / 12 / 0.1, derivedFlatRate: dfr);
}

/// Annuity monthly payment = P * r * (1+r)^n / ((1+r)^n - 1)
({AnnuityResult result, List<RepaymentRow> schedule}) calcAnnuity(
    double principal, int periods, double annualRate) {
  final mr = annualRate / 100 / 12;
  final mpmt = principal * mr * pow(1 + mr, periods) / (pow(1 + mr, periods) - 1);
  final tp = mpmt * periods;
  final ti = tp - principal;
  final ir = (ti / tp) * 100;
  final schedule = <RepaymentRow>[];
  double bal = principal;
  for (int i = 1; i <= periods; i++) {
    final interest = bal * mr;
    final principalPart = mpmt - interest;
    bal -= principalPart;
    schedule.add(RepaymentRow(i, mpmt, principalPart, interest, max(bal, 0)));
  }
  return (result: AnnuityResult(mpmt, tp, ti, ir), schedule: schedule);
}

CompareData calcCompare(double principal, int periods, double flatRate, double annualRate) {
  final fMonthly = principal / periods + principal * (flatRate / 100);
  final fPrincipal = principal / periods;
  final fInterest = principal * (flatRate / 100);
  final fTotalInt = fInterest * periods;
  final fIrr = irrAnnual(principal, fMonthly, periods);
  final aMr = annualRate / 100 / 12;
  final aMonthly = principal * aMr * pow(1 + aMr, periods) / (pow(1 + aMr, periods) - 1);
  final aTotalInt = aMonthly * periods - principal;
  double aBal(int m) => principal * pow(1 + aMr, m) -
      aMonthly * (pow(1 + aMr, m) - 1) / aMr;
  final checkpoints = [12, 24, 36, 48, 60].where((m) => m <= periods).toList();
  final rows = checkpoints.map((m) {
    final fPaid = m * fMonthly, fBal = principal - m * fPrincipal, fTotal = fPaid + fBal;
    final aPaid = m * aMonthly, aBal_ = aBal(m), aTotal = aPaid + aBal_;
    final diff = fTotal - aTotal;
    return CompareRow(m, fTotal, aTotal, diff,
        diff < 0 ? 'flat' : diff > 0 ? 'annuity' : 'tie');
  }).toList();
  final tipping = rows.cast<CompareRow?>().firstWhere((r) => r!.diff >= 0, orElse: () => null);
  return CompareData(fMonthly, fPrincipal, fInterest, fTotalInt, fIrr,
      aMonthly, aTotalInt, rows, tipping);
}

String flatSummary(FlatResult r) {
  if (r.totalInterest <= 0) return '';
  final ratio = r.realAnnualRate / r.nominalAnnualRate;
  if (ratio >= 1.9) return '真实年化利率是名义的 ${ratio.toStringAsFixed(1)} 倍，销售说的"低息"实际并不低。';
  if (ratio >= 1.4) return '真实成本约为名义的 ${ratio.toStringAsFixed(1)} 倍，要注意合同上的年化利率。';
  return '名义利率与真实成本差距较小，但仍建议核对合同年化利率。';
}

/// Pick: first 3 + every 12th + last 3
List<RepaymentRow> pickScheduleRows(List<RepaymentRow> schedule) {
  if (schedule.length <= 12) return schedule;
  final n = schedule.length;
  final rows = <RepaymentRow>[];
  for (int i = 0; i < 3; i++) rows.add(schedule[i]);
  for (int i = 11; i < n - 3; i += 12) {
    if (i > 2 && i < n - 3) rows.add(schedule[i]);
  }
  for (int i = n - 3; i < n; i++) rows.add(schedule[i]);
  return rows;
}

// ═══════════════════════════════════════════
// Toolbox page
// ═══════════════════════════════════════════
class ToolboxPage extends StatefulWidget {
  const ToolboxPage({super.key});
  @override
  State<ToolboxPage> createState() => _ToolboxPageState();
}

class _ToolboxPageState extends State<ToolboxPage> {
  LoanType _loanType = LoanType.flat;
  FlatMode _flatMode = FlatMode.forward;
  bool _showWhy = false, _showSchedule = false;

  final _principalCtl = TextEditingController(text: '100000');
  final _yearsCtl = TextEditingController(text: '5');
  final _flatRateCtl = TextEditingController(text: '0.2');
  final _revInterestCtl = TextEditingController(text: '200');
  final _annualRateCtl = TextEditingController(text: '3');
  final _cmpFlatRateCtl = TextEditingController(text: '0.18');
  final _cmpAnnualRateCtl = TextEditingController(text: '3');

  int get periods {
    final y = double.tryParse(_yearsCtl.text) ?? 5;
    return y <= 0 ? 60 : (y * 12).round();
  }

  double _parse(String s) => double.tryParse(s) ?? double.nan;

  @override
  void dispose() {
    _principalCtl.dispose(); _yearsCtl.dispose(); _flatRateCtl.dispose();
    _revInterestCtl.dispose(); _annualRateCtl.dispose();
    _cmpFlatRateCtl.dispose(); _cmpAnnualRateCtl.dispose();
    super.dispose();
  }

  // ═══ Input field ═══
  Widget _input(String label, TextEditingController ctl, {String? hint, String? suffix, IconData? icon, Color? textColor}) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
      const SizedBox(height: 4),
      TextField(
        controller: ctl,
        style: TextStyle(color: textColor ?? AppTheme.textPrimary, fontSize: 13, fontFamily: 'monospace'),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
          suffixText: suffix,
          suffixStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 11),
          prefixIcon: icon != null ? Icon(icon, size: 14, color: AppTheme.textMuted) : null,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          filled: true, fillColor: AppTheme.background,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: AppTheme.accent.withValues(alpha: 0.5))),
        ),
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        onChanged: (_) => setState(() {}),
      ),
    ]);
  }

  // ═══ Table helpers ═══
  Widget _tableHeader(List<String> cols, {List<Color>? colors}) {
    return Container(
      color: AppTheme.background,
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
      child: Row(children: List.generate(cols.length, (i) => Expanded(
        child: Text(cols[i],
          textAlign: i == 0 ? TextAlign.left : TextAlign.right,
          style: TextStyle(color: colors?[i] ?? AppTheme.textMuted, fontSize: 11, fontWeight: FontWeight.w500)),
      ))),
    );
  }

  Widget _tableRow(List<Widget> cells, {Color? bg}) {
    return Container(
      color: bg,
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
      child: Row(children: cells.asMap().entries.map((e) => Expanded(
        child: e.key == 0 ? Align(alignment: Alignment.centerLeft, child: e.value)
            : Align(alignment: Alignment.centerRight, child: e.value),
      )).toList()),
    );
  }

  Widget _tcell(String text, {Color? color, bool bold = false, double size = 12}) =>
      Text(text, style: TextStyle(color: color ?? AppTheme.textSecondary, fontSize: size, fontWeight: bold ? FontWeight.w600 : FontWeight.normal, fontFamily: 'monospace'));

  Widget _resultCard(String title, Color accent, List<Widget> rows) {
    return Container(
      decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), border: Border.all(color: AppTheme.border)),
      clipBehavior: Clip.antiAlias,
      child: Column(children: [
        Container(
          width: double.infinity, padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
          color: AppTheme.background,
          child: Text(title, style: TextStyle(color: accent, fontSize: 11, fontWeight: FontWeight.w500)),
        ),
        ...rows,
      ]),
    );
  }

  Widget _tipBox(String text, Color color) => Container(
    width: double.infinity, padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(8), border: Border.all(color: color.withValues(alpha: 0.2))),
    child: Text(text, style: TextStyle(color: color.withValues(alpha: 0.85), fontSize: 11, height: 1.5)),
  );

  Widget _pill(String label, {bool active = false, VoidCallback? onTap, Color? activeColor}) {
    final color = activeColor ?? AppTheme.accent;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: active ? color.withValues(alpha: 0.2) : Colors.transparent,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(label, style: TextStyle(color: active ? color : AppTheme.textMuted, fontSize: 11, fontWeight: FontWeight.w500)),
      ),
    );
  }

  // ═══════════════════════════════════
  // Flat result table
  // ═══════════════════════════════════
  Widget _flatResultTable(FlatResult r, FlatMode mode) {
    final label1 = mode == FlatMode.forward ? '销售说的' : '名义值';
    return _resultCard('计算结果', AppTheme.error, [
      _tableHeader([label1, '真实成本'], colors: [AppTheme.textMuted, AppTheme.error]),
      _tableRow([_tcell('月供（合计）', size: 12), _tcell('${fmt(r.monthlyPayment)} 元', color: AppTheme.textPrimary, bold: true), _tcell('—', color: AppTheme.textMuted, size: 11)]),
      _tableRow([_tcell('　本金', color: AppTheme.textMuted, size: 11), _tcell('${fmt(r.monthlyPrincipal)} 元', color: AppTheme.textMuted, size: 11), _tcell('—', color: AppTheme.textMuted, size: 10)]),
      _tableRow([_tcell('　利息', color: AppTheme.textMuted, size: 11), _tcell('${fmt(r.monthlyInterest)} 元', color: AppTheme.amber.withValues(alpha: 0.8), size: 11), _tcell('—', color: AppTheme.textMuted, size: 10)]),
      _tableRow([_tcell('总利息', size: 12), _tcell('${fmt(r.totalInterest)} 元', color: AppTheme.textPrimary), _tcell('—', color: AppTheme.textMuted, size: 11)]),
      _tableRow([_tcell('年化利率', size: 12), _tcell(fmtPct(r.nominalAnnualRate), color: AppTheme.textMuted), _tcell(fmtPct(r.realAnnualRate), color: AppTheme.error, bold: true)]),
      _tableRow([_tcell('月息', size: 12), _tcell(fmtLi(r.nominalMonthlyLi), color: AppTheme.textMuted), _tcell(fmtLi(r.realMonthlyLi), color: AppTheme.error, bold: true)]),
    ]);
  }

  // ═══════════════════════════════════
  // Annuity result table
  // ═══════════════════════════════════
  Widget _annuityResultTable(AnnuityResult ar) {
    return _resultCard('计算结果', AppTheme.emerald, [
      _tableHeader(['项目', '数值']),
      _tableRow([_tcell('月供', size: 12), _tcell('${fmt(ar.monthlyPayment)} 元', color: AppTheme.textPrimary, bold: true)]),
      _tableRow([_tcell('还款总额', size: 12), _tcell('${fmt(ar.totalPayment)} 元', color: AppTheme.textPrimary)]),
      _tableRow([_tcell('利息总额', size: 12), _tcell('${fmt(ar.totalInterest)} 元', color: AppTheme.amber.withValues(alpha: 0.8))]),
      _tableRow([_tcell('月息', size: 12), _tcell(fmtLi((_parse(_annualRateCtl.text)) / 12 / 0.1), color: AppTheme.textMuted)]),
      _tableRow([_tcell('利息占比', size: 12), _tcell(fmtPct(ar.interestRatio), color: AppTheme.textMuted)]),
    ]);
  }

  // ═══════════════════════════════════
  // Compare tables
  // ═══════════════════════════════════
  Widget _compareResultTable(CompareData cd) {
    return Column(children: [
      // Basic comparison
      _resultCard('基本信息对比', AppTheme.sky, [
        _tableHeader(['项目', '等本等息', '等额本息'], colors: [AppTheme.textMuted, AppTheme.error, AppTheme.emerald]),
        _tableRow([_tcell('月供', size: 12), _tcell('${fmt(cd.fMonthly)}', color: AppTheme.textPrimary, bold: true), _tcell('${fmt(cd.aMonthly)}', color: AppTheme.textPrimary, bold: true)]),
        _tableRow([_tcell('其中本金', size: 12), _tcell('${fmt(cd.fPrincipal)}', color: AppTheme.textMuted), _tcell('—', color: AppTheme.textMuted)]),
        _tableRow([_tcell('利息（首期→末期）', size: 12), _tcell('${fmt(cd.fInterest)}（固定）', color: AppTheme.amber.withValues(alpha: 0.8)), _tcell('${fmt(cd.aMonthly - cd.fPrincipal)}→递减', color: AppTheme.amber.withValues(alpha: 0.8))]),
        _tableRow([_tcell('借满总利息', size: 12), _tcell('${fmt(cd.fTotalInt)}', color: AppTheme.amber.withValues(alpha: 0.8)), _tcell('${fmt(cd.aTotalInt)}', color: AppTheme.amber.withValues(alpha: 0.8))]),
        _tableRow([_tcell('IRR 真实年化', size: 12), _tcell(fmtPct(cd.fIrr), color: AppTheme.error, bold: true), _tcell(fmtPct(_parse(_cmpAnnualRateCtl.text)), color: AppTheme.emerald)]),
      ]),
      const SizedBox(height: 16),
      // Checkpoints
      _resultCard('提前还清总支出对比', AppTheme.sky, [
        _tableHeader(['提前还清时间', '等本等息', '等额本息', '差额', '结果'], colors: [AppTheme.textMuted, AppTheme.error, AppTheme.emerald, AppTheme.textMuted, AppTheme.textMuted]),
        ...cd.rows.map((r) {
          final diffColor = r.diff < 0 ? AppTheme.error : r.diff > 0 ? AppTheme.emerald : AppTheme.textMuted;
          final winnerColor = r.winner == 'flat' ? AppTheme.error : r.winner == 'annuity' ? AppTheme.emerald : AppTheme.textMuted;
          final winnerLabel = r.winner == 'flat' ? '等本等息' : r.winner == 'annuity' ? '等额本息' : '持平';
          return _tableRow([
            _tcell('${r.month} 期（${r.month / 12} 年）'),
            _tcell(fmt(r.fTotal), color: AppTheme.textSecondary),
            _tcell(fmt(r.aTotal), color: AppTheme.textSecondary),
            _tcell('${r.diff < 0 ? '-' : '+'}${fmt(r.diff.abs())}', color: diffColor, bold: true),
            Container(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(color: winnerColor.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(4)),
              child: Text(winnerLabel, style: TextStyle(color: winnerColor, fontSize: 10, fontWeight: FontWeight.w500))),
          ]);
        }),
      ]),
    ]);
  }

  // ═══════════════════════════════════
  // Build
  // ═══════════════════════════════════
  @override
  Widget build(BuildContext context) {
    final p = _parse(_principalCtl.text);

    // Results
    FlatResult? flatResult = null;
    if (_loanType == LoanType.flat && p > 0 && periods > 0) {
      if (_flatMode == FlatMode.forward) {
        final r = _parse(_flatRateCtl.text);
        if (!r.isNaN && r >= 0) { flatResult = calcFlatForward(p, periods, r); }
      } else {
        final mi = _parse(_revInterestCtl.text);
        if (!mi.isNaN && mi > 0) {
          final mpmt = p / periods + mi;
          if (mpmt > p / periods) { flatResult = calcFlatReverse(p, periods, mpmt); }
        }
      }
    }

    AnnuityResult? annuityResult = null;
    List<RepaymentRow> annuitySchedule = [];
    if (_loanType == LoanType.annuity && p > 0 && periods > 0) {
      final r = _parse(_annualRateCtl.text);
      if (!r.isNaN && r > 0) {
        final d = calcAnnuity(p, periods, r);
        annuityResult = d.result;
        annuitySchedule = d.schedule;
      }
    }

    CompareData? compareData = null;
    if (_loanType == LoanType.compare && p > 0 && periods > 0) {
      final fr = _parse(_cmpFlatRateCtl.text);
      final ar = _parse(_cmpAnnualRateCtl.text);
      if (!fr.isNaN && !ar.isNaN && fr > 0 && ar > 0) {
        compareData = calcCompare(p, periods, fr, ar);
      }
    }

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Center(child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 640),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // Header
            Row(children: [
              const Icon(Icons.build, color: AppTheme.orange, size: 24),
              const SizedBox(width: 12),
              const Text('工具箱', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text('贷款利率换算器', style: TextStyle(color: AppTheme.accent, fontSize: 13, fontWeight: FontWeight.w500)),
            ]),
            const SizedBox(height: 20),

            // Card
            Container(
              decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.border)),
              child: Column(children: [
                // Mode tabs
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(children: [
                    _pill('等本等息', active: _loanType == LoanType.flat, activeColor: AppTheme.error, onTap: () => setState(() => _loanType = LoanType.flat)),
                    const SizedBox(width: 4),
                    _pill('等额本息', active: _loanType == LoanType.annuity, activeColor: AppTheme.emerald, onTap: () => setState(() => _loanType = LoanType.annuity)),
                    const SizedBox(width: 4),
                    _pill('方案对比', active: _loanType == LoanType.compare, activeColor: AppTheme.sky, onTap: () => setState(() => _loanType = LoanType.compare)),
                    const Spacer(),
                    if (_loanType == LoanType.flat) ... [
                      _pill('正向', active: _flatMode == FlatMode.forward, onTap: () => setState(() => _flatMode = FlatMode.forward)),
                      const SizedBox(width: 4),
                      _pill('反向', active: _flatMode == FlatMode.reverse, onTap: () => setState(() => _flatMode = FlatMode.reverse)),
                    ],
                  ]),
                ),

                // Inputs
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Column(children: [
                    Row(children: [
                      Expanded(child: _input('贷款金额（元）', _principalCtl, hint: '100000')),
                      const SizedBox(width: 12),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        _input('还款年限', _yearsCtl, hint: '5'),
                        const SizedBox(height: 2),
                        Text('$periods 期（月）', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                      ])),
                    ]),

                    // Flat forward
                    if (_loanType == LoanType.flat && _flatMode == FlatMode.forward) ...[
                      const SizedBox(height: 12),
                      _input('月分期利率（%）', _flatRateCtl, hint: '0.2', suffix: '销售常说的"每期手续费率"'),
                    ],

                    // Flat reverse
                    if (_loanType == LoanType.flat && _flatMode == FlatMode.reverse) ...[
                      const SizedBox(height: 12),
                      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('月供拆分（元）', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                        const SizedBox(height: 4),
                        Row(children: [
                          Expanded(child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
                            decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8), border: Border.all(color: AppTheme.border)),
                            child: Text('${fmt(p / periods)} 本金', style: const TextStyle(color: AppTheme.textMuted, fontSize: 12, fontFamily: 'monospace')),
                          )),
                          const Padding(padding: EdgeInsets.symmetric(horizontal: 6), child: Text('+', style: TextStyle(color: AppTheme.textMuted, fontSize: 13))),
                          Expanded(child: _input('', _revInterestCtl, hint: '200')),
                          const Padding(padding: EdgeInsets.symmetric(horizontal: 6), child: Text('=', style: TextStyle(color: AppTheme.textMuted, fontSize: 13))),
                          Expanded(child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
                            decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8), border: Border.all(color: AppTheme.border)),
                            child: Text('${fmt(p / periods + _parse(_revInterestCtl.text))} 月供',
                              style: TextStyle(color: AppTheme.textPrimary, fontSize: 12, fontWeight: FontWeight.w600, fontFamily: 'monospace')),
                          )),
                        ]),
                        const SizedBox(height: 2),
                        const Text('本金固定 = 总金额 ÷ 期数，调整利息即可反推利率', style: TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                      ]),
                    ],

                    // Annuity input
                    if (_loanType == LoanType.annuity) ...[
                      const SizedBox(height: 12),
                      _input('年化利率（%）', _annualRateCtl, hint: '3', suffix: '银行合同上的年化利率'),
                    ],

                    // Compare inputs
                    if (_loanType == LoanType.compare) ...[
                      const SizedBox(height: 12),
                      Row(children: [
                        Expanded(child: _input('等本等息 · 月分期利率（%）', _cmpFlatRateCtl, hint: '0.18')),
                        const SizedBox(width: 12),
                        Expanded(child: _input('等额本息 · 年化利率（%）', _cmpAnnualRateCtl, hint: '3')),
                      ]),
                    ],
                  ]),
                ),
                const SizedBox(height: 16),

                // Results
                if (_loanType == LoanType.flat && flatResult != null) ...[
                  const Divider(height: 1, color: AppTheme.border),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(children: [
                      // Reverse: show derived rate
                      if (_flatMode == FlatMode.reverse && flatResult.derivedFlatRate != null)
                        Container(
                          width: double.infinity, padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8)),
                          child: Row(children: [
                            const Icon(Icons.swap_horiz, size: 14, color: AppTheme.amber),
                            const SizedBox(width: 8),
                            Text('反推月分期利率：${fmtPct(flatResult.derivedFlatRate!)}',
                              style: const TextStyle(color: AppTheme.amber, fontSize: 11, fontFamily: 'monospace', fontWeight: FontWeight.w500)),
                            const SizedBox(width: 8),
                            Text('（名义 ${fmtLi(flatResult.derivedFlatRate! / 0.1)}）',
                              style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                          ]),
                        ),
                      const SizedBox(height: 12),
                      _flatResultTable(flatResult, _flatMode),
                      const SizedBox(height: 12),
                      _tipBox('💡 ${flatSummary(flatResult)}', AppTheme.error),
                      const SizedBox(height: 8),
                      GestureDetector(
                        onTap: () => setState(() => _showWhy = !_showWhy),
                        child: Row(children: [
                          Icon(_showWhy ? Icons.expand_less : Icons.expand_more, size: 14, color: AppTheme.textMuted),
                          const SizedBox(width: 4),
                          const Text('为什么「销售说的」和「真实成本」不一样？', style: TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                        ]),
                      ),
                      if (_showWhy) ...[
                        const SizedBox(height: 8),
                        Container(
                          width: double.infinity, padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8), border: Border.all(color: AppTheme.border)),
                          child: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text('等本等息的陷阱：每月利息按最初的贷款总额计算，固定不变。',
                              style: TextStyle(color: AppTheme.textSecondary, fontSize: 11, height: 1.6)),
                            SizedBox(height: 4),
                            Text('但你每月都在还本金——实际占用资金越来越少，利息却没有减少。以 10 万 60 期为例：',
                              style: TextStyle(color: AppTheme.textSecondary, fontSize: 11, height: 1.6)),
                            SizedBox(height: 6),
                            _WhyExampleRow('第 1 个月', '100,000', '200', '0.20%', AppTheme.textMuted),
                            _WhyExampleRow('第 30 个月', '50,000', '200', '0.40%', AppTheme.amber),
                            _WhyExampleRow('第 60 个月', '1,667', '200', '12%', AppTheme.error),
                            SizedBox(height: 6),
                            Text('IRR 真实年化是把 60 期不等的实际利率加权平均后换算的年化值，反映了你真正的资金成本。',
                              style: TextStyle(color: AppTheme.textSecondary, fontSize: 11, height: 1.6)),
                          ]),
                        ),
                      ],
                      const SizedBox(height: 8),
                      Text('IRR 采用二分查找法计算，精度 0.01，年化 = (1+月利率)¹² − 1。\n速算参考：年化 ≈ 月分期利率 × 期数 × 24 ÷ (期数 + 1)',
                        style: TextStyle(color: AppTheme.textMuted.withValues(alpha: 0.6), fontSize: 10, height: 1.5)),
                    ]),
                  ),
                ],

                if (_loanType == LoanType.annuity && annuityResult != null) ...[
                  const Divider(height: 1, color: AppTheme.border),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(children: [
                      _annuityResultTable(annuityResult),
                      const SizedBox(height: 12),
                      _tipBox('💡 等额本息按剩余本金计息，IRR = 名义年化 = ${fmtPct(_parse(_annualRateCtl.text))}，不存在「低息陷阱」。', AppTheme.emerald),
                      const SizedBox(height: 8),
                      GestureDetector(
                        onTap: () => setState(() => _showSchedule = !_showSchedule),
                        child: Row(children: [
                          Icon(_showSchedule ? Icons.expand_less : Icons.expand_more, size: 14, color: AppTheme.textMuted),
                          const SizedBox(width: 4),
                          const Icon(Icons.table_chart, size: 12, color: AppTheme.textMuted),
                          const SizedBox(width: 4),
                          const Text('还款计划明细', style: TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                        ]),
                      ),
                      if (_showSchedule) ...[
                        const SizedBox(height: 8),
                        Container(
                          decoration: BoxDecoration(borderRadius: BorderRadius.circular(8), border: Border.all(color: AppTheme.border)),
                          clipBehavior: Clip.antiAlias,
                          child: Column(children: [
                            _tableHeader(['期数', '月供', '本金', '利息', '剩余本金']),
                            ...pickScheduleRows(annuitySchedule).asMap().entries.map((e) {
                              final i = e.key; final row = e.value;
                              final prevPeriod = i > 0 ? pickScheduleRows(annuitySchedule)[i - 1].period : 0;
                              return _tableRow([
                                _tcell('${row.period}', color: AppTheme.textMuted),
                                _tcell(fmt(row.payment), color: AppTheme.textSecondary),
                                _tcell(fmt(row.principal), color: AppTheme.textMuted),
                                _tcell(fmt(row.interest), color: AppTheme.amber.withValues(alpha: 0.7)),
                                _tcell(fmt(row.balance), color: AppTheme.textMuted.withValues(alpha: 0.6)),
                              ], bg: row.period - prevPeriod > 1 ? AppTheme.background : null);
                            }),
                            Container(
                              width: double.infinity, padding: const EdgeInsets.all(8),
                              color: AppTheme.background,
                              child: Text('显示首3期 + 中段每12期 + 末3期（共${annuitySchedule.length}期，省略中间行）',
                                style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                            ),
                          ]),
                        ),
                      ],
                      const SizedBox(height: 8),
                      Text('月供 = 本金 × 月利率 × (1+月利率)ⁿ ÷ ((1+月利率)ⁿ − 1)，每月利息按剩余本金重新计算。',
                        style: TextStyle(color: AppTheme.textMuted.withValues(alpha: 0.6), fontSize: 10, height: 1.5)),
                    ]),
                  ),
                ],

                if (_loanType == LoanType.compare && compareData != null) ...[
                  const Divider(height: 1, color: AppTheme.border),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(children: [
                      _compareResultTable(compareData),
                      if (compareData.tipping != null) ...[
                        const SizedBox(height: 12),
                        _tipBox('💡 拐点约在第 ${compareData.tipping!.month} 期（${compareData.tipping!.month / 12} 年）：在此之前等本等息更划算，之后等额本息优势越来越大。', AppTheme.sky),
                      ],
                    ]),
                  ),
                ],

                // Empty state
                if ((_loanType == LoanType.flat && flatResult == null) ||
                    (_loanType == LoanType.annuity && annuityResult == null) ||
                    (_loanType == LoanType.compare && compareData == null))
                  Padding(
                    padding: const EdgeInsets.only(bottom: 32),
                    child: Text(
                      _loanType == LoanType.compare ? '请输入两种方案的利率参数' : '请输入参数查看计算结果',
                      style: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                    ),
                  ),

                const SizedBox(height: 8),
              ]),
            ),
          ]),
        )),
      ),
    );
  }
}

// tiny sub-widget for the "why" expandable
class _WhyExampleRow extends StatelessWidget {
  final String label, owed, interest, rate;
  final Color color;
  const _WhyExampleRow(this.label, this.owed, this.interest, this.rate, this.color);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text('$label：欠 $owed，利息 $interest → 月利率 $rate',
        style: TextStyle(color: color, fontSize: 11, fontFamily: 'monospace')),
    );
  }
}
