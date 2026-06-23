import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class EventsPage extends StatefulWidget {
  const EventsPage({super.key});

  @override
  State<EventsPage> createState() => _EventsPageState();
}

class _EventsPageState extends State<EventsPage> {
  List<Map<String, dynamic>> _events = [];
  bool _loading = true;
  String? _error;
  int _page = 1;
  int _total = 0;
  final _searchCtrl = TextEditingController();
  static const int _pageSize = 50;

  @override
  void initState() {
    super.initState();
    _loadEvents();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadEvents({int? page, String? search}) async {
    if (page != null) _page = page;
    setState(() => _loading = true);
    try {
      final api = ApiClient();
      final resp = await api.getEvents(
        offset: (_page - 1) * _pageSize,
        limit: _pageSize,
        search: search ?? _searchCtrl.text,
        includeCount: true,
      );
      final items = (resp['items'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
      final total = resp['total'] as int? ?? items.length;
      if (mounted) {
        setState(() { _events = items; _total = total; _loading = false; _error = null; });
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
            // Header
            Container(
              padding: const EdgeInsets.fromLTRB(32, 24, 32, 0),
              child: Row(
                children: [
                  const Icon(Icons.auto_awesome, color: AppTheme.purple, size: 24),
                  const SizedBox(width: 12),
                  const Text('事件列表', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text('共 $_total 条', style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                ],
              ),
            ),
            // Search
            Padding(
              padding: const EdgeInsets.fromLTRB(32, 12, 32, 12),
              child: TextField(
                controller: _searchCtrl,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14),
                decoration: InputDecoration(
                  hintText: '搜索事件...',
                  prefixIcon: const Icon(Icons.search, color: AppTheme.textMuted, size: 18),
                  suffixIcon: _searchCtrl.text.isNotEmpty
                      ? IconButton(
                          icon: const Icon(Icons.clear, size: 16),
                          onPressed: () { _searchCtrl.clear(); _loadEvents(page: 1, search: ''); },
                        )
                      : null,
                ),
                onSubmitted: (v) => _loadEvents(page: 1, search: v),
              ),
            ),
            // List
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
                  : _error != null
                      ? _buildError()
                      : _events.isEmpty
                          ? const Center(child: Text('暂无事件', style: TextStyle(color: AppTheme.textMuted)))
                          : ListView.builder(
                              itemCount: _events.length + 1, // +1 for pagination bar
                              itemBuilder: (context, index) {
                                if (index == _events.length) return _buildPagination();
                                return _buildEventRow(_events[index]);
                              },
                            ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(_error!, style: const TextStyle(color: AppTheme.error)),
          const SizedBox(height: 8),
          TextButton(onPressed: () => _loadEvents(), child: const Text('重试')),
        ],
      ),
    );
  }

  Widget _buildEventRow(Map<String, dynamic> event) {
    final title = event['title'] as String? ?? '(无标题)';
    final summary = event['summary'] as String? ?? '';
    final source = event['source_name'] as String? ?? '';
    final createdAt = event['created_at'] as String? ?? '';
    final hasTranslation = event['translated_title'] != null;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32, vertical: 2),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.border, width: 0.5),
      ),
      child: InkWell(
        onTap: () {
          // TODO: navigate to event detail
        },
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: AppTheme.textPrimary, fontSize: 15, fontWeight: FontWeight.w500),
                    ),
                  ),
                  if (hasTranslation)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppTheme.emerald.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Text('已翻译', style: TextStyle(color: AppTheme.emerald, fontSize: 10)),
                    ),
                ],
              ),
              if (summary.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  summary,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13, height: 1.4),
                ),
              ],
              const SizedBox(height: 8),
              Row(
                children: [
                  if (source.isNotEmpty)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppTheme.panelActive,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(source, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                    ),
                  const Spacer(),
                  Text(
                    _formatDate(createdAt),
                    style: const TextStyle(color: AppTheme.textMuted, fontSize: 11),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPagination() {
    final totalPages = (_total / _pageSize).ceil();
    if (totalPages <= 1) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32, vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.border, width: 0.5),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          IconButton(
            onPressed: _page > 1 ? () => _loadEvents(page: _page - 1) : null,
            icon: const Icon(Icons.chevron_left, size: 18),
            color: AppTheme.textSecondary,
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text(
              '$_page / $totalPages',
              style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
            ),
          ),
          IconButton(
            onPressed: _page < totalPages ? () => _loadEvents(page: _page + 1) : null,
            icon: const Icon(Icons.chevron_right, size: 18),
            color: AppTheme.textSecondary,
          ),
        ],
      ),
    );
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso);
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}
