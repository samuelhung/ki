import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

typedef JsonMap = Map<String, dynamic>;

enum DiscoveryMode {
  choose,
  globalStage1,
  globalStage2,
  topicInput,
  topicResults,
  manualCreate,
  manualSuggest,
}

class SeriesPage extends StatefulWidget {
  const SeriesPage({super.key});
  @override
  State<SeriesPage> createState() => _SeriesPageState();
}

class _SeriesPageState extends State<SeriesPage> {
  final _dio = ApiClient().dio;

  // ── Saved series ──
  List<JsonMap> _series = [];
  bool _loading = true;
  String _error = '';

  // ── Discovery ──
  bool _showDiscovery = false;
  DiscoveryMode _mode = DiscoveryMode.choose;
  bool _discovering = false;

  // Stage 1
  List<JsonMap> _stage1Groups = [];
  Set<int> _selectedGroupIndices = {};
  String _stage1Message = '';

  // Stage 2 / topic results
  List<JsonMap> _candidates = [];
  List<JsonMap> _duplicates = [];
  String _discoverSummary = '';

  // Topic input
  final _topicCtrl = TextEditingController();

  // Manual create
  final _manualTitleCtrl = TextEditingController();
  final _eventsSearchCtrl = TextEditingController();
  Set<String> _manualSelectedIds = {};
  List<JsonMap> _availableEvents = [];
  bool _eventsLoading = false;
  String _manualCreatedId = '';
  String _manualCreatedName = '';
  bool _suggesting = false;
  String _suggestedName = '';
  String _suggestedDescription = '';
  String _suggestError = '';
  bool _adopting = false;

  // Save state
  Set<int> _saving = {};

  // Dialog bridge — auto-refresh dialog when setState is called
  VoidCallback? _dialogRefresh;
  bool _mounted = true;

  @override
  void initState() {
    super.initState();
    _loadSeries();
  }

  @override
  void dispose() {
    _mounted = false;
    _topicCtrl.dispose();
    _manualTitleCtrl.dispose();
    _eventsSearchCtrl.dispose();
    super.dispose();
  }

  /// Override setState to also refresh the discovery dialog if open
  @override
  void setState(VoidCallback fn) {
    super.setState(fn);
    _dialogRefresh?.call();
  }

  // ═══════════════════════════════════════════
  // Load saved series
  // ═══════════════════════════════════════════
  Future<void> _loadSeries() async {
    if (!_mounted) return;
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final resp = await _dio.get('/api/ingest/series');
      final data = resp.data is Map ? resp.data as JsonMap : <String, dynamic>{};
      final items = (data['items'] as List<dynamic>?)
              ?.map((e) => e as JsonMap)
              .toList() ??
          [];
      if (_mounted) {
        setState(() {
          _series = items;
          _loading = false;
        });
      }
    } catch (e) {
      if (_mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  // ═══════════════════════════════════════════
  // Discovery open / close
  // ═══════════════════════════════════════════
  void _openDiscovery() {
    setState(() {
      _showDiscovery = true;
      _mode = DiscoveryMode.choose;
      _error = '';
      _stage1Groups = [];
      _candidates = [];
      _duplicates = [];
      _selectedGroupIndices = {};
      _stage1Message = '';
      _topicCtrl.clear();
      _discoverSummary = '';
      _manualTitleCtrl.clear();
      _manualSelectedIds = {};
      _availableEvents = [];
      _eventsSearchCtrl.clear();
      _manualCreatedId = '';
      _manualCreatedName = '';
      _suggestedName = '';
      _suggestedDescription = '';
      _suggestError = '';
      _adopting = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_mounted && _showDiscovery) _showDiscoveryDialog();
    });
  }

  void _closeDiscovery() {
    setState(() {
      _showDiscovery = false;
      _mode = DiscoveryMode.choose;
    });
    _loadSeries();
  }

  // ═══════════════════════════════════════════
  // Global discovery — Stage 1
  // ═══════════════════════════════════════════
  Future<void> _handleGlobalStage1() async {
    setState(() {
      _mode = DiscoveryMode.globalStage1;
      _discovering = true;
      _stage1Message = '';
      _stage1Groups = [];
    });
    try {
      final resp = await _dio.post('/api/ingest/series/discover/stage1');
      final d = resp.data is Map ? resp.data as JsonMap : <String, dynamic>{};
      final groups = (d['groups'] as List<dynamic>?)
              ?.map((e) => e as JsonMap)
              .toList() ??
          [];
      if (_mounted) {
        setState(() {
          if ((d['message'] as String?)?.isNotEmpty == true && groups.isEmpty) {
            _stage1Message = d['message'] as String;
          }
          _stage1Groups = groups;
          if (groups.isNotEmpty) {
            _selectedGroupIndices =
                Set<int>.from(List.generate(groups.length, (i) => i));
          }
          _discovering = false;
        });
      }
    } catch (e) {
      if (_mounted) {
        setState(() {
          _error = e.toString();
          _discovering = false;
        });
      }
    }
  }

  void _toggleGroup(int idx) {
    setState(() {
      final next = Set<int>.from(_selectedGroupIndices);
      next.contains(idx) ? next.remove(idx) : next.add(idx);
      _selectedGroupIndices = next;
    });
  }

  void _selectAllGroups() {
    setState(() => _selectedGroupIndices =
        Set<int>.from(List.generate(_stage1Groups.length, (i) => i)));
  }

  void _deselectAllGroups() {
    setState(() => _selectedGroupIndices = {});
  }

  // ═══════════════════════════════════════════
  // Global discovery — Stage 2
  // ═══════════════════════════════════════════
  Future<void> _handleGlobalStage2() async {
    final selectedIds = <String>[];
    final selectedNames = <String>[];
    for (final i in _selectedGroupIndices) {
      if (i < _stage1Groups.length) {
        final g = _stage1Groups[i];
        selectedIds.addAll(
            (g['event_ids'] as List<dynamic>?)?.map((e) => e.toString()) ?? []);
        selectedNames.add((g['name'] as String?) ?? '');
      }
    }
    if (selectedIds.length < 2) {
      setState(() => _stage1Message = '请至少选择 2 条事件');
      return;
    }
    setState(() {
      _mode = DiscoveryMode.globalStage2;
      _discovering = true;
      _candidates = [];
      _duplicates = [];
    });
    try {
      final resp = await _dio.post('/api/ingest/series/discover/stage2', data: {
        'event_ids': selectedIds,
        'name_hint': selectedNames.where((n) => n.isNotEmpty).join('、'),
      });
      final d = resp.data is Map ? resp.data as JsonMap : <String, dynamic>{};
      final series = (d['series'] as List<dynamic>?)
              ?.map((e) => e as JsonMap)
              .toList() ??
          [];
      final dups = (d['duplicates'] as List<dynamic>?)
              ?.map((e) => e as JsonMap)
              .toList() ??
          [];
      final skipped = d['duplicates_skipped'];
      final summary = (d['message'] as String?)?.isNotEmpty == true && series.isEmpty
          ? d['message'] as String
          : skipped != null
              ? '发现 ${series.length} 个候选，过滤 $skipped 个重复'
              : '发现 ${series.length} 个候选';
      if (_mounted) {
        setState(() {
          _candidates = series;
          _duplicates = dups;
          _discoverSummary = summary;
          _discovering = false;
        });
      }
    } catch (e) {
      if (_mounted) setState(() { _error = e.toString(); _discovering = false; });
    }
  }

  // ═══════════════════════════════════════════
  // Topic discovery
  // ═══════════════════════════════════════════
  Future<void> _handleTopicDiscover() async {
    final t = _topicCtrl.text.trim();
    if (t.isEmpty) return;
    setState(() {
      _mode = DiscoveryMode.topicResults;
      _discovering = true;
      _candidates = [];
      _duplicates = [];
      _discoverSummary = '';
    });
    try {
      final resp = await _dio.post('/api/ingest/series/discover/by-topic', data: {'topic': t});
      final d = resp.data is Map ? resp.data as JsonMap : <String, dynamic>{};
      final series = (d['series'] as List<dynamic>?)
              ?.map((e) => e as JsonMap)
              .toList() ??
          [];
      final dups = (d['duplicates'] as List<dynamic>?)
              ?.map((e) => e as JsonMap)
              .toList() ??
          [];
      final matched = d['matched_events'] ?? '?';
      final summary = (d['message'] as String?)?.isNotEmpty == true && series.isEmpty
          ? d['message'] as String
          : '匹配 $matched 条内容，发现 ${series.length} 个候选';
      if (_mounted) {
        setState(() {
          _candidates = series;
          _duplicates = dups;
          _discoverSummary = summary;
          _discovering = false;
        });
      }
    } catch (e) {
      if (_mounted) setState(() { _error = e.toString(); _discovering = false; });
    }
  }

  // ═══════════════════════════════════════════
  // Save candidate
  // ═══════════════════════════════════════════
  Future<void> _handleSave(int idx) async {
    if (idx < 0 || idx >= _candidates.length) return;
    final c = _candidates[idx];
    setState(() => _saving = Set.from(_saving)..add(idx));
    try {
      final resp = await _dio.post('/api/ingest/series', data: {
        'name': c['name'],
        'description': c['description'] ?? '',
        'member_ids': c['member_ids'],
      });
      if (resp.statusCode != null && resp.statusCode! < 400) {
        if (_mounted) {
          setState(() {
            _candidates.removeAt(idx);
            if (_candidates.isEmpty) { _discoverSummary = ''; _duplicates = []; }
          });
          _loadSeries();
        }
      }
    } catch (_) {}
    if (_mounted) {
      setState(() { final n = Set<int>.from(_saving); n.remove(idx); _saving = n; });
    }
  }

  // ═══════════════════════════════════════════
  // Manual create
  // ═══════════════════════════════════════════
  Future<void> _openManualCreate() async {
    setState(() { _mode = DiscoveryMode.manualCreate; _eventsLoading = true; });
    try {
      final resp = await _dio.get('/api/events?limit=500');
      final list = resp.data is List ? (resp.data as List).cast<JsonMap>() : <JsonMap>[];
      if (_mounted) setState(() { _availableEvents = list; _eventsLoading = false; });
    } catch (_) {
      if (_mounted) setState(() { _availableEvents = []; _eventsLoading = false; });
    }
  }

  void _toggleManualEvent(String id) {
    setState(() {
      final next = Set<String>.from(_manualSelectedIds);
      next.contains(id) ? next.remove(id) : next.add(id);
      _manualSelectedIds = next;
    });
  }

  Future<void> _handleManualCreate() async {
    final title = _manualTitleCtrl.text.trim();
    final ids = _manualSelectedIds.toList();
    if (ids.length < 2 || title.isEmpty) return;
    setState(() => _saving = {-1});
    try {
      final resp = await _dio.post('/api/ingest/series', data: {'name': title, 'member_ids': ids});
      if (resp.statusCode != null && resp.statusCode! < 400) {
        final d = resp.data is Map ? resp.data as JsonMap : <String, dynamic>{};
        final createdId = (d['id'] as dynamic)?.toString() ?? '';
        if (_mounted) {
          setState(() {
            _manualCreatedId = createdId;
            _manualCreatedName = title;
            _mode = DiscoveryMode.manualSuggest;
          });
          _loadSeries();
          _handleSuggestName(ids: ids, currentName: title);
        }
      } else {
        if (_mounted) setState(() => _error = '创建失败');
      }
    } catch (_) {
      if (_mounted) setState(() => _error = '创建失败');
    }
    if (_mounted) setState(() => _saving = {});
  }

  Future<void> _handleSuggestName({List<String>? ids, String? currentName}) async {
    final memberIds = ids ?? _manualSelectedIds.toList();
    if (_mounted) setState(() {
      _suggesting = true; _suggestError = ''; _suggestedName = ''; _suggestedDescription = '';
    });
    try {
      final resp = await _dio.post('/api/ingest/series/suggest-name', data: {
        'member_ids': memberIds, 'current_name': currentName ?? _manualCreatedName,
      });
      final d = resp.data is Map ? resp.data as JsonMap : <String, dynamic>{};
      if (_mounted) {
        setState(() {
          if ((d['suggested_name'] as String?)?.isNotEmpty == true) {
            _suggestedName = d['suggested_name'] as String;
            _suggestedDescription = (d['suggested_description'] as String?) ?? '';
          } else if ((d['message'] as String?)?.isNotEmpty == true) {
            _suggestError = d['message'] as String;
          }
          _suggesting = false;
        });
      }
    } catch (_) {
      if (_mounted) setState(() { _suggestError = '请求失败'; _suggesting = false; });
    }
  }

  Future<void> _handleAdoptSuggestion() async {
    if (_manualCreatedId.isEmpty || _suggestedName.isEmpty) return;
    if (_mounted) setState(() => _adopting = true);
    try {
      await _dio.put('/api/ingest/series/$_manualCreatedId', data: {
        'name': _suggestedName, 'description': _suggestedDescription,
      });
      if (_mounted) {
        setState(() {
          _manualCreatedName = _suggestedName;
          _suggestedName = ''; _suggestedDescription = ''; _adopting = false;
        });
        _loadSeries();
      }
    } catch (_) {
      if (_mounted) setState(() => _adopting = false);
    }
  }

  // ═══════════════════════════════════════════
  // Modal title
  // ═══════════════════════════════════════════
  String _discoveryTitle() {
    switch (_mode) {
      case DiscoveryMode.choose: return '发现专题';
      case DiscoveryMode.globalStage1: return '全局发现 · 选择主题领域';
      case DiscoveryMode.globalStage2: return '全局发现 · 候选专题';
      case DiscoveryMode.topicInput: return '按主题发现';
      case DiscoveryMode.topicResults: return '按主题发现 · 候选专题';
      case DiscoveryMode.manualCreate: return '自由组题';
      case DiscoveryMode.manualSuggest: return '自由组题 · AI 命名建议';
    }
  }

  // ═══════════════════════════════════════════
  // Main build
  // ═══════════════════════════════════════════
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: Column(children: [
        _buildHeader(),
        if (_error.isNotEmpty) _buildErrorBanner(),
        Expanded(child: _buildContent()),
      ]),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.fromLTRB(32, 24, 32, 16),
      decoration: const BoxDecoration(color: AppTheme.background),
      child: Row(children: [
        const Icon(Icons.layers, color: AppTheme.purple, size: 40),
        const SizedBox(width: 12),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('专题系列',
              style: TextStyle(color: AppTheme.textPrimary, fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 2),
          Text('AI 驱动的知识聚类，将分散内容串联为专题',
              style: TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
        ]),
        const Spacer(),
        _buildDiscoverButton(),
      ]),
    );
  }

  Widget _buildDiscoverButton() {
    return InkWell(
      onTap: _openDiscovery,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: AppTheme.purple.withOpacity(0.15),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppTheme.purple.withOpacity(0.3)),
        ),
        child: const Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(Icons.lightbulb_outline, color: AppTheme.purple, size: 16),
          SizedBox(width: 6),
          Text('发现专题', style: TextStyle(color: AppTheme.purple, fontSize: 14, fontWeight: FontWeight.w500)),
        ]),
      ),
    );
  }

  Widget _buildErrorBanner() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32, vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.error.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.error.withOpacity(0.2)),
      ),
      child: Text(_error, style: const TextStyle(color: AppTheme.error, fontSize: 13)),
    );
  }

  Widget _buildContent() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: AppTheme.textMuted, strokeWidth: 2));
    }
    if (_series.isEmpty) {
      return Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.layers, size: 40, color: Color(0xFF374151)),
          const SizedBox(height: 12),
          const Text('暂无专题', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
          const SizedBox(height: 4),
          Text('点击「发现专题」让 AI 帮你找出内容之间的关联',
              style: TextStyle(color: AppTheme.textMuted.withOpacity(0.7), fontSize: 12)),
        ]),
      );
    }
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      children: [
        const SizedBox(height: 4),
        Text('已保存专题（${_series.length}）',
            style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500)),
        const SizedBox(height: 12),
        ..._series.map((s) => _buildSeriesCard(s)),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _buildSeriesCard(JsonMap s) {
    final id = (s['id'] as dynamic)?.toString() ?? '';
    final name = (s['name'] as String?) ?? '(无标题)';
    final description = (s['description'] as String?) ?? '';
    final memberCount = (s['members'] as List<dynamic>?)?.length ?? 0;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () => context.go('/series/$id'),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppTheme.border),
          ),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500)),
                if (description.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(description, maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                ],
              ]),
            ),
            const SizedBox(width: 12),
            Text('$memberCount 条内容', style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
            const SizedBox(width: 8),
            Icon(Icons.open_in_new, size: 14, color: AppTheme.textMuted.withOpacity(0.5)),
          ]),
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════
  // Discovery Modal
  // ═══════════════════════════════════════════
  void _showDiscoveryDialog() {
    if (!_showDiscovery) return;
    showDialog(
      context: context,
      useRootNavigator: true,
      barrierDismissible: false,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setDialogState) {
            _dialogRefresh = () => setDialogState(() {});
            return AlertDialog(
              backgroundColor: AppTheme.panel,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: const BorderSide(color: AppTheme.border),
              ),
              titlePadding: const EdgeInsets.fromLTRB(24, 20, 16, 0),
              contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              actionsPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              title: Row(children: [
                Expanded(child: Text(_discoveryTitle(),
                    style: const TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600))),
                if (_mode != DiscoveryMode.choose && _mode != DiscoveryMode.manualSuggest)
                  InkWell(
                    onTap: () => setState(() { _mode = DiscoveryMode.choose; _error = ''; }),
                    borderRadius: BorderRadius.circular(6),
                    child: Padding(
                      padding: const EdgeInsets.all(4),
                      child: Icon(Icons.arrow_back, size: 18, color: AppTheme.textMuted.withOpacity(0.6)),
                    ),
                  ),
                const SizedBox(width: 8),
                InkWell(
                  onTap: () { _closeDiscovery(); Navigator.of(context, rootNavigator: true).pop(); },
                  borderRadius: BorderRadius.circular(6),
                  child: const Padding(
                    padding: EdgeInsets.all(4),
                    child: Icon(Icons.close, size: 20, color: AppTheme.textMuted),
                  ),
                ),
              ]),
              content: SizedBox(width: 600, child: _buildDiscoveryContent()),
            );
          },
        );
      },
    ).then((_) {
      if (_mounted && _showDiscovery) _closeDiscovery();
    });
  }

  Widget _buildDiscoveryContent() {
    switch (_mode) {
      case DiscoveryMode.choose: return _buildChooseMode();
      case DiscoveryMode.globalStage1: return _buildStage1Mode();
      case DiscoveryMode.globalStage2: return _buildCandidatesDisplay();
      case DiscoveryMode.topicInput: return _buildTopicInputMode();
      case DiscoveryMode.topicResults: return _buildCandidatesDisplay();
      case DiscoveryMode.manualCreate: return _buildManualCreateMode();
      case DiscoveryMode.manualSuggest: return _buildManualSuggestMode();
    }
  }

  // ── Choose mode ──
  Widget _buildChooseMode() {
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Padding(
        padding: EdgeInsets.only(bottom: 16),
        child: Text('选择一种方式，让 AI 帮你发现知识专题',
            style: TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
      ),
      _choiceCard(
        icon: Icons.bolt, iconColor: AppTheme.purple, title: '全局发现',
        description: '全量扫描所有内容，AI 自动聚类。先粗分主题领域，再精细发现',
        onTap: _handleGlobalStage1,
      ),
      const SizedBox(height: 12),
      _choiceCard(
        icon: Icons.search, iconColor: AppTheme.amber, title: '按主题发现',
        description: '输入一个主题或关键词，AI 围绕它整理相关专题。更省 token',
        onTap: () => setState(() => _mode = DiscoveryMode.topicInput),
      ),
      const SizedBox(height: 12),
      _choiceCard(
        icon: Icons.draw_outlined, iconColor: AppTheme.emerald, title: '自由组题',
        description: '手动选文档、起标题，AI 帮你优化命名和副标题',
        onTap: _openManualCreate,
      ),
    ]);
  }

  Widget _choiceCard({
    required IconData icon, required Color iconColor,
    required String title, required String description, required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppTheme.background,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.border),
        ),
        child: Row(children: [
          Container(
            width: 40, height: 40,
            decoration: BoxDecoration(color: iconColor.withOpacity(0.15), borderRadius: BorderRadius.circular(8)),
            child: Icon(icon, color: iconColor, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500)),
              const SizedBox(height: 2),
              Text(description, style: TextStyle(color: AppTheme.textMuted.withOpacity(0.8), fontSize: 11)),
            ]),
          ),
        ]),
      ),
    );
  }

  // ── Stage 1 mode ──
  Widget _buildStage1Mode() {
    if (_discovering) return _buildLoadingState('正在分析全部事件标题，发现主题领域...');
    if (_stage1Message.isNotEmpty && _stage1Groups.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 32),
          child: Text(_stage1Message, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              textAlign: TextAlign.center),
        ),
      );
    }

    final totalSelected = _selectedGroupIndices.fold<int>(
        0, (sum, i) => sum + ((_stage1Groups[i]['count'] as int?) ?? 0));

    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Expanded(
          child: RichText(text: TextSpan(
            style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
            children: [
              const TextSpan(text: 'AI 发现 '),
              TextSpan(text: '${_stage1Groups.length}',
                  style: const TextStyle(color: AppTheme.purple, fontWeight: FontWeight.w500)),
              const TextSpan(text: ' 个主题领域，选择感兴趣的进入精细发现'),
            ],
          )),
        ),
        Row(children: [
          _textButton('全选', _selectAllGroups),
          const SizedBox(width: 8),
          _textButton('取消', _deselectAllGroups),
        ]),
      ]),
      const SizedBox(height: 12),
      ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 350),
        child: ListView(
          shrinkWrap: true,
          children: _stage1Groups.asMap().entries.map((entry) {
            final idx = entry.key;
            final g = entry.value;
            return _buildGroupCheckbox(idx, g);
          }).toList(),
        ),
      ),
      const SizedBox(height: 12),
      Divider(color: AppTheme.border, height: 1),
      const SizedBox(height: 12),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text('已选 ${_selectedGroupIndices.length} 个领域，共 $totalSelected 条内容',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        _actionButton(
          label: '精细发现', icon: Icons.lightbulb_outline, color: AppTheme.purple,
          enabled: totalSelected >= 2, onTap: _handleGlobalStage2,
        ),
      ]),
    ]);
  }

  Widget _buildGroupCheckbox(int idx, JsonMap g) {
    final name = (g['name'] as String?) ?? '';
    final description = (g['description'] as String?) ?? '';
    final count = g['count'] as int? ?? 0;
    final checked = _selectedGroupIndices.contains(idx);

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: () => _toggleGroup(idx),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: checked ? AppTheme.purple.withOpacity(0.05) : AppTheme.background,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: checked ? AppTheme.purple.withOpacity(0.4) : AppTheme.border),
          ),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(
              width: 20, height: 20,
              child: Checkbox(
                value: checked, onChanged: (_) => _toggleGroup(idx),
                activeColor: AppTheme.purple, side: const BorderSide(color: AppTheme.border),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                visualDensity: VisualDensity.compact,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Flexible(child: Text(name,
                      style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500))),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(color: AppTheme.panelActive, borderRadius: BorderRadius.circular(10)),
                    child: Text('$count 条', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
                  ),
                ]),
                if (description.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(description, maxLines: 2, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                ],
              ]),
            ),
          ]),
        ),
      ),
    );
  }

  // ── Candidates display (stage2 / topic_results) ──
  Widget _buildCandidatesDisplay() {
    if (_discovering) return _buildLoadingState('正在精细分析，生成候选专题...');

    if (_discoverSummary.isNotEmpty && _candidates.isEmpty) {
      return Column(mainAxisSize: MainAxisSize.min, children: [
        const SizedBox(height: 24),
        Center(child: Text(_discoverSummary,
            style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13), textAlign: TextAlign.center)),
        const SizedBox(height: 12),
        InkWell(
          onTap: () => setState(() => _mode = DiscoveryMode.choose),
          child: const Text('返回', style: TextStyle(color: AppTheme.purple, fontSize: 12)),
        ),
      ]);
    }

    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (_discoverSummary.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(_discoverSummary, style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
        ),
      ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 400),
        child: ListView(
          shrinkWrap: true,
          children: _candidates.asMap().entries.map((entry) {
            final idx = entry.key;
            return _buildCandidateCard(idx, entry.value);
          }).toList(),
        ),
      ),
      if (_duplicates.isNotEmpty) ...[
        const SizedBox(height: 12),
        _buildDuplicatesSection(),
      ],
      const SizedBox(height: 12),
      Divider(color: AppTheme.border, height: 1),
      const SizedBox(height: 12),
      InkWell(
        onTap: () => setState(() => _mode = DiscoveryMode.choose),
        child: const Text('← 返回选择', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ),
    ]);
  }

  Widget _buildCandidateCard(int idx, JsonMap c) {
    final name = (c['name'] as String?) ?? '';
    final description = (c['description'] as String?) ?? '';
    final rationale = (c['rationale'] as String?) ?? '';
    final memberTitles = (c['member_titles'] as List<dynamic>?)?.map((e) => e.toString()) ??
        (c['member_ids'] as List<dynamic>?)?.map((e) => e.toString()) ?? [];
    final dupOf = c['_duplicate_of'] as JsonMap?;
    final isDuplicate = dupOf != null;
    final isSaving = _saving.contains(idx);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppTheme.panel, borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.border),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Flexible(child: Text(name,
                      style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500))),
                  if (isDuplicate) ...[
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppTheme.amber.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: AppTheme.amber.withOpacity(0.2)),
                      ),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(Icons.warning_amber_rounded, size: 10, color: AppTheme.amber),
                        const SizedBox(width: 4),
                        Text('疑似重复: ${dupOf['name'] ?? ''}',
                            style: const TextStyle(color: AppTheme.amber, fontSize: 10)),
                      ]),
                    ),
                  ],
                ]),
                if (description.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(description, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
                ],
              ]),
            ),
            const SizedBox(width: 12),
            _actionButton(
              label: isSaving ? '...' : (isDuplicate ? '已存在' : '保存'),
              color: AppTheme.emerald,
              enabled: !isSaving && !isDuplicate,
              onTap: () => _handleSave(idx),
            ),
          ]),
          if (rationale.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(rationale, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
          ],
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: memberTitles.map((t) {
            final displayTitle = t.length > 30 ? '${t.substring(0, 30)}…' : t;
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(color: AppTheme.panelActive, borderRadius: BorderRadius.circular(4)),
              child: Text(displayTitle, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 10)),
            );
          }).toList()),
        ]),
      ),
    );
  }

  Widget _buildDuplicatesSection() {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: const EdgeInsets.only(top: 8),
      shape: const Border(),
      collapsedShape: const Border(),
      title: Text('已过滤 ${_duplicates.length} 个重复候选',
          style: TextStyle(color: AppTheme.textMuted.withOpacity(0.6), fontSize: 11)),
      children: _duplicates.map((d) {
        final name = (d['name'] as String?) ?? '';
        final dupOf = d['_duplicate_of'] as JsonMap?;
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.panel, borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppTheme.amber.withOpacity(0.1)),
            ),
            child: Opacity(
              opacity: 0.6,
              child: Row(children: [
                Text(name, style: const TextStyle(
                    color: AppTheme.textMuted, fontSize: 12, decoration: TextDecoration.lineThrough)),
                const SizedBox(width: 8),
                Text('→ ${dupOf?['name'] ?? ''}', style: const TextStyle(color: AppTheme.amber, fontSize: 10)),
              ]),
            ),
          ),
        );
      }).toList(),
    );
  }

  // ── Topic input mode ──
  Widget _buildTopicInputMode() {
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('输入一个主题或关键词，AI 围绕它发现相关专题',
          style: TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
      const SizedBox(height: 16),
      Row(children: [
        Expanded(
          child: TextField(
            controller: _topicCtrl, autofocus: true,
            onSubmitted: (_) => _handleTopicDiscover(),
            style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14),
            decoration: InputDecoration(
              hintText: '例如：伊朗核问题、台海局势、AI 监管...',
              hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 14),
              filled: true, fillColor: AppTheme.background,
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: AppTheme.amber.withOpacity(0.5))),
            ),
          ),
        ),
        const SizedBox(width: 8),
        _actionButton(label: '发现', icon: Icons.search, color: AppTheme.amber,
          enabled: _topicCtrl.text.trim().isNotEmpty, onTap: _handleTopicDiscover),
      ]),
      const SizedBox(height: 12),
      InkWell(
        onTap: () => setState(() => _mode = DiscoveryMode.choose),
        child: const Text('← 返回选择', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ),
    ]);
  }

  // ── Manual create mode ──
  Widget _buildManualCreateMode() {
    const topicColorMap = {
      '格局': Color(0xFFA78BFA), '财富': Color(0xFFFBBF24),
      '认知': Color(0xFF60A5FA), '前瞻': Color(0xFF34D399),
    };

    final manualEvents = _availableEvents.where((ev) {
      final contentType = ev['content_type'] as String?;
      final status = ev['status'] as String?;
      final overview = ev['overview'] as String?;
      final aiSummary = ev['ai_summary'] as String?;
      final title = ev['title'] as String?;
      return contentType == 'event' &&
          status != 'pending' && status != 'error' &&
          ((overview != null && overview.trim().isNotEmpty) || (aiSummary != null && aiSummary.trim().isNotEmpty)) &&
          title != null && !title.contains('孤儿视频恢复');
    }).toList()
      ..sort((a, b) => ((b['created_at'] as String?) ?? '').compareTo((a['created_at'] as String?) ?? ''));

    final searchText = _eventsSearchCtrl.text.trim().toLowerCase();
    final filtered = searchText.isEmpty
        ? manualEvents
        : manualEvents.where((ev) => ((ev['title'] as String?) ?? '').toLowerCase().contains(searchText)).toList();

    final selectedCount = _manualSelectedIds.length;

    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Text('手动选择关联文档，起个临时标题，AI 会帮你优化',
          style: TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
      const SizedBox(height: 16),
      Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        const Text('专题标题（可选，后续 AI 可帮你优化）', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        const SizedBox(height: 6),
        TextField(
          controller: _manualTitleCtrl,
          style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14),
          decoration: InputDecoration(
            hintText: '例如：伊朗与中东地缘博弈',
            hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 14),
            filled: true, fillColor: AppTheme.background,
            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
            enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
            focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: AppTheme.emerald.withOpacity(0.5))),
          ),
        ),
      ]),
      const SizedBox(height: 16),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        const Text('选择关联文档（至少2条）', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        Text(_eventsLoading ? '加载中...' : '$selectedCount / ${manualEvents.length} 条',
            style: TextStyle(color: AppTheme.textMuted.withOpacity(0.6), fontSize: 10)),
      ]),
      const SizedBox(height: 6),
      TextField(
        controller: _eventsSearchCtrl,
        style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14),
        decoration: InputDecoration(
          hintText: '🔍 搜索文档标题...',
          hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 14),
          filled: true, fillColor: AppTheme.background,
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide(color: AppTheme.emerald.withOpacity(0.5))),
        ),
      ),
      const SizedBox(height: 8),
      Container(
        constraints: const BoxConstraints(maxHeight: 300),
        decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(8), border: Border.all(color: AppTheme.border)),
        child: _eventsLoading
            ? const Center(child: Padding(padding: EdgeInsets.all(32),
                child: CircularProgressIndicator(color: AppTheme.textMuted, strokeWidth: 2)))
            : filtered.isEmpty
                ? const Center(child: Padding(padding: EdgeInsets.all(32),
                    child: Text('无匹配文档', style: TextStyle(color: AppTheme.textMuted, fontSize: 12))))
                : ListView(
                    shrinkWrap: true, padding: const EdgeInsets.all(8),
                    children: filtered.map((ev) {
                      final evId = (ev['id'] as dynamic)?.toString() ?? '';
                      final title = (ev['title'] as String?) ?? '';
                      final topic = ev['topic'] as String?;
                      final createdAt = (ev['created_at'] as String?) ?? '';
                      final checked = _manualSelectedIds.contains(evId);
                      String formattedDate = '';
                      if (createdAt.length >= 16) {
                        final month = createdAt.substring(5, 7);
                        final day = createdAt.substring(8, 10);
                        final hourRaw = int.tryParse(createdAt.substring(11, 13)) ?? 0;
                        final hour = (hourRaw + 8) % 24;
                        final minute = createdAt.substring(14, 16);
                        formattedDate = '$month/$day ${hour.toString().padLeft(2, '0')}:$minute';
                      }
                      final topicColor = topicColorMap[topic] ?? AppTheme.textMuted;

                      return Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: InkWell(
                          onTap: () => _toggleManualEvent(evId),
                          borderRadius: BorderRadius.circular(8),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            decoration: BoxDecoration(
                              color: checked ? AppTheme.emerald.withOpacity(0.1) : null,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: checked ? AppTheme.emerald.withOpacity(0.2) : Colors.transparent),
                            ),
                            child: Row(children: [
                              SizedBox(
                                width: 18, height: 18,
                                child: Checkbox(
                                  value: checked, onChanged: (_) => _toggleManualEvent(evId),
                                  activeColor: AppTheme.emerald, side: const BorderSide(color: AppTheme.border),
                                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                  visualDensity: VisualDensity.compact,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(child: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12))),
                              if (formattedDate.isNotEmpty) ...[
                                const SizedBox(width: 8),
                                SizedBox(width: 58,
                                  child: Text(formattedDate, textAlign: TextAlign.right,
                                      style: TextStyle(color: AppTheme.textMuted.withOpacity(0.5), fontSize: 9, fontFamily: 'monospace'))),
                              ],
                              if (topic != null) ...[
                                const SizedBox(width: 8),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: topicColor.withOpacity(0.15),
                                    borderRadius: BorderRadius.circular(4),
                                    border: Border.all(color: topicColor.withOpacity(0.2)),
                                  ),
                                  child: Text(topic, style: TextStyle(color: topicColor, fontSize: 9)),
                                ),
                              ],
                            ]),
                          ),
                        ),
                      );
                    }).toList(),
                  ),
      ),
      const SizedBox(height: 12),
      Divider(color: AppTheme.border, height: 1),
      const SizedBox(height: 12),
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text('已选 $selectedCount 条${selectedCount < 2 ? '（至少需要2条）' : ''}',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        _actionButton(
          label: '创建专题', icon: Icons.add, color: AppTheme.emerald,
          enabled: selectedCount >= 2 && _manualTitleCtrl.text.trim().isNotEmpty,
          onTap: _handleManualCreate,
        ),
      ]),
      const SizedBox(height: 12),
      InkWell(
        onTap: () => setState(() => _mode = DiscoveryMode.choose),
        child: const Text('← 返回选择', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ),
    ]);
  }

  // ── Manual suggest mode ──
  Widget _buildManualSuggestMode() {
    return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        const Icon(Icons.check, color: AppTheme.emerald, size: 16),
        const SizedBox(width: 8),
        const Text('专题已创建：', style: TextStyle(color: AppTheme.textSecondary, fontSize: 14)),
        Flexible(child: Text(_manualCreatedName,
            style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500))),
      ]),
      const SizedBox(height: 16),
      Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.border)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Row(children: [
            Icon(Icons.draw_outlined, color: AppTheme.emerald, size: 14),
            SizedBox(width: 8),
            Text('AI 分析所选文档后的建议', style: TextStyle(color: AppTheme.textSecondary, fontSize: 14)),
          ]),
          const SizedBox(height: 12),
          if (_suggesting)
            const Row(children: [
              SizedBox(width: 18, height: 18, child: CircularProgressIndicator(color: AppTheme.emerald, strokeWidth: 2)),
              SizedBox(width: 12),
              Text('正在分析文档内容，生成建议名称...', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
            ])
          else if (_suggestError.isNotEmpty) ...[
            Text(_suggestError, style: const TextStyle(color: AppTheme.error, fontSize: 12)),
            const SizedBox(height: 8),
            InkWell(
              onTap: () => _handleSuggestName(),
              child: const Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.refresh, color: AppTheme.emerald, size: 12),
                SizedBox(width: 4),
                Text('重试', style: TextStyle(color: AppTheme.emerald, fontSize: 12)),
              ]),
            ),
          ]
          else if (_suggestedName.isNotEmpty) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.emerald.withOpacity(0.05),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.emerald.withOpacity(0.15)),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('AI 建议标题', style: TextStyle(color: AppTheme.emerald.withOpacity(0.7), fontSize: 10, letterSpacing: 1)),
                const SizedBox(height: 4),
                Text(_suggestedName, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w500)),
                if (_suggestedDescription.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('AI 建议副标题', style: TextStyle(color: AppTheme.emerald.withOpacity(0.7), fontSize: 10, letterSpacing: 1)),
                  const SizedBox(height: 4),
                  Text(_suggestedDescription, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
                ],
              ]),
            ),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                child: _actionButton(
                  label: '采用此名称和副标题', icon: _adopting ? null : Icons.check,
                  color: AppTheme.emerald, enabled: !_adopting,
                  onTap: _handleAdoptSuggestion, loading: _adopting,
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                onPressed: () => setState(() { _suggestedName = ''; _suggestedDescription = ''; }),
                child: const Text('保留原名', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
              ),
            ]),
            const SizedBox(height: 8),
            InkWell(
              onTap: () => _handleSuggestName(),
              child: const Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.refresh, color: AppTheme.textMuted, size: 10),
                SizedBox(width: 4),
                Text('重新生成建议', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
              ]),
            ),
          ],
        ]),
      ),
      const SizedBox(height: 16),
      Row(children: [
        InkWell(
          onTap: () {
            if (_manualCreatedId.isNotEmpty) {
              context.go('/series/$_manualCreatedId');
              Navigator.of(context, rootNavigator: true).pop();
            }
          },
          child: const Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.open_in_new, color: AppTheme.emerald, size: 12),
            SizedBox(width: 4),
            Text('查看专题详情', style: TextStyle(color: AppTheme.emerald, fontSize: 12)),
          ]),
        ),
        const SizedBox(width: 16),
        InkWell(
          onTap: () { _closeDiscovery(); Navigator.of(context, rootNavigator: true).pop(); },
          child: const Text('完成', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
        ),
      ]),
    ]);
  }

  // ═══════════════════════════════════════════
  // Shared widgets
  // ═══════════════════════════════════════════
  Widget _buildLoadingState(String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 48),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const SizedBox(width: 32, height: 32,
              child: CircularProgressIndicator(color: AppTheme.purple, strokeWidth: 2)),
          const SizedBox(height: 16),
          Text(message, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
        ]),
      ),
    );
  }

  Widget _textButton(String label, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
        child: Text(label, style: TextStyle(color: AppTheme.textMuted.withOpacity(0.7), fontSize: 11)),
      ),
    );
  }

  Widget _actionButton({
    required String label, IconData? icon, required Color color,
    required bool enabled, required VoidCallback onTap, bool loading = false,
  }) {
    return InkWell(
      onTap: enabled ? onTap : null,
      borderRadius: BorderRadius.circular(8),
      child: Opacity(
        opacity: enabled ? 1.0 : 0.4,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: color.withOpacity(0.3)),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (loading)
              const SizedBox(width: 14, height: 14,
                  child: CircularProgressIndicator(color: AppTheme.emerald, strokeWidth: 2))
            else if (icon != null) ...[
              Icon(icon, color: color, size: 14),
              const SizedBox(width: 6),
            ],
            Text(label, style: TextStyle(color: color, fontSize: 14, fontWeight: FontWeight.w500)),
          ]),
        ),
      ),
    );
  }
}
