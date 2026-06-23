import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class SourcesPage extends StatefulWidget {
  const SourcesPage({super.key});
  @override
  State<SourcesPage> createState() => _SourcesPageState();
}

class _SourcesPageState extends State<SourcesPage> {
  List<Map<String, dynamic>> _sources = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSources();
  }

  Future<void> _loadSources() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = ApiClient();
      final data = await api.getSources();
      if (mounted) {
        setState(() {
          _sources = (data as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
          _loading = false;
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
                  const Icon(Icons.rss_feed, color: AppTheme.cyan, size: 24),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text('来源管理', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                  ),
                  Text('${_sources.length} 个源', style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                ],
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
                  : _error != null
                      ? Center(child: Text(_error!, style: const TextStyle(color: AppTheme.error)))
                      : _sources.isEmpty
                          ? const Center(child: Text('暂无来源', style: TextStyle(color: AppTheme.textMuted)))
                          : ListView.builder(
                              padding: const EdgeInsets.symmetric(horizontal: 32),
                              itemCount: _sources.length,
                              itemBuilder: (_, i) => _buildSourceRow(_sources[i]),
                            ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSourceRow(Map<String, dynamic> s) {
    final name = s['name'] as String? ?? '(未知)';
    final type = s['type'] as String? ?? '';
    final topic = s['topic'] as String? ?? '';
    final enabled = (s['enabled'] as int?) == 1;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.border, width: 0.5),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500)),
                const SizedBox(height: 4),
                Row(
                  children: [
                    if (type.isNotEmpty)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(color: AppTheme.panelActive, borderRadius: BorderRadius.circular(4)),
                        child: Text(type.toUpperCase(), style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                      ),
                    if (type.isNotEmpty && topic.isNotEmpty) const SizedBox(width: 6),
                    if (topic.isNotEmpty)
                      Text(topic, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                  ],
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: enabled ? AppTheme.emerald.withOpacity(0.15) : AppTheme.textMuted.withOpacity(0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              enabled ? '启用' : '停用',
              style: TextStyle(
                color: enabled ? AppTheme.emerald : AppTheme.textMuted,
                fontSize: 11,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
