import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class BrainstormPage extends StatefulWidget {
  const BrainstormPage({super.key});
  @override
  State<BrainstormPage> createState() => _BrainstormPageState();
}

class _BrainstormPageState extends State<BrainstormPage> {
  List<Map<String, dynamic>> _items = [];
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
      final api = ApiClient();
      final resp = await api.getBrainstorms(offset: 0, limit: 200);
      if (mounted) {
        final items = (resp['items'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
        setState(() { _items = items; _loading = false; });
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(32, 24, 32, 16),
              child: Row(
                children: [
                  const Icon(Icons.lightbulb, color: AppTheme.amber, size: 24),
                  const SizedBox(width: 12),
                  const Text('头脑风暴', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text('${_items.length} 个问题', style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                ],
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
                  : _error != null
                      ? Center(child: Text(_error!, style: const TextStyle(color: AppTheme.error)))
                      : _items.isEmpty
                          ? const Center(child: Text('暂无问题', style: TextStyle(color: AppTheme.textMuted)))
                          : ListView.builder(
                              padding: const EdgeInsets.symmetric(horizontal: 32),
                              itemCount: _items.length,
                              itemBuilder: (_, i) {
                                final item = _items[i];
                                final question = item['question'] as String? ?? item['title'] as String? ?? '(无问题)';
                                final createdAt = item['created_at'] as String? ?? '';
                                return Container(
                                  margin: const EdgeInsets.only(bottom: 6),
                                  padding: const EdgeInsets.all(14),
                                  decoration: BoxDecoration(
                                    color: AppTheme.panel,
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: AppTheme.border, width: 0.5),
                                  ),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          const Icon(Icons.help_outline, size: 16, color: AppTheme.amber),
                                          const SizedBox(width: 8),
                                          Expanded(child: Text(question, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14))),
                                        ],
                                      ),
                                      if (createdAt.isNotEmpty) ...[
                                        const SizedBox(height: 6),
                                        Text(_formatDate(createdAt), style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                                      ],
                                    ],
                                  ),
                                );
                              },
                            ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso);
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) { return iso; }
  }
}
