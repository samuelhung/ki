import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class BrainstormDetailPage extends StatefulWidget {
  final String id;
  const BrainstormDetailPage({super.key, required this.id});

  @override
  State<BrainstormDetailPage> createState() => _BrainstormDetailPageState();
}

class _BrainstormDetailPageState extends State<BrainstormDetailPage> {
  final ApiClient _api = ApiClient();
  Map<String, dynamic>? _question;
  List<Map<String, dynamic>> _linkedEvents = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final data = await _api.getBrainstorm(widget.id);
      if (mounted) {
        setState(() { _question = data; _loading = false; });
        _loadLinkedEvents();
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _loadLinkedEvents() async {
    try {
      final raw = _question?['answered_event_ids'] as String?;
      if (raw == null || raw.isEmpty) return;
      List<dynamic> list;
      try {
        list = jsonDecode(raw) as List<dynamic>;
      } catch (_) {
        return;
      }
      if (list.isEmpty) return;
      final events = <Map<String, dynamic>>[];
      for (final id in list.take(30)) {
        try {
          final evt = await _api.getEvent(int.tryParse(id.toString()) ?? 0);
          events.add(evt);
        } catch (_) {}
      }
      if (mounted) setState(() => _linkedEvents = events);
    } catch (_) {}
  }

  Color _topicColor(String? topic) {
    switch (topic) {
      case '格局': return const Color(0xFF60A5FA);
      case '财富': return const Color(0xFFFBBF24);
      case '认知': return const Color(0xFFA78BFA);
      case '前瞻': return const Color(0xFF34D399);
      default: return AppTheme.textMuted;
    }
  }

  Color _topicBg(String? topic) {
    switch (topic) {
      case '格局': return const Color(0xFF60A5FA).withOpacity(0.12);
      case '财富': return const Color(0xFFFBBF24).withOpacity(0.12);
      case '认知': return const Color(0xFFA78BFA).withOpacity(0.12);
      case '前瞻': return const Color(0xFF34D399).withOpacity(0.12);
      default: return AppTheme.textMuted.withOpacity(0.1);
    }
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso).toUtc().add(const Duration(hours: 8));
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) { return iso; }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        backgroundColor: AppTheme.background,
        body: Center(child: CircularProgressIndicator(color: AppTheme.accent)),
      );
    }

    if (_error != null || _question == null) {
      return Scaffold(
        backgroundColor: AppTheme.background,
        body: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(_error ?? '问题不存在', style: const TextStyle(color: AppTheme.error, fontSize: 14)),
            const SizedBox(height: 16),
            TextButton(onPressed: () => context.pop(), child: const Text('返回')),
          ]),
        ),
      );
    }

    final q = _question!;
    final question = q['question'] as String? ?? '(无问题)';
    final topic = q['topic'] as String? ?? '';
    final createdAt = q['created_at'] as String? ?? '';
    final answer = q['answer'] as String?;

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(children: [
          // Header
          Container(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 12),
            decoration: const BoxDecoration(
              color: AppTheme.background,
              border: Border(bottom: BorderSide(color: AppTheme.border)),
            ),
            child: Row(children: [
              GestureDetector(
                onTap: () => context.pop(),
                child: const Icon(Icons.arrow_back, color: AppTheme.textSecondary, size: 20),
              ),
              const SizedBox(width: 12),
              const Icon(Icons.lightbulb, color: AppTheme.purple, size: 20),
              const SizedBox(width: 8),
              const Text('头脑风暴 · 详情', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
              const Spacer(),
              if (topic.isNotEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(color: _topicBg(topic), borderRadius: BorderRadius.circular(4)),
                  child: Text(topic, style: TextStyle(color: _topicColor(topic), fontSize: 11, fontWeight: FontWeight.w500)),
                ),
            ]),
          ),

          // Content
          Expanded(
            child: ListView(padding: const EdgeInsets.fromLTRB(32, 24, 32, 32), children: [
              // Question card
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: AppTheme.panel,
                  border: Border.all(color: AppTheme.border),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('问题', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                  const SizedBox(height: 12),
                  Text(question, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w500, height: 1.5)),
                  if (createdAt.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    Text('提交于 ${_formatDate(createdAt)}', style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                  ],
                ]),
              ),

              const SizedBox(height: 24),

              // Answer section
              if (answer != null && answer.isNotEmpty) ...[
                const Text('AI 回答', style: TextStyle(color: AppTheme.textSecondary, fontSize: 12, fontWeight: FontWeight.w500)),
                const SizedBox(height: 12),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: AppTheme.panel,
                    border: Border.all(color: AppTheme.border),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(answer, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13, height: 1.6)),
                ),
                const SizedBox(height: 24),
              ],

              // Linked events
              if (_linkedEvents.isNotEmpty) ...[
                const Text('关联文档', style: TextStyle(color: AppTheme.textSecondary, fontSize: 12, fontWeight: FontWeight.w500)),
                const SizedBox(height: 12),
                ..._linkedEvents.map((evt) => _buildEventRow(evt)),
              ],
            ]),
          ),
        ]),
      ),
    );
  }

  Widget _buildEventRow(Map<String, dynamic> evt) {
    final title = (evt['title'] as String?) ?? (evt['title_cn'] as String?) ?? '(无标题)';
    final source = evt['source_id'] as String? ?? '';
    final createdAt = evt['created_at'] as String? ?? '';
    final evtId = evt['id'];

    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13), maxLines: 2, overflow: TextOverflow.ellipsis),
            if (createdAt.isNotEmpty || source.isNotEmpty) ...[
              const SizedBox(height: 4),
              Row(children: [
                if (source.isNotEmpty)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(color: AppTheme.panelActive.withOpacity(0.5), borderRadius: BorderRadius.circular(3)),
                    child: Text(source, style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                  ),
                if (source.isNotEmpty && createdAt.isNotEmpty) const SizedBox(width: 8),
                if (createdAt.isNotEmpty)
                  Text(_formatDate(createdAt), style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
              ]),
            ],
          ]),
        ),
        const SizedBox(width: 8),
        IconButton(
          onPressed: () => context.go('/events/${evtId}'),
          icon: const Icon(Icons.open_in_new, size: 16, color: AppTheme.textMuted),
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
        ),
      ]),
    );
  }
}
