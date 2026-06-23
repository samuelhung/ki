import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class DigestPage extends StatefulWidget {
  const DigestPage({super.key});
  @override
  State<DigestPage> createState() => _DigestPageState();
}

class _DigestPageState extends State<DigestPage> {
  List<Map<String, dynamic>> _digests = [];
  bool _loading = true;
  String? _error;
  int _page = 1;
  int _total = 0;
  static const _pageSize = 30;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({int? page}) async {
    if (page != null) _page = page;
    setState(() => _loading = true);
    try {
      final api = ApiClient();
      final resp = await api.getDigests(offset: (_page - 1) * _pageSize, limit: _pageSize);
      if (mounted) {
        final items = (resp['items'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
        setState(() {
          _digests = items;
          _total = resp['total'] as int? ?? items.length;
          _loading = false;
          _error = null;
        });
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
                  const Icon(Icons.article, color: AppTheme.rose, size: 24),
                  const SizedBox(width: 12),
                  const Text('摘要', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text('$_total 条', style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                ],
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
                  : _error != null
                      ? Center(child: Text(_error!, style: const TextStyle(color: AppTheme.error)))
                      : _digests.isEmpty
                          ? const Center(child: Text('暂无摘要', style: TextStyle(color: AppTheme.textMuted)))
                          : ListView.builder(
                              padding: const EdgeInsets.symmetric(horizontal: 32),
                              itemCount: _digests.length,
                              itemBuilder: (_, i) => _buildDigestCard(_digests[i]),
                            ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDigestCard(Map<String, dynamic> d) {
    final title = d['title'] as String? ?? '(无标题)';
    final content = d['content'] as String? ?? d['summary'] as String? ?? '';
    final createdAt = d['created_at'] as String? ?? '';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.border, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 15, fontWeight: FontWeight.w600)),
          if (content.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(content, maxLines: 4, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13, height: 1.5)),
          ],
          const SizedBox(height: 8),
          Text(_formatDate(createdAt), style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        ],
      ),
    );
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso);
      return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) { return iso; }
  }
}
