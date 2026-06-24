import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

// ── helpers ──

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

Color _topicColor(String? topic) {
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
      return AppTheme.textMuted;
  }
}

Color _topicBg(String? topic) {
  switch (topic) {
    case '格局':
      return const Color(0xFF60A5FA).withValues(alpha: 0.12);
    case '财富':
      return const Color(0xFFFBBF24).withValues(alpha: 0.12);
    case '认知':
      return const Color(0xFFA78BFA).withValues(alpha: 0.12);
    case '前瞻':
      return const Color(0xFF34D399).withValues(alpha: 0.12);
    default:
      return AppTheme.textMuted.withValues(alpha: 0.1);
  }
}

String _formatTime(String iso) {
  try {
    final dt = DateTime.parse(iso).toUtc().add(const Duration(hours: 8));
    return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  } catch (_) {
    return iso;
  }
}

// ── page ──

class BrainstormDetailPage extends StatefulWidget {
  final String id;
  const BrainstormDetailPage({super.key, required this.id});

  @override
  State<BrainstormDetailPage> createState() => _BrainstormDetailPageState();
}

class _BrainstormDetailPageState extends State<BrainstormDetailPage> {
  final ApiClient _api = ApiClient();

  // ── core ──
  bool _loading = true;
  bool _notFound = false;
  Map<String, dynamic>? _question;

  // ── docs tab ──
  List<dynamic> _availableEvents = [];
  final Set<String> _selectedEventIds = {};
  final Set<String> _lockedEventIds = {};
  final Map<String, String> _judgedEvents = {};
  bool _eventsLoading = false;
  String _eventSearch = '';

  bool _contemplating = false;
  String _contemplateError = '';
  List<Map<String, dynamic>> _contemplateResults = [];
  final Set<String> _contemplateSelected = {};
  bool _contemplateLinking = false;

  // ── chat tab ──
  List<Map<String, dynamic>> _conversationMessages = [];
  bool _conversationLoading = false;
  List<String> _conversationLockedIds = [];
  final TextEditingController _followUpCtrl = TextEditingController();
  bool _sendingFollowUp = false;
  final ScrollController _chatScrollCtrl = ScrollController();

  // ── summary tab ──
  String _summary = '';
  bool _summaryLoading = false;
  bool _summaryUpdated = false;
  String _summaryCreatedAt = '';
  bool _initialStaleCheckDone = false;

  // ── concepts tab ──
  List<Map<String, dynamic>> _summaryConcepts = [];
  bool _conceptsLoading = false;
  String _precipitatingName = '';

  // ── tab ──
  String _conceptTab = 'docs';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _followUpCtrl.dispose();
    _chatScrollCtrl.dispose();
    super.dispose();
  }

  // ═══════════════════════════════════════════
  //  loading
  // ═══════════════════════════════════════════

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _notFound = false;
    });

    try {
      final qData = await _api.getBrainstorm(widget.id);
      if (!mounted) return;
      setState(() => _question = qData);

      // parse answered_event_ids → locked
      List<String> answered = [];
      try {
        answered = (jsonDecode(qData['answered_event_ids'] as String? ?? '[]')
                as List<dynamic>)
            .cast<String>();
      } catch (_) {}
      final locked = answered.toSet();
      _lockedEventIds
        ..clear()
        ..addAll(locked);
      _selectedEventIds
        ..clear()
        ..addAll(locked);

      // summary
      final ans = qData['answer'] as String?;
      if (ans != null && ans.isNotEmpty) _summary = ans;
      final sca = qData['summary_created_at'] as String?;
      if (sca != null && sca.isNotEmpty) _summaryCreatedAt = sca;

      // judged_events
      final jMap = <String, String>{};
      try {
        final jArr =
            jsonDecode(qData['judged_events'] as String? ?? '[]') as List<dynamic>;
        for (final j in jArr) {
          if (j is Map<String, dynamic>) {
            jMap[j['event_id'] as String] = j['relevance'] as String? ?? 'high';
          }
        }
      } catch (_) {}
      for (final evtId in locked) {
        if (!jMap.containsKey(evtId)) jMap[evtId] = 'high';
      }
      _judgedEvents
        ..clear()
        ..addAll(jMap);

      // page renders immediately
      setState(() => _loading = false);

      // fetch events async
      _fetchEvents();
      // fetch conversation async
      _loadConversation();
    } catch (e) {
      if (!mounted) return;
      // check for 404 via DioException
      final msg = e.toString();
      if (msg.contains('404')) {
        setState(() {
          _notFound = true;
          _loading = false;
        });
      } else {
        setState(() {
          _loading = false;
          _notFound = true;
        });
      }
    }
  }

  Future<void> _fetchEvents() async {
    setState(() => _eventsLoading = true);
    try {
      final results = await Future.wait([
        _api.getEvents(sourceId: 'douyin', limit: 50),
        _api.getEvents(sourceId: 'user-upload', limit: 50),
        _api.getEvents(contentType: 'concept', limit: 100),
      ]);
      final e0 = (results[0]['items'] as List<dynamic>?) ?? [];
      final e1 = (results[1]['items'] as List<dynamic>?) ?? [];
      final e2 = (results[2]['items'] as List<dynamic>?) ?? [];
      final all = <dynamic>[...e0, ...e1, ...e2];
      final filtered = all.where((e) {
        final status = (e as Map<String, dynamic>)['status'] as String? ?? '';
        return status != 'error' && status != 'processing';
      }).toList();
      if (mounted) setState(() => _availableEvents = filtered);
    } catch (_) {}
    if (mounted) setState(() => _eventsLoading = false);
  }

  // ═══════════════════════════════════════════
  //  conversation
  // ═══════════════════════════════════════════

  Future<void> _loadConversation() async {
    try {
      final data = await _api.getConversation(widget.id);
      if (!mounted) return;
      final msgs = (data['messages'] as List<dynamic>?)
              ?.cast<Map<String, dynamic>>() ??
          [];
      final lids = (data['locked_event_ids'] as List<dynamic>?)
              ?.cast<String>() ??
          [];
      setState(() {
        _conversationMessages = msgs;
        _conversationLockedIds = lids;
        if (msgs.isNotEmpty && _conceptTab != 'summary') {
          _conceptTab = 'chat';
        }
      });
      _checkStale();
    } catch (_) {}
  }

  void _checkStale() {
    if (_initialStaleCheckDone) return;
    if (_conversationMessages.isEmpty) return;
    final lastMsg = _conversationMessages.last;
    if (_summary.isEmpty && _summaryCreatedAt.isEmpty) {
      _summaryUpdated = true;
    } else if (_summaryCreatedAt.isNotEmpty) {
      final lastTs = lastMsg['created_at'] as String? ?? '';
      if (lastTs.compareTo(_summaryCreatedAt) > 0) {
        _summaryUpdated = true;
      }
    }
    _initialStaleCheckDone = true;
  }

  Future<void> _startConversation() async {
    if (_selectedEventIds.isEmpty) return;
    setState(() => _conversationLoading = true);
    try {
      final data = await _api.startConversation(
        widget.id,
        _selectedEventIds.toList(),
        question: _question?['question'] as String? ?? '',
      );
      if (!mounted) return;
      if (data['error'] != null) {
        setState(() => _contemplateError = data['error'] as String);
      } else {
        final msgs = (data['messages'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [];
        final lids = (data['locked_event_ids'] as List<dynamic>?)
                ?.cast<String>() ??
            [];
        setState(() {
          _conversationMessages = msgs;
          _conversationLockedIds = lids;
          _lockedEventIds
            ..clear()
            ..addAll(lids);
          _selectedEventIds
            ..clear()
            ..addAll(lids);
          _conceptTab = 'chat';
          _summaryUpdated = true;
          _initialStaleCheckDone = false;
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _conversationLoading = false);
  }

  Future<void> _sendFollowUp() async {
    final text = _followUpCtrl.text.trim();
    if (text.isEmpty) return;
    setState(() => _sendingFollowUp = true);
    _followUpCtrl.clear();

    final userMsg = <String, dynamic>{
      'id': -DateTime.now().millisecondsSinceEpoch,
      'role': 'user',
      'content': text,
      'refs': <String>[],
      'created_at': DateTime.now().toUtc().toIso8601String(),
    };
    setState(() => _conversationMessages = [..._conversationMessages, userMsg]);
    _scrollToChatBottom();

    try {
      final data = await _api.sendFollowUp(widget.id, text);
      if (!mounted) return;
      if (data['error'] != null) {
        setState(() {
          _contemplateError = data['error'] as String;
          _conversationMessages =
              _conversationMessages.where((m) => m['id'] != userMsg['id']).toList();
        });
      } else {
        final msg = data['message'] as Map<String, dynamic>? ?? {};
        setState(() {
          _conversationMessages = [
            ..._conversationMessages.where((m) => m['id'] != userMsg['id']),
            {
              'id': DateTime.now().millisecondsSinceEpoch,
              'role': 'user',
              'content': text,
              'refs': <String>[],
              'created_at': DateTime.now().toUtc().toIso8601String(),
            },
            {
              'id': DateTime.now().millisecondsSinceEpoch + 1,
              'role': 'assistant',
              'content': msg['content'] as String? ?? '',
              'refs': msg['refs'] as List<dynamic>? ?? [],
              'created_at': msg['created_at'] as String? ?? '',
            },
          ];
          _summaryUpdated = true;
          _initialStaleCheckDone = false;
        });
        _scrollToChatBottom();
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _conversationMessages =
              _conversationMessages.where((m) => m['id'] != userMsg['id']).toList();
        });
      }
    }
    if (mounted) setState(() => _sendingFollowUp = false);
  }

  void _scrollToChatBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_chatScrollCtrl.hasClients) {
        _chatScrollCtrl.animateTo(
          _chatScrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ═══════════════════════════════════════════
  //  summary
  // ═══════════════════════════════════════════

  Future<void> _generateSummary() async {
    setState(() => _summaryLoading = true);
    try {
      final data = await _api.generateSummary(widget.id);
      if (!mounted) return;
      if (data['error'] != null) {
        setState(() => _contemplateError = data['error'] as String);
      } else {
        setState(() {
          _summary = data['summary'] as String? ?? '';
          _summaryCreatedAt = data['created_at'] as String? ?? '';
          _summaryUpdated = false;
        });
      }
    } catch (_) {}
    if (mounted) setState(() => _summaryLoading = false);
  }

  // ═══════════════════════════════════════════
  //  concepts
  // ═══════════════════════════════════════════

  Future<void> _loadConcepts() async {
    setState(() => _conceptsLoading = true);
    try {
      final data = await _api.getConcepts(widget.id);
      if (!mounted) return;
      final concepts = (data['concepts'] as List<dynamic>?)
              ?.cast<Map<String, dynamic>>() ??
          [];
      setState(() => _summaryConcepts = concepts);
    } catch (_) {}
    if (mounted) setState(() => _conceptsLoading = false);
  }

  Future<void> _precipitateConcept(String name, String description) async {
    setState(() => _precipitatingName = name);
    try {
      await _api.precipitateConcept(widget.id, name, description);
      if (!mounted) return;
      setState(() {
        _summaryConcepts = _summaryConcepts.map((c) {
          if (c['name'] == name) {
            return {...c, 'precipitated': true};
          }
          return c;
        }).toList();
      });
    } catch (_) {}
    if (mounted) setState(() => _precipitatingName = '');
  }

  // ═══════════════════════════════════════════
  //  contemplate
  // ═══════════════════════════════════════════

  Future<void> _handleContemplate() async {
    setState(() {
      _contemplating = true;
      _contemplateError = '';
      _contemplateResults = [];
      _contemplateSelected.clear();
    });
    try {
      final data = await _api.contemplate(widget.id);
      if (!mounted) return;
      if (data['error'] != null) {
        setState(() => _contemplateError = data['error'] as String);
      } else {
        final suggestions = (data['suggestions'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [];
        setState(() {
          _contemplateResults = suggestions;
          _contemplateSelected.clear();
        });
        // update judged map
        final next = Map<String, String>.from(_judgedEvents);
        for (final s in suggestions) {
          next[s['event_id'] as String] = s['relevance'] as String? ?? 'medium';
        }
        setState(() {
          _judgedEvents
            ..clear()
            ..addAll(next);
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _contemplateError = e.toString());
      }
    }
    if (mounted) setState(() => _contemplating = false);
  }

  Future<void> _handleContemplateLink() async {
    if (_contemplateSelected.isEmpty) return;
    setState(() => _contemplateLinking = true);
    try {
      final data = await _api.answerQuestion(
        widget.id,
        _contemplateSelected.toList(),
      );
      if (!mounted) return;
      final answeredIds = data['answered_event_ids'];
      if (answeredIds is List) {
        final ids = answeredIds.cast<String>().toSet();
        setState(() {
          _lockedEventIds
            ..clear()
            ..addAll(ids);
          _selectedEventIds
            ..clear()
            ..addAll(ids);
        });
      }
      setState(() {
        _availableEvents = _availableEvents
            .where((e) =>
                !_contemplateSelected
                    .contains((e as Map<String, dynamic>)['id'] as String?))
            .toList();
        _contemplateResults = [];
      });
    } catch (e) {
      if (mounted) {
        setState(() => _contemplateError = '关联失败: $e');
      }
    }
    if (mounted) setState(() => _contemplateLinking = false);
  }

  // ═══════════════════════════════════════════
  //  event helpers
  // ═══════════════════════════════════════════

  List<dynamic> _filteredEvents() {
    const relevanceOrder = {'high': 0, 'medium': 1, 'low': 2};
    final list = _eventSearch.trim().isNotEmpty
        ? _availableEvents.where((e) {
            final m = e as Map<String, dynamic>;
            final t = ((m['title_cn'] ?? m['title']) as String? ?? '')
                .toLowerCase();
            return t.contains(_eventSearch.toLowerCase());
          }).toList()
        : List<dynamic>.from(_availableEvents);

    list.sort((a, b) {
      final ma = a as Map<String, dynamic>;
      final mb = b as Map<String, dynamic>;
      final ra = relevanceOrder[_judgedEvents[ma['id'] as String?]] ?? 3;
      final rb = relevanceOrder[_judgedEvents[mb['id'] as String?]] ?? 3;
      return ra.compareTo(rb);
    });
    return list;
  }

  void _toggleEvent(String eventId) {
    if (_lockedEventIds.contains(eventId) && _selectedEventIds.contains(eventId)) {
      return;
    }
    setState(() {
      if (_selectedEventIds.contains(eventId)) {
        _selectedEventIds.remove(eventId);
      } else {
        _selectedEventIds.add(eventId);
      }
    });
  }

  void _selectAllEvents() {
    setState(() {
      _selectedEventIds
        ..clear()
        ..addAll(_filteredEvents()
            .map((e) => (e as Map<String, dynamic>)['id'] as String));
    });
  }

  void _deselectAllEvents() {
    setState(() => _selectedEventIds.clear());
  }

  void _toggleContemplateSelect(String eventId) {
    setState(() {
      if (_contemplateSelected.contains(eventId)) {
        _contemplateSelected.remove(eventId);
      } else {
        _contemplateSelected.add(eventId);
      }
    });
  }

  // ═══════════════════════════════════════════
  //  markdown renderer
  // ═══════════════════════════════════════════

  /// Build a title→eventId map from available events
  Map<String, String> get _eventTitleMap {
    final m = <String, String>{};
    for (final e in _availableEvents) {
      final em = e as Map<String, dynamic>;
      m[em['id'] as String? ?? ''] =
          (em['title_cn'] ?? em['title']) as String? ?? '';
    }
    return m;
  }

  Widget _renderMarkdownWithRefs(
      String content, List<String> lockedIds, BuildContext context) {
    if (content.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: 16),
          child: Text('暂无内容',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
        ),
      );
    }

    // strip common prefixes
    String md = content.replaceFirst(RegExp(r'^好的，[^。\n]+。\n\n'), '');
    md = md.replaceFirst(
        RegExp(r'^根据(所选|您提供的)文章(内容)?[，,]\s*[^。\n]*[。，：:]\s*',
            dotAll: true),
        '');

    final lines = md.split('\n');
    final widgets = <Widget>[];
    List<InlineSpan> listItems = [];
    void flushList() {
      if (listItems.isNotEmpty) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: listItems
                .map((span) => Padding(
                      padding: const EdgeInsets.only(bottom: 2),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('• ',
                              style: TextStyle(
                                  color: AppTheme.textMuted, fontSize: 13)),
                          Expanded(
                              child: Text.rich(span,
                                  style: const TextStyle(
                                      color: Color(0xFFD1D5DB),
                                      fontSize: 13,
                                      height: 1.5))),
                        ],
                      ),
                    ))
                .toList(),
          ),
        ));
        listItems = [];
      }
    }

    InlineSpan renderInline(String text) {
      final spans = <InlineSpan>[];
      // Split on **bold**, [文档N], （证据：...）
      final parts = text.split(RegExp(r'(\*\*.+?\*\*|\[文档\d+\]|（证据：[^）]*）)'));
      for (final part in parts) {
        if (part.startsWith('**') && part.endsWith('**')) {
          spans.add(TextSpan(
            text: part.substring(2, part.length - 2),
            style: const TextStyle(
                fontWeight: FontWeight.w600, color: Color(0xFFE5E7EB)),
          ));
        } else if (part.startsWith('（证据：')) {
          spans.add(TextSpan(
            text: part,
            style: const TextStyle(
                color: AppTheme.textMuted, fontStyle: FontStyle.italic),
          ));
        } else {
          final refMatch = RegExp(r'^\[文档(\d+)\]$').firstMatch(part);
          if (refMatch != null) {
            final idx = int.tryParse(refMatch.group(1)!) ?? 0;
            final eventId = idx > 0 && idx <= lockedIds.length
                ? lockedIds[idx - 1]
                : null;
            if (eventId != null) {
              final title =
                  _eventTitleMap[eventId] ?? '点击查看文档详情';
              spans.add(WidgetSpan(
                alignment: PlaceholderAlignment.middle,
                child: GestureDetector(
                  onTap: () =>
                      context.go('/events/$eventId'),
                  child: Tooltip(
                    message: title,
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 1),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 4, vertical: 0),
                      decoration: BoxDecoration(
                        color: AppTheme.purple.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(part,
                          style: const TextStyle(
                              color: AppTheme.purple, fontSize: 12)),
                    ),
                  ),
                ),
              ));
            } else {
              spans.add(TextSpan(
                  text: part,
                  style: const TextStyle(
                      color: AppTheme.textSecondary, fontSize: 13)));
            }
          } else {
            spans.add(TextSpan(
                text: part,
                style: const TextStyle(
                    color: Color(0xFFD1D5DB), fontSize: 13, height: 1.5)));
          }
        }
      }
      return TextSpan(children: spans);
    }

    for (int i = 0; i < lines.length; i++) {
      final line = lines[i];
      if (line.startsWith('## ')) {
        flushList();
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 20, bottom: 8),
          child: Text(line.substring(3),
              style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: AppTheme.purple)),
        ));
      } else if (line.startsWith('### ')) {
        flushList();
        widgets.add(Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Text(line.substring(4),
              style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: AppTheme.purple,
                  height: 1.5)),
        ));
      } else if (line.startsWith('- ')) {
        listItems.add(renderInline(line.substring(2)));
      } else if (line.trim().isEmpty) {
        flushList();
      } else if (RegExp(r'^[-*]{3,}$').hasMatch(line.trim())) {
        flushList();
      } else {
        flushList();
        widgets.add(Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Text.rich(renderInline(line),
              style: const TextStyle(
                  color: Color(0xFFD1D5DB), fontSize: 13, height: 1.5)),
        ));
      }
    }
    flushList();

    return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: widgets);
  }

  // ═══════════════════════════════════════════
  //  build
  // ═══════════════════════════════════════════

  @override
  Widget build(BuildContext context) {
    // ── loading ──
    if (_loading) {
      return const Scaffold(
        backgroundColor: AppTheme.background,
        body: Center(
            child: CircularProgressIndicator(color: AppTheme.accent)),
      );
    }

    // ── not found ──
    if (_notFound || _question == null) {
      return Scaffold(
        backgroundColor: AppTheme.background,
        body: SafeArea(
          child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Text('问题不存在',
                  style: TextStyle(color: AppTheme.error, fontSize: 14)),
              const SizedBox(height: 16),
              TextButton(
                  onPressed: () => context.pop(),
                  child: const Text('返回',
                      style: TextStyle(color: AppTheme.textMuted))),
            ]),
          ),
        ),
      );
    }

    final q = _question!;
    final question = q['question'] as String? ?? '(无问题)';
    final topic = q['topic'] as String? ?? '';
    final createdAt = q['created_at'] as String? ?? '';
    final updatedAt = q['updated_at'] as String?;
    final hasConversation = _conversationMessages.isNotEmpty;

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ═══ Breadcrumb + Header ═══
            _buildHeader(question, topic, createdAt, updatedAt,
                hasConversation),

            // ═══ Tab bar ═══
            _buildTabBar(hasConversation),

            // ═══ Tab content ═══
            Expanded(child: _buildTabContent(question, hasConversation)),

            // ═══ Bottom bar ═══
            _buildBottomBar(hasConversation),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(String question, String topic, String createdAt,
      String? updatedAt, bool hasConversation) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      decoration: const BoxDecoration(
        color: AppTheme.background,
        border: Border(bottom: BorderSide(color: AppTheme.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Breadcrumb
          GestureDetector(
            onTap: () => context.go('/brainstorm'),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.arrow_back, size: 14, color: AppTheme.textMuted),
                SizedBox(width: 4),
                Text('头脑风暴',
                    style: TextStyle(
                        color: AppTheme.textMuted, fontSize: 11)),
              ],
            ),
          ),
          const SizedBox(height: 8),

          // Question row + actions
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.only(top: 2),
                child: Icon(Icons.lightbulb,
                    size: 22, color: AppTheme.purple),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(question,
                        style: const TextStyle(
                            color: AppTheme.textPrimary,
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            height: 1.4)),
                    if (topic.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: _topicBg(topic),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(topic,
                            style: TextStyle(
                                color: _topicColor(topic),
                                fontSize: 10,
                                fontWeight: FontWeight.w500)),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              // Action buttons
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  _actionButton(
                    icon: _conversationLoading
                        ? Icons.hourglass_empty
                        : Icons.message_outlined,
                    label: '发起问答',
                    color: AppTheme.purple,
                    onTap: _selectedEventIds.isEmpty
                        ? null
                        : _startConversation,
                    loading: _conversationLoading,
                  ),
                  _actionButton(
                    icon: _contemplating
                        ? Icons.hourglass_empty
                        : Icons.auto_awesome,
                    label: '凝神静思',
                    color: AppTheme.amber,
                    onTap: _contemplating ? null : _handleContemplate,
                    loading: _contemplating,
                  ),
                  _actionButton(
                    icon: Icons.add,
                    label: '添加待办',
                    color: AppTheme.sky,
                    onTap: () => context.go(
                        '/tasks?source=brainstorm&source_id=${widget.id}'),
                  ),
                ],
              ),
            ],
          ),

          // Metadata row
          const SizedBox(height: 6),
          Row(
            children: [
              Text('${_lockedEventIds.length} 条文档',
                  style: const TextStyle(
                      color: AppTheme.textMuted, fontSize: 10)),
              const SizedBox(width: 12),
              Text('创建于 ${_formatTime(createdAt)}',
                  style: const TextStyle(
                      color: AppTheme.textMuted, fontSize: 10)),
              if (updatedAt != null) ...[
                const SizedBox(width: 12),
                Text('更新于 ${_formatTime(updatedAt)}',
                    style: const TextStyle(
                        color: AppTheme.textMuted, fontSize: 10)),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _actionButton({
    required IconData icon,
    required String label,
    required Color color,
    VoidCallback? onTap,
    bool loading = false,
  }) {
    final enabled = onTap != null;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.2)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            loading
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 1.5, color: AppTheme.textMuted),
                  )
                : Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
            Text(label,
                style: TextStyle(
                    color: enabled ? color : AppTheme.textMuted,
                    fontSize: 11,
                    fontWeight: FontWeight.w500)),
          ],
        ),
      ),
    );
  }

  Widget _buildTabBar(bool hasConversation) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: const BoxDecoration(
        color: AppTheme.background,
        border: Border(bottom: BorderSide(color: AppTheme.border)),
      ),
      child: Row(
        children: [
          _tabButton('chat', '💬 对话', AppTheme.purple,
              badge: hasConversation
                  ? '(${_conversationMessages.length})'
                  : null),
          _tabButton('summary', '📝 总结', AppTheme.purple,
              stale: _summaryUpdated),
          _tabButton('concepts', '🧠 概念沉淀', AppTheme.emerald),
          _tabButton('docs', '📄 参考文档', AppTheme.purple,
              badge: '(${_selectedEventIds.length}/${_availableEvents.length})'),
        ],
      ),
    );
  }

  Widget _tabButton(String tab, String label, Color activeColor,
      {String? badge, bool stale = false}) {
    final isActive = _conceptTab == tab;
    final color = tab == 'concepts' ? AppTheme.emerald : AppTheme.purple;
    return GestureDetector(
      onTap: () {
        setState(() => _conceptTab = tab);
        if (tab == 'concepts') _loadConcepts();
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: isActive ? color : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label,
                style: TextStyle(
                    color: isActive ? color : AppTheme.textMuted,
                    fontSize: 11,
                    fontWeight: FontWeight.w500)),
            if (badge != null) ...[
              const SizedBox(width: 2),
              Text(badge,
                  style: const TextStyle(
                      color: AppTheme.textMuted, fontSize: 9)),
            ],
            if (stale) ...[
              const SizedBox(width: 4),
              Container(
                width: 6,
                height: 6,
                decoration: const BoxDecoration(
                  color: AppTheme.amber,
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildTabContent(String question, bool hasConversation) {
    switch (_conceptTab) {
      case 'chat':
        return _buildChatTab(hasConversation);
      case 'summary':
        return _buildSummaryTab();
      case 'concepts':
        return _buildConceptsTab();
      case 'docs':
      default:
        return _buildDocsTab();
    }
  }

  // ── Docs tab ──

  Widget _buildDocsTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Container(
        decoration: BoxDecoration(
          color: AppTheme.panel,
          border: Border.all(color: AppTheme.border),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: const BoxDecoration(
                border:
                    Border(bottom: BorderSide(color: AppTheme.border)),
              ),
              child: Row(
                children: [
                  Text(
                    _contemplateResults.isNotEmpty ? '凝神静思结果' : '全部可用文档',
                    style: const TextStyle(
                        color: AppTheme.textSecondary, fontSize: 12),
                  ),
                  const Spacer(),
                  if (_contemplateResults.isEmpty) ...[
                    GestureDetector(
                      onTap: _selectAllEvents,
                      child: const Text('全选',
                          style: TextStyle(
                              color: AppTheme.textMuted, fontSize: 11)),
                    ),
                    const SizedBox(width: 12),
                    GestureDetector(
                      onTap: _deselectAllEvents,
                      child: const Text('清空',
                          style: TextStyle(
                              color: AppTheme.textMuted, fontSize: 11)),
                    ),
                  ],
                ],
              ),
            ),

            // Error banner
            if (_contemplateError.isNotEmpty)
              Container(
                margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: AppTheme.error.withValues(alpha: 0.1),
                  border: Border.all(
                      color: AppTheme.error.withValues(alpha: 0.2)),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(_contemplateError,
                    style: const TextStyle(
                        color: AppTheme.error, fontSize: 11)),
              ),

            // Contemplate results
            if (_contemplateResults.isNotEmpty)
              _buildContemplateResults()
            else ...[
              // Search
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                child: SizedBox(
                  height: 34,
                  child: TextField(
                    style: const TextStyle(
                        color: AppTheme.textPrimary, fontSize: 12),
                    decoration: InputDecoration(
                      hintText: '搜索文档...',
                      hintStyle: const TextStyle(
                          color: AppTheme.textMuted, fontSize: 12),
                      prefixIcon: const Icon(Icons.search,
                          size: 14, color: AppTheme.textMuted),
                      filled: true,
                      fillColor: AppTheme.background,
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 0),
                      border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide:
                              const BorderSide(color: AppTheme.border)),
                      enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide:
                              const BorderSide(color: AppTheme.border)),
                      focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: const BorderSide(
                              color: AppTheme.purple, width: 0.5)),
                    ),
                    onChanged: (v) =>
                        setState(() => _eventSearch = v),
                  ),
                ),
              ),

              // Event list
              _buildEventList(),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildContemplateResults() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppTheme.background,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
              color: AppTheme.amber.withValues(alpha: 0.1)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text('找到 ${_contemplateResults.length} 条可能相关的文档',
                    style: const TextStyle(
                        color: AppTheme.amber, fontSize: 11)),
                const Spacer(),
                GestureDetector(
                  onTap:
                      (_contemplateLinking || _contemplateSelected.isEmpty)
                          ? null
                          : _handleContemplateLink,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTheme.amber.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(
                          color:
                              AppTheme.amber.withValues(alpha: 0.2)),
                    ),
                    child: Text(
                      _contemplateLinking
                          ? '关联中…'
                          : '确认关联 (${_contemplateSelected.length})',
                      style: const TextStyle(
                          color: AppTheme.amber, fontSize: 10),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 256),
              child: ListView(
                shrinkWrap: true,
                children: _contemplateResults.map((item) {
                  final eventId = item['event_id'] as String? ?? '';
                  final title = item['event_title'] as String? ?? '';
                  final relevance =
                      item['relevance'] as String? ?? 'medium';
                  final isChecked =
                      _contemplateSelected.contains(eventId);
                  return GestureDetector(
                    onTap: () => _toggleContemplateSelect(eventId),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 6),
                      margin: const EdgeInsets.only(bottom: 2),
                      decoration: BoxDecoration(
                        color: isChecked
                            ? AppTheme.amber.withValues(alpha: 0.08)
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Row(
                        children: [
                          SizedBox(
                            width: 16,
                            height: 16,
                            child: Checkbox(
                              value: isChecked,
                              onChanged: (_) =>
                                  _toggleContemplateSelect(eventId),
                              activeColor: AppTheme.amber,
                              materialTapTargetSize:
                                  MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                              side: const BorderSide(
                                  color: AppTheme.textMuted,
                                  width: 1),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(title,
                                style: const TextStyle(
                                    color: Color(0xFFD1D5DB),
                                    fontSize: 11),
                                overflow: TextOverflow.ellipsis),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 4, vertical: 1),
                            decoration: BoxDecoration(
                              color: relevance == 'high'
                                  ? AppTheme.emerald
                                      .withValues(alpha: 0.15)
                                  : AppTheme.amber
                                      .withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(3),
                            ),
                            child: Text(
                              relevance == 'high' ? '高' : '中',
                              style: TextStyle(
                                color: relevance == 'high'
                                    ? AppTheme.emerald
                                    : AppTheme.amber,
                                fontSize: 9,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEventList() {
    final filtered = _filteredEvents();
    if (_eventsLoading) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: Center(
            child: Text('加载中...',
                style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
      );
    }
    if (filtered.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: Center(
            child: Text('无匹配文档',
                style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
      );
    }

    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 320),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        shrinkWrap: true,
        children: filtered.map((e) {
          final m = e as Map<String, dynamic>;
          final evtId = m['id'] as String? ?? '';
          final title = (m['title_cn'] ?? m['title']) as String? ?? '';
          final sourceId = m['source_id'] as String? ?? '';
          final contentType = m['content_type'] as String? ?? '';
          final hasSummary =
              (m['ai_summary'] as String?)?.isNotEmpty == true;
          final isSelected = _selectedEventIds.contains(evtId);
          final isLocked = _lockedEventIds.contains(evtId);
          final relevance = _judgedEvents[evtId];

          return GestureDetector(
            onTap: isLocked && isSelected
                ? null
                : () => _toggleEvent(evtId),
            child: Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              margin: const EdgeInsets.only(bottom: 2),
              decoration: BoxDecoration(
                color: isSelected
                    ? AppTheme.purple.withValues(alpha: 0.08)
                    : Colors.transparent,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Row(
                children: [
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: Checkbox(
                      value: isSelected,
                      onChanged: (isLocked && isSelected)
                          ? null
                          : (_) => _toggleEvent(evtId),
                      activeColor: AppTheme.purple,
                      materialTapTargetSize:
                          MaterialTapTargetSize.shrinkWrap,
                      visualDensity: VisualDensity.compact,
                      side: const BorderSide(
                          color: AppTheme.textMuted, width: 1),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Row(
                      children: [
                        if (isLocked)
                          const Padding(
                            padding: EdgeInsets.only(right: 4),
                            child: Text('🔒',
                                style: TextStyle(fontSize: 11)),
                          ),
                        if (contentType == 'concept')
                          const Padding(
                            padding: EdgeInsets.only(right: 4),
                            child: Text('📘',
                                style: TextStyle(fontSize: 11)),
                          ),
                        Expanded(
                          child: Text(title,
                              style: TextStyle(
                                color: isSelected
                                    ? AppTheme.textPrimary
                                    : AppTheme.textSecondary,
                                fontSize: 11,
                              ),
                              overflow: TextOverflow.ellipsis),
                        ),
                      ],
                    ),
                  ),
                  if (relevance != null) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 4, vertical: 1),
                      decoration: BoxDecoration(
                        color: relevance == 'high'
                            ? AppTheme.emerald.withValues(alpha: 0.15)
                            : relevance == 'medium'
                                ? AppTheme.amber.withValues(alpha: 0.15)
                                : AppTheme.textMuted
                                    .withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(3),
                      ),
                      child: Text(
                        relevance == 'high'
                            ? '高'
                            : relevance == 'medium'
                                ? '中'
                                : '低',
                        style: TextStyle(
                          color: relevance == 'high'
                              ? AppTheme.emerald
                              : relevance == 'medium'
                                  ? AppTheme.amber
                                  : AppTheme.textMuted,
                          fontSize: 9,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(width: 6),
                  Text(_sourceLabel(sourceId),
                      style: const TextStyle(
                          color: AppTheme.textMuted, fontSize: 9)),
                  if (hasSummary) ...[
                    const SizedBox(width: 4),
                    const Text('AI',
                        style: TextStyle(
                            color: AppTheme.purple,
                            fontSize: 9,
                            fontWeight: FontWeight.w500)),
                  ],
                  const SizedBox(width: 8),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  // ── Chat tab ──

  Widget _buildChatTab(bool hasConversation) {
    if (_conversationMessages.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text('在"参考文档"中勾选文档，然后点击右上角「发起问答」',
              style: TextStyle(color: AppTheme.textMuted, fontSize: 12),
              textAlign: TextAlign.center),
        ),
      );
    }

    return ListView.builder(
      controller: _chatScrollCtrl,
      padding: const EdgeInsets.all(16),
      itemCount: _conversationMessages.length,
      itemBuilder: (context, index) {
        final msg = _conversationMessages[index];
        final role = msg['role'] as String? ?? 'user';
        final content = msg['content'] as String? ?? '';
        final isUser = role == 'user';
        final createdAt = msg['created_at'] as String?;

        return Align(
          alignment:
              isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.7),
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: isUser
                  ? AppTheme.purple.withValues(alpha: 0.12)
                  : AppTheme.panel,
              borderRadius: BorderRadius.circular(12),
              border: isUser
                  ? Border.all(
                      color: AppTheme.purple.withValues(alpha: 0.2))
                  : Border.all(color: AppTheme.border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (isUser)
                  Text(content,
                      style: const TextStyle(
                          color: AppTheme.textPrimary,
                          fontSize: 13,
                          height: 1.5))
                else
                  _renderMarkdownWithRefs(
                      content, _conversationLockedIds, context),
                if (!isUser && createdAt != null) ...[
                  const SizedBox(height: 6),
                  Text(createdAt.substring(0, 16).replaceAll('T', ' '),
                      style: const TextStyle(
                          color: AppTheme.textMuted, fontSize: 9)),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  // ── Summary tab ──

  Widget _buildSummaryTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Stale warning
          if (_summaryUpdated)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.amber.withValues(alpha: 0.05),
                border: Border.all(
                    color: AppTheme.amber.withValues(alpha: 0.15)),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Expanded(
                    child: Text('对话已更新，总结可能已过期',
                        style: TextStyle(
                            color: AppTheme.amber, fontSize: 11)),
                  ),
                  GestureDetector(
                    onTap:
                        _summaryLoading ? null : _generateSummary,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: AppTheme.amber.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                            color: AppTheme.amber
                                .withValues(alpha: 0.2)),
                      ),
                      child: Text(
                        _summaryLoading ? '生成中...' : '生成总结',
                        style: const TextStyle(
                            color: AppTheme.amber, fontSize: 10),
                      ),
                    ),
                  ),
                ],
              ),
            ),

          const SizedBox(height: 16),

          if (_summary.isNotEmpty) ...[
            // Summary header
            Row(
              children: [
                Container(
                  width: 4,
                  height: 14,
                  decoration: BoxDecoration(
                    color: AppTheme.amber,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(width: 8),
                const Text('📝 AI 深度总结',
                    style: TextStyle(
                        color: AppTheme.amber,
                        fontSize: 12,
                        fontWeight: FontWeight.w500)),
                const Spacer(),
                if (_summaryCreatedAt.isNotEmpty)
                  Text(
                      _summaryCreatedAt
                          .substring(0, 16)
                          .replaceAll('T', ' '),
                      style: const TextStyle(
                          color: AppTheme.textMuted, fontSize: 10)),
              ],
            ),
            const SizedBox(height: 12),
            _renderMarkdownWithRefs(
                _summary, _conversationLockedIds, context),
          ] else ...[
            const Center(
              child: Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Text('在"参考文档"中勾选文档并发起问答后，可生成总结',
                    style: TextStyle(
                        color: AppTheme.textMuted, fontSize: 12),
                    textAlign: TextAlign.center),
              ),
            ),
          ],
        ],
      ),
    );
  }

  // ── Concepts tab ──

  Widget _buildConceptsTab() {
    if (_conceptsLoading) {
      return const Center(
        child: CircularProgressIndicator(color: AppTheme.accent),
      );
    }

    if (_summaryConcepts.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Text(
            _summary.isNotEmpty ? '总结中未找到相关概念' : '请先生成总结',
            style: const TextStyle(
                color: AppTheme.textMuted, fontSize: 12),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: _summaryConcepts.map((c) {
        final name = c['name'] as String? ?? '';
        final description = c['description'] as String? ?? '';
        final precipitated = c['precipitated'] == true;
        final isPrecipitating = _precipitatingName == name;

        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.panel,
            border: Border.all(color: AppTheme.border),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name,
                        style: const TextStyle(
                            color: Color(0xFFE5E7EB),
                            fontSize: 13,
                            fontWeight: FontWeight.w500)),
                    const SizedBox(height: 6),
                    Text(description,
                        style: const TextStyle(
                            color: AppTheme.textSecondary,
                            fontSize: 12,
                            height: 1.5)),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              if (precipitated)
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppTheme.emerald.withValues(alpha: 0.1),
                    border: Border.all(
                        color:
                            AppTheme.emerald.withValues(alpha: 0.2)),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text('已沉淀 ✓',
                      style: TextStyle(
                          color: AppTheme.emerald, fontSize: 10)),
                )
              else
                GestureDetector(
                  onTap: isPrecipitating
                      ? null
                      : () => _precipitateConcept(name, description),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTheme.purple.withValues(alpha: 0.1),
                      border: Border.all(
                          color: AppTheme.purple
                              .withValues(alpha: 0.2)),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      isPrecipitating ? '沉淀中...' : '沉淀',
                      style: const TextStyle(
                          color: AppTheme.purple, fontSize: 10),
                    ),
                  ),
                ),
            ],
          ),
        );
      }).toList(),
    );
  }

  // ── Bottom bar ──

  Widget _buildBottomBar(bool hasConversation) {
    if (_conceptTab == 'chat' && hasConversation) {
      return Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: const BoxDecoration(
          color: AppTheme.background,
          border: Border(top: BorderSide(color: AppTheme.border)),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _followUpCtrl,
                enabled: !_sendingFollowUp,
                maxLines: null,
                minLines: 1,
                style: const TextStyle(
                    color: AppTheme.textPrimary, fontSize: 13),
                decoration: InputDecoration(
                  hintText: '输入追问... Shift+Enter 换行',
                  hintStyle: const TextStyle(
                      color: AppTheme.textMuted, fontSize: 13),
                  filled: true,
                  fillColor: AppTheme.panel,
                  contentPadding: const EdgeInsets.symmetric(
                      horizontal: 12, vertical: 10),
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide:
                          const BorderSide(color: AppTheme.border)),
                  enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide:
                          const BorderSide(color: AppTheme.border)),
                  focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: const BorderSide(
                          color: AppTheme.purple, width: 0.5)),
                ),
                onSubmitted: (_) => _sendFollowUp(),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap:
                  (_sendingFollowUp || _followUpCtrl.text.trim().isEmpty)
                      ? null
                      : _sendFollowUp,
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.purple.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                      color: AppTheme.purple.withValues(alpha: 0.2)),
                ),
                child: Icon(Icons.send,
                    size: 16,
                    color: (_sendingFollowUp ||
                            _followUpCtrl.text.trim().isEmpty)
                        ? AppTheme.textMuted
                        : AppTheme.purple),
              ),
            ),
          ],
        ),
      );
    }

    if (_conceptTab == 'summary') {
      return Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: const BoxDecoration(
          color: AppTheme.background,
          border: Border(top: BorderSide(color: AppTheme.border)),
        ),
        child: GestureDetector(
          onTap: _summaryLoading ? null : _generateSummary,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: AppTheme.amber.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                  color: AppTheme.amber.withValues(alpha: 0.2)),
            ),
            child: Center(
              child: Text(
                _summaryLoading
                    ? '生成中...'
                    : (_summary.isNotEmpty ? '重新生成总结' : '生成总结'),
                style: const TextStyle(
                    color: AppTheme.amber,
                    fontSize: 13,
                    fontWeight: FontWeight.w500),
              ),
            ),
          ),
        ),
      );
    }

    if (_conceptTab == 'docs' && hasConversation) {
      return Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: const BoxDecoration(
          color: AppTheme.background,
          border: Border(top: BorderSide(color: AppTheme.border)),
        ),
        child: GestureDetector(
          onTap: () => setState(() => _conceptTab = 'chat'),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              color: AppTheme.purple.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                  color: AppTheme.purple.withValues(alpha: 0.2)),
            ),
            child: const Center(
              child: Text('返回对话',
                  style: TextStyle(
                      color: AppTheme.purple,
                      fontSize: 13,
                      fontWeight: FontWeight.w500)),
            ),
          ),
        ),
      );
    }

    return const SizedBox.shrink();
  }
}
