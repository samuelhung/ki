import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../theme/app_theme.dart';

class UsageWidget extends StatefulWidget {
  const UsageWidget({super.key});
  @override
  State<UsageWidget> createState() => _UsageWidgetState();
}

class _UsageWidgetState extends State<UsageWidget> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  bool _expanded = false;

  static const _moduleNames = {
    'ingest_pipeline': '采集 pipeline',
    'series': '专题引擎',
    'brainstorm': '头脑风暴',
    'digest_briefing': '摘要快报',
    'tasks': '待办事务',
    'concept': '概念沉淀',
  };

  static const _moduleColors = {
    'ingest_pipeline': Color(0xFF06B6D4),
    'series': Color(0xFFA855F7),
    'brainstorm': Color(0xFFF59E0B),
    'digest_briefing': Color(0xFF10B981),
    'tasks': Color(0xFF0EA5E9),
    'concept': Color(0xFF3B82F6),
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final resp = await ApiClient().dio.get('/api/usage/dashboard');
      if (mounted) setState(() { _data = resp.data as Map<String, dynamic>; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  static String _fmtTokens(int n) {
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}K';
    return n.toString();
  }

  static String _fmtCost(double n) {
    if (n == 0) return '¥0';
    if (n < 0.01) return '<¥0.01';
    return '¥${n.toStringAsFixed(2)}';
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: AppTheme.panel, border: Border.all(color: AppTheme.border),
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Center(child: CircularProgressIndicator(color: AppTheme.textMuted, strokeWidth: 2)),
      );
    }

    if (_data == null) return const SizedBox.shrink();

    final today = _data!['today'] as Map<String, dynamic>? ?? {};
    final modules = (_data!['modules'] as List?)?.cast<Map<String, dynamic>>() ?? [];
    final trend = (_data!['trend'] as List?)?.cast<Map<String, dynamic>>() ?? [];

    final maxTokens = modules.fold<int>(1, (a, b) => a > (b['tokens'] as int? ?? 0) ? a : (b['tokens'] as int? ?? 0));
    final maxTrendTokens = trend.fold<int>(1, (a, b) => a > (b['tokens'] as int? ?? 0) ? a : (b['tokens'] as int? ?? 0));
    final maxTrendCost = trend.fold<double>(0.01, (a, b) => a > ((b['cost'] as num?)?.toDouble() ?? 0) ? a : ((b['cost'] as num?)?.toDouble() ?? 0));

    return Container(
      decoration: BoxDecoration(
        color: AppTheme.panel, border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(12),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        // Header
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
          child: Row(children: [
            const Icon(Icons.bolt, size: 18, color: AppTheme.purple),
            const SizedBox(width: 8),
            const Text('AI 运转', style: TextStyle(color: AppTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
            const Text(' 今日', style: TextStyle(color: AppTheme.textMuted, fontSize: 10)),
            const Spacer(),
            GestureDetector(
              onTap: () { setState(() { _expanded = !_expanded; if (!_expanded) setState(() {}); }); },
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(_expanded ? '收起' : '展开明细', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                const SizedBox(width: 2),
                Icon(_expanded ? Icons.expand_less : Icons.expand_more, size: 12, color: AppTheme.textMuted),
              ]),
            ),
          ]),
        ),
        const Divider(height: 1, color: AppTheme.border),

        // 4 mini cards
        IntrinsicHeight(
          child: Row(children: [
            _miniCard('今日调用', Icons.auto_awesome, AppTheme.purple, '${today['total_calls'] ?? 0}次',
                (today['error_calls'] as int? ?? 0) > 0 ? '${today['error_calls']} 次失败' : null, null),
            _vDivider(),
            _miniCard('知识吞吐', Icons.dns, AppTheme.cyan, _fmtTokens(today['total_tokens'] as int? ?? 0),
                null, '入 ${_fmtTokens(today['prompt_tokens'] as int? ?? 0)} · 出 ${_fmtTokens(today['completion_tokens'] as int? ?? 0)}'),
            _vDivider(),
            _miniCard('缓存命中', Icons.bar_chart, AppTheme.emerald, '${today['cache_hit_rate'] ?? 0}%',
                null, '省 ${_fmtCost((today['cache_saved'] as num?)?.toDouble() ?? 0)}'),
            _vDivider(),
            _miniCard('今日花费', Icons.monetization_on, AppTheme.amber,
                _fmtCost((today['cost_rmb'] as num?)?.toDouble() ?? 0), null,
                '均 ${(today['avg_duration_ms'] as int? ?? 0) > 0 ? '${((today['avg_duration_ms'] as int) / 1000).toStringAsFixed(1)}s' : '—'}/次'),
          ]),
        ),

        // Expanded detail
        if (_expanded) ...[
          const Divider(height: 1, color: AppTheme.border),
          IntrinsicHeight(
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Module bar chart
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('模块消耗分布', style: TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 16),
                    ...modules.map((m) => _moduleBar(m, maxTokens)),
                    if (modules.isEmpty)
                      const Center(child: Text('暂无数据', style: TextStyle(color: AppTheme.textMuted, fontSize: 11))),
                  ]),
                ),
              ),
              const VerticalDivider(width: 1, color: AppTheme.border),
              // 7-day trend
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('7 天趋势', style: TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontWeight: FontWeight.w500)),
                    const SizedBox(height: 16),
                    _trendChart(trend, maxTrendTokens, maxTrendCost),
                  ]),
                ),
              ),
            ]),
          ),
        ],
      ]),
    );
  }

  Widget _miniCard(String label, IconData icon, Color color, String value, String? error, String? sub) {
    return Expanded(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Row(children: [
            Icon(icon, size: 13, color: color),
            const SizedBox(width: 6),
            Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
          ]),
          const SizedBox(height: 8),
          Text(value, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.bold)),
          if (error != null)
            Text(error, style: const TextStyle(color: AppTheme.error, fontSize: 10)),
          if (sub != null)
            Text(sub, style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
        ]),
      ),
    );
  }

  Widget _vDivider() => const VerticalDivider(width: 1, color: AppTheme.border);

  Widget _moduleBar(Map<String, dynamic> m, int maxTokens) {
    final module = m['module'] as String? ?? '';
    final tokens = m['tokens'] as int? ?? 0;
    final calls = m['calls'] as int? ?? 0;
    final cost = (m['cost'] as num?)?.toDouble() ?? 0;
    final ratio = maxTokens > 0 ? tokens / maxTokens : 0.0;
    final color = _moduleColors[module] ?? Colors.grey;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(children: [
        SizedBox(width: 80, child: Text(_moduleNames[module] ?? module,
            style: const TextStyle(color: AppTheme.textSecondary, fontSize: 10), textAlign: TextAlign.right)),
        const SizedBox(width: 12),
        Expanded(
          child: Container(
            height: 10,
            decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(2)),
            child: FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: ratio.clamp(0.0, 1.0),
              child: Container(decoration: BoxDecoration(color: color.withOpacity(0.8), borderRadius: BorderRadius.circular(2))),
            ),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(width: 120, child: Text('$calls 次 · ${tokens > 1000 ? _fmtTokens(tokens) : '$tokens tok'}',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 10))),
        const SizedBox(width: 4),
        SizedBox(width: 56, child: Text(_fmtCost(cost),
            style: TextStyle(color: AppTheme.amber.withOpacity(0.8), fontSize: 10), textAlign: TextAlign.right)),
      ]),
    );
  }

  Widget _trendChart(List<Map<String, dynamic>> trend, int maxTokens, double maxCost) {
    if (trend.isEmpty) {
      return const Center(child: Text('暂无数据，AI 调用后将自动记录', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)));
    }
    return Column(mainAxisSize: MainAxisSize.min, children: [
      SizedBox(
        height: 128,
        child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          ...trend.map((t) => _trendBar(t, maxTokens, maxCost)),
        ]),
      ),
      const SizedBox(height: 12),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        _legendDot(AppTheme.purple.withOpacity(0.6), 'token'),
        const SizedBox(width: 16),
        _legendDot(AppTheme.amber.withOpacity(0.4), '花费'),
      ]),
    ]);
  }

  Widget _trendBar(Map<String, dynamic> t, int maxTokens, double maxCost) {
    final tokens = t['tokens'] as int? ?? 0;
    final cost = (t['cost'] as num?)?.toDouble() ?? 0;
    final tokenH = maxTokens > 0 ? (tokens / maxTokens * 100).clamp(0.0, 100.0) : 0.0;
    final costH = maxCost > 0 ? (cost / maxCost * 100).clamp(0.0, 100.0) : 0.0;
    final day = (t['day'] as String?) ?? '';
    final label = day.length >= 10 ? day.substring(5, 10) : day;

    return Expanded(
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Spacer(),
        Row(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
          Container(width: 10, height: tokenH > 0 ? (tokenH * 0.96).clamp(2.0, 96.0) : (tokens > 0 ? 2 : 0),
              decoration: BoxDecoration(color: AppTheme.purple.withOpacity(0.6), borderRadius: const BorderRadius.only(topLeft: Radius.circular(2), topRight: Radius.circular(2)))),
          const SizedBox(width: 2),
          Container(width: 10, height: costH > 0 ? (costH * 0.96).clamp(2.0, 96.0) : (cost > 0 ? 2 : 0),
              decoration: BoxDecoration(color: AppTheme.amber.withOpacity(0.4), borderRadius: const BorderRadius.only(topLeft: Radius.circular(2), topRight: Radius.circular(2)))),
        ]),
        const SizedBox(height: 4),
        Text(label, style: const TextStyle(color: AppTheme.textMuted, fontSize: 9)),
      ]),
    );
  }

  Widget _legendDot(Color color, String label) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 10, height: 10, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
      const SizedBox(width: 6),
      Text(label, style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
    ]);
  }
}
