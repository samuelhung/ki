import 'dart:async';
import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class QueuePage extends StatefulWidget {
  const QueuePage({super.key});
  @override
  State<QueuePage> createState() => _QueuePageState();
}

class _QueuePageState extends State<QueuePage> {
  final _dio = ApiClient().dio;
  List<Map<String, dynamic>> _items = [];
  Timer? _timer;
  bool _showAllDone = false;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final resp = await _dio.get('/api/ingest/queue?limit=50');
      final items = List<Map<String, dynamic>>.from(resp.data['items'] ?? []);
      if (mounted) setState(() => _items = items);
    } catch (_) {}
  }

  Future<void> _retry(int taskId) async {
    try {
      await _dio.post('/api/ingest/queue/$taskId/retry');
      _load();
    } catch (_) {}
  }

  Future<void> _delete(int taskId) async {
    try {
      await _dio.delete('/api/ingest/queue/$taskId');
      _load();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final running = _items.where((t) => t['status'] == 'running').toList();
    final pending = _items.where((t) => t['status'] == 'pending').toList();
    final errors = _items.where((t) => t['status'] == 'failed' || t['status'] == 'error').toList();
    final done = _items.where((t) => t['status'] == 'done').toList();
    final visibleDone = _showAllDone ? done : done.take(5).toList();

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 24, 32, 16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              const Icon(Icons.list_alt, size: 24, color: AppTheme.purple),
              const SizedBox(width: 10),
              const Text('处理队列', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
              const Spacer(),
              IconButton(icon: const Icon(Icons.refresh, size: 20, color: AppTheme.textMuted), onPressed: _load),
            ]),
            const SizedBox(height: 16),
            Expanded(
              child: ListView(children: [
                ...running.map((t) => _card(t, Icons.sync, AppTheme.amber, true)),
                if (pending.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text('排队等待（${pending.length}）', style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                  ...pending.map((t) => _row(t, Icons.hourglass_empty, AppTheme.textMuted, '排队中…', showDelete: true)),
                ],
                if (errors.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text('失败（${errors.length}）', style: const TextStyle(color: AppTheme.error, fontSize: 12)),
                  ...errors.map((t) => _row(t, Icons.error_outline, AppTheme.error, t['error']?.toString() ?? '', showRetry: true, showDelete: true)),
                ],
                if (done.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Row(children: [
                    Text('已完成（${done.length}）', style: const TextStyle(color: AppTheme.emerald, fontSize: 12)),
                    if (done.length > 5) ...[
                      const Spacer(),
                      GestureDetector(
                        onTap: () => setState(() => _showAllDone = !_showAllDone),
                        child: Text(_showAllDone ? '收起' : '展开全部 ${done.length} 条', style: const TextStyle(color: AppTheme.accent, fontSize: 11)),
                      ),
                    ],
                  ]),
                  ...visibleDone.map((t) => _row(t, Icons.check_circle, AppTheme.emerald, '已完成', showDelete: true)),
                ],
                if (_items.isEmpty)
                  const Center(child: Padding(padding: EdgeInsets.all(40), child: Text('队列为空', style: TextStyle(color: AppTheme.textMuted)))),
              ]),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _card(Map<String, dynamic> t, IconData icon, Color color, bool running) {
    final pct = (t['progress'] is num) ? (t['progress'] as num).toDouble() : 0.0;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppTheme.border)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Expanded(child: Text(t['title'] as String? ?? t['ingest_type'] as String? ?? '', style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis)),
          if (running) SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: color)),
        ]),
        if (running) ...[
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(value: pct / 100, minHeight: 4, backgroundColor: color.withOpacity(0.15), valueColor: AlwaysStoppedAnimation(color)),
          ),
          const SizedBox(height: 4),
          Text('${pct.toStringAsFixed(0)}%', style: TextStyle(color: color, fontSize: 11)),
        ],
      ]),
    );
  }

  Widget _row(Map<String, dynamic> t, IconData icon, Color color, String subtitle, {bool showRetry = false, bool showDelete = false}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 2),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(6)),
      child: Row(children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 8),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(t['title'] as String? ?? t['ingest_type'] as String? ?? '', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12), maxLines: 1, overflow: TextOverflow.ellipsis),
          Text(subtitle, style: TextStyle(color: color.withOpacity(0.7), fontSize: 10)),
        ])),
        if (showRetry) IconButton(icon: const Icon(Icons.refresh, size: 14, color: AppTheme.amber), onPressed: () => _retry(t['id'] as int)),
        if (showDelete) IconButton(icon: const Icon(Icons.close, size: 14, color: AppTheme.textMuted), onPressed: () => _delete(t['id'] as int)),
      ]),
    );
  }
}
