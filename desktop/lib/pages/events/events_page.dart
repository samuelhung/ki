import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

// ── Topic badge colours (same as brainstorm) ──
Color _topicColor(String topic) {
  switch (topic) {
    case '格局':
      return const Color(0xFF60A5FA);
    case '财富':
      return const Color(0xFFFBBF24);
    case '认知':
      return const Color(0xFFA78BFA);
    case '前瞻':
      return const Color(0xFF34D399);
    default:
      return const Color(0xFF9CA3AF);
  }
}

Color _topicBg(String topic) {
  switch (topic) {
    case '格局':
      return const Color(0xFF60A5FA).withOpacity(0.12);
    case '财富':
      return const Color(0xFFFBBF24).withOpacity(0.12);
    case '认知':
      return const Color(0xFFA78BFA).withOpacity(0.12);
    case '前瞻':
      return const Color(0xFF34D399).withOpacity(0.12);
    default:
      return const Color(0xFF9CA3AF).withOpacity(0.12);
  }
}

// ── Status badge helpers ──
String _statusLabel(String status) {
  switch (status) {
    case 'new':
      return '新增';
    case 'processing':
      return '处理中';
    case 'completed':
      return '已完成';
    case 'error':
      return '异常';
    default:
      return status;
  }
}

Color _statusColor(String status) {
  switch (status) {
    case 'new':
      return AppTheme.blue; // 蓝色
    case 'processing':
      return AppTheme.amber; // 黄色
    case 'completed':
      return AppTheme.emerald; // 绿色
    case 'error':
      return AppTheme.error; // 红色
    default:
      return AppTheme.textMuted;
  }
}

const _kAllStatuses = ['new', 'processing', 'completed', 'error'];
const _kAllTopics = ['格局', '财富', '认知', '前瞻'];

// ═══════════════════════════════════════════════════════════
// EventsPage
// ═══════════════════════════════════════════════════════════
class EventsPage extends StatefulWidget {
  const EventsPage({super.key});

  @override
  State<EventsPage> createState() => _EventsPageState();
}

class _EventsPageState extends State<EventsPage> {
  final ApiClient _api = ApiClient();

  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  String? _error;

  String _search = '';
  String? _statusFilter; // null = all
  String? _topicFilter; // null = all (server-side)

  final Set<String> _expandedIds = {};

  static const _pageSize = 15;
  int _page = 1;

  @override
  void initState() {
    super.initState();
    _load();
  }

  // ── Load all events (bulk fetch, then client-filter) ──
  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final resp = await _api.getEvents(
        offset: 0,
        limit: 5000,
        search: null, // we filter client-side
        topic: _topicFilter,
        includeCount: true,
      );
      if (mounted) {
        final items =
            (resp['items'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ??
                [];
        setState(() {
          _items = items;
          _loading = false;
          _page = 1;
          _expandedIds.clear();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  // ── Client-side filter: search + status ──
  List<Map<String, dynamic>> _filtered() {
    var result = _items;

    if (_search.isNotEmpty) {
      final s = _search.toLowerCase();
      result = result.where((item) {
        final title = (item['title'] as String? ?? '').toLowerCase();
        return title.contains(s);
      }).toList();
    }

    if (_statusFilter != null) {
      result =
          result.where((item) => item['status'] == _statusFilter).toList();
    }

    return result;
  }

  void _toggleExpand(String id) {
    setState(() {
      if (_expandedIds.contains(id)) {
        _expandedIds.remove(id);
      } else {
        _expandedIds.add(id);
      }
    });
  }

  // ═════════════════════════════════════════════════════════
  // Build
  // ═════════════════════════════════════════════════════════
  @override
  Widget build(BuildContext context) {
    final filtered = _filtered();
    final totalPages =
        filtered.isEmpty ? 1 : ((filtered.length / _pageSize).ceil());
    final safePage = _page.clamp(1, totalPages);
    final paged = filtered.isEmpty
        ? <Map<String, dynamic>>[]
        : filtered.sublist(
            (safePage - 1) * _pageSize,
            safePage * _pageSize > filtered.length
                ? filtered.length
                : safePage * _pageSize,
          );
    final total = _items.length;

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          children: [
            // ── Sticky header ──
            Container(
              padding: const EdgeInsets.fromLTRB(32, 24, 32, 0),
              decoration: const BoxDecoration(color: AppTheme.background),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Title row
                  Row(
                    children: [
                      const Icon(Icons.auto_awesome,
                          color: AppTheme.purple, size: 32),
                      const SizedBox(width: 12),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('事件列表',
                              style: TextStyle(
                                  color: AppTheme.textPrimary,
                                  fontSize: 22,
                                  fontWeight: FontWeight.bold)),
                          Text('共 $total 条事件',
                              style: const TextStyle(
                                  color: AppTheme.textSecondary,
                                  fontSize: 13)),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),

                  // Error banner
                  if (_error != null)
                    Container(
                      margin: const EdgeInsets.only(top: 8),
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: AppTheme.error.withOpacity(0.1),
                        border:
                            Border.all(color: AppTheme.error.withOpacity(0.2)),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline,
                              color: AppTheme.error, size: 14),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(_error!,
                                style: const TextStyle(
                                    color: AppTheme.error, fontSize: 12)),
                          ),
                          GestureDetector(
                            onTap: _load,
                            child: const Text('重试',
                                style: TextStyle(
                                    color: AppTheme.error,
                                    fontSize: 12,
                                    decoration: TextDecoration.underline)),
                          ),
                        ],
                      ),
                    ),

                  // ── Search bar + filters ──
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Row(
                      children: [
                        // Search
                        SizedBox(
                          width: 260,
                          height: 36,
                          child: TextField(
                            style: const TextStyle(
                                color: AppTheme.textPrimary, fontSize: 13),
                            decoration: InputDecoration(
                              hintText: '搜索事件...',
                              hintStyle: const TextStyle(
                                  color: AppTheme.textMuted, fontSize: 12),
                              prefixIcon: const Icon(Icons.search,
                                  size: 16, color: AppTheme.textMuted),
                              suffixIcon: _search.isNotEmpty
                                  ? GestureDetector(
                                      onTap: () {
                                        setState(() {
                                          _search = '';
                                          _page = 1;
                                        });
                                      },
                                      child: const Icon(Icons.clear,
                                          size: 14,
                                          color: AppTheme.textMuted),
                                    )
                                  : null,
                              filled: true,
                              fillColor: AppTheme.panel,
                              contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 0),
                              border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide: const BorderSide(
                                      color: AppTheme.border)),
                              enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide: const BorderSide(
                                      color: AppTheme.border)),
                              focusedBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide: const BorderSide(
                                      color: AppTheme.purple, width: 0.5)),
                            ),
                            onChanged: (v) {
                              setState(() {
                                _search = v;
                                _page = 1;
                              });
                            },
                          ),
                        ),
                        const SizedBox(width: 12),

                        // Status filter chips
                        ..._buildFilterChips(
                          label: '状态',
                          items: _kAllStatuses,
                          selected: _statusFilter,
                          labelFn: _statusLabel,
                          onSelected: (v) {
                            setState(() {
                              _statusFilter =
                                  v == _statusFilter ? null : v;
                              _page = 1;
                            });
                          },
                        ),
                        const SizedBox(width: 12),

                        // Topic filter chips
                        ..._buildFilterChips(
                          label: '分类',
                          items: _kAllTopics,
                          selected: _topicFilter,
                          labelFn: (t) => t,
                          onSelected: (v) {
                            setState(() {
                              _topicFilter =
                                  v == _topicFilter ? null : v;
                              _page = 1;
                            });
                            _load();
                          },
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1, color: AppTheme.border),
                ],
              ),
            ),

            // ── Scrollable content ──
            Expanded(
              child: _loading
                  ? const Center(
                      child: CircularProgressIndicator(
                          color: AppTheme.accent))
                  : _items.isEmpty
                      ? const Center(
                          child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text('📡',
                                    style: TextStyle(fontSize: 48)),
                                SizedBox(height: 12),
                                Text('暂无事件',
                                    style: TextStyle(
                                        color: AppTheme.textSecondary,
                                        fontSize: 15)),
                                SizedBox(height: 4),
                                Text('事件将在这里展示',
                                    style: TextStyle(
                                        color: AppTheme.textMuted,
                                        fontSize: 12)),
                              ]),
                        )
                      : Column(
                          children: [
                            Expanded(
                              child: ListView(
                                padding: const EdgeInsets.fromLTRB(
                                    32, 12, 32, 12),
                                children: [
                                  // ── Table container ──
                                  Container(
                                    decoration: BoxDecoration(
                                      color: AppTheme.panel,
                                      border: Border.all(
                                          color: AppTheme.border),
                                      borderRadius:
                                          BorderRadius.circular(12),
                                    ),
                                    clipBehavior: Clip.antiAlias,
                                    child: Column(
                                      children: [
                                        // Table header
                                        Container(
                                          padding:
                                              const EdgeInsets.symmetric(
                                                  horizontal: 20,
                                                  vertical: 12),
                                          decoration: const BoxDecoration(
                                            border: Border(
                                                bottom: BorderSide(
                                                    color:
                                                        AppTheme.border)),
                                          ),
                                          child: Row(
                                            children: [
                                              const Expanded(
                                                  flex: 5,
                                                  child: Text('标题',
                                                      style: TextStyle(
                                                          color: AppTheme
                                                              .textMuted,
                                                          fontSize: 12))),
                                              const SizedBox(
                                                  width: 80,
                                                  child: Center(
                                                      child: Text('来源',
                                                          style: TextStyle(
                                                              color: AppTheme
                                                                  .textMuted,
                                                              fontSize:
                                                                  12)))),
                                              const SizedBox(
                                                  width: 64,
                                                  child: Center(
                                                      child: Text('分类',
                                                          style: TextStyle(
                                                              color: AppTheme
                                                                  .textMuted,
                                                              fontSize:
                                                                  12)))),
                                              const SizedBox(
                                                  width: 64,
                                                  child: Center(
                                                      child: Text('状态',
                                                          style: TextStyle(
                                                              color: AppTheme
                                                                  .textMuted,
                                                              fontSize:
                                                                  12)))),
                                              const SizedBox(
                                                  width: 104,
                                                  child: Center(
                                                      child: Text('时间',
                                                          style: TextStyle(
                                                              color: AppTheme
                                                                  .textMuted,
                                                              fontSize:
                                                                  12)))),
                                              const SizedBox(
                                                  width: 64,
                                                  child: Center(
                                                      child: Text('操作',
                                                          style: TextStyle(
                                                              color: AppTheme
                                                                  .textMuted,
                                                              fontSize:
                                                                  12)))),
                                            ],
                                          ),
                                        ),

                                        // Rows
                                        if (paged.isEmpty)
                                          const Padding(
                                            padding: EdgeInsets.symmetric(
                                                vertical: 48),
                                            child: Center(
                                                child: Text('没有匹配的结果',
                                                    style: TextStyle(
                                                        color: AppTheme
                                                            .textMuted,
                                                        fontSize: 13))),
                                          )
                                        else
                                          ...paged.map(
                                              (item) => _buildRow(item)),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
                            ),

                            // ── Bottom bar (pagination) ──
                            Container(
                              padding: const EdgeInsets.fromLTRB(
                                  32, 0, 32, 12),
                              color: AppTheme.background,
                              child: Row(
                                children: [
                                  Text('共 ${filtered.length} 条',
                                      style: const TextStyle(
                                          color: AppTheme.textMuted,
                                          fontSize: 12)),
                                  const Spacer(),
                                  if (totalPages > 1) ...[
                                    IconButton(
                                      onPressed: safePage > 1
                                          ? () => setState(
                                              () => _page = safePage - 1)
                                          : null,
                                      icon: const Icon(Icons.chevron_left,
                                          size: 18),
                                      color: AppTheme.textMuted,
                                      padding: EdgeInsets.zero,
                                      constraints: const BoxConstraints(
                                          minWidth: 28, minHeight: 28),
                                    ),
                                    Text('$safePage / $totalPages',
                                        style: const TextStyle(
                                            color: AppTheme.textMuted,
                                            fontSize: 12)),
                                    IconButton(
                                      onPressed:
                                          safePage < totalPages
                                              ? () => setState(() =>
                                                  _page = safePage + 1)
                                              : null,
                                      icon: const Icon(
                                          Icons.chevron_right,
                                          size: 18),
                                      color: AppTheme.textMuted,
                                      padding: EdgeInsets.zero,
                                      constraints: const BoxConstraints(
                                          minWidth: 28, minHeight: 28),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ],
                        ),
            ),
          ],
        ),
      ),
    );
  }

  // ── Filter chip builder ──
  List<Widget> _buildFilterChips({
    required String label,
    required List<String> items,
    required String? selected,
    required String Function(String) labelFn,
    required void Function(String) onSelected,
  }) {
    final chips = <Widget>[
      Text('$label:',
          style:
              const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
      const SizedBox(width: 6),
    ];
    for (final item in items) {
      final active = selected == item;
      chips.add(
        Padding(
          padding: const EdgeInsets.only(right: 4),
          child: GestureDetector(
            onTap: () => onSelected(item),
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: active
                    ? AppTheme.purple.withOpacity(0.15)
                    : AppTheme.panel,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(
                    color: active
                        ? AppTheme.purple.withOpacity(0.3)
                        : AppTheme.border),
              ),
              child: Text(
                labelFn(item),
                style: TextStyle(
                  color:
                      active ? AppTheme.purple : AppTheme.textMuted,
                  fontSize: 11,
                  fontWeight:
                      active ? FontWeight.w500 : FontWeight.normal,
                ),
              ),
            ),
          ),
        ),
      );
    }
    return chips;
  }

  // ── Table row + inline expand ──
  Widget _buildRow(Map<String, dynamic> item) {
    final id = item['id']?.toString() ?? '';
    final title = item['title'] as String? ?? '(无标题)';
    final sourceName = item['source_name'] as String? ?? '';
    final topic = item['topic'] as String? ?? '';
    final status = item['status'] as String? ?? '';
    final createdAt = item['created_at'] as String? ?? '';
    final expanded = _expandedIds.contains(id);

    return Column(
      children: [
        InkWell(
          onTap: () => _toggleExpand(id),
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: 20, vertical: 14),
            decoration: const BoxDecoration(
              border: Border(
                  bottom: BorderSide(
                      color: AppTheme.border, width: 0.5)),
            ),
            child: Row(
              children: [
                // Title (flex 5)
                Expanded(
                  flex: 5,
                  child: Text(
                    title,
                    style: const TextStyle(
                        color: AppTheme.textPrimary, fontSize: 13),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),

                // Source badge
                SizedBox(
                  width: 80,
                  child: Center(
                    child: sourceName.isNotEmpty
                        ? Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                                color: AppTheme.panelActive,
                                borderRadius:
                                    BorderRadius.circular(4)),
                            child: Text(
                              sourceName,
                              style: const TextStyle(
                                  color: AppTheme.textMuted,
                                  fontSize: 10),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          )
                        : const Text('—',
                            style: TextStyle(
                                color: AppTheme.textMuted,
                                fontSize: 11)),
                  ),
                ),

                // Topic badge
                SizedBox(
                  width: 64,
                  child: Center(
                    child: topic.isNotEmpty
                        ? Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                                color: _topicBg(topic),
                                borderRadius:
                                    BorderRadius.circular(4)),
                            child: Text(
                              topic,
                              style: TextStyle(
                                  color: _topicColor(topic),
                                  fontSize: 10,
                                  fontWeight: FontWeight.w500),
                            ),
                          )
                        : const Text('—',
                            style: TextStyle(
                                color: AppTheme.textMuted,
                                fontSize: 11)),
                  ),
                ),

                // Status badge
                SizedBox(
                  width: 64,
                  child: Center(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                          color: _statusColor(status)
                              .withOpacity(0.12),
                          borderRadius:
                              BorderRadius.circular(4)),
                      child: Text(
                        _statusLabel(status),
                        style: TextStyle(
                            color: _statusColor(status),
                            fontSize: 10,
                            fontWeight: FontWeight.w500),
                      ),
                    ),
                  ),
                ),

                // Date
                SizedBox(
                  width: 104,
                  child: Center(
                    child: Text(
                      _formatDate(createdAt),
                      style: const TextStyle(
                          color: AppTheme.textMuted, fontSize: 11),
                    ),
                  ),
                ),

                // Actions
                SizedBox(
                  width: 64,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      GestureDetector(
                        onTap: () => _toggleExpand(id),
                        child: Container(
                          width: 28,
                          height: 28,
                          decoration: BoxDecoration(
                              color: Colors.transparent,
                              borderRadius:
                                  BorderRadius.circular(4)),
                          child: Icon(
                            expanded
                                ? Icons.expand_less
                                : Icons.expand_more,
                            size: 16,
                            color: AppTheme.textMuted,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),

        // ── Inline expand detail panel ──
        if (expanded) _buildDetailPanel(item),
      ],
    );
  }

  // ── Detail panel: title_cn, summary_cn / raw_summary, metadata ──
  Widget _buildDetailPanel(Map<String, dynamic> item) {
    final titleCn = item['title_cn'] as String?;
    final summaryCn = item['summary_cn'] as String?;
    final rawSummary = item['raw_summary'] as String?;
    final sourceName = item['source_name'] as String? ?? '';
    final sourceId = item['source_id']?.toString() ?? '';
    final status = item['status'] as String? ?? '';
    final createdAt = item['created_at'] as String? ?? '';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
      decoration: const BoxDecoration(
        border: Border(
            bottom: BorderSide(color: AppTheme.border, width: 0.5)),
        color: Color(0xFF0E0F14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Chinese title
          if (titleCn != null && titleCn.isNotEmpty) ...[
            _detailLabel('中文标题'),
            const SizedBox(height: 4),
            Text(titleCn,
                style: const TextStyle(
                    color: AppTheme.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500)),
            const SizedBox(height: 12),
          ],

          // Chinese summary
          if (summaryCn != null && summaryCn.isNotEmpty) ...[
            _detailLabel('中文摘要'),
            const SizedBox(height: 4),
            Text(summaryCn,
                style: const TextStyle(
                    color: AppTheme.textSecondary,
                    fontSize: 13,
                    height: 1.5)),
            const SizedBox(height: 12),
          ],

          // Raw summary
          if (rawSummary != null && rawSummary.isNotEmpty) ...[
            _detailLabel('原始摘要'),
            const SizedBox(height: 4),
            Text(rawSummary,
                style: const TextStyle(
                    color: AppTheme.textMuted,
                    fontSize: 12,
                    height: 1.5),
                maxLines: 8,
                overflow: TextOverflow.ellipsis),
            const SizedBox(height: 12),
          ],

          // Metadata
          _detailLabel('元数据'),
          const SizedBox(height: 6),
          Wrap(
            spacing: 16,
            runSpacing: 6,
            children: [
              _metaItem('来源', sourceName),
              if (sourceId.isNotEmpty) _metaItem('来源ID', sourceId),
              _metaItem('状态', _statusLabel(status)),
              _metaItem('时间', _formatDate(createdAt)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _detailLabel(String text) {
    return Text(text,
        style: const TextStyle(
            color: AppTheme.textMuted,
            fontSize: 11,
            fontWeight: FontWeight.w600));
  }

  Widget _metaItem(String label, String value) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('$label: ',
            style: const TextStyle(
                color: AppTheme.textMuted, fontSize: 11)),
        Text(value,
            style: const TextStyle(
                color: AppTheme.textSecondary, fontSize: 11)),
      ],
    );
  }

  // ── Beijing time formatter (UTC+8) ──
  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso).add(const Duration(hours: 8));
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}
