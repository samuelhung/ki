import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class SeriesPage extends StatefulWidget {
  const SeriesPage({super.key});
  @override
  State<SeriesPage> createState() => _SeriesPageState();
}

class _SeriesPageState extends State<SeriesPage> {
  List<Map<String, dynamic>> _series = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSeries();
  }

  Future<void> _loadSeries() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = ApiClient();
      final resp = await api.getSeriesList(offset: 0, limit: 200);
      if (mounted) {
        setState(() {
          _series = (resp['items'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
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
                  const Icon(Icons.layers, color: AppTheme.purple, size: 24),
                  const SizedBox(width: 12),
                  const Text('专题系列', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text('${_series.length} 个专题', style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                ],
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
                  : _error != null
                      ? Center(child: Text(_error!, style: const TextStyle(color: AppTheme.error)))
                      : _series.isEmpty
                          ? const Center(child: Text('暂无专题', style: TextStyle(color: AppTheme.textMuted)))
                          : ListView.builder(
                              padding: const EdgeInsets.symmetric(horizontal: 32),
                              itemCount: _series.length,
                              itemBuilder: (_, i) => _buildSeriesCard(_series[i]),
                            ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSeriesCard(Map<String, dynamic> s) {
    final name = s['name'] as String? ?? s['title'] as String? ?? '(无标题)';
    final description = s['description'] as String? ?? '';
    final eventCount = s['event_count'] as int? ?? 0;

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
                Text(name, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 15, fontWeight: FontWeight.w600)),
                if (description.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(description, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
                ],
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(color: AppTheme.purple.withOpacity(0.15), borderRadius: BorderRadius.circular(12)),
            child: Text('$eventCount 事件', style: const TextStyle(color: AppTheme.purple, fontSize: 11)),
          ),
        ],
      ),
    );
  }
}
