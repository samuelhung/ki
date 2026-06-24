import 'dart:async';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

/// 1:1 port of EventDetailPage.tsx
class EventDetailPage extends StatefulWidget {
  final String eventId;

  const EventDetailPage({super.key, required this.eventId});

  @override
  State<EventDetailPage> createState() => _EventDetailPageState();
}

class _EventDetailPageState extends State<EventDetailPage> {
  final _dio = ApiClient().dio;

  // ── Data ──
  Map<String, dynamic>? _detail;
  bool _loading = true;

  // ── Tab ──
  String _tab = 'body';

  // ── Summary ──
  bool _summarizing = false;

  // ── Questions ──
  bool _contemplating = false;
  String _contemplateError = '';
  List<Map<String, dynamic>> _contemplateResults = [];
  final _contemplateSelected = <String>{};
  bool _contemplateLinking = false;
  List<Map<String, dynamic>> _linkedQuestions = [];
  bool _linkedQuestionsLoading = false;

  // ── Chain ──
  String _chainAnalysis = '';
  bool _chainLoading = false;
  String _chainError = '';
  List<Map<String, dynamic>> _chainHints = [];
  bool _syncingHints = false;
  String _syncResult = '';
  int _chainSuggestionsCount = 0;

  // ── Polling timer ──
  Timer? _pollTimer;

  // ── Video ──
  WebViewController? _webVideoController;

  // ── Handy derived flags ──
  bool get _hasTabs => _detail != null && _tabSources.contains(_detail!['source_id']);

  // ── Lifecycle ──
  @override
  void initState() {
    super.initState();
    _fetchDetail();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  // ═══════════════════════════════════════════
  //  DATA LOADING
  // ═══════════════════════════════════════════

  Future<void> _fetchDetail() async {
    setState(() {
      _loading = true;
      _contemplateError = '';
    });
    try {
      final resp = await _dio.get('/api/events/${widget.eventId}');
      final data = resp.data as Map<String, dynamic>;

      // Determine initial tab
      final src = data['source_id'] as String? ?? '';
      final initialTab = src == 'user-concept' ? 'summary' : 'body';

      // Process associated questions into contemplate results
      final associated = (data['associated_questions'] as List<dynamic>?)
              ?.map((q) => {
                    'question_id': q['id'],
                    'question_text': q['question'],
                    'link_status': 'linked',
                    'relevance': 'medium',
                  })
              .toList()
              .cast<Map<String, dynamic>>() ??
          [];

      if (!mounted) return;
      setState(() {
        _detail = data;
        _tab = initialTab;
        _loading = false;
        // Cached chain analysis
        if (data['chain_analysis'] != null && data['chain_analysis'].toString().isNotEmpty) {
          _chainAnalysis = data['chain_analysis'].toString();
        }
        _contemplateResults = associated;
      });

      // Load chain suggestions count (fire-and-forget)
      _fetchChainSuggestionsCount();
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Future<void> _fetchChainSuggestionsCount() async {
    try {
      final r = await _dio.get('/api/chains/suggestions/count');
      final d = r.data as Map<String, dynamic>;
      if (!mounted) return;
      setState(() => _chainSuggestionsCount = d['pending'] as int? ?? 0);
    } catch (_) {}
  }

  // ═══════════════════════════════════════════
  //  SUMMARY
  // ═══════════════════════════════════════════

  Future<void> _handleSummarize() async {
    if (_detail == null || _summarizing) return;
    final id = _detail!['id'].toString();
    setState(() => _summarizing = true);

    try {
      final res = await _dio.post('/api/events/$id/summarize', queryParameters: {'force': 'true'});
      if (res.statusCode != 200) throw Exception('总结失败');

      for (int i = 0; i < 30; i++) {
        await Future.delayed(const Duration(seconds: 2));
        try {
          final dRes = await _dio.get('/api/events/$id');
          final d = dRes.data as Map<String, dynamic>;
          if (d['ai_summary'] != null && d['ai_summary'].toString().isNotEmpty) {
            if (!mounted) return;
            setState(() {
              _detail = d;
              _summarizing = false;
            });
            _fetchChainSuggestionsCount();
            return;
          }
        } catch (_) {
          break;
        }
      }
    } catch (e) {
      // silently fail
    }
    if (!mounted) return;
    setState(() => _summarizing = false);
  }

  // ═══════════════════════════════════════════
  //  QUESTIONS
  // ═══════════════════════════════════════════

  Future<void> _fetchLinkedQuestions() async {
    if (_detail == null) return;
    setState(() => _linkedQuestionsLoading = true);
    try {
      final r = await _dio.get('/api/brainstorm/event/${_detail!['id']}/linked-questions');
      final d = r.data as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _linkedQuestions = (d['linked_questions'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [];
      });
    } catch (_) {
      if (mounted) setState(() => _linkedQuestions = []);
    }
    if (mounted) setState(() => _linkedQuestionsLoading = false);
  }

  Future<void> _handleContemplate() async {
    if (_detail == null) return;
    setState(() {
      _contemplating = true;
      _contemplateError = '';
      _contemplateSelected.clear();
    });
    try {
      final res = await _dio.post('/api/brainstorm/contemplate', data: {
        'direction': 'event_to_questions',
        'entity_id': _detail!['id'],
      });
      final d = res.data as Map<String, dynamic>;
      if (!mounted) return;
      if (d['error'] != null && d['error'].toString().isNotEmpty) {
        setState(() {
          _contemplateError = d['error'].toString();
          _contemplating = false;
        });
        return;
      }
      setState(() {
        _contemplateResults = (d['suggestions'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [];
        _contemplateSelected.clear();
        _contemplating = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _contemplateError = e.toString();
        _contemplating = false;
      });
    }
  }

  Future<void> _handleContemplateLink() async {
    if (_detail == null || _contemplateSelected.isEmpty) return;
    setState(() => _contemplateLinking = true);
    try {
      final eventId = _detail!['id'];
      for (final qid in _contemplateSelected.toList()) {
        await _dio.post('/api/brainstorm/answer', data: {
          'question_id': qid,
          'question': '',
          'event_ids': [eventId],
        });
      }
      // Refresh event data
      final dRes = await _dio.get('/api/events/$eventId');
      if (!mounted) return;
      final d = dRes.data as Map<String, dynamic>;
      setState(() {
        _detail = d;
        _contemplateResults = [];
        _contemplateError = '';
      });
      await _handleContemplate();
    } catch (e) {
      if (!mounted) return;
      setState(() => _contemplateError = '关联失败: $e');
    }
    if (mounted) setState(() => _contemplateLinking = false);
  }

  // ═══════════════════════════════════════════
  //  CHAIN
  // ═══════════════════════════════════════════

  Future<void> _handleChainAnalyze() async {
    if (_detail == null) return;
    setState(() {
      _chainLoading = true;
      _chainError = '';
      _chainAnalysis = '';
      _chainHints = [];
      _syncResult = '';
    });
    try {
      final res = await _dio.post('/api/chains/analyze', data: {
        'event_id': _detail!['id'],
      });
      final d = res.data as Map<String, dynamic>;
      if (!mounted) return;
      if (d['error'] != null && d['error'].toString().isNotEmpty) {
        setState(() {
          _chainError = d['error'].toString();
          _chainLoading = false;
        });
        return;
      }
      setState(() {
        _chainAnalysis = d['analysis'] as String? ?? '';
        _chainHints = (d['extracted_hints'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [];
        _chainLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _chainError = e.toString();
        _chainLoading = false;
      });
    }
  }

  Future<void> _handleSyncHints() async {
    if (_chainHints.isEmpty) return;
    setState(() {
      _syncingHints = true;
      _syncResult = '';
    });
    try {
      final res = await _dio.post('/api/chains/hints/sync', data: {
        'hints': _chainHints,
      });
      final d = res.data as Map<String, dynamic>;
      if (!mounted) return;
      if (d['ok'] == true) {
        final saved = d['saved_hints'] ?? 0;
        final news = d['new_suggestions'] ?? 0;
        setState(() {
          _syncResult = '已同步 $saved 条更新 + $news 条新链建议';
          _chainHints = [];
        });
      }
    } catch (e) {
      if (mounted) setState(() => _syncResult = '同步失败: $e');
    }
    if (mounted) setState(() => _syncingHints = false);
  }

  // ═══════════════════════════════════════════
  //  HELPERS
  // ═══════════════════════════════════════════

  static String? toMediaUrl(String? absolutePath) {
    if (absolutePath == null) return null;
    final idx = absolutePath.indexOf('/data/ingest/');
    if (idx == -1) return null;
    return '/ingest${absolutePath.substring(idx + '/data/ingest'.length)}';
  }

  IconData _sourceIcon(String sourceId) {
    switch (sourceId) {
      case 'douyin':
        return Icons.public;
      case 'user-upload':
        return Icons.description;
      case 'user-concept':
        return Icons.lightbulb;
      default:
        return Icons.description;
    }
  }

  Color _sourceIconColor(String sourceId) {
    switch (sourceId) {
      case 'douyin':
        return AppTheme.blue;
      case 'user-upload':
        return AppTheme.amber;
      case 'user-concept':
        return AppTheme.purple;
      default:
        return AppTheme.textMuted;
    }
  }

  String _sourceLabel(String sourceId) {
    switch (sourceId) {
      case 'douyin':
        return '抖音';
      case 'user-upload':
        return '上传';
      case 'user-concept':
        return '概念';
      default:
        return sourceId;
    }
  }

  String _statusLabel(String status) {
    const map = {
      'ready': '就绪',
      'processing': '处理中',
      'failed': '失败',
      'done': '已完成',
      'completed': '已完成',
      'digest': '已摘要',
    };
    return map[status] ?? status;
  }

  Color _statusColor(String status) {
    const map = {
      'ready': AppTheme.textMuted,
      'processing': AppTheme.amber,
      'failed': AppTheme.error,
      'done': AppTheme.emerald,
      'completed': AppTheme.emerald,
      'digest': AppTheme.purple,
    };
    return map[status] ?? AppTheme.textMuted;
  }

  String _formatTime(String? t) {
    if (t == null) return '';
    try {
      return DateFormat('yyyy-MM-dd HH:mm').format(DateTime.parse(t));
    } catch (_) {
      return '';
    }
  }

  static const _tabSources = ['douyin', 'user-upload', 'user-concept'];

  // ═══════════════════════════════════════════
  //  TABS: on-change handler
  // ═══════════════════════════════════════════

  void _onTabChanged(String t) {
    setState(() => _tab = t);
    if (t == 'questions') {
      _fetchLinkedQuestions();
    }
    if (t == 'chain' && _chainAnalysis.isEmpty && !_chainLoading) {
      _handleChainAnalyze();
    }
    if (t == 'summary' && _detail != null && _detail!['ai_summary'] == null && !_summarizing) {
      _handleSummarize();
    }
  }

  // ═══════════════════════════════════════════
  //  BUILD
  // ═══════════════════════════════════════════

  @override
  Widget build(BuildContext context) {
    // ── Loading ──
    if (_loading) {
      return const Scaffold(
        backgroundColor: AppTheme.background,
        body: Center(child: CircularProgressIndicator(color: AppTheme.textMuted)),
      );
    }

    // ── Not found ──
    if (_detail == null) {
      return Scaffold(
        backgroundColor: AppTheme.background,
        body: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Text('内容不存在', style: TextStyle(color: AppTheme.error, fontSize: 14)),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('返回', style: TextStyle(color: AppTheme.textMuted)),
            ),
          ]),
        ),
      );
    }

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Breadcrumb ──
              _buildBreadcrumb(),
              const SizedBox(height: 24),

              // ── Header ──
              _buildHeader(),
              const SizedBox(height: 24),

              // ── Meta info bar ──
              _buildMetaBar(),
              const SizedBox(height: 24),

              // ── Video player ──
              _buildVideoPlayer(),
              // const SizedBox is inside the condition

              // ── Tabs ──
              if (_hasTabs) ...[
                const SizedBox(height: 24),
                _buildTabs(),
                const SizedBox(height: 16),
              ],

              // ── Content ──
              _buildContent(),

              // ── Last error ──
              if (_detail!['last_error'] != null && _detail!['last_error'].toString().isNotEmpty) ...[
                const SizedBox(height: 16),
                _buildErrorBox('⚠️ ${_detail!['last_error']}'),
              ],
            ],
          ),
        ),
      ),
    );
  }

  // ── Breadcrumb ──
  Widget _buildBreadcrumb() {
    return GestureDetector(
      onTap: () => Navigator.pop(context),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.arrow_back_ios, size: 14, color: AppTheme.textMuted),
        const SizedBox(width: 4),
        Text('内容采集',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ]),
    );
  }

  // ── Header ──
  Widget _buildHeader() {
    final d = _detail!;
    final srcId = d['source_id'] as String? ?? '';
    final title = (d['title_cn'] ?? d['title'] ?? '') as String;
    final status = d['status'] as String? ?? '';

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Title row
      Row(children: [
        Icon(_sourceIcon(srcId), size: 24, color: _sourceIconColor(srcId)),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
                color: AppTheme.textPrimary,
                fontSize: 20,
                fontWeight: FontWeight.bold),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(width: 8),
        _statusBadge(status),
      ]),
      const SizedBox(height: 8),
      // Meta row
      Row(children: [
        Text('来源：${_sourceLabel(srcId)}',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        const SizedBox(width: 12),
        Text('提交于 ${_formatTime(d['created_at'] as String?)}',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
      ]),
      const SizedBox(height: 12),
      // Top action buttons
      _buildActionButtons(),
    ]);
  }

  Widget _statusBadge(String status) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: AppTheme.panelHover,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        _statusLabel(status),
        style: TextStyle(
            color: _statusColor(status), fontSize: 10, fontWeight: FontWeight.w500),
      ),
    );
  }

  Widget _buildActionButtons() {
    final d = _detail!;
    final id = d['id'].toString();
    final hasAiSummary = d['ai_summary'] != null && d['ai_summary'].toString().isNotEmpty;

    return Row(children: [
      // AI 生成总结
      _actionChip(
        label: hasAiSummary ? '重新生成总结' : 'AI 生成总结',
        icon: _summarizing ? Icons.hourglass_empty : Icons.auto_awesome,
        color: AppTheme.purple,
        disabled: _summarizing,
        onTap: _handleSummarize,
      ),
      const SizedBox(width: 8),
      // 凝神静思
      _actionChip(
        label: '凝神静思',
        icon: _contemplating ? Icons.hourglass_empty : Icons.auto_awesome,
        color: AppTheme.amber,
        disabled: _contemplating,
        onTap: _handleContemplate,
      ),
      const SizedBox(width: 8),
      // 添加待办
      _actionChip(
        label: '添加待办',
        icon: Icons.add,
        color: AppTheme.sky,
        onTap: () {
          // Navigate to tasks page - placeholder since we don't have tasks page in Flutter yet
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('任务功能将在后续版本中提供')),
          );
        },
      ),
    ]);
  }

  Widget _actionChip({
    required String label,
    required IconData icon,
    required Color color,
    bool disabled = false,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: disabled ? null : onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withOpacity(0.2)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (_summarizing && color == AppTheme.purple)
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.purple),
            )
          else
            Icon(icon, size: 14, color: disabled ? color.withOpacity(0.4) : color),
          const SizedBox(width: 4),
          Text(label,
              style: TextStyle(
                  color: disabled ? color.withOpacity(0.4) : color,
                  fontSize: 12,
                  fontWeight: FontWeight.w500)),
        ]),
      ),
    );
  }

  // ── Meta info bar ──
  Widget _buildMetaBar() {
    final d = _detail!;
    final srcId = d['source_id'] as String? ?? '';
    final url = d['url'] as String?;
    final videoPath = d['video_path'] as String?;
    final transcriptPath = d['transcript_path'] as String?;

    String urlLabel;
    if (srcId == 'douyin') {
      urlLabel = '视频地址：';
    } else if (srcId == 'user-upload') {
      urlLabel = '文档地址：';
    } else {
      urlLabel = '原文链接：';
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (url != null) ...[
          _metaRow(urlLabel, url),
          const SizedBox(height: 6),
        ],
        if (videoPath != null) ...[
          _metaRow('保存路径：', videoPath),
          const SizedBox(height: 6),
        ],
        if (transcriptPath != null) _metaRow('转写文档：', transcriptPath),
      ]),
    );
  }

  Widget _metaRow(String label, String value) {
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label,
          style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      const SizedBox(width: 4),
      Expanded(
        child: Text(value,
            style:
                const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
      ),
    ]);
  }

  // ── Video player ──
  Widget _buildVideoPlayer() {
    final videoPath = _detail!['video_path'] as String?;
    final mediaUrl = toMediaUrl(videoPath);
    if (mediaUrl == null) return const SizedBox.shrink();

    final fullUrl = '${ApiClient().dio.options.baseUrl}$mediaUrl';
    if (_webVideoController == null) {
      _webVideoController = WebViewController()
        ..setJavaScriptMode(JavaScriptMode.unrestricted)
        ..loadHtmlString('''
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;background:#000;display:flex;align-items:center;justify-content:center;height:100vh;}
video{max-width:100%;max-height:100%;}</style></head>
<body><video controls autoplay src="$fullUrl"></video></body></html>
''');
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      height: 360,
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: WebViewWidget(controller: _webVideoController!),
    );
  }

  // ── Tabs ──
  Widget _buildTabs() {
    final d = _detail!;
    final srcId = d['source_id'] as String? ?? '';
    final showBody = srcId != 'user-concept';

    return Container(
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.border)),
      ),
      child: Row(children: [
        if (showBody) _tabBtn('body', '正文'),
        _tabBtn('summary', _summarizing ? '生成中…' : (srcId == 'user-concept' ? '概念详解' : 'AI 总结')),
        _tabBtn('questions', '关联问题'),
        _tabBtnChain(),
      ]),
    );
  }

  Widget _tabBtn(String tabKey, String label) {
    final active = _tab == tabKey;
    return GestureDetector(
      onTap: () => _onTabChanged(tabKey),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
                color: active ? AppTheme.purple : Colors.transparent, width: 2),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: active ? AppTheme.purple : AppTheme.textMuted,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }

  Widget _tabBtnChain() {
    final active = _tab == 'chain';
    return GestureDetector(
      onTap: () => _onTabChanged('chain'),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
                color: active ? AppTheme.purple : Colors.transparent, width: 2),
          ),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(
            _chainLoading ? '分析中…' : '产业分析',
            style: TextStyle(
              color: active ? AppTheme.purple : AppTheme.textMuted,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          if (_chainSuggestionsCount > 0 && !_chainLoading) ...[
            const SizedBox(width: 4),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              decoration: BoxDecoration(
                color: AppTheme.error.withOpacity(0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '$_chainSuggestionsCount',
                style: const TextStyle(
                    color: AppTheme.error, fontSize: 10, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ]),
      ),
    );
  }

  // ── Content area ──
  Widget _buildContent() {
    if (_hasTabs) {
      switch (_tab) {
        case 'body':
          return _buildBody();
        case 'summary':
          return _buildSummary();
        case 'questions':
          return _buildQuestions();
        case 'chain':
          return _buildChain();
        default:
          return _buildBody();
      }
    }
    // No tabs: show body + questions stacked
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _buildBody(),
      const SizedBox(height: 24),
      _buildQuestions(),
    ]);
  }

  // ── Body tab ──
  Widget _buildBody() {
    final d = _detail!;
    final bodyText = (d['summary_cn'] ?? d['raw_summary'] ?? '') as String;

    if (bodyText.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: 48),
          child: Text('暂无转写内容',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
        ),
      );
    }

    return Text(
      bodyText,
      style: const TextStyle(
        color: AppTheme.textSecondary,
        fontSize: 13,
        height: 1.6,
      ),
    );
  }

  // ── Summary tab ──
  Widget _buildSummary() {
    final d = _detail!;
    final hasOverview =
        d['overview'] != null && d['overview'].toString().isNotEmpty;
    final hasAiSummary =
        d['ai_summary'] != null && d['ai_summary'].toString().isNotEmpty;

    if (_summarizing) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: 64),
          child: CircularProgressIndicator(color: AppTheme.purple),
        ),
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Overview
      if (hasOverview) ...[
        _sectionHeader('内容概述', AppTheme.purple),
        const SizedBox(height: 8),
        Text(
          d['overview'] as String,
          style: const TextStyle(
              color: AppTheme.textSecondary, fontSize: 13, height: 1.6),
        ),
      ],

      // AI Summary divider
      if (hasOverview && hasAiSummary) ...[
        const SizedBox(height: 20),
        const Divider(color: AppTheme.border),
        const SizedBox(height: 20),
      ],

      // AI Summary
      if (hasAiSummary) ...[
        if (hasOverview) _sectionHeader('AI 深度总结', AppTheme.amber),
        const SizedBox(height: 8),
        _buildMarkdownText(d['ai_summary'] as String),
      ],

      // Generate button
      if (!hasAiSummary) ...[
        if (hasOverview) ...[
          const Divider(color: AppTheme.border),
          const SizedBox(height: 16),
        ],
        Center(
          child: Column(children: [
            Text(
              hasOverview ? '概述已生成，可补充完整 AI 总结' : '该内容尚未生成 AI 总结',
              style: const TextStyle(color: AppTheme.textMuted, fontSize: 13),
            ),
            const SizedBox(height: 16),
            _primaryButton(
              '生成 AI 总结',
              onTap: _handleSummarize,
            ),
          ]),
        ),
      ],
    ]);
  }

  Widget _sectionHeader(String title, Color color) {
    return Row(children: [
      Container(
        width: 3,
        height: 16,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(2),
        ),
      ),
      const SizedBox(width: 6),
      Text(
        title,
        style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w500),
      ),
    ]);
  }

  Widget _primaryButton(String label, {required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        decoration: BoxDecoration(
          color: AppTheme.purple.withOpacity(0.12),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppTheme.purple.withOpacity(0.2)),
        ),
        child: Text(
          label,
          style: const TextStyle(
              color: AppTheme.purple,
              fontSize: 13,
              fontWeight: FontWeight.w500),
        ),
      ),
    );
  }

  /// Simple markdown-like rendering for the summary content.
  /// Renders bold (**text**), headings (## / ###), and code blocks (``` ```).
  Widget _buildMarkdownText(String text) {
    // Simple markdown-to-rich-text parser
    final spans = <InlineSpan>[];
    final lines = text.split('\n');
    bool inCodeBlock = false;

    for (int i = 0; i < lines.length; i++) {
      final line = lines[i];

      // Code block toggle
      if (line.trimLeft().startsWith('```')) {
        inCodeBlock = !inCodeBlock;
        if (spans.isNotEmpty && i > 0) {
          spans.add(const TextSpan(text: '\n'));
        }
        continue;
      }

      if (inCodeBlock) {
        spans.add(TextSpan(
          text: '$line\n',
          style: const TextStyle(
            fontFamily: 'monospace',
            fontSize: 12,
            color: AppTheme.emerald,
            backgroundColor: Color(0x1A000000),
          ),
        ));
        continue;
      }

      // Headings
      if (line.trimLeft().startsWith('### ')) {
        spans.add(TextSpan(
          text: '${line.trimLeft().substring(4)}\n',
          style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: AppTheme.textPrimary),
        ));
        continue;
      }
      if (line.trimLeft().startsWith('## ')) {
        spans.add(TextSpan(
          text: '${line.trimLeft().substring(3)}\n',
          style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: AppTheme.textPrimary),
        ));
        continue;
      }
      if (line.trimLeft().startsWith('# ')) {
        spans.add(TextSpan(
          text: '${line.trimLeft().substring(2)}\n',
          style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: AppTheme.textPrimary),
        ));
        continue;
      }

      // Bold: **text**
      spans.addAll(_parseInlineMarkdown(line));
      if (i < lines.length - 1) {
        spans.add(const TextSpan(text: '\n'));
      }
    }

    return RichText(text: TextSpan(children: spans));
  }

  List<InlineSpan> _parseInlineMarkdown(String line) {
    final spans = <InlineSpan>[];
    final regex = RegExp(r'(\*\*(.+?)\*\*)');
    int lastEnd = 0;

    for (final m in regex.allMatches(line)) {
      if (m.start > lastEnd) {
        spans.add(TextSpan(
          text: line.substring(lastEnd, m.start),
          style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13, height: 1.6),
        ));
      }
      spans.add(TextSpan(
        text: m.group(2) ?? '',
        style: const TextStyle(
            color: AppTheme.purple,
            fontSize: 13,
            height: 1.6,
            fontWeight: FontWeight.w600),
      ));
      lastEnd = m.end;
    }
    if (lastEnd < line.length) {
      spans.add(TextSpan(
        text: line.substring(lastEnd),
        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13, height: 1.6),
      ));
    }
    return spans;
  }

  // ── Questions tab ──
  Widget _buildQuestions() {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Linked questions
      if (_linkedQuestions.isNotEmpty) ...[
        Text('已关联问题 · ${_linkedQuestions.length} 条',
            style: const TextStyle(
                color: AppTheme.purple, fontSize: 11, fontWeight: FontWeight.w500)),
        const SizedBox(height: 8),
        ..._linkedQuestions.map((q) => _linkedQuestionTile(q)),
        const SizedBox(height: 16),
      ],
      if (_linkedQuestionsLoading)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 8),
          child: Row(children: [
            SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(strokeWidth: 1.5, color: AppTheme.textMuted)),
            SizedBox(width: 8),
            Text('加载已关联问题…',
                style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
          ]),
        ),

      // Contemplate error
      if (_contemplateError.isNotEmpty) ...[
        const SizedBox(height: 8),
        _buildErrorBox(_contemplateError),
        const SizedBox(height: 12),
      ],

      // Contemplate loading
      if (_contemplating && _contemplateResults.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 12),
          child: Row(children: [
            SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 1.5, color: AppTheme.textMuted)),
            SizedBox(width: 8),
            Text('匹配关联问题中…',
                style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
          ]),
        ),

      // Contemplate results
      _buildContemplateResults(),
    ]);
  }

  Widget _linkedQuestionTile(Map<String, dynamic> q) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.purple.withOpacity(0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.purple.withOpacity(0.1)),
      ),
      child: Row(children: [
        const Text('🔗', style: TextStyle(fontSize: 12)),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            q['question'] as String? ?? '',
            style: const TextStyle(
                color: AppTheme.textSecondary, fontSize: 12),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (q['topic'] != null && q['topic'].toString().isNotEmpty)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: AppTheme.panel,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(q['topic'].toString(),
                style:
                    const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
          ),
      ]),
    );
  }

  Widget _buildContemplateResults() {
    final unlinked = _contemplateResults
        .where((s) => s['link_status'] != 'linked')
        .toList();

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Header row
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(
          unlinked.isNotEmpty ? '推荐关联 · ${unlinked.length} 条' : '推荐关联',
          style: const TextStyle(
              color: AppTheme.textSecondary, fontSize: 11, fontWeight: FontWeight.w500),
        ),
        Row(children: [
          if (unlinked.isNotEmpty)
            GestureDetector(
              onTap: (_contemplateLinking || _contemplateSelected.isEmpty)
                  ? null
                  : _handleContemplateLink,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: AppTheme.purple.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: AppTheme.purple.withOpacity(0.15)),
                ),
                child: Text(
                  _contemplateLinking
                      ? '关联中…'
                      : '确认关联 (${_contemplateSelected.length})',
                  style: TextStyle(
                    color: (_contemplateLinking ||
                            _contemplateSelected.isEmpty)
                        ? AppTheme.purple.withOpacity(0.4)
                        : AppTheme.purple,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: _contemplating ? null : _handleContemplate,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: AppTheme.amber.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.amber.withOpacity(0.15)),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.auto_awesome,
                    size: 12,
                    color: _contemplating
                        ? AppTheme.amber.withOpacity(0.4)
                        : AppTheme.amber),
                const SizedBox(width: 4),
                Text(
                  _contemplating ? '思考中…' : '凝神静思',
                  style: TextStyle(
                    color: _contemplating
                        ? AppTheme.amber.withOpacity(0.4)
                        : AppTheme.amber,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ]),
            ),
          ),
        ]),
      ]),
      const SizedBox(height: 8),

      // Results list
      if (unlinked.isNotEmpty)
        ...unlinked.map((item) => _contemplateResultTile(item))
      else if (!_contemplating && _contemplateError.isEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 16),
          child: Center(
            child: Text('暂无推荐关联',
                style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
          ),
        ),
    ]);
  }

  Widget _contemplateResultTile(Map<String, dynamic> item) {
    final qid = item['question_id'] as String? ?? '';
    final isChecked = _contemplateSelected.contains(qid);
    final relevance = item['relevance'] as String? ?? 'medium';

    String relevanceLabel;
    Color relevanceColor;
    switch (relevance) {
      case 'high':
        relevanceLabel = '高';
        relevanceColor = AppTheme.emerald;
        break;
      case 'medium':
        relevanceLabel = '中';
        relevanceColor = AppTheme.amber;
        break;
      default:
        relevanceLabel = '低';
        relevanceColor = AppTheme.textMuted;
    }

    return GestureDetector(
      onTap: () {
        setState(() {
          if (isChecked) {
            _contemplateSelected.remove(qid);
          } else {
            _contemplateSelected.add(qid);
          }
        });
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 6),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: isChecked ? AppTheme.purple.withOpacity(0.06) : null,
          borderRadius: BorderRadius.circular(8),
          border: isChecked
              ? Border.all(color: AppTheme.purple.withOpacity(0.15))
              : null,
        ),
        child: Row(children: [
          SizedBox(
            width: 16,
            height: 16,
            child: Checkbox(
              value: isChecked,
              onChanged: (_) {
                setState(() {
                  if (isChecked) {
                    _contemplateSelected.remove(qid);
                  } else {
                    _contemplateSelected.add(qid);
                  }
                });
              },
              activeColor: AppTheme.accent,
              side: const BorderSide(color: AppTheme.textMuted),
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              visualDensity: VisualDensity.compact,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              item['question_text'] as String? ?? '',
              style: const TextStyle(
                  color: AppTheme.textSecondary, fontSize: 12),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: relevanceColor.withOpacity(0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              relevanceLabel,
              style: TextStyle(
                color: relevanceColor,
                fontSize: 10,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ]),
      ),
    );
  }

  // ── Chain tab ──
  Widget _buildChain() {
    if (_chainLoading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: 64),
          child: CircularProgressIndicator(color: AppTheme.purple),
        ),
      );
    }

    if (_chainError.isNotEmpty) {
      return _buildErrorBox(_chainError);
    }

    if (_chainAnalysis.isEmpty) {
      return Center(
        child: Column(children: [
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('基于知识库分析事件对各产业链的影响',
                style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
          ),
          const SizedBox(height: 12),
          _primaryButton('开始分析', onTap: _handleChainAnalyze),
        ]),
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Analysis result
      _buildMarkdownText(_chainAnalysis),
      const SizedBox(height: 16),

      // Extracted hints + sync button
      if (_chainHints.isNotEmpty) _buildChainHints(),
      if (_syncResult.isNotEmpty) ...[
        const SizedBox(height: 12),
        _buildSuccessBox(_syncResult),
      ],
    ]);
  }

  Widget _buildChainHints() {
    final visible = _chainHints.take(5).toList();
    final remaining = _chainHints.length > 5 ? _chainHints.length - 5 : 0;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.emerald.withOpacity(0.03),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.emerald.withOpacity(0.15)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Row(children: [
            const Icon(Icons.link, size: 14, color: AppTheme.emerald),
            const SizedBox(width: 8),
            Text('从分析中提取到 ${_chainHints.length} 个数据点',
                style: const TextStyle(
                    color: AppTheme.emerald,
                    fontSize: 11,
                    fontWeight: FontWeight.w500)),
          ]),
          GestureDetector(
            onTap: _syncingHints ? null : _handleSyncHints,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: AppTheme.emerald.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.emerald.withOpacity(0.15)),
              ),
              child: Text(
                _syncingHints ? '同步中…' : '同步到产业链',
                style: TextStyle(
                  color: _syncingHints
                      ? AppTheme.emerald.withOpacity(0.4)
                      : AppTheme.emerald,
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        ...visible.map((h) => _hintTile(h)),
        if (remaining > 0)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('…及其他 $remaining 条',
                style:
                    const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
          ),
      ]),
    );
  }

  Widget _hintTile(Map<String, dynamic> h) {
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(children: [
        Text(
          h['node_name'] as String? ?? '',
          style: const TextStyle(
              color: AppTheme.emerald,
              fontSize: 11,
              fontWeight: FontWeight.w500),
        ),
        const Text(' · ', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        Text(h['field'] as String? ?? '',
            style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
        const Text(' → ', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        Expanded(
          child: Text(
            h['value'] as String? ?? '',
            style: const TextStyle(color: AppTheme.emerald, fontSize: 11),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ]),
    );
  }

  // ── Shared widgets ──

  Widget _buildErrorBox(String message) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.error.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.error.withOpacity(0.15)),
      ),
      child: Text(message,
          style:
              const TextStyle(color: AppTheme.error, fontSize: 13)),
    );
  }

  Widget _buildSuccessBox(String message) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.emerald.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.emerald.withOpacity(0.15)),
      ),
      child: Text(message,
          style:
              const TextStyle(color: AppTheme.emerald, fontSize: 13)),
    );
  }
}
