import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../theme/app_theme.dart';

/// GitHub-style contribution heatmap chart
class HeatmapChartWidget extends StatefulWidget {
  const HeatmapChartWidget({super.key});
  @override
  State<HeatmapChartWidget> createState() => _HeatmapChartWidgetState();
}

class _HeatmapChartWidgetState extends State<HeatmapChartWidget> {
  static const _daysShort = ['一', '二', '三', '四', '五', '六', '日'];
  static const _months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];
  static const _cellSize = 14.0;
  static const _cellGap = 3.0;

  List<_CellData> _cells = [];
  List<_MonthLabel> _monthLabels = [];
  bool _loading = true;
  int _total = 0;
  int _streak = 0;
  int _maxDay = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final resp = await ApiClient().dio.get('/api/dashboard/trend?days=84');
      final rawData = (resp.data as List?)?.cast<Map<String, dynamic>>() ?? [];

      final countMap = <String, int>{};
      int totalEvents = 0;
      for (final d in rawData) {
        final day = d['day'] as String? ?? '';
        final count = d['count'] as int? ?? 0;
        countMap[day] = count;
        totalEvents += count;
      }

      final allDates = countMap.keys.toList()..sort();
      final endDate = allDates.isNotEmpty
          ? allDates.last
          : DateTime.now().toIso8601String().substring(0, 10);

      String startDate = _addDays(endDate, -83);
      final startDow = _getDowIndex(startDate);
      startDate = _addDays(startDate, -startDow);

      final endDow = _getDowIndex(endDate);
      final extraDays = 6 - endDow;
      final totalDays = 84 + startDow + extraDays;
      final numWeeks = (totalDays / 7).ceil();
      final totalCells = numWeeks * 7;

      final cellList = <_CellData>[];
      final monthsSeen = <int, int>{};

      for (int i = 0; i < totalCells; i++) {
        final dateStr = _addDays(startDate, i);
        final isInRange = dateStr.compareTo(_addDays(endDate, -83)) >= 0 && dateStr.compareTo(endDate) <= 0;

        if (!isInRange) {
          cellList.add(_CellData(date: dateStr, count: -1, level: 0, isToday: false));
          continue;
        }

        final count = countMap[dateStr] ?? 0;
        cellList.add(_CellData(date: dateStr, count: count, level: _getLevel(count), isToday: dateStr == endDate));

        final mNum = int.parse(dateStr.substring(5, 7));
        final monthKey = int.parse(dateStr.substring(0, 4)) * 100 + mNum;
        monthsSeen.putIfAbsent(monthKey, () => i ~/ 7);
      }

      final mlabels = monthsSeen.entries
          .map((e) => _MonthLabel(label: _months[(e.key % 100) - 1], col: e.value))
          .toList()
        ..sort((a, b) => a.col.compareTo(b.col));

      int streak = 0;
      String checkDate = endDate;
      while (true) {
        if ((countMap[checkDate] ?? 0) > 0) {
          streak++;
          checkDate = _addDays(checkDate, -1);
        } else {
          break;
        }
      }

      final maxDay = countMap.values.fold(0, (a, b) => a > b ? a : b);

      if (mounted) {
        setState(() {
          _cells = cellList;
          _monthLabels = mlabels;
          _total = totalEvents;
          _streak = streak;
          _maxDay = maxDay;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  static int _getLevel(int count) {
    if (count == 0) return 0;
    if (count == 1) return 1;
    if (count <= 3) return 2;
    return 3;
  }

  static Color _levelColor(int level) {
    switch (level) {
      case 0: return const Color(0xFF1A1B20);
      case 1: return const Color(0x33A855F7);
      case 2: return const Color(0x73A855F7);
      case 3: return const Color(0xBFA855F7);
      default: return const Color(0xFF1A1B20);
    }
  }

  static String _addDays(String dateStr, int n) {
    final y = int.parse(dateStr.substring(0, 4));
    final m = int.parse(dateStr.substring(5, 7));
    final d = int.parse(dateStr.substring(8, 10));
    final dt = DateTime.utc(y, m, d).add(Duration(days: n));
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
  }

  static int _getDowIndex(String dateStr) {
    final y = int.parse(dateStr.substring(0, 4));
    final m = int.parse(dateStr.substring(5, 7));
    final d = int.parse(dateStr.substring(8, 10));
    final dow = DateTime.utc(y, m, d).weekday;
    return dow - 1; // Mon=0, Sun=6
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: AppTheme.panel,
          border: Border.all(color: AppTheme.border),
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Center(child: CircularProgressIndicator(color: AppTheme.textMuted, strokeWidth: 2)),
      );
    }

    if (_cells.isEmpty) return const SizedBox.shrink();

    final numWeeks = (_cells.length / 7).ceil();

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Header
        Row(children: [
          const Text('事件热力图', style: TextStyle(color: AppTheme.textSecondary, fontSize: 13, fontWeight: FontWeight.w500)),
          const SizedBox(width: 12),
          Text('$_total 条事件 · 连续 $_streak 天 · 单日最多 $_maxDay',
              style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
          const Spacer(),
          // Legend
          const Text('少', style: TextStyle(color: AppTheme.textMuted, fontSize: 10)),
          const SizedBox(width: 4),
          ...List.generate(4, (i) => Container(
            width: 12, height: 12,
            decoration: BoxDecoration(
              color: _levelColor(i),
              borderRadius: BorderRadius.circular(2),
              border: i == 0 ? Border.all(color: Colors.white.withOpacity(0.06)) : null,
            ),
          )).expand((w) => [w, const SizedBox(width: 2)]),
          const SizedBox(width: 6),
          const Text('多', style: TextStyle(color: AppTheme.textMuted, fontSize: 10)),
        ]),
        const SizedBox(height: 16),

        // Grid
        SizedBox(
          height: 7 * _cellSize + 6 * _cellGap + 18,
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // Day labels
            SizedBox(
              width: 24,
              child: Padding(
                padding: const EdgeInsets.only(top: 18),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [0, 2, 4, 6].map((d) => SizedBox(
                    height: _cellSize,
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: Padding(
                        padding: const EdgeInsets.only(right: 4, bottom: _cellGap),
                        child: Text(_daysShort[d], style: const TextStyle(color: AppTheme.textMuted, fontSize: 9)),
                      ),
                    ),
                  )).toList(),
                ),
              ),
            ),
            const SizedBox(width: 4),

            // Cells grid
            Expanded(
              child: LayoutBuilder(builder: (context, constraints) {
                final availableW = constraints.maxWidth;
                final computedSize = ((availableW - (numWeeks - 1) * _cellGap) / numWeeks).clamp(10.0, 20.0);

                // Month labels
                return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  SizedBox(
                    height: 18,
                    child: Stack(children: _monthLabels.map((ml) {
                      final left = ml.col * (computedSize + _cellGap);
                      return Positioned(
                        left: left,
                        top: 0,
                        child: Text(ml.label, style: const TextStyle(color: AppTheme.textMuted, fontSize: 9)),
                      );
                    }).toList()),
                  ),
                  // Cells
                  Expanded(
                    child: Wrap(
                      direction: Axis.vertical,
                      spacing: _cellGap,
                      runSpacing: _cellGap,
                      children: _cells.map((cell) {
                        if (cell.count < 0) return SizedBox(width: computedSize, height: computedSize);
                        return Tooltip(
                          message: '${cell.date}: ${cell.count} 条事件',
                          child: Container(
                            width: computedSize,
                            height: computedSize,
                            decoration: BoxDecoration(
                              color: _levelColor(cell.level),
                              borderRadius: BorderRadius.circular(2),
                              border: cell.isToday
                                  ? Border.all(color: AppTheme.accent.withOpacity(0.8))
                                  : Border.all(color: Colors.transparent),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                ]);
              }),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _CellData {
  final String date;
  final int count;
  final int level;
  final bool isToday;
  const _CellData({required this.date, required this.count, required this.level, required this.isToday});
}

class _MonthLabel {
  final String label;
  final int col;
  const _MonthLabel({required this.label, required this.col});
}
