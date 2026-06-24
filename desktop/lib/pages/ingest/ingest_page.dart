import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';
import 'event_detail_page.dart';

class IngestPage extends StatefulWidget {
  const IngestPage({super.key});
  @override
  State<IngestPage> createState() => _IngestPageState();
}

class _IngestPageState extends State<IngestPage> {
  final _dio = ApiClient().dio;
  final _scrollCtrl = ScrollController();

  // Tabs
  String _tab = '格局';
  static const _tabs = ['格局', '财富', '认知', '前瞻', 'briefing'];

  // Events
  List<Map<String, dynamic>> _events = [];
  bool _loading = false;
  String _error = '';
  int _total = 0;
  int _page = 1;
  static const _pageSize = 15;

  // Search
  final _searchCtrl = TextEditingController();
  Timer? _searchDebounce;

  // Selection
  final _selected = <String>{};

  // Stats
  int _todaySubs = 0;
  int _processing = 0;
  int _completed = 0;

  // Queue
  List<Map<String, dynamic>> _queueItems = [];
  Timer? _queueTimer;
  bool _queueShowAllDone = false;

  // Modals
  String? _modalType; // 'douyin' | 'file' | 'concept' | 'queue'
  final _dyTextCtrl = TextEditingController();
  final _dyTopicCtrl = TextEditingController();
  bool _dySubmitting = false;
  String _dyError = '';
  final _fileTitleCtrl = TextEditingController();
  final _fileTopicCtrl = TextEditingController();
  String? _selectedFilePath;
  String? _selectedFileName;
  bool _fileSubmitting = false;
  String _flError = '';
  final _conceptTitleCtrl = TextEditingController();
  String _conceptTopic = '';
  final _conceptDescCtrl = TextEditingController();
  bool _conceptSubmitting = false;
  String _ceError = '';

  // Polling
  String? _pollId;
  Map<String, dynamic>? _pollStatus;
  List<Map<String, dynamic>>? _progressStages;
  Timer? _pollTimer;

  // Briefing
  List<Map<String, dynamic>> _briefingTopics = [];
  bool _briefingLoading = false;
  final _bpExpanded = <String>{};

  @override
  void initState() {
    super.initState();
    _load();
    _loadStats();
    _loadQueue();
    _queueTimer = Timer.periodic(const Duration(seconds: 3), (_) => _loadQueue());
  }

  @override
  void dispose() {
    _scrollCtrl.dispose();
    _searchCtrl.dispose();
    _searchDebounce?.cancel();
    _queueTimer?.cancel();
    _pollTimer?.cancel();
    _dyTextCtrl.dispose();
    _dyTopicCtrl.dispose();
    _fileTitleCtrl.dispose();
    _fileTopicCtrl.dispose();
    _conceptTitleCtrl.dispose();
    _conceptDescCtrl.dispose();
    super.dispose();
  }

  // ── API ──
  Future<void> _load() async {
    setState(() { _loading = true; _error = ''; });
    try {
      final sourceId = _tab == 'briefing' ? '' : 'douyin,user-upload,user-concept';
      final topicParam = ['格局','财富','认知','前瞻'].contains(_tab) ? '&topic=$_tab' : '';
      final searchParam = _searchCtrl.text.isNotEmpty ? '&search=${Uri.encodeComponent(_searchCtrl.text)}' : '';
      final resp = await _dio.get(
        '/api/events?source_id=$sourceId$topicParam$searchParam&limit=$_pageSize&offset=${(_page-1)*_pageSize}&count=1',
      );
      final data = resp.data;
      setState(() {
        _events = List<Map<String, dynamic>>.from(data['items'] ?? []);
        _total = data['total'] ?? 0;
        _loading = false;
      });
    } catch (e) {
      setState(() { _error = '$e'; _loading = false; });
    }
  }

  Future<void> _loadStats() async {
    try {
      final resp = await _dio.get('/api/ingest/stats');
      final d = resp.data;
      setState(() {
        _todaySubs = d['today_submissions'] ?? 0;
        _processing = d['processing'] ?? 0;
        _completed = d['completed'] ?? 0;
      });
    } catch (_) {}
  }

  Future<void> _loadQueue() async {
    try {
      final resp = await _dio.get('/api/ingest/queue?limit=30');
      final items = List<Map<String, dynamic>>.from(resp.data['items'] ?? []);
      if (mounted) setState(() => _queueItems = items);
    } catch (_) {}
  }

  Future<void> _deleteQueueTask(int taskId) async {
    try {
      await _dio.delete('/api/ingest/queue/$taskId');
      _loadQueue();
    } catch (_) {}
  }

  Future<void> _retryQueueTask(int taskId) async {
    try {
      await _dio.post('/api/ingest/queue/$taskId/retry');
      _loadQueue();
    } catch (_) {}
  }

  Future<void> _deleteEvent(String eventId) async {
    try {
      await _dio.delete('/api/events/$eventId');
      _load(); _loadStats();
    } catch (_) {}
  }

  Future<void> _batchDelete() async {
    if (_selected.isEmpty) return;
    try {
      await _dio.post('/api/events/batch-delete', data: {'event_ids': _selected.toList()});
      _selected.clear();
      _load(); _loadStats();
    } catch (_) {}
  }

  void _onTabChanged(String t) {
    setState(() { _tab = t; _page = 1; _selected.clear(); });
    _load();
    if (t == 'briefing') _loadBriefing();
  }

  void _openDetail(String eventId) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => EventDetailPage(eventId: eventId)));
  }

  void _onSearch(String v) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 400), () {
      setState(() => _page = 1);
      _load();
    });
  }

  // ── Douyin submit ──
  Future<void> _submitDouyin() async {
    final text = _dyTextCtrl.text.trim();
    if (text.isEmpty) return;
    setState(() { _dySubmitting = true; _dyError = ''; });
    try {
      final resp = await _dio.post('/api/ingest/douyin', data: {
        'share_text': text, 'topic': _dyTopicCtrl.text.trim().isEmpty ? 'uncategorized' : _dyTopicCtrl.text.trim(),
      });
      final eventId = resp.data['event_id'];
      _startPolling(eventId);
      _dyTextCtrl.clear(); _dyTopicCtrl.clear();
      _loadQueue();
    } catch (e) {
      setState(() => _dyError = '$e');
    }
    setState(() => _dySubmitting = false);
  }

  // ── File submit ──
  Future<void> _pickFile() async {
    final result = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'doc', 'docx', 'txt', 'md', 'mp4', 'mp3', 'wav', 'jpg', 'jpeg', 'png'],
    );
    if (result != null && result.files.isNotEmpty) {
      final f = result.files.first;
      setState(() {
        _selectedFilePath = f.path;
        _selectedFileName = f.name;
        if (_fileTitleCtrl.text.isEmpty) {
          _fileTitleCtrl.text = f.name.replaceAll(RegExp(r'\.[^.]+$'), '');
        }
      });
    }
  }

  Future<void> _submitFile() async {
    if (_selectedFilePath == null) return;
    setState(() { _fileSubmitting = true; _flError = ''; });
    try {
      final formData = FormData.fromMap({
        'file': await MultipartFile.fromFile(_selectedFilePath!, filename: _selectedFileName),
        'title': _fileTitleCtrl.text,
        'topic': _fileTopicCtrl.text.trim().isEmpty ? 'uncategorized' : _fileTopicCtrl.text.trim(),
      });
      final resp = await _dio.post('/api/ingest/file', data: formData);
      final eventId = resp.data['event_id'];
      _startPolling(eventId);
      setState(() { _selectedFilePath = null; _selectedFileName = null; _fileTitleCtrl.clear(); _fileTopicCtrl.clear(); });
      _loadQueue();
    } catch (e) {
      setState(() => _flError = '$e');
    }
    setState(() => _fileSubmitting = false);
  }

  // ── Concept submit ──
  Future<void> _submitConcept() async {
    final title = _conceptTitleCtrl.text.trim();
    if (title.isEmpty) return;
    setState(() { _conceptSubmitting = true; _ceError = ''; });
    try {
      await _dio.post('/api/ingest/concept', data: {
        'title': title,
        'topic': _conceptTopic.isEmpty ? 'uncategorized' : _conceptTopic,
        'description': _conceptDescCtrl.text.trim(),
      });
      _conceptTitleCtrl.clear(); _conceptTopic = ''; _conceptDescCtrl.clear();
      setState(() => _modalType = null);
      _load();
    } catch (e) {
      setState(() => _ceError = '$e');
    }
    setState(() => _conceptSubmitting = false);
  }

  // ── Polling ──
  void _startPolling(String eventId) {
    _pollTimer?.cancel();
    _pollId = eventId;
    _pollStatus = {'event_id': eventId, 'status': 'processing'};
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) => _pollStatusCheck());
  }

  Future<void> _pollStatusCheck() async {
    if (_pollId == null) return;
    try {
      final resp = await _dio.get('/api/ingest/status/$_pollId');
      final d = resp.data;
      if (!mounted) return;
      setState(() {
        _pollStatus = d;
        _progressStages = d['progress_stages'] != null
            ? List<Map<String, dynamic>>.from(d['progress_stages'])
            : null;
      });
      if (d['status'] == 'completed' || d['status'] == 'failed') {
        _pollTimer?.cancel();
        Future.delayed(const Duration(seconds: 2), () {
          if (!mounted) return;
          setState(() { _pollId = null; _pollStatus = null; _progressStages = null; _modalType = null; });
          _load(); _loadStats(); _loadQueue();
        });
      }
    } catch (_) {}
  }

  // ── Briefing ──
  Future<void> _loadBriefing() async {
    setState(() => _briefingLoading = true);
    try {
      final resp = await _dio.get('/api/briefing/latest?briefing_type=quick');
      setState(() => _briefingTopics = List<Map<String, dynamic>>.from(resp.data['topics'] ?? []));
    } catch (_) {}
    setState(() => _briefingLoading = false);
  }

  // ── Collect ──
  Future<void> _handleCollect() async {
    try {
      final resp = await _dio.post('/api/collect');
      final d = resp.data;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('采集完成：新增 ${d['new_events'] ?? 0} 条'), behavior: SnackBarBehavior.floating, width: 280),
        );
        _load(); _loadStats();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('采集失败: $e'), behavior: SnackBarBehavior.floating, width: 280),
        );
      }
    }
  }

  // ── Helpers ──
  String _taskTitle(Map<String, dynamic> t) {
    if (t['title'] != null && t['title'] != '待处理') return t['title'];
    try {
      final p = t['payload_json'] != null ? jsonDecode(t['payload_json']) : null;
      if (p != null && p['content_text'] != null) {
        final s = p['content_text'] as String;
        return s.length > 50 ? '${s.substring(0, 50)}…' : s;
      }
    } catch (_) {}
    return _taskTypeLabel(t['ingest_type'] ?? '');
  }

  String _taskTypeLabel(String t) {
    switch (t) {
      case 'douyin_share': return '抖音分享';
      case 'video_file': return '视频文件';
      case 'audio_file': return '音频文件';
      case 'document': return '文档';
      default: return t;
    }
  }

  String _sourceLabel(String id) {
    if (id.startsWith('douyin')) return '抖音';
    if (id == 'user-upload') return '上传';
    if (id == 'user-concept') return '概念';
    return id;
  }

  Color _sourceColor(String id) {
    if (id.startsWith('douyin')) return AppTheme.rose;
    if (id == 'user-upload') return AppTheme.cyan;
    if (id == 'user-concept') return AppTheme.emerald;
    return AppTheme.textMuted;
  }

  String _formatTime(String? t) {
    if (t == null) return '';
    try {
      final dt = DateTime.parse(t);
      return DateFormat('HH:mm').format(dt);
    } catch (_) { return ''; }
  }

  // ── Build ──
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(children: [
          // Header
          _buildHeader(),
          // Tabs
          _buildTabs(),
          const Divider(height: 1, color: AppTheme.border),
          // Content
          Expanded(child: _tab == 'briefing' ? _buildBriefingTab() : _buildEventList()),
        ]),
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 20, 32, 12),
      child: Row(children: [
        const Icon(Icons.download, size: 28, color: AppTheme.purple),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('内容采集', style: TextStyle(color: AppTheme.textPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            const Text('今天也是汲取智慧的一天', style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
          ]),
        ),
        const SizedBox(width: 12),
        // Search
        SizedBox(
          width: 180, height: 32,
          child: TextField(
            controller: _searchCtrl,
            style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
            decoration: InputDecoration(
              hintText: '搜索...', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
              prefixIcon: const Icon(Icons.search, size: 14, color: AppTheme.textMuted),
              contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              filled: true, fillColor: AppTheme.panel,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: AppTheme.border)),
            ),
            onChanged: _onSearch,
          ),
        ),
        const SizedBox(width: 8),
        _actionBtn('抖音分享', Icons.music_note, AppTheme.rose, _showDouyinModal),
        const SizedBox(width: 6),
        _actionBtn('上传文件', Icons.upload_file, AppTheme.cyan, _showFileModal),
        const SizedBox(width: 6),
        _actionBtn('沉淀概念', Icons.lightbulb, AppTheme.emerald, _showConceptModal),
        const SizedBox(width: 6),
        _actionBtn('立即采集', Icons.sync, AppTheme.emerald, _handleCollect),
      ]),
    );
  }

  Widget _statChip(String label, int count, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: color.withOpacity(0.12), borderRadius: BorderRadius.circular(4)),
      child: Text('$label $count', style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w500)),
    );
  }

  Widget _actionBtn(String label, IconData icon, Color color, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: color.withOpacity(0.1),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withOpacity(0.25)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w500)),
        ]),
      ),
    );
  }

  Widget _buildTabs() {
    return SizedBox(
      height: 56,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 24),
        children: [
          for (final t in _tabs) _tabBtn(t),
        ],
      ),
    );
  }

  Widget _tabBtn(String t) {
    final active = _tab == t;
    final icon = switch (t) { '格局' => Icons.public, '财富' => Icons.monetization_on, '认知' => Icons.psychology, '前瞻' => Icons.explore, _ => Icons.bolt };
    final sub = switch (t) {
      '格局' => '地缘政治·大国博弈·国际关系',
      '财富' => '经济金融·商业洞察·投资理财',
      '认知' => '思维模型·方法论·底层逻辑',
      '前瞻' => '科技趋势·未来预判·前沿动态',
      _ => '全球要闻·智能整理·快速浏览',
    };
    return GestureDetector(
      onTap: () => _onTabChanged(t),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: active ? AppTheme.accent : Colors.transparent, width: 2)),
        ),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 16, color: active ? AppTheme.accent : AppTheme.textMuted),
            const SizedBox(width: 4),
            Text(t, style: TextStyle(color: active ? AppTheme.textPrimary : AppTheme.textMuted, fontSize: 13, fontWeight: active ? FontWeight.w600 : FontWeight.w400)),
          ]),
          const SizedBox(height: 2),
          Text(sub, style: TextStyle(color: active ? AppTheme.textSecondary : AppTheme.textMuted.withOpacity(0.5), fontSize: 10)),
        ]),
      ),
    );
  }

  Widget _buildEventList() {
    if (_loading) return const Center(child: CircularProgressIndicator(color: AppTheme.accent));
    if (_events.isEmpty) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.inbox, size: 48, color: AppTheme.textMuted),
        const SizedBox(height: 12),
        const Text('暂无内容', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
        const SizedBox(height: 4),
        const Text('上传抖音链接或文件开始摄入', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ]));
    }

    final maxPage = (_total / _pageSize).ceil();

    return Column(children: [
      Expanded(
        child: ListView.builder(
          controller: _scrollCtrl,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
          itemCount: _events.length,
          itemBuilder: (_, i) {
            final evt = _events[i];
            final id = evt['id'] as String;
            final sel = _selected.contains(id);
            return Container(
              margin: const EdgeInsets.only(bottom: 4),
              decoration: BoxDecoration(
                color: sel ? AppTheme.accent.withOpacity(0.08) : AppTheme.panel,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: sel ? AppTheme.accent.withOpacity(0.3) : AppTheme.border.withOpacity(0.5)),
              ),
              child: InkWell(
                onTap: () => setState(() => sel ? _selected.remove(id) : _selected.add(id)),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
                  child: Row(children: [
                    Checkbox(
                      value: sel, onChanged: (_) => setState(() => sel ? _selected.remove(id) : _selected.add(id)),
                      activeColor: AppTheme.accent,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      visualDensity: VisualDensity.compact,
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: GestureDetector(
                        onTap: () => _openDetail(id),
                        child: Text(evt['title'] as String? ?? '', style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(color: _sourceColor(evt['source_id'] as String? ?? '').withOpacity(0.12), borderRadius: BorderRadius.circular(4)),
                      child: Text(_sourceLabel(evt['source_id'] as String? ?? ''), style: TextStyle(color: _sourceColor(evt['source_id'] as String? ?? ''), fontSize: 10, fontWeight: FontWeight.w500)),
                    ),
                    const SizedBox(width: 8),
                    Text(_formatTime(evt['created_at'] as String?), style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                    const SizedBox(width: 4),
                    IconButton(
                      icon: const Icon(Icons.open_in_new, size: 14), color: AppTheme.textMuted,
                      tooltip: '详情',
                      onPressed: () => _openDetail(id),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 16), color: AppTheme.textMuted,
                      onPressed: () {
                        showDialog(useRootNavigator: true, context: context, builder: (_) => AlertDialog(
                          backgroundColor: AppTheme.panel,
                          title: const Text('删除确认', style: TextStyle(color: AppTheme.textPrimary)),
                          content: const Text('确定要删除这条记录吗？', style: TextStyle(color: AppTheme.textSecondary)),
                          actions: [
                            TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(), child: const Text('取消')),
                            TextButton(onPressed: () { Navigator.of(context, rootNavigator: true).pop(); _deleteEvent(id); }, child: const Text('删除', style: TextStyle(color: AppTheme.error))),
                          ],
                        ));
                      },
                    ),
                  ]),
                ),
              ),
            );
          },
        ),
      ),
      // Pagination
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
        child: Row(children: [
          if (_selected.isNotEmpty) ...[
            TextButton.icon(
              onPressed: _batchDelete,
              icon: const Icon(Icons.delete_outline, size: 16, color: AppTheme.error),
              label: Text('删除选中 (${_selected.length})', style: const TextStyle(color: AppTheme.error, fontSize: 12)),
            ),
            const SizedBox(width: 8),
          ],
          const Spacer(),
          Text('共 $_total 条', style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
          const SizedBox(width: 16),
          IconButton(
            icon: const Icon(Icons.chevron_left, size: 18), color: _page > 1 ? AppTheme.textSecondary : AppTheme.textMuted,
            onPressed: _page > 1 ? () { setState(() => _page--); _load(); } : null,
          ),
          Text('$_page / $maxPage', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
          IconButton(
            icon: const Icon(Icons.chevron_right, size: 18), color: _page < maxPage ? AppTheme.textSecondary : AppTheme.textMuted,
            onPressed: _page < maxPage ? () { setState(() => _page++); _load(); } : null,
          ),
        ]),
      ),
    ]);
  }

  // ── Briefing tab ──
  Widget _buildBriefingTab() {
    if (_briefingLoading) return const Center(child: CircularProgressIndicator(color: AppTheme.accent));
    if (_briefingTopics.isEmpty) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.newspaper, size: 48, color: AppTheme.textMuted),
        const SizedBox(height: 12),
        const Text('暂无新闻简报', style: TextStyle(color: AppTheme.textMuted)),
        const SizedBox(height: 8),
        TextButton.icon(onPressed: _handleCollect, icon: const Icon(Icons.sync, size: 16), label: const Text('立即采集')),
      ]));
    }
    return ListView.builder(
      padding: const EdgeInsets.all(24),
      itemCount: _briefingTopics.length,
      itemBuilder: (_, i) {
        final t = _briefingTopics[i];
        final expanded = _bpExpanded.contains(t['topic']);
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppTheme.border)),
          child: Column(children: [
            InkWell(
              onTap: () => setState(() => expanded ? _bpExpanded.remove(t['topic']) : _bpExpanded.add(t['topic'])),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(10)),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(children: [
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(t['topic_label'] as String? ?? t['topic'] as String? ?? '', style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
                    if (t['summary'] != null) ...[
                      const SizedBox(height: 4),
                      Text(t['summary'] as String, style: const TextStyle(color: AppTheme.textMuted, fontSize: 12), maxLines: 2, overflow: TextOverflow.ellipsis),
                    ],
                  ])),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(color: AppTheme.accent.withOpacity(0.12), borderRadius: BorderRadius.circular(4)),
                    child: Text('${(t['events'] as List?)?.length ?? 0} 条', style: const TextStyle(color: AppTheme.accent, fontSize: 11)),
                  ),
                  const SizedBox(width: 4),
                  Icon(expanded ? Icons.expand_less : Icons.expand_more, size: 18, color: AppTheme.textMuted),
                ]),
              ),
            ),
            if (expanded) ...(t['events'] as List? ?? []).map((e) => _briefingEventRow(e as Map<String, dynamic>)),
          ]),
        );
      },
    );
  }

  Widget _briefingEventRow(Map<String, dynamic> e) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: AppTheme.border))),
      child: Row(children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(e['title_cn'] as String? ?? e['title'] as String? ?? '', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12), maxLines: 1),
          Row(children: [
            if (e['source_name'] != null) Text(e['source_name'] as String, style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
            const SizedBox(width: 8),
            Text(_formatTime(e['created_at'] as String?), style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
          ]),
        ])),
      ]),
    );
  }

  // ── Queue modal ──
  void _showQueueModal() {
    final running = _queueItems.where((t) => t['status'] == 'running').toList();
    final pending = _queueItems.where((t) => t['status'] == 'pending').toList();
    final errors = _queueItems.where((t) => t['status'] == 'failed' || t['status'] == 'error').toList();
    final done = _queueItems.where((t) => t['status'] == 'done').toList();
    final showAll = _queueShowAllDone;
    final visibleDone = showAll ? done : done.take(5).toList();

    showDialog(
      useRootNavigator: true,
      context: context,
      builder: (_) => StatefulBuilder(builder: (ctx, setDlgState) {
        return AlertDialog(
          backgroundColor: AppTheme.panel,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: AppTheme.border)),
          insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
          title: Row(children: [
            const Icon(Icons.list_alt, size: 20, color: AppTheme.purple),
            const SizedBox(width: 8),
            const Text('处理队列', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
            const Spacer(),
            IconButton(icon: const Icon(Icons.refresh, size: 18, color: AppTheme.textMuted), onPressed: () { _loadQueue(); setDlgState(() {}); }),
          ]),
          content: SizedBox(
            width: 560,
            child: SingleChildScrollView(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                // Running
                ...running.map((t) => _queueItemCard(t, Icons.sync, AppTheme.amber, true)),
                if (pending.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('排队等待（${pending.length}）', style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                  ...pending.map((t) => _queueItemRow(t, Icons.hourglass_empty, AppTheme.textMuted, '排队中…', showDelete: true)),
                ],
                if (errors.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('失败（${errors.length}）', style: const TextStyle(color: AppTheme.error, fontSize: 11)),
                  ...errors.map((t) => _queueItemRow(t, Icons.error_outline, AppTheme.error, t['error']?.toString() ?? '', showRetry: true, showDelete: true)),
                ],
                if (done.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Row(children: [
                    Text('已完成（${done.length}）', style: const TextStyle(color: AppTheme.emerald, fontSize: 11)),
                    if (done.length > 5) ...[
                      const Spacer(),
                      GestureDetector(
                        onTap: () { _queueShowAllDone = !showAll; setDlgState(() {}); },
                        child: Text(showAll ? '收起' : '展开全部 ${done.length} 条', style: const TextStyle(color: AppTheme.accent, fontSize: 11)),
                      ),
                    ],
                  ]),
                  ...visibleDone.map((t) => _queueItemRow(t, Icons.check_circle, AppTheme.emerald, '已完成', showDelete: true)),
                ],
              ]),
            ),
          ),
          actions: [TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(), child: const Text('关闭', style: TextStyle(color: AppTheme.textMuted)))],
        );
      }),
    );
  }

  Widget _queueItemCard(Map<String, dynamic> t, IconData icon, Color color, bool showStages) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: color.withOpacity(0.06), borderRadius: BorderRadius.circular(8), border: Border.all(color: color.withOpacity(0.2))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _pulsingDot(color),
          const SizedBox(width: 8),
          Expanded(child: Text(_taskTitle(t), style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis)),
        ]),
        if (showStages && _progressStages != null) ...[
          const SizedBox(height: 8),
          _buildStages(),
        ],
      ]),
    );
  }

  Widget _queueItemRow(Map<String, dynamic> t, IconData icon, Color color, String subtitle, {bool showRetry = false, bool showDelete = false}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 2),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 8),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(_taskTitle(t), style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12), maxLines: 1, overflow: TextOverflow.ellipsis),
          Text(subtitle, style: TextStyle(color: color.withOpacity(0.7), fontSize: 10), maxLines: 1, overflow: TextOverflow.ellipsis),
        ])),
        if (showRetry) IconButton(icon: const Icon(Icons.refresh, size: 16, color: AppTheme.amber), onPressed: () => _retryQueueTask(t['id'])),
        if (showDelete) IconButton(icon: const Icon(Icons.close, size: 16, color: AppTheme.textMuted), onPressed: () => _deleteQueueTask(t['id'])),
      ]),
    );
  }

  Widget _buildStages() {
    final stages = _progressStages ?? [];
    return Row(children: [
      for (int i = 0; i < stages.length; i++) ...[
        _stageDot(stages[i]['status'] as String? ?? 'pending'),
        if (i < stages.length - 1) Expanded(child: Container(height: 1, color: AppTheme.border)),
      ],
    ]);
  }

  Widget _stageDot(String status) {
    Color c;
    IconData i;
    switch (status) {
      case 'done': c = AppTheme.emerald; i = Icons.check_circle; break;
      case 'active': c = AppTheme.amber; i = Icons.circle; break;
      case 'error': c = AppTheme.error; i = Icons.cancel; break;
      default: c = AppTheme.textMuted; i = Icons.circle_outlined;
    }
    return Icon(i, size: 14, color: c);
  }

  Widget _pulsingDot(Color color) {
    return Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle));
  }

  // ── Douyin / File / Concept modals ──
  void _showDouyinModal() {
    showDialog(
      useRootNavigator: true,
      context: context,
      builder: (_) => StatefulBuilder(builder: (ctx, setDlgState) {
        return AlertDialog(
          backgroundColor: AppTheme.panel,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: AppTheme.rose, width: 1)),
          insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
          title: const Row(children: [
            Icon(Icons.music_note, size: 20, color: AppTheme.rose),
            SizedBox(width: 8),
            Text('抖音分享', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
          ]),
          content: SizedBox(
            width: 440,
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              TextField(
                controller: _dyTextCtrl, maxLines: 4,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '粘贴抖音分享文本...', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 13),
                  filled: true, fillColor: AppTheme.background,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _dyTopicCtrl,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '分类（格局/财富/认知/前瞻）', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                  filled: true, fillColor: AppTheme.background,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                ),
              ),
              if (_dyError.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_dyError, style: const TextStyle(color: AppTheme.error, fontSize: 12))),
              if (_pollStatus != null) ...[
                const SizedBox(height: 12),
                _queueItemCard({'title': '处理中...', 'payload_json': null, 'ingest_type': 'douyin_share'}, Icons.sync, AppTheme.amber, true),
              ],
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(), child: const Text('取消', style: TextStyle(color: AppTheme.textMuted))),
            FilledButton(
              onPressed: _dySubmitting ? null : () { _submitDouyin(); setDlgState(() {}); },
              style: FilledButton.styleFrom(backgroundColor: AppTheme.rose),
              child: _dySubmitting ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('提交'),
            ),
          ],
        );
      }),
    );
  }

  void _showFileModal() {
    showDialog(
      useRootNavigator: true,
      context: context,
      builder: (_) => StatefulBuilder(builder: (ctx, setDlgState) {
        return AlertDialog(
          backgroundColor: AppTheme.panel,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: AppTheme.cyan, width: 1)),
          insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
          title: const Row(children: [
            Icon(Icons.upload_file, size: 20, color: AppTheme.cyan),
            SizedBox(width: 8),
            Text('上传文件', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
          ]),
          content: SizedBox(
            width: 440,
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              TextField(
                controller: _fileTitleCtrl,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '标题（可选）', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                  filled: true, fillColor: AppTheme.background,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _fileTopicCtrl,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '分类', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                  filled: true, fillColor: AppTheme.background,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                ),
              ),
              const SizedBox(height: 12),
              GestureDetector(
                onTap: () { _pickFile().then((_) => setDlgState(() {})); },
                child: Container(
                  width: double.infinity, padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: AppTheme.background, borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppTheme.border, style: BorderStyle.solid),
                  ),
                  child: Column(children: [
                    Icon(Icons.cloud_upload_outlined, size: 32, color: _selectedFileName != null ? AppTheme.cyan : AppTheme.textMuted),
                    const SizedBox(height: 8),
                    Text(_selectedFileName ?? '点击选择文件', style: TextStyle(color: _selectedFileName != null ? AppTheme.cyan : AppTheme.textMuted, fontSize: 13)),
                    const SizedBox(height: 4),
                    const Text('支持音视频、文档格式', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                  ]),
                ),
              ),
              if (_flError.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_flError, style: const TextStyle(color: AppTheme.error, fontSize: 12))),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(), child: const Text('取消', style: TextStyle(color: AppTheme.textMuted))),
            FilledButton(
              onPressed: (_fileSubmitting || _selectedFilePath == null) ? null : () { _submitFile(); setDlgState(() {}); },
              style: FilledButton.styleFrom(backgroundColor: AppTheme.cyan),
              child: _fileSubmitting ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('上传'),
            ),
          ],
        );
      }),
    );
  }

  void _showConceptModal() {
    showDialog(
      useRootNavigator: true,
      context: context,
      builder: (_) => StatefulBuilder(builder: (ctx, setDlgState) {
        return AlertDialog(
          backgroundColor: AppTheme.panel,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: AppTheme.emerald, width: 1)),
          insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
          title: const Row(children: [
            Icon(Icons.lightbulb, size: 20, color: AppTheme.emerald),
            SizedBox(width: 8),
            Text('沉淀概念', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
          ]),
          content: SizedBox(
            width: 440,
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              TextField(
                controller: _conceptTitleCtrl, autofocus: true,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '概念名称', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 13),
                  filled: true, fillColor: AppTheme.background,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                ),
              ),
              const SizedBox(height: 8),
              Wrap(spacing: 6, children: ['格局', '财富', '认知', '前瞻'].map((topic) {
                final sel = _conceptTopic == topic;
                final color = switch (topic) { '格局' => AppTheme.blue, '财富' => AppTheme.amber, '认知' => AppTheme.purple, _ => AppTheme.cyan };
                return GestureDetector(
                  onTap: () => setDlgState(() => _conceptTopic = sel ? '' : topic),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: sel ? color.withOpacity(0.15) : AppTheme.background,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: sel ? color : AppTheme.border),
                    ),
                    child: Text(topic, style: TextStyle(color: sel ? color : AppTheme.textMuted, fontSize: 12)),
                  ),
                );
              }).toList()),
              const SizedBox(height: 8),
              TextField(
                controller: _conceptDescCtrl, maxLines: 3,
                style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '描述（留空则 AI 自动补全）', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                  filled: true, fillColor: AppTheme.background,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
                ),
              ),
              if (_ceError.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_ceError, style: const TextStyle(color: AppTheme.error, fontSize: 12))),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(context, rootNavigator: true).pop(), child: const Text('取消', style: TextStyle(color: AppTheme.textMuted))),
            FilledButton(
              onPressed: (_conceptSubmitting || _conceptTitleCtrl.text.trim().isEmpty) ? null : _submitConcept,
              style: FilledButton.styleFrom(backgroundColor: AppTheme.emerald),
              child: _conceptSubmitting ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('创建'),
            ),
          ],
        );
      }),
    );
  }
}
