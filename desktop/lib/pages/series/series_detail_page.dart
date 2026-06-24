import 'dart:async';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';
import '../ingest/event_detail_page.dart';

// ── Constants (1:1 from TSX) ──

const Map<String, String> _statusLabel = {
  'published': '已发布',
  'draft': '草稿',
  'candidate': '候选',
};

const Map<String, Color> _topicColors = {
  '格局': AppTheme.blue,
  '财富': AppTheme.amber,
  '认知': AppTheme.purple,
  '前瞻': AppTheme.emerald,
};

const Map<String, String> _sourceLabel = {
  'douyin': '抖音',
  'user-upload': '上传',
  'user-concept': '概念',
};

const _refColors = [
  AppTheme.blue,
  AppTheme.amber,
  AppTheme.emerald,
  AppTheme.rose,
  AppTheme.cyan,
  Color(0xFFA78BFA),
  AppTheme.orange,
  AppTheme.teal,
];

Color _refColor(int n) => _refColors[(n - 1) % _refColors.length];

// ── Helpers ──

String _formatTimeBeijing(String? t) {
  if (t == null) return '';
  try {
    final dt = DateTime.parse(t);
    return DateFormat('yyyy-MM-dd HH:mm').format(dt);
  } catch (_) {
    return '';
  }
}

Color _getTopicColor(String topic) =>
    _topicColors[topic] ?? AppTheme.textMuted;

String _getSourceLabel(String id) {
  for (final key in _sourceLabel.keys) {
    if (id.startsWith(key)) return _sourceLabel[key]!;
  }
  return id;
}

// ── SeriesDetailPage ──

class SeriesDetailPage extends StatefulWidget {
  final String seriesId;
  const SeriesDetailPage({super.key, required this.seriesId});

  @override
  State<SeriesDetailPage> createState() => _SeriesDetailPageState();
}

class _SeriesDetailPageState extends State<SeriesDetailPage> {
  final _dio = ApiClient().dio;

  // Core state
  Map<String, dynamic>? _series;
  bool _loading = true;
  String _error = '';

  // Generation flags
  bool _introGenerating = false;
  bool _summaryGenerating = false;
  bool _paperGenerating = false;
  bool _deleting = false;

  // Tab
  String _tab = 'overview';

  // Suggestions
  List<Map<String, dynamic>> _suggestions = [];
  final _selectedIds = <String>{};
  bool _batchAdding = false;

  // Refresh
  bool _refreshing = false;
  bool _allProcessed = false;

  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _loadDetail();
    _loadSuggestions();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  // ── API ──

  Future<void> _loadDetail() async {
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final resp = await _dio.get('/api/ingest/series/${widget.seriesId}');
      final d = resp.data as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _series = d;
        _loading = false;
        final hasIntro =
            d['intro'] != null && (d['intro'] as String).isNotEmpty;
        final hasSummary =
            d['summary'] != null && (d['summary'] as String).isNotEmpty;
        final hasPaper =
            d['paper'] != null && (d['paper'] as String).isNotEmpty;
        if (!hasIntro && !hasSummary && !hasPaper) {
          _tab = 'content';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _loadSuggestions() async {
    try {
      final resp =
          await _dio.get('/api/ingest/series/${widget.seriesId}/suggestions');
      final items = (resp.data['suggestions'] as List<dynamic>?)
              ?.cast<Map<String, dynamic>>() ??
          [];
      if (!mounted) return;
      setState(() {
        _suggestions = items;
        _allProcessed = items.isEmpty;
      });
    } catch (_) {}
  }

  Future<void> _handleGenerateIntro() async {
    if (_series == null) return;
    final members = (_series!['members'] as List<dynamic>?) ?? [];
    if (members.length < 2) return;
    setState(() => _introGenerating = true);
    try {
      final resp =
          await _dio.put('/api/ingest/series/${widget.seriesId}/intro');
      if (resp.statusCode == 200 && mounted) {
        final d = resp.data;
        setState(() {
          _series = {...?_series, 'intro': d['intro']};
          _introGenerating = false;
        });
      } else {
        if (mounted) setState(() => _introGenerating = false);
      }
    } catch (_) {
      if (mounted) setState(() => _introGenerating = false);
    }
  }

  Future<void> _handleGenerateSummary() async {
    if (_series == null) return;
    final members = (_series!['members'] as List<dynamic>?) ?? [];
    if (members.length < 2) return;
    setState(() => _summaryGenerating = true);
    try {
      final resp =
          await _dio.put('/api/ingest/series/${widget.seriesId}/summary');
      if (resp.statusCode == 200 && mounted) {
        final d = resp.data;
        setState(() {
          _series = {...?_series, 'summary': d['summary']};
          _summaryGenerating = false;
        });
      } else {
        if (mounted) setState(() => _summaryGenerating = false);
      }
    } catch (_) {
      if (mounted) setState(() => _summaryGenerating = false);
    }
  }

  Future<void> _handleGeneratePaper() async {
    if (_series == null) return;
    final members = (_series!['members'] as List<dynamic>?) ?? [];
    if (members.length < 2) return;
    setState(() => _paperGenerating = true);
    try {
      final resp =
          await _dio.put('/api/ingest/series/${widget.seriesId}/paper');
      if (resp.statusCode == 200 && mounted) {
        final d = resp.data;
        setState(() {
          _series = {...?_series, 'paper': d['paper']};
          _paperGenerating = false;
        });
      } else {
        if (mounted) setState(() => _paperGenerating = false);
      }
    } catch (_) {
      if (mounted) setState(() => _paperGenerating = false);
    }
  }

  Future<void> _handleDelete() async {
    if (_series == null) return;
    setState(() => _deleting = true);
    try {
      await _dio.delete('/api/ingest/series/${widget.seriesId}');
      if (mounted) {
        Navigator.pop(context);
      }
    } catch (_) {
      if (mounted) setState(() => _deleting = false);
    }
  }

  void _toggleSelect(String eventId) {
    setState(() {
      if (_selectedIds.contains(eventId)) {
        _selectedIds.remove(eventId);
      } else {
        _selectedIds.add(eventId);
      }
    });
  }

  void _toggleSelectAll() {
    setState(() {
      if (_selectedIds.length == _suggestions.length &&
          _suggestions.isNotEmpty) {
        _selectedIds.clear();
      } else {
        _selectedIds.addAll(_suggestions.map((s) => s['id'] as String));
      }
    });
  }

  void _handleBatchDismiss() {
    if (_selectedIds.isEmpty) return;
    setState(() {
      _suggestions =
          _suggestions.where((s) => !_selectedIds.contains(s['id'])).toList();
      _allProcessed = _suggestions.isEmpty;
      _selectedIds.clear();
    });
  }

  Future<void> _handleBatchAdd() async {
    if (_selectedIds.isEmpty) return;
    setState(() => _batchAdding = true);

    // Show progress modal
    if (mounted) {
      _showProgressModal();
    }

    try {
      // Stage 1: Add members
      await _dio.post('/api/ingest/series/${widget.seriesId}/members',
          data: {'event_ids': _selectedIds.toList()});
      if (!mounted) return;
      _updateProgress('summary');

      // Stage 2: Regenerate summary
      await _dio.put('/api/ingest/series/${widget.seriesId}/summary');
      if (!mounted) return;
      _updateProgress('paper');

      // Stage 3: Regenerate paper
      await _dio.put('/api/ingest/series/${widget.seriesId}/paper');
      if (!mounted) return;
      _updateProgress('done');

      // Refresh data
      await _loadDetail();
      if (!mounted) return;

      // Remove processed suggestions
      setState(() {
        _suggestions = _suggestions
            .where((s) => !_selectedIds.contains(s['id']))
            .toList();
        _allProcessed = _suggestions.isEmpty;
        _selectedIds.clear();
        _batchAdding = false;
      });

      // Auto-close modals after brief pause
      Future.delayed(const Duration(milliseconds: 1500), () {
        if (!mounted) return;
        Navigator.of(context, rootNavigator: true).popUntil((route) {
          // Close all dialogs
          return route.settings.name != null ||
              route is! PopupRoute;
        });
        // Then pop any remaining dialogs
        if (Navigator.of(context, rootNavigator: true).canPop()) {
          Navigator.of(context, rootNavigator: true).pop();
        }
      });
    } catch (_) {
      if (mounted) setState(() => _batchAdding = false);
    }
  }

  // Progress modal is shown via a separate overlay; track stage separately
  String _progressStage = 'adding';
  OverlayEntry? _progressOverlay;

  void _updateProgress(String stage) {
    _progressStage = stage;
    // Progress overlay is stateless — we don't need to rebuild it for this simple flow.
    // The overlay shows a static view; we don't update it mid-flight since the API calls
    // go quickly. For a more interactive progress UI, we'd use a StatefulBuilder dialog.
  }

  Future<void> _handleRefresh() async {
    if (_series == null) return;
    setState(() {
      _refreshing = true;
      _allProcessed = false;
    });
    try {
      await _dio.post('/api/ingest/series/${widget.seriesId}/expand');
      await _loadSuggestions();
    } catch (_) {}
    if (mounted) setState(() => _refreshing = false);
  }

  void _handleRefClick(int n) {
    if (_series == null) return;
    final members = (_series!['members'] as List<dynamic>?) ?? [];
    final idx = n - 1;
    if (idx >= 0 && idx < members.length) {
      final member = members[idx] as Map<String, dynamic>;
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => EventDetailPage(eventId: member['id'] as String),
        ),
      );
    }
  }

  void _navigateToTask() {
    final name = _series?['name'] as String? ?? '';
    Navigator.pushNamed(context, '/tasks',
        arguments:
            'source=series&source_id=${widget.seriesId}&source_label=来自专题：$name');
  }

  // ── Build ──

  @override
  Widget build(BuildContext context) {
    // Loading
    if (_loading) {
      return const Scaffold(
        backgroundColor: AppTheme.background,
        body: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(
                strokeWidth: 2, color: AppTheme.textMuted),
          ),
        ),
      );
    }

    // Error
    if (_error.isNotEmpty || _series == null) {
      return Scaffold(
        backgroundColor: AppTheme.background,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _error.isNotEmpty ? _error : '专题不存在',
                style: const TextStyle(color: AppTheme.error, fontSize: 13),
              ),
              const SizedBox(height: 16),
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('返回专题列表',
                    style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
              ),
            ],
          ),
        ),
      );
    }

    final members =
        (_series!['members'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ??
            [];
    final name = _series!['name'] as String? ?? '';
    final description = _series!['description'] as String? ?? '';
    final status = _series!['status'] as String? ?? '';
    final intro = _series!['intro'] as String?;
    final summary = _series!['summary'] as String?;
    final paper = _series!['paper'] as String?;
    final createdAt = _series!['created_at'] as String?;
    final updatedAt = _series!['updated_at'] as String?;

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(32, 16, 32, 32),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1152),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildBreadcrumb(),
                const SizedBox(height: 24),
                _buildHeader(name, description, status, members, createdAt,
                    updatedAt),
                if (intro != null && intro.isNotEmpty) ...[
                  const SizedBox(height: 24),
                  _buildIntro(intro),
                ],
                const SizedBox(height: 24),
                _buildTabBar(),
                const SizedBox(height: 24),
                _buildTabContent(members, summary, paper, intro),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ── Breadcrumb ──

  Widget _buildBreadcrumb() {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => Navigator.pop(context),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.arrow_back, size: 14, color: AppTheme.textMuted),
            SizedBox(width: 6),
            Text('专题系列',
                style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
          ],
        ),
      ),
    );
  }

  // ── Header ──

  Widget _buildHeader(
    String name,
    String description,
    String status,
    List<Map<String, dynamic>> members,
    String? createdAt,
    String? updatedAt,
  ) {
    final hasIntro = _series?['intro'] is String &&
        (_series!['intro'] as String).isNotEmpty;
    final hasSummary = _series?['summary'] is String &&
        (_series!['summary'] as String).isNotEmpty;
    final hasPaper = _series?['paper'] is String &&
        (_series!['paper'] as String).isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.layers, size: 24, color: AppTheme.purple),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    crossAxisAlignment: WrapCrossAlignment.center,
                    spacing: 8,
                    children: [
                      Text(name,
                          style: const TextStyle(
                              color: AppTheme.textPrimary,
                              fontSize: 20,
                              fontWeight: FontWeight.bold)),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppTheme.panelActive,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          _statusLabel[status] ?? status,
                          style: const TextStyle(
                              color: AppTheme.textMuted, fontSize: 10),
                        ),
                      ),
                    ],
                  ),
                  if (description.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(description,
                        style: const TextStyle(
                            color: AppTheme.textSecondary, fontSize: 13)),
                  ],
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text('${members.length} 条内容',
                              style: const TextStyle(
                                  color: AppTheme.textMuted, fontSize: 11)),
                          if (_suggestions.isEmpty && !_allProcessed) ...[
                            const SizedBox(width: 4),
                            GestureDetector(
                              onTap: _refreshing ? null : _handleRefresh,
                              child: _refreshing
                                  ? const SizedBox(
                                      width: 11,
                                      height: 11,
                                      child: CircularProgressIndicator(
                                          strokeWidth: 1.5,
                                          color: AppTheme.textMuted))
                                  : const Icon(Icons.refresh,
                                      size: 11, color: AppTheme.textMuted),
                            ),
                          ],
                        ],
                      ),
                      if (_suggestions.isNotEmpty)
                        GestureDetector(
                          onTap: () => _showSuggestionsModal(),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppTheme.amber.withOpacity(0.1),
                              border: Border.all(
                                  color: AppTheme.amber.withOpacity(0.2)),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(Icons.notifications,
                                    size: 10, color: AppTheme.amber),
                                const SizedBox(width: 4),
                                Text('待确认 (${_suggestions.length})',
                                    style: const TextStyle(
                                        color: AppTheme.amber, fontSize: 11)),
                              ],
                            ),
                          ),
                        ),
                      Text('创建于 ${_formatTimeBeijing(createdAt)}',
                          style: const TextStyle(
                              color: AppTheme.textMuted, fontSize: 11)),
                      if (updatedAt != null)
                        Text('更新于 ${_formatTimeBeijing(updatedAt)}',
                            style: const TextStyle(
                                color: AppTheme.textMuted, fontSize: 11)),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        // Action buttons row
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            _actionBtn(
              _introGenerating
                  ? '...'
                  : (hasIntro ? '重新生成导言' : 'AI 生成导言'),
              Icons.auto_awesome,
              AppTheme.amber,
              _introGenerating || members.length < 2
                  ? null
                  : _handleGenerateIntro,
              loading: _introGenerating,
            ),
            _actionBtn(
              _summaryGenerating
                  ? '...'
                  : (hasSummary ? '重新生成总结' : 'AI 生成总结'),
              Icons.auto_awesome,
              AppTheme.emerald,
              _summaryGenerating || members.length < 2
                  ? null
                  : _handleGenerateSummary,
              loading: _summaryGenerating,
            ),
            _actionBtn(
              _paperGenerating
                  ? '...'
                  : (hasPaper ? '重新生成深度分析' : 'AI 深度分析'),
              Icons.auto_awesome,
              AppTheme.sky,
              _paperGenerating || members.length < 2
                  ? null
                  : _handleGeneratePaper,
              loading: _paperGenerating,
            ),
            _actionBtn(
                '添加待办', Icons.add, AppTheme.sky, _navigateToTask),
            _actionBtn(
              '',
              Icons.delete_outline,
              AppTheme.error,
              () => _showConfirmDeleteModal(),
              iconOnly: true,
            ),
          ],
        ),
      ],
    );
  }

  Widget _actionBtn(
    String label,
    IconData icon,
    Color color,
    VoidCallback? onTap, {
    bool loading = false,
    bool iconOnly = false,
  }) {
    final disabled = onTap == null;
    return MouseRegion(
      cursor: disabled ? SystemMouseCursors.basic : SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: Opacity(
          opacity: disabled ? 0.5 : 1.0,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: color.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: color.withOpacity(0.2)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (loading)
                  SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 1.5, color: color),
                  )
                else
                  Icon(icon, size: 14, color: color),
                if (!iconOnly && label.isNotEmpty) ...[
                  const SizedBox(width: 6),
                  Text(label,
                      style: TextStyle(
                          color: color,
                          fontSize: 12,
                          fontWeight: FontWeight.w500)),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ── Intro section ──

  Widget _buildIntro(String intro) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [
            Color(0x0D8B5CF6),
            Colors.transparent,
          ],
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
        ),
        border: Border.all(color: AppTheme.purple.withOpacity(0.1)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.auto_awesome, size: 14, color: AppTheme.purple),
              SizedBox(width: 8),
              Text('专题导言',
                  style: TextStyle(
                      color: AppTheme.purple,
                      fontSize: 12,
                      fontWeight: FontWeight.w500)),
            ],
          ),
          const SizedBox(height: 12),
          _renderIntroLines(intro),
        ],
      ),
    );
  }

  Widget _renderIntroLines(String intro) {
    final lines = intro.split('\n');
    final children = <Widget>[];
    for (int i = 0; i < lines.length; i++) {
      if (i > 0) {
        children.add(const SizedBox(height: 0));
      }
      children.add(_renderLineWithRefs(lines[i]));
    }
    return Column(
        crossAxisAlignment: CrossAxisAlignment.start, children: children);
  }

  Widget _renderLineWithRefs(String line) {
    final parts = line.split(RegExp(r'(\[\d+\])'));
    final spans = <InlineSpan>[];
    for (final part in parts) {
      final m = RegExp(r'^\[(\d+)\]$').firstMatch(part);
      if (m != null) {
        final n = int.parse(m.group(1)!);
        spans.add(WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: GestureDetector(
            onTap: () => _handleRefClick(n),
            child: Text('[$n]',
                style: TextStyle(
                    color: _refColor(n),
                    fontSize: 11,
                    fontFamily: 'monospace',
                    decoration: TextDecoration.underline)),
          ),
        ));
      } else {
        spans.add(TextSpan(
            text: part,
            style: const TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 13,
                height: 1.6)));
      }
    }
    return RichText(text: TextSpan(children: spans));
  }

  // ── Tab Bar ──

  Widget _buildTabBar() {
    return Container(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.border)),
      ),
      child: Row(
        children: [
          _tabBtn('overview', '结构化速览', AppTheme.purple),
          _tabBtn('paper', '深度分析', AppTheme.sky),
          _tabBtn('content', '专题内容', AppTheme.purple),
          _tabBtn('knowledge', '知识网络', AppTheme.emerald),
        ],
      ),
    );
  }

  Widget _tabBtn(String key, String label, Color activeColor) {
    final active = _tab == key;
    return GestureDetector(
      onTap: () => setState(() => _tab = key),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: active ? activeColor : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: active ? activeColor : AppTheme.textMuted,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }

  // ── Tab Content ──

  Widget _buildTabContent(List<Map<String, dynamic>> members, String? summary,
      String? paper, String? intro) {
    switch (_tab) {
      case 'overview':
        return _buildOverviewTab(summary, intro);
      case 'paper':
        return _buildPaperTab(paper);
      case 'content':
        return _buildContentTab(members);
      case 'knowledge':
        return _buildKnowledgeTab();
      default:
        return const SizedBox.shrink();
    }
  }

  // ── Overview Tab ──

  Widget _buildOverviewTab(String? summary, String? intro) {
    final hasIntro = intro != null && intro.isNotEmpty;
    final hasSummary = summary != null && summary.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (hasSummary) ...[
          const Row(
            children: [
              _BarIndicator(color: AppTheme.emerald),
              SizedBox(width: 8),
              Text('结构化速览',
                  style: TextStyle(
                      color: AppTheme.emerald,
                      fontSize: 11,
                      fontWeight: FontWeight.w500)),
            ],
          ),
          const SizedBox(height: 12),
          _renderSummaryWidget(summary!),
        ] else
          const Center(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 48),
              child: Text('点击上方「AI 生成总结」按钮生成结构化速览',
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
            ),
          ),
        if (!hasIntro && !hasSummary)
          Container(
            margin: const EdgeInsets.only(top: 32),
            padding: const EdgeInsets.only(top: 32),
            decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: AppTheme.border)),
            ),
            child: const Center(
              child: Text('点击上方「AI 生成导言」或「AI 生成总结」来丰富专题概览',
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
            ),
          ),
      ],
    );
  }

  Widget _renderSummaryWidget(String md) {
    // Strip AI meta titles
    String text = md
        .replaceAll(RegExp(r'^##\s*结构化速览\s*\n+', multiLine: true), '')
        .replaceAll(RegExp(r'^##\s*专题总结\s*\n+', multiLine: true), '');

    final lines = text.split('\n');
    final widgets = <Widget>[];
    bool inList = false;

    for (final rawLine in lines) {
      final line = rawLine;

      if (line.startsWith('## ')) {
        if (inList) inList = false;
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 20, bottom: 8),
          child:
              _buildBoldText(line.substring(3), AppTheme.purple, 14, true, 1.4),
        ));
      } else if (line.startsWith('### ')) {
        if (inList) inList = false;
        widgets.add(Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: _buildBoldText(
              line.substring(4), AppTheme.purple, 13, false, 1.5),
        ));
      } else if (RegExp(r'^- ').hasMatch(line)) {
        if (!inList) inList = true;
        final content = line.replaceFirst(RegExp(r'^- '), '');
        widgets.add(Padding(
          padding: const EdgeInsets.only(left: 8, bottom: 2),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('• ',
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
              Expanded(
                  child: _buildBoldText(
                      content, AppTheme.textSecondary, 13, false, 1.5)),
            ],
          ),
        ));
      } else if (line.trim().isEmpty) {
        if (inList) inList = false;
        widgets.add(const SizedBox(height: 8));
      } else if (RegExp(r'^[-*]{3,}$').hasMatch(line.trim())) {
        if (inList) inList = false;
        widgets.add(
            const Divider(color: AppTheme.border, height: 16, thickness: 0.5));
      } else {
        if (inList) inList = false;
        widgets.add(Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: _buildBoldText(
              line, AppTheme.textSecondary, 13, false, 1.6),
        ));
      }
    }

    if (widgets.isEmpty) {
      return const Text('暂无内容',
          style: TextStyle(color: AppTheme.textMuted, fontSize: 13));
    }

    return Column(
        crossAxisAlignment: CrossAxisAlignment.start, children: widgets);
  }

  Widget _buildBoldText(
      String text, Color baseColor, double fontSize, bool bold, double height) {
    final parts = text.split(RegExp(r'(\*\*.+?\*\*)'));
    final spans = <InlineSpan>[];

    for (final part in parts) {
      if (part.startsWith('**') && part.endsWith('**')) {
        final inner = part.substring(2, part.length - 2);
        spans.addAll(_buildRefSpans(
            inner,
            TextStyle(
                color: AppTheme.textPrimary,
                fontSize: fontSize,
                fontWeight: FontWeight.w600,
                height: height)));
      } else {
        spans.addAll(_buildRefSpans(
            part,
            TextStyle(
                color: baseColor,
                fontSize: fontSize,
                fontWeight: bold ? FontWeight.w600 : FontWeight.w400,
                height: height)));
      }
    }

    return RichText(text: TextSpan(children: spans));
  }

  List<InlineSpan> _buildRefSpans(String text, TextStyle style) {
    final spans = <InlineSpan>[];
    final parts = text.split(RegExp(r'(\[\d+\])'));
    for (final part in parts) {
      final m = RegExp(r'^\[(\d+)\]$').firstMatch(part);
      if (m != null) {
        final n = int.parse(m.group(1)!);
        spans.add(WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: GestureDetector(
            onTap: () => _handleRefClick(n),
            child: Text('[$n]',
                style: TextStyle(
                    color: _refColor(n),
                    fontSize: 11,
                    fontFamily: 'monospace',
                    decoration: TextDecoration.underline)),
          ),
        ));
      } else {
        spans.add(TextSpan(text: part, style: style));
      }
    }
    return spans;
  }

  // ── Paper Tab ──

  Widget _buildPaperTab(String? paper) {
    if (paper != null && paper.isNotEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              _BarIndicator(color: AppTheme.sky),
              SizedBox(width: 8),
              Text('深度分析',
                  style: TextStyle(
                      color: AppTheme.sky,
                      fontSize: 11,
                      fontWeight: FontWeight.w500)),
              SizedBox(width: 8),
              Text('论文/讲稿式',
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 10)),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            paper,
            style: const TextStyle(
                color: AppTheme.textSecondary, fontSize: 14, height: 1.6),
          ),
        ],
      );
    }
    return const Center(
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: 48),
        child: Text('点击上方「AI 深度分析」按钮生成论文式深度分析',
            style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ),
    );
  }

  // ── Content Tab ──

  String? _expandedCardId;

  Widget _buildContentTab(List<Map<String, dynamic>> members) {
    if (members.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: 64),
          child: Text('暂无内容成员',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
        ),
      );
    }

    return Column(
      children: [
        for (int idx = 0; idx < members.length; idx++)
          _contentCard(members[idx], idx, members.length),
      ],
    );
  }

  Widget _contentCard(
      Map<String, dynamic> m, int idx, int total) {
    final id = m['id'] as String? ?? '';
    final title = m['title'] as String? ?? '(无标题)';
    final overview = m['overview'] as String?;
    final topic = m['topic'] as String? ?? '未分类';
    final sourceId = m['source_id'] as String? ?? '';
    final url = m['url'] as String? ?? '';
    final createdAt = m['created_at'] as String?;
    final isExpanded = _expandedCardId == id;
    final isLast = idx == total - 1;

    return Column(
      children: [
        Container(
          margin: const EdgeInsets.only(bottom: 8),
          decoration: BoxDecoration(
            color: AppTheme.panel,
            border: Border.all(color: AppTheme.border),
            borderRadius: BorderRadius.circular(12),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              GestureDetector(
                onTap: () {
                  setState(
                      () => _expandedCardId = isExpanded ? null : id);
                },
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: AppTheme.purple.withOpacity(0.1),
                          shape: BoxShape.circle,
                          border: Border.all(
                              color: AppTheme.purple.withOpacity(0.2)),
                        ),
                        alignment: Alignment.center,
                        child: Text('${idx + 1}',
                            style: const TextStyle(
                                color: AppTheme.purple,
                                fontSize: 12,
                                fontWeight: FontWeight.bold)),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(title,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                          color: AppTheme.textPrimary,
                                          fontSize: 14,
                                          fontWeight: FontWeight.w500)),
                                ),
                                GestureDetector(
                                  onTap: () {
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (_) =>
                                            EventDetailPage(eventId: id),
                                      ),
                                    );
                                  },
                                  child: const Icon(Icons.open_in_new,
                                      size: 12, color: AppTheme.textMuted),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Wrap(
                              spacing: 8,
                              runSpacing: 4,
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: Colors.white.withOpacity(0.05),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: Text(topic,
                                      style: TextStyle(
                                          color: _getTopicColor(topic),
                                          fontSize: 10)),
                                ),
                                Text(_getSourceLabel(sourceId),
                                    style: const TextStyle(
                                        color: AppTheme.textMuted,
                                        fontSize: 10)),
                                if (createdAt != null)
                                  Text(_formatTimeBeijing(createdAt),
                                      style: const TextStyle(
                                          color: Color(0xFF4B5563),
                                          fontSize: 10)),
                              ],
                            ),
                            if (!isExpanded &&
                                overview != null &&
                                overview.isNotEmpty) ...[
                              const SizedBox(height: 8),
                              Text(overview,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      color: AppTheme.textMuted, fontSize: 12)),
                            ],
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Icon(
                        isExpanded
                            ? Icons.keyboard_arrow_up
                            : Icons.keyboard_arrow_down,
                        size: 16,
                        color: AppTheme.textMuted,
                      ),
                    ],
                  ),
                ),
              ),
              if (isExpanded)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  decoration: const BoxDecoration(
                    border: Border(top: BorderSide(color: AppTheme.border)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(height: 16),
                      if (overview != null && overview.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 16),
                          child: Text(overview,
                              style: const TextStyle(
                                  color: AppTheme.textSecondary,
                                  fontSize: 12,
                                  height: 1.6)),
                        ),
                      if (url.isNotEmpty)
                        GestureDetector(
                          onTap: () {
                            // URL display only — Flutter desktop can use
                            // url_launcher if available. For now, display text.
                          },
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.open_in_new,
                                  size: 10, color: AppTheme.purple),
                              const SizedBox(width: 4),
                              Flexible(
                                child: Text(url,
                                    style: const TextStyle(
                                        color: AppTheme.purple, fontSize: 10),
                                    overflow: TextOverflow.ellipsis),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  // ── Knowledge Tab ──

  Widget _buildKnowledgeTab() {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 64),
      alignment: Alignment.center,
      child: const Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.hub, size: 48, color: AppTheme.textMuted),
          SizedBox(height: 16),
          Text('知识网络可视化（需要 vis.js 支持）',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
          SizedBox(height: 8),
          Text('采集内容后系统将自动提取实体关系',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        ],
      ),
    );
  }

  // ═══════════════════════════════════════════
  // ── Modals ──
  // ═══════════════════════════════════════════

  // ── Suggestions Modal ──

  void _showSuggestionsModal() {
    showDialog(
      context: context,
      useRootNavigator: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setModalState) {
            return AlertDialog(
              backgroundColor: AppTheme.panel,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: const BorderSide(color: AppTheme.border)),
              title: Text('待确认建议（${_suggestions.length}）',
                  style: const TextStyle(
                      color: AppTheme.textPrimary, fontSize: 16)),
              content: SizedBox(
                width: 600,
                child: _suggestions.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.symmetric(vertical: 32),
                        child: Center(
                          child: Text('暂无待确认的建议',
                              style: TextStyle(
                                  color: AppTheme.textMuted, fontSize: 13)),
                        ),
                      )
                    : Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          ConstrainedBox(
                            constraints:
                                const BoxConstraints(maxHeight: 400),
                            child: SingleChildScrollView(
                              child: Column(
                                children: [
                                  for (final s in _suggestions)
                                    _suggestionItem(s, setModalState),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          const Divider(
                              color: AppTheme.border, height: 1),
                          const SizedBox(height: 12),
                          // Bottom action bar
                          Row(
                            children: [
                              GestureDetector(
                                onTap: () {
                                  _toggleSelectAll();
                                  setModalState(() {});
                                },
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(
                                      _selectedIds.length ==
                                                  _suggestions.length &&
                                              _suggestions.isNotEmpty
                                          ? Icons.check_box
                                          : Icons.check_box_outline_blank,
                                      size: 16,
                                      color: AppTheme.purple,
                                    ),
                                    const SizedBox(width: 6),
                                    const Text('全选',
                                        style: TextStyle(
                                            color: AppTheme.textSecondary,
                                            fontSize: 12)),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 16),
                              Text('已选 ${_selectedIds.length} 项',
                                  style: const TextStyle(
                                      color: AppTheme.textMuted,
                                      fontSize: 11)),
                              const Spacer(),
                              TextButton(
                                onPressed: _selectedIds.isEmpty
                                    ? null
                                    : () {
                                        _handleBatchDismiss();
                                        setModalState(() {});
                                      },
                                child: const Text('忽略选中',
                                    style: TextStyle(
                                        color: AppTheme.textSecondary,
                                        fontSize: 12)),
                              ),
                              const SizedBox(width: 8),
                              ElevatedButton.icon(
                                onPressed:
                                    _selectedIds.isEmpty || _batchAdding
                                        ? null
                                        : () {
                                            Navigator.pop(ctx);
                                            _handleBatchAdd();
                                          },
                                icon: _batchAdding
                                    ? const SizedBox(
                                        width: 12,
                                        height: 12,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 1.5,
                                            color: AppTheme.emerald),
                                      )
                                    : const Icon(Icons.add, size: 14),
                                label: const Text('添加选中',
                                    style: TextStyle(fontSize: 12)),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor:
                                      AppTheme.emerald.withOpacity(0.15),
                                  foregroundColor: AppTheme.emerald,
                                  side: BorderSide(
                                      color: AppTheme.emerald
                                          .withOpacity(0.3)),
                                  shape: RoundedRectangleBorder(
                                      borderRadius:
                                          BorderRadius.circular(8)),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _suggestionItem(
      Map<String, dynamic> s, StateSetter setModalState) {
    final id = s['id'] as String? ?? '';
    final title = s['title'] as String? ?? '';
    final topic = s['topic'] as String? ?? '未分类';
    final reason = s['reason'] as String?;
    final selected = _selectedIds.contains(id);

    return GestureDetector(
      onTap: () {
        _toggleSelect(id);
        setModalState(() {});
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 6),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: AppTheme.background,
          border: Border.all(
            color: selected
                ? AppTheme.purple.withOpacity(0.4)
                : AppTheme.border,
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  selected
                      ? Icons.check_box
                      : Icons.check_box_outline_blank,
                  size: 16,
                  color: AppTheme.purple,
                ),
                const SizedBox(width: 12),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.05),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(topic,
                      style: TextStyle(
                          color: _getTopicColor(topic),
                          fontSize: 10,
                          fontWeight: FontWeight.w500)),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(title,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: AppTheme.textPrimary, fontSize: 13)),
                ),
              ],
            ),
            if (reason != null && reason.isNotEmpty) ...[
              const SizedBox(height: 4),
              Padding(
                padding: const EdgeInsets.only(left: 28),
                child: Text(reason,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: AppTheme.textMuted, fontSize: 11)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  // ── Progress Modal ──

  void _showProgressModal() {
    _progressStage = 'adding';
    showDialog(
      context: context,
      useRootNavigator: true,
      barrierDismissible: false,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setModalState) {
            // Poll _progressStage from outer scope
            return AlertDialog(
              backgroundColor: AppTheme.panel,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: const BorderSide(color: AppTheme.border)),
              title: const Text('处理进度',
                  style: TextStyle(
                      color: AppTheme.textPrimary, fontSize: 16)),
              content: SizedBox(
                width: 360,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _progressRow(
                        '添加成员到专题', 'adding', AppTheme.emerald),
                    const SizedBox(height: 16),
                    _progressRow('重新生成结构化速览', 'summary',
                        AppTheme.amber),
                    const SizedBox(height: 16),
                    _progressRow(
                        '重新生成深度分析', 'paper', AppTheme.sky),
                    const SizedBox(height: 16),
                    if (_progressStage == 'done')
                      const Text('全部完成，页面已自动刷新',
                          style: TextStyle(
                              color: AppTheme.emerald, fontSize: 11)),
                    const SizedBox(height: 12),
                    const Text('关闭弹窗不会中断处理',
                        style: TextStyle(
                            color: AppTheme.textMuted, fontSize: 10),
                        textAlign: TextAlign.center),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _progressRow(String label, String stage, Color activeColor) {
    final isDone = _isStageDone(stage);
    final isActive = _progressStage == stage;
    final isPending = _isStagePending(stage);

    Widget icon;
    if (isDone) {
      icon = const Icon(Icons.check_circle, size: 18, color: AppTheme.emerald);
    } else if (isActive) {
      icon = SizedBox(
        width: 18,
        height: 18,
        child: CircularProgressIndicator(strokeWidth: 2, color: activeColor),
      );
    } else {
      icon = Container(
        width: 18,
        height: 18,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(
              color: isPending ? AppTheme.textMuted : AppTheme.textMuted,
              width: 2),
        ),
      );
    }

    return Row(
      children: [
        icon,
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              color: isPending || isActive || isDone
                  ? AppTheme.textPrimary
                  : AppTheme.textMuted,
              fontSize: 13,
            ),
          ),
        ),
        if (isActive)
          Text('处理中...',
              style: TextStyle(color: activeColor, fontSize: 11)),
        if (isDone)
          const Text('已完成',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
      ],
    );
  }

  bool _isStageDone(String stage) {
    const order = ['adding', 'summary', 'paper'];
    final currentIdx = order.indexOf(_progressStage);
    final stageIdx = order.indexOf(stage);
    return currentIdx > stageIdx || _progressStage == 'done';
  }

  bool _isStagePending(String stage) {
    const order = ['adding', 'summary', 'paper'];
    final currentIdx = order.indexOf(_progressStage);
    final stageIdx = order.indexOf(stage);
    return currentIdx < stageIdx && _progressStage != 'done';
  }

  // ── Delete Confirmation Modal ──

  void _showConfirmDeleteModal() {
    final name = _series?['name'] as String? ?? '';
    showDialog(
      context: context,
      useRootNavigator: true,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: AppTheme.panel,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: const BorderSide(color: AppTheme.border)),
          title: const Text('删除专题',
              style: TextStyle(color: AppTheme.textPrimary, fontSize: 16)),
          content: SizedBox(
            width: 400,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                RichText(
                  text: TextSpan(
                    style: const TextStyle(
                        color: AppTheme.textSecondary, fontSize: 13),
                    children: [
                      const TextSpan(text: '确认删除专题 '),
                      TextSpan(
                        text: '「$name」',
                        style: const TextStyle(
                            color: AppTheme.textPrimary,
                            fontWeight: FontWeight.w500),
                      ),
                      const TextSpan(text: '？'),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  '删除后专题及所有成员关联将被移除，此操作不可撤销。',
                  style: TextStyle(color: AppTheme.textMuted, fontSize: 12),
                ),
                const SizedBox(height: 20),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('取消',
                          style: TextStyle(
                              color: AppTheme.textSecondary, fontSize: 12)),
                    ),
                    const SizedBox(width: 12),
                    ElevatedButton(
                      onPressed: _deleting
                          ? null
                          : () {
                              Navigator.pop(ctx);
                              _handleDelete();
                            },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.error,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (_deleting)
                            const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(
                                  strokeWidth: 1.5, color: Colors.white),
                            )
                          else
                            const Icon(Icons.delete, size: 14),
                          const SizedBox(width: 6),
                          const Text('确认删除', style: TextStyle(fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ── Bar Indicator Widget ──

class _BarIndicator extends StatelessWidget {
  final Color color;
  const _BarIndicator({required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 4,
      height: 12,
      decoration:
          BoxDecoration(color: color, borderRadius: BorderRadius.circular(2)),
    );
  }
}
