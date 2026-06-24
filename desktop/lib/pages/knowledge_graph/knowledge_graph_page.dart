import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../../theme/app_theme.dart';
import '../../services/api_client.dart';
import '../events/event_detail_page.dart';

// ── Type Colors (matches web) ──
const Map<String, Color> _typeColors = {
  'person': Color(0xFFA855F7),
  'organization': Color(0xFF3B82F6),
  'location': Color(0xFF10B981),
  'concept': Color(0xFFF59E0B),
  'event': Color(0xFFEF4444),
  'theory': Color(0xFFEC4899),
  'book': Color(0xFF6366F1),
  'metric': Color(0xFF06B6D4),
};
const Map<String, String> _typeLabels = {
  'person': '人物', 'organization': '组织', 'location': '地点', 'concept': '概念',
  'event': '事件', 'theory': '理论', 'book': '书籍', 'metric': '指标',
};
const Map<String, String> _relationLabels = {
  'claims': '主张', 'refutes': '反驳', 'extends': '继承', 'causes': '导致',
  'belongs_to': '属于', 'contrasts': '对比', 'cites': '引用', 'synergizes': '协同',
};

class KnowledgeGraphPage extends StatefulWidget {
  const KnowledgeGraphPage({super.key});

  @override
  State<KnowledgeGraphPage> createState() => _KnowledgeGraphPageState();
}

class _KnowledgeGraphPageState extends State<KnowledgeGraphPage> {
  final _api = ApiClient();
  WebViewController? _webCtrl;
  bool _loading = true;
  List<Map<String, dynamic>> _nodes = [];
  List<Map<String, dynamic>> _edges = [];
  String? _selectedId;
  Map<String, dynamic>? _entityDetail;
  bool _detailLoading = false;
  String? _insight;
  bool _insightLoading = false;
  String? _insightError;
  Map<String, dynamic>? _previewEvent;
  bool _previewLoading = false;
  bool _fullscreen = false;
  final _searchCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadGraph();
  }

  Future<void> _loadGraph() async {
    setState(() => _loading = true);
    try {
      final data = await _api.getKnowledgeGraph();
      final nodes = (data['nodes'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
      final edges = (data['edges'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
      setState(() {
        _nodes = nodes;
        _edges = edges;
        _loading = false;
      });
      if (_webCtrl != null) {
        _renderGraph();
      }
    } catch (_) {
      setState(() => _loading = false);
    }
  }

  void _renderGraph() {
    if (_nodes.isEmpty || _webCtrl == null) return;
    final nodesJson = jsonEncode(_nodes);
    final edgesJson = jsonEncode(_edges);
    final typeColorsJson = jsonEncode(_typeColors.map((k, v) => MapEntry(k, '#${v.value.toRadixString(16).padLeft(8, '0')}')));
    final relationLabelsJson = jsonEncode(_relationLabels);
    _webCtrl!.runJavaScript('''
      if (window.renderGraph) { window.renderGraph($nodesJson, $edgesJson, $typeColorsJson, $relationLabelsJson); }
    ''');
  }

  Future<void> _loadEntityDetail(String id) async {
    setState(() { _detailLoading = true; _entityDetail = null; _insight = null; _insightError = null; });
    try {
      final data = await _api.getEntityDetail(id);
      setState(() { _entityDetail = data; _detailLoading = false; });
    } catch (_) {
      setState(() => _detailLoading = false);
    }
  }

  Future<void> _loadInsight() async {
    if (_selectedId == null) return;
    setState(() { _insightLoading = true; _insightError = null; _insight = null; });
    try {
      final data = await _api.getEntityInsight(_selectedId!);
      setState(() { _insight = data['insight'] as String?; _insightLoading = false; });
    } catch (e) {
      setState(() { _insightError = '生成失败'; _insightLoading = false; });
    }
  }

  Future<void> _openPreview(String eventId) async {
    setState(() { _previewLoading = true; _previewEvent = null; });
    try {
      final data = await _api.getEvent(int.parse(eventId));
      setState(() { _previewEvent = data; _previewLoading = false; });
    } catch (_) {
      setState(() { _previewLoading = false; });
    }
  }

  void _handleSearch() {
    final q = _searchCtrl.text.trim();
    if (q.isEmpty || _webCtrl == null) return;
    _webCtrl!.runJavaScript('window.searchNode("$q");');
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  // ── Build vis-network HTML ──
  String _buildGraphHtml() {
    return '''
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#111318}
#graph{width:100%;height:100%}
</style>
<script src="https://unpkg.com/vis-network@9.1.6/dist/vis-network.min.js"></script>
<script src="https://unpkg.com/vis-data@7.1.9/standalone/umd/vis-data.min.js"></script>
</head><body>
<div id="graph"></div>
<script>
var network = null, allNodes = [];
window.renderGraph = function(nodes, edges, typeColors, relationLabels) {
  allNodes = nodes;
  var dsNodes = new vis.DataSet(nodes.map(function(n) {
    return {
      id: n.id, label: n.name,
      color: { background: typeColors[n.type] || '#6b7280', border: '#1a1b20' },
      font: { color: '#e5e7eb', size: 12 },
      size: Math.max(10, Math.min(30, 8 + Math.log2((n.relation_count||0) + 1) * 5)),
      borderWidth: 2, shape: 'dot'
    };
  }));
  var dsEdges = new vis.DataSet(edges.map(function(e) {
    return {
      id: e.id, from: e.source, to: e.target,
      color: { color: '#4b5563', highlight: '#a855f7' },
      width: Math.max(1, Math.min(4, (e.weight||0) * 2)),
      smooth: { type: 'continuous' },
      title: relationLabels[e.type] || e.type
    };
  }));
  if (network) network.destroy();
  network = new vis.Network(document.getElementById('graph'), {nodes: dsNodes, edges: dsEdges}, {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: { gravitationalConstant: -50, centralGravity: 0.01, springLength: 150, springConstant: 0.08 },
      stabilization: { iterations: 100 }
    },
    interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
    nodes: { font: { face: 'system-ui, sans-serif' } }
  });
  network.on('click', function(params) {
    if (params.nodes.length > 0) {
      window.flutterChannel.postMessage(JSON.stringify({type:'select', id: params.nodes[0]}));
    } else {
      window.flutterChannel.postMessage(JSON.stringify({type:'deselect'}));
    }
  });
};
window.searchNode = function(q) {
  if (!network) return;
  var match = allNodes.find(function(n) { return n.name.includes(q); });
  if (match) {
    network.selectNodes([match.id]);
    network.focus(match.id, { scale: 1.5, animation: true });
  }
};
</script>
</body></html>''';
  }

  @override
  Widget build(BuildContext context) {
    final containerClass = _fullscreen
        ? Stack(children: [_buildGraphArea(), _buildFullscreenToggle()])
        : _buildGraphArea();

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(children: [
          // Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            decoration: const BoxDecoration(
              color: Color(0xFF0B0C10),
              border: Border(bottom: BorderSide(color: Color(0xFF1A1B20))),
            ),
            child: Row(children: [
              const Text('知识图谱', style: TextStyle(color: AppTheme.textPrimary, fontSize: 18, fontWeight: FontWeight.w600)),
              const Spacer(),
              SizedBox(
                width: 192,
                height: 32,
                child: TextField(
                  controller: _searchCtrl,
                  style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                  decoration: InputDecoration(
                    hintText: '搜索实体...',
                    hintStyle: const TextStyle(color: Color(0xFF6B7280), fontSize: 13),
                    filled: true,
                    fillColor: const Color(0xFF1A1B20),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
                    enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
                    focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFFA855F7))),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    suffixIcon: GestureDetector(onTap: _handleSearch, child: const Icon(Icons.search, size: 16, color: Color(0xFF6B7280))),
                  ),
                  onSubmitted: (_) => _handleSearch(),
                ),
              ),
              const SizedBox(width: 12),
              GestureDetector(
                onTap: () => setState(() => _fullscreen = !_fullscreen),
                child: Icon(_fullscreen ? Icons.fullscreen_exit : Icons.fullscreen, size: 20, color: const Color(0xFF6B7280)),
              ),
            ]),
          ),
          // Main area
          Expanded(
            child: Row(children: [
              // Graph canvas
              Expanded(child: containerClass),
              // Entity detail panel
              if (_selectedId != null) _buildDetailPanel(),
            ]),
          ),
          // Preview modal
          if (_previewEvent != null) _buildPreviewModal(),
          if (_previewLoading) _buildOverlay(),
        ]),
      ),
    );
  }

  WebViewController get _controller {
    _webCtrl ??= _createController();
    return _webCtrl!;
  }

  WebViewController _createController() {
    final ctrl = WebViewController();
    ctrl.setJavaScriptMode(JavaScriptMode.unrestricted);
    ctrl.addJavaScriptChannel('flutterChannel', onMessageReceived: (msg) {
      final data = jsonDecode(msg.message);
      if (data['type'] == 'select') {
        _selectedId = data['id'];
        _loadEntityDetail(_selectedId!);
      } else {
        setState(() { _selectedId = null; _entityDetail = null; });
      }
    });
    ctrl.setNavigationDelegate(NavigationDelegate(
      onPageFinished: (_) {
        if (_nodes.isNotEmpty) _renderGraph();
      },
    ));
    ctrl.loadHtmlString(_buildGraphHtml());
    return ctrl;
  }

  Widget _buildGraphArea() {
    return Stack(children: [
      if (_loading)
        const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7))),
      GestureDetector(
        onTap: () {}, // absorb taps to prevent webview issues
        child: WebViewWidget(controller: _controller),
      ),
      // Legend
      Positioned(
        bottom: 12, left: 12,
        child: Wrap(
          spacing: 4, runSpacing: 4,
          children: _typeColors.entries.map((e) => Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(color: const Color(0xFF1A1B20).withAlpha(230), borderRadius: BorderRadius.circular(4)),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Container(width: 8, height: 8, decoration: BoxDecoration(color: e.value, shape: BoxShape.circle)),
              const SizedBox(width: 4),
              Text(_typeLabels[e.key] ?? e.key, style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 9)),
            ]),
          )).toList(),
        ),
      ),
    ]);
  }

  Widget _buildFullscreenToggle() {
    return Positioned(
      top: 12, right: 12,
      child: GestureDetector(
        onTap: () => setState(() => _fullscreen = false),
        child: const Icon(Icons.fullscreen_exit, size: 20, color: Color(0xFF6B7280)),
      ),
    );
  }

  Widget _buildDetailPanel() {
    return Container(
      width: 480,
      decoration: const BoxDecoration(
        color: Color(0xFF111318),
        border: Border(left: BorderSide(color: Color(0xFF1A1B20))),
      ),
      child: _detailLoading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7)))
          : _entityDetail == null
              ? const Center(child: Text('加载失败', style: TextStyle(color: Color(0xFF6B7280), fontSize: 13)))
              : _EntityPanel(
                  detail: _entityDetail!,
                  onClose: () => setState(() { _selectedId = null; _entityDetail = null; }),
                  onEventClick: _openPreview,
                  onLoadInsight: _loadInsight,
                  insight: _insight,
                  insightLoading: _insightLoading,
                  insightError: _insightError,
                ),
    );
  }

  Widget _buildPreviewModal() {
    final ev = _previewEvent!;
    return Stack(children: [
      GestureDetector(
        onTap: () => setState(() => _previewEvent = null),
        child: Container(color: Colors.black.withAlpha(179)),
      ),
      Center(child: GestureDetector(
        onTap: () {},
        child: Container(
          width: 672,
          constraints: const BoxConstraints(maxHeight: 600),
          decoration: BoxDecoration(color: const Color(0xFF111318), borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFF2A2B30))),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF1A1B20)))),
              child: Row(children: [
                Expanded(child: Text(ev['title'] ?? '', style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis)),
                GestureDetector(onTap: () => setState(() => _previewEvent = null), child: const Icon(Icons.close, size: 18, color: Color(0xFF6B7280))),
              ]),
            ),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  if (ev['overview'] != null) ...[
                    _sectionLabel('内容概述', const Color(0xFFA855F7)),
                    const SizedBox(height: 4),
                    Text(ev['overview'], style: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 13, height: 1.6)),
                  ],
                  if (ev['ai_summary'] != null) ...[
                    SizedBox(height: ev['overview'] != null ? 16 : 0),
                    if (ev['overview'] != null) _sectionLabel('AI 深度总结', const Color(0xFFF59E0B)),
                    const SizedBox(height: 4),
                    Text(ev['ai_summary'], style: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 13, height: 1.6)),
                  ],
                  if (ev['overview'] == null && ev['ai_summary'] == null && ev['raw_summary'] != null) ...[
                    _sectionLabel('转写内容', const Color(0xFF9CA3AF)),
                    const SizedBox(height: 4),
                    Text((ev['raw_summary'] as String).length > 2000 ? (ev['raw_summary'] as String).substring(0, 2000) : ev['raw_summary'],
                        style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 13, height: 1.6)),
                  ],
                  const SizedBox(height: 16),
                  const Divider(color: Color(0xFF1A1B20)),
                  const SizedBox(height: 8),
                  Text('来源: ${ev['source_id'] ?? '—'}  ·  状态: ${ev['status'] ?? '—'}  ·  主题: ${ev['topic'] ?? '—'}',
                      style: const TextStyle(color: Color(0xFF6B7280), fontSize: 11)),
                ]),
              ),
            ),
          ]),
        ),
      )),
    ]);
  }

  Widget _sectionLabel(String text, Color color) {
    return Row(children: [
      Container(width: 4, height: 16, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
      const SizedBox(width: 8),
      Text(text, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w500)),
    ]);
  }

  Widget _buildOverlay() {
    return Container(
      color: Colors.black.withAlpha(128),
      child: const Center(child: CircularProgressIndicator(color: Color(0xFFA855F7))),
    );
  }
}

class _EntityPanel extends StatelessWidget {
  final Map<String, dynamic> detail;
  final VoidCallback onClose;
  final Future<void> Function(String id) onEventClick;
  final VoidCallback onLoadInsight;
  final String? insight;
  final bool insightLoading;
  final String? insightError;

  const _EntityPanel({
    required this.detail,
    required this.onClose,
    required this.onEventClick,
    required this.onLoadInsight,
    this.insight,
    this.insightLoading = false,
    this.insightError,
  });

  @override
  Widget build(BuildContext context) {
    final e = detail['entity'] as Map<String, dynamic>? ?? {};
    final events = (detail['events'] as List<dynamic>?) ?? [];
    final related = (detail['related_entities'] as List<dynamic>?) ?? [];
    final type = e['type'] as String? ?? '';
    final typeColor = _typeColors[type] ?? const Color(0xFF6B7280);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Header
        Row(children: [
          Container(width: 12, height: 12, decoration: BoxDecoration(color: typeColor, shape: BoxShape.circle)),
          const SizedBox(width: 8),
          Text(_typeLabels[type] ?? type, style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 12)),
          const Spacer(),
          GestureDetector(onTap: onClose, child: const Icon(Icons.close, size: 16, color: Color(0xFF6B7280))),
        ]),
        const SizedBox(height: 12),
        Text(e['name'] ?? '', style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
        if (e['category'] != null) ...[
          const SizedBox(height: 6),
          Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2), decoration: BoxDecoration(color: const Color(0xFFA855F7).withAlpha(26), borderRadius: BorderRadius.circular(4)),
            child: Text(e['category'], style: const TextStyle(color: Color(0xFFA855F7), fontSize: 10))),
        ],
        if (e['summary'] != null) ...[
          const SizedBox(height: 12),
          Text(e['summary'], style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 13)),
        ],
        const SizedBox(height: 12),
        Text('关联 ${e['event_count'] ?? 0} 条内容', style: const TextStyle(color: Color(0xFF6B7280), fontSize: 12)),

        // Related entities
        if (related.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('关联实体 (${related.length})', style: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 12, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          ...related.take(15).map((r) {
            final rt = r['type'] as String? ?? '';
            return Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(children: [
                Container(width: 8, height: 8, decoration: BoxDecoration(color: _typeColors[rt] ?? const Color(0xFF6B7280), shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Expanded(child: Text(r['name'] ?? '', style: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 12), overflow: TextOverflow.ellipsis)),
                Text('${_relationLabels[r['relation_type'] as String?] ?? r['relation_type'] ?? ''}${r['direction'] == 'in' ? ' ←' : ' →'}',
                    style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
              ]),
            );
          }),
        ],

        // Related events
        if (events.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('关联内容 (${events.length})', style: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 12, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          ...events.map((ev) => GestureDetector(
            onTap: () => onEventClick(ev['id']?.toString() ?? ''),
            child: Container(
              margin: const EdgeInsets.only(bottom: 4),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: const Color(0xFF1A1B20), borderRadius: BorderRadius.circular(6)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(ev['title'] ?? '', style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
                if (ev['overview'] != null) ...[
                  const SizedBox(height: 4),
                  Text(ev['overview'], style: const TextStyle(color: Color(0xFF6B7280), fontSize: 12), maxLines: 2, overflow: TextOverflow.ellipsis),
                ],
              ]),
            ),
          )),
        ],

        if (events.isEmpty && related.isEmpty)
          const Text('暂无关联内容', style: TextStyle(color: Color(0xFF6B7280), fontSize: 12)),

        // Insight section
        const SizedBox(height: 20),
        const Divider(color: Color(0xFF1A1B20)),
        const SizedBox(height: 16),
        if (insight == null && !insightLoading && insightError == null)
          GestureDetector(
            onTap: onLoadInsight,
            child: Container(
              width: double.infinity, padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: const Color(0xFFA855F7).withAlpha(26), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFFA855F7).withAlpha(51))),
              child: const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(Icons.auto_awesome, size: 14, color: Color(0xFFA855F7)),
                SizedBox(width: 8),
                Text('深度分析', style: TextStyle(color: Color(0xFFA855F7), fontSize: 14, fontWeight: FontWeight.w500)),
              ]),
            ),
          ),
        if (insightLoading)
          const Center(child: Padding(padding: EdgeInsets.all(16), child: Row(mainAxisSize: MainAxisSize.min, children: [
            SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFA855F7))),
            SizedBox(width: 8),
            Text('分析生成中…', style: TextStyle(color: Color(0xFFA855F7), fontSize: 13)),
          ]))),
        if (insightError != null)
          Center(child: Column(children: [
            Text(insightError!, style: const TextStyle(color: Color(0xFFF87171), fontSize: 13)),
            const SizedBox(height: 8),
            GestureDetector(onTap: onLoadInsight, child: const Text('重试', style: TextStyle(color: Color(0xFFA855F7), fontSize: 12))),
          ])),
        if (insight != null)
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(width: 4, height: 16, decoration: BoxDecoration(color: const Color(0xFFA855F7), borderRadius: BorderRadius.circular(2))),
              const SizedBox(width: 8),
              const Text('深度分析', style: TextStyle(color: Color(0xFFE5E7EB), fontSize: 14, fontWeight: FontWeight.w600)),
            ]),
            const SizedBox(height: 8),
            Text(insight!, style: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 13, height: 1.6)),
          ]),
      ]),
    );
  }
}
