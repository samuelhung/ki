import 'package:flutter/material.dart';
import '../services/api_client.dart';
import '../theme/app_theme.dart';

/// 信息源订阅列表弹窗
class SourcesModal extends StatefulWidget {
  const SourcesModal({super.key});
  @override
  State<SourcesModal> createState() => _SourcesModalState();
}

class _SourcesModalState extends State<SourcesModal> {
  List<Map<String, dynamic>> _sources = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final resp = await ApiClient().dio.get('/api/sources');
      final data = resp.data;
      final list = (data is List ? data.cast<Map<String, dynamic>>() : <Map<String, dynamic>>[]);
      if (mounted) setState(() { _sources = list; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppTheme.panel,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppTheme.border),
      ),
      titlePadding: const EdgeInsets.fromLTRB(20, 20, 16, 0),
      contentPadding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
      actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      title: Row(children: [
        const Icon(Icons.language, size: 18, color: AppTheme.cyan),
        const SizedBox(width: 8),
        const Expanded(child: Text('订阅信息源', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600))),
        GestureDetector(
          onTap: () => Navigator.of(context, rootNavigator: true).pop(),
          child: const Icon(Icons.close, size: 20, color: AppTheme.textMuted),
        ),
      ]),
      content: SizedBox(
        width: 480,
        height: 400,
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: AppTheme.textMuted, strokeWidth: 2))
            : _sources.isEmpty
                ? const Center(child: Text('暂无订阅源', style: TextStyle(color: AppTheme.textMuted, fontSize: 13)))
                : ListView.separated(
                    itemCount: _sources.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 8),
                    itemBuilder: (_, i) => _buildSourceRow(_sources[i]),
                  ),
      ),
    );
  }

  Widget _buildSourceRow(Map<String, dynamic> s) {
    final name = s['name'] as String? ?? '';
    final type = s['type'] as String? ?? '';
    final topic = s['topic'] as String? ?? '';
    final enabled = s['enabled'] == true;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: AppTheme.background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(name, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            Row(children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.06),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(type.toUpperCase(), style: const TextStyle(color: AppTheme.textMuted, fontSize: 9)),
              ),
              if (topic.isNotEmpty) ...[
                const SizedBox(width: 6),
                Text(topic, style: const TextStyle(color: AppTheme.textMuted, fontSize: 9)),
              ],
            ]),
          ]),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: enabled ? AppTheme.emerald.withOpacity(0.15) : Colors.white.withOpacity(0.05),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            enabled ? '启用' : '停用',
            style: TextStyle(
              color: enabled ? AppTheme.emerald : AppTheme.textMuted,
              fontSize: 10,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ]),
    );
  }
}
