import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

const _kTopics = [
  ('格局', '地缘政治·大国博弈·国际关系', Icons.public, '格局', AppTheme.blue),
  ('财富', '经济金融·商业洞察·投资理财', Icons.monetization_on_outlined, '财富', AppTheme.amber),
  ('认知', '思维模型·方法论·底层逻辑', Icons.psychology, '认知', AppTheme.purple),
  ('前瞻', '科技趋势·未来预判·前沿动态', Icons.explore, '前瞻', AppTheme.emerald),
];

Color _topicColor(String topic) {
  switch (topic) {
    case '格局': return const Color(0xFF60A5FA);
    case '财富': return const Color(0xFFFBBF24);
    case '认知': return const Color(0xFFA78BFA);
    case '前瞻': return const Color(0xFF34D399);
    default: return const Color(0xFF9CA3AF);
  }
}

Color _topicBg(String topic) {
  switch (topic) {
    case '格局': return const Color(0xFF60A5FA).withOpacity(0.12);
    case '财富': return const Color(0xFFFBBF24).withOpacity(0.12);
    case '认知': return const Color(0xFFA78BFA).withOpacity(0.12);
    case '前瞻': return const Color(0xFF34D399).withOpacity(0.12);
    default: return const Color(0xFF9CA3AF).withOpacity(0.12);
  }
}

int _docCount(Map<String, dynamic> item) {
  try {
    final raw = item['answered_event_ids'] as String?;
    if (raw == null || raw.isEmpty) return 0;
    final list = jsonDecode(raw);
    return list is List ? list.length : 0;
  } catch (_) {
    return 0;
  }
}

class BrainstormPage extends StatefulWidget {
  const BrainstormPage({super.key});
  @override
  State<BrainstormPage> createState() => _BrainstormPageState();
}

class _BrainstormPageState extends State<BrainstormPage> {
  final ApiClient _api = ApiClient();

  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  String? _error;
  String _tab = '格局';
  String _search = '';
  final Set<String> _selectedIds = {};
  Map<String, int> _topicCounts = {};

  static const _pageSize = 15;
  int _page = 1;

  // Create modal
  final _questionCtrl = TextEditingController();
  bool _creating = false;
  String? _createError;

  @override
  void initState() {
    super.initState();
    _load();
    _loadTopicCounts();
  }

  @override
  void dispose() {
    _questionCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final resp = await _api.getBrainstorms(topic: _tab, limit: 5000);
      if (mounted) {
        final items = (resp['questions'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
        setState(() { _items = items; _loading = false; _page = 1; _selectedIds.clear(); });
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _loadTopicCounts() async {
    try {
      final d = await _api.getBrainstormTopicCounts();
      if (mounted) {
        final m = <String, int>{};
        d.forEach((k, v) => m[k] = (v is int) ? v : int.tryParse('$v') ?? 0);
        setState(() => _topicCounts = m);
      }
    } catch (_) {}
  }

  Future<void> _delete(String id) async {
    final ok = await showDialog<bool>(
      useRootNavigator: true,
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppTheme.panel,
        title: const Text('确认删除', style: TextStyle(color: AppTheme.textPrimary)),
        content: const Text('确认删除这条问题？', style: TextStyle(color: AppTheme.textSecondary)),
        actions: [
          TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(true), child: const Text('删除', style: TextStyle(color: AppTheme.error))),
        ],
      ),
    );
    if (ok == true) {
      try {
        await _api.deleteBrainstorm(id);
        _load();
      } catch (_) {}
    }
  }

  Future<void> _batchDelete() async {
    if (_selectedIds.isEmpty) return;
    final ok = await showDialog<bool>(
      useRootNavigator: true,
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppTheme.panel,
        title: const Text('批量删除', style: TextStyle(color: AppTheme.textPrimary)),
        content: Text('确定要删除选中的 ${_selectedIds.length} 条问题吗？', style: const TextStyle(color: AppTheme.textSecondary)),
        actions: [
          TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(true), child: const Text('删除', style: TextStyle(color: AppTheme.error))),
        ],
      ),
    );
    if (ok == true) {
      try {
        await _api.batchDeleteBrainstorms(_selectedIds.toList());
        setState(() => _selectedIds.clear());
        _load();
      } catch (_) {}
    }
  }

  void _toggleSelect(String id) {
    setState(() {
      if (_selectedIds.contains(id)) _selectedIds.remove(id); else _selectedIds.add(id);
    });
  }

  void _showCreateModal() {
    _questionCtrl.clear();
    _createError = null;
    showDialog(
      useRootNavigator: true,
      context: context,
      builder: (_) => StatefulBuilder(builder: (ctx, setDlgState) {
        return AlertDialog(
          backgroundColor: AppTheme.panel,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: AppTheme.purple, width: 0.5),
          ),
          title: const Row(children: [
            Icon(Icons.lightbulb, size: 20, color: AppTheme.purple),
            SizedBox(width: 8),
            Text('新建问题', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
          ]),
          content: SizedBox(
            width: 440,
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('问题内容', style: TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
              const SizedBox(height: 6),
              TextField(
                controller: _questionCtrl,
                autofocus: true,
                maxLines: 3,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '输入你想探索的问题...',
                  hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                  filled: true,
                  fillColor: AppTheme.background,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.purple, width: 0.5)),
                ),
              ),
              if (_createError != null) Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_createError!, style: const TextStyle(color: AppTheme.error, fontSize: 12)),
              ),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(), child: const Text('取消', style: TextStyle(color: AppTheme.textMuted))),
            FilledButton(
              onPressed: _creating ? null : () async {
                final q = _questionCtrl.text.trim();
                if (q.isEmpty) return;
                setState(() { _creating = true; _createError = null; });
                setDlgState(() => _creating = true);
                try {
                  await _api.createBrainstorm(q);
                  if (mounted) Navigator.of(context, rootNavigator: true).pop();
                  _load();
                } catch (e) {
                  _createError = e.toString();
                  setDlgState(() { _creating = false; _createError = _createError; });
                }
                if (mounted) setState(() => _creating = false);
              },
              style: FilledButton.styleFrom(backgroundColor: AppTheme.purple.withOpacity(0.6)),
              child: _creating ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('创建'),
            ),
          ],
        );
      }),
    );
  }

  // Client-side search filter
  List<Map<String, dynamic>> _filtered() {
    if (_search.isEmpty) return _items;
    final s = _search.toLowerCase();
    return _items.where((item) {
      final q = (item['question'] as String? ?? '').toLowerCase();
      return q.contains(s);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final filtered = _filtered();
    final totalPages = filtered.isEmpty ? 1 : ((filtered.length / _pageSize).ceil());
    final safePage = _page.clamp(1, totalPages);
    final paged = filtered.isEmpty ? <Map<String, dynamic>>[] : filtered.sublist(
      (safePage - 1) * _pageSize,
      safePage * _pageSize > filtered.length ? filtered.length : safePage * _pageSize,
    );
    final count = _topicCounts[_tab] ?? _items.length;

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(children: [
          // Sticky header
          Container(
            padding: const EdgeInsets.fromLTRB(32, 24, 32, 0),
            decoration: const BoxDecoration(
              color: AppTheme.background,
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Title row
              Row(children: [
                const Icon(Icons.lightbulb, color: AppTheme.purple, size: 32),
                const SizedBox(width: 12),
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('头脑风暴', style: TextStyle(color: AppTheme.textPrimary, fontSize: 22, fontWeight: FontWeight.bold)),
                  const Text('好的问题，比答案更接近真相', style: TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
                ]),
                const Spacer(),
                GestureDetector(
                  onTap: _showCreateModal,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: AppTheme.purple.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppTheme.purple.withOpacity(0.25)),
                    ),
                    child: const Row(mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.add, size: 14, color: AppTheme.purple),
                      SizedBox(width: 6),
                      Text('新建问题', style: TextStyle(color: AppTheme.purple, fontSize: 13, fontWeight: FontWeight.w500)),
                    ]),
                  ),
                ),
              ]),
              const SizedBox(height: 4),
              // Error
              if (_error != null)
                Container(
                  margin: const EdgeInsets.only(top: 8),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: AppTheme.error.withOpacity(0.1),
                    border: Border.all(color: AppTheme.error.withOpacity(0.2)),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(children: [
                    const Icon(Icons.error_outline, color: AppTheme.error, size: 14),
                    const SizedBox(width: 8),
                    Expanded(child: Text(_error!, style: const TextStyle(color: AppTheme.error, fontSize: 12))),
                    GestureDetector(onTap: _load, child: const Text('重试', style: TextStyle(color: AppTheme.error, fontSize: 12, decoration: TextDecoration.underline))),
                  ]),
                ),
              // Tabs
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: SizedBox(
                  height: 48,
                  child: Row(children: _kTopics.map((t) {
                    final (key, sub, icon, label, color) = t;
                    final active = _tab == key;
                    return GestureDetector(
                      onTap: () { setState(() { _tab = key; _page = 1; _selectedIds.clear(); }); _load(); },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 20),
                        decoration: BoxDecoration(
                          border: Border(bottom: BorderSide(color: active ? AppTheme.purple : Colors.transparent, width: 2)),
                        ),
                        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                          Row(mainAxisSize: MainAxisSize.min, children: [
                            Icon(icon, size: 16, color: active ? color : AppTheme.textMuted),
                            const SizedBox(width: 6),
                            Text(label, style: TextStyle(color: active ? AppTheme.textPrimary : AppTheme.textMuted, fontSize: 13, fontWeight: FontWeight.w600)),
                          ]),
                          const SizedBox(height: 2),
                          Text(sub, style: const TextStyle(color: AppTheme.textMuted, fontSize: 9)),
                        ]),
                      ),
                    );
                  }).toList()),
                ),
              ),
              const Divider(height: 1, color: AppTheme.border),
            ]),
          ),

          // Scrollable content
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
                : _items.isEmpty
                    ? Center(
                        child: Column(mainAxisSize: MainAxisSize.min, children: [
                          const Text('💡', style: TextStyle(fontSize: 48)),
                          const SizedBox(height: 12),
                          const Text('暂无头脑风暴问题', style: TextStyle(color: AppTheme.textSecondary, fontSize: 15)),
                          const SizedBox(height: 4),
                          const Text('点击上方「+ 新建问题」按钮手动添加灵感', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                        ]),
                      )
                    : Column(children: [
                        Expanded(
                          child: ListView(padding: const EdgeInsets.fromLTRB(32, 12, 32, 12), children: [
                            // Table container
                            Container(
                              decoration: BoxDecoration(
                                color: AppTheme.panel,
                                border: Border.all(color: AppTheme.border),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              clipBehavior: Clip.antiAlias,
                              child: Column(children: [
                                // Table header
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                                  decoration: const BoxDecoration(
                                    border: Border(bottom: BorderSide(color: AppTheme.border)),
                                  ),
                                  child: Row(children: [
                                    const SizedBox(width: 28),
                                    const Expanded(flex: 5, child: Center(child: Text('问题', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)))),
                                    const SizedBox(width: 80, child: Center(child: Text('分类', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)))),
                                    const SizedBox(width: 72, child: Center(child: Text('关联文档', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)))),
                                    const SizedBox(width: 104, child: Center(child: Text('提交时间', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)))),
                                    const SizedBox(width: 64, child: Center(child: Text('操作', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)))),
                                  ]),
                                ),
                                // Rows
                                if (paged.isEmpty)
                                  const Padding(
                                    padding: EdgeInsets.symmetric(vertical: 48),
                                    child: Center(child: Text('没有匹配的结果', style: TextStyle(color: AppTheme.textMuted, fontSize: 13))),
                                  )
                                else
                                  ...paged.map((item) => _buildRow(item)),
                              ]),
                            ),
                          ]),
                        ),
                        // Bottom bar
                        Container(
                          padding: const EdgeInsets.fromLTRB(32, 0, 32, 12),
                          color: AppTheme.background,
                          child: Row(children: [
                            // Search
                            SizedBox(
                              width: 200, height: 32,
                              child: TextField(
                                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
                                decoration: InputDecoration(
                                  hintText: '搜索问题...',
                                  hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                                  prefixIcon: const Icon(Icons.search, size: 14, color: AppTheme.textMuted),
                                  filled: true, fillColor: AppTheme.panel,
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 8),
                                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                                  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.purple, width: 0.5)),
                                ),
                                onChanged: (v) => setState(() { _search = v; _page = 1; }),
                              ),
                            ),
                            const Spacer(),
                            // Batch delete
                            if (_selectedIds.isNotEmpty)
                              GestureDetector(
                                onTap: _batchDelete,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: AppTheme.error.withOpacity(0.12),
                                    borderRadius: BorderRadius.circular(6),
                                    border: Border.all(color: AppTheme.error.withOpacity(0.2)),
                                  ),
                                  child: Text('删除选中 (${_selectedIds.length})', style: const TextStyle(color: AppTheme.error, fontSize: 12)),
                                ),
                              ),
                            const SizedBox(width: 16),
                            // Pagination
                            Text('共 $count 条', style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                            if (totalPages > 1) ...[
                              const SizedBox(width: 8),
                              Row(mainAxisSize: MainAxisSize.min, children: [
                                IconButton(
                                  onPressed: safePage > 1 ? () => setState(() => _page = safePage - 1) : null,
                                  icon: const Icon(Icons.chevron_left, size: 18),
                                  color: AppTheme.textMuted,
                                  padding: EdgeInsets.zero,
                                  constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                                ),
                                Text('$safePage / $totalPages', style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                                IconButton(
                                  onPressed: safePage < totalPages ? () => setState(() => _page = safePage + 1) : null,
                                  icon: const Icon(Icons.chevron_right, size: 18),
                                  color: AppTheme.textMuted,
                                  padding: EdgeInsets.zero,
                                  constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                                ),
                              ]),
                            ],
                          ]),
                        ),
                      ]),
          ),
        ]),
      ),
    );
  }

  Widget _buildRow(Map<String, dynamic> item) {
    final id = item['id'] as String? ?? '';
    final question = item['question'] as String? ?? '(无问题)';
    final topic = item['topic'] as String? ?? '';
    final createdAt = item['created_at'] as String? ?? '';
    final count = _docCount(item);
    final selected = _selectedIds.contains(id);

    return InkWell(
      onTap: () => _toggleSelect(id),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: AppTheme.border, width: 0.5)),
        ),
        child: Row(children: [
          // Checkbox
          SizedBox(
            width: 28,
            child: Align(
              alignment: Alignment.center,
              child: GestureDetector(
                onTap: () => _toggleSelect(id),
                child: Container(
                  width: 16, height: 16,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(2),
                    border: Border.all(color: selected ? AppTheme.purple : const Color(0xFF555555), width: 1.5),
                    color: selected ? AppTheme.purple.withOpacity(0.2) : Colors.transparent,
                  ),
                  child: selected ? const Icon(Icons.check, size: 10, color: AppTheme.purple) : null,
                ),
              ),
            ),
          ),
          // Question
          Expanded(
            flex: 5,
            child: Text(question, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13), maxLines: 2, overflow: TextOverflow.ellipsis),
          ),
          // Topic badge
          SizedBox(
            width: 80,
            child: Center(
              child: topic.isNotEmpty
                  ? Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(color: _topicBg(topic), borderRadius: BorderRadius.circular(4)),
                      child: Text(topic, style: TextStyle(color: _topicColor(topic), fontSize: 10, fontWeight: FontWeight.w500)),
                    )
                  : const Text('—', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
            ),
          ),
          // Doc count
          SizedBox(
            width: 72,
            child: Center(
              child: count > 0
                  ? Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(color: AppTheme.purple.withOpacity(0.12), borderRadius: BorderRadius.circular(4)),
                      child: Text('$count 篇', style: const TextStyle(color: AppTheme.purple, fontSize: 10, fontWeight: FontWeight.w500)),
                    )
                  : const Text('—', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
            ),
          ),
          // Date
          SizedBox(
            width: 104,
            child: Center(child: Text(_formatDate(createdAt), style: const TextStyle(color: AppTheme.textMuted, fontSize: 11))),
          ),
          // Actions
          SizedBox(
            width: 64,
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              GestureDetector(
                onTap: () => context.go('/brainstorm/$id'),
                child: Container(
                  width: 28, height: 28,
                  decoration: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(4)),
                  child: const Icon(Icons.open_in_full, size: 14, color: AppTheme.textMuted),
                ),
              ),
              GestureDetector(
                onTap: () => _delete(id),
                child: Container(
                  width: 28, height: 28,
                  decoration: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(4)),
                  child: const Icon(Icons.delete_outline, size: 14, color: AppTheme.textMuted),
                ),
              ),
            ]),
          ),
        ]),
      ),
    );
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso).add(const Duration(hours: 8));
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) { return iso; }
  }
}
