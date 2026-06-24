import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../../theme/app_theme.dart';
import '../../services/api_client.dart';

// ── Constants from parent ──
const Map<String, Color> _ctColors = {
  '原材料': Color(0xFFF59E0B),
  '中间品': Color(0xFFA855F7),
  '零部件': Color(0xFF3B82F6),
  '终端': Color(0xFF10B981),
};
const Map<String, Color> _ctBg = {
  '原材料': Color(0x26F59E0B),
  '中间品': Color(0x26A855F7),
  '零部件': Color(0x263B82F6),
  '终端': Color(0x2610B981),
};

class ChainDetailPage extends StatefulWidget {
  final String chainName;
  final List<Map<String, dynamic>> chainNodes;
  final String? chainIcon;
  final String flowSummary;
  final List<Map<String, dynamic>> allNodes;

  const ChainDetailPage({
    super.key,
    required this.chainName,
    required this.chainNodes,
    this.chainIcon,
    this.flowSummary = '',
    required this.allNodes,
  });

  @override
  State<ChainDetailPage> createState() => _ChainDetailPageState();
}

class _ChainDetailPageState extends State<ChainDetailPage> {
  final _api = ApiClient();
  Set<String> _expanded = {};
  Set<String> _sourcesExpanded = {};
  String? _report;
  bool _reportLoading = false;
  String? _reportError;
  bool _reportFromCache = false;
  String _flowSummary = '';
  bool _autoGenSummary = false;

  // Chat
  final List<Map<String, String>> _chatMessages = [];
  final _chatCtrl = TextEditingController();
  bool _chatLoading = false;
  final _scrollCtrl = ScrollController();

  List<Map<String, dynamic>> get _sorted {
    final nodes = List<Map<String, dynamic>>.from(widget.chainNodes);
    nodes.sort((a, b) => (a['sort_order'] as int? ?? 0) - (b['sort_order'] as int? ?? 0));
    return nodes;
  }

  @override
  void initState() {
    super.initState();
    _flowSummary = widget.flowSummary;
    _loadReport();
    if (_flowSummary.isEmpty) _genFlowSummary();
  }

  Future<void> _genFlowSummary() async {
    final nodeInfo = _sorted.map((n) => '[${n['node_type']}]${n['name']}').join(' → ');
    try {
      final data = await _api.chainChat(widget.chainName, '请用2-3句话简述以下产业链节点的流转逻辑，解释为什么节点按此顺序连接：$nodeInfo。只输出摘要，不要序号、不要标题。', []);
      if (data['reply'] != null) {
        setState(() { _flowSummary = data['reply']; _autoGenSummary = true; });
      }
    } catch (_) {}
  }

  Future<void> _loadReport({bool force = false}) async {
    setState(() { _reportLoading = true; _reportError = null; });
    try {
      final data = await _api.getChainReport(widget.chainName, force: force);
      if (data['report'] != null) {
        setState(() {
          _report = data['report'];
          _reportFromCache = data['cached'] == true;
          _reportLoading = false;
        });
      } else {
        setState(() { _reportError = data['error'] ?? '分析失败'; _reportLoading = false; });
      }
    } catch (e) {
      setState(() { _reportError = '$e'; _reportLoading = false; });
    }
  }

  Future<void> _sendMessage() async {
    final msg = _chatCtrl.text.trim();
    if (msg.isEmpty || _chatLoading) return;
    setState(() { _chatMessages.add({'role': 'user', 'content': msg}); _chatCtrl.clear(); _chatLoading = true; });
    try {
      final data = await _api.chainChat(widget.chainName, msg, _chatMessages.where((m) => m['role'] != 'user' || m != _chatMessages.last).toList());
      if (data['reply'] != null) {
        setState(() => _chatMessages.add({'role': 'assistant', 'content': data['reply'] as String}));
      } else {
        setState(() => _chatMessages.add({'role': 'assistant', 'content': '❌ ${data['error'] ?? '请求失败'}'}));
      }
    } catch (e) {
      setState(() => _chatMessages.add({'role': 'assistant', 'content': '❌ $e'}));
    }
    setState(() => _chatLoading = false);
    WidgetsBinding.instance.addPostFrameCallback((_) => _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut));
  }

  String _transitionLabel(String prev, String next) {
    const labels = {
      '原材料-中间品': '提炼/合成', '原材料-零部件': '加工', '原材料-终端': '直接应用', '原材料-原材料': '并列',
      '中间品-中间品': '深加工', '中间品-零部件': '制造', '中间品-终端': '应用', '中间品-原材料': '回用',
      '零部件-终端': '集成', '零部件-零部件': '组装',
    };
    return labels['$prev-$next'] ?? '→';
  }

  Map<String, List<Map<String, dynamic>>> _normalizeShares(dynamic raw) {
    try {
      final data = raw is String ? jsonDecode(raw) : raw;
      if (data is Map && data['groups'] != null) {
        return {
          'production': (data['groups']['production'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [],
          'supply': (data['groups']['supply'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [],
          'demand': (data['groups']['demand'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [],
        };
      }
      if (data is List) return {'production': data.cast<Map<String, dynamic>>(), 'supply': [], 'demand': []};
    } catch (_) {}
    return {'production': [], 'supply': [], 'demand': []};
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(children: [
          // Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            decoration: const BoxDecoration(color: Color(0xFF141518), border: Border(bottom: BorderSide(color: Color(0xFF2A2B30)))),
            child: Row(children: [
              GestureDetector(
                onTap: () => Navigator.pop(context),
                child: const Icon(Icons.arrow_back, size: 18, color: Color(0xFF6B7280)),
              ),
              const SizedBox(width: 12),
              Text(widget.chainName, style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
              const SizedBox(width: 8),
              Text('${_sorted.length}节点', style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
              const Spacer(),
              GestureDetector(
                onTap: () async {
                  try { await _api.collectChain(_sorted.first['id'] as String); } catch (_) {}
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(color: const Color(0xFF38BDF8).withAlpha(26), borderRadius: BorderRadius.circular(6), border: Border.all(color: const Color(0xFF38BDF8).withAlpha(51))),
                  child: const Row(children: [
                    Icon(Icons.search, size: 12, color: Color(0xFF38BDF8)),
                    SizedBox(width: 4),
                    Text('联网采集', style: TextStyle(color: Color(0xFF38BDF8), fontSize: 10, fontWeight: FontWeight.w500)),
                  ]),
                ),
              ),
              const SizedBox(width: 12),
              GestureDetector(
                onTap: () => Navigator.pop(context),
                child: const Icon(Icons.close, size: 18, color: Color(0xFF6B7280)),
              ),
            ]),
          ),
          // Body
          Expanded(child: Column(children: [
            // Top: Flow view
            Flexible(flex: 45, child: _buildFlowView()),
            // Divider
            const Divider(color: Color(0xFF2A2B30), height: 1),
            // Bottom: Report + Chat
            Flexible(flex: 55, child: Row(children: [
              // Left: AI Report
              Expanded(child: _buildReport()),
              // Right: Chat
              Expanded(child: _buildChat()),
            ])),
          ])),
        ]),
      ),
    );
  }

  Widget _buildFlowView() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Flow pills
        Wrap(spacing: 6, runSpacing: 4, children: _sorted.asMap().entries.map((e) {
          final idx = e.key;
          final node = e.value;
          final type = node['node_type'] as String? ?? '';
          final isOpen = _expanded.contains(node['id']);
          final prevType = idx > 0 ? _sorted[idx - 1]['node_type'] as String? ?? '' : '';
          final color = _ctColors[type] ?? const Color(0xFF6B7280);
          final bg = _ctBg[type] ?? Colors.transparent;

          return Row(mainAxisSize: MainAxisSize.min, children: [
            if (idx > 0) Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: Text(_transitionLabel(prevType, type), style: const TextStyle(color: Color(0xFF6B7280), fontSize: 8)),
            ),
            GestureDetector(
              onTap: () => setState(() {
                if (isOpen) { _expanded.remove(node['id']); } else { _expanded = {node['id'] as String}; }
              }),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: isOpen ? color.withAlpha(64) : bg,
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: isOpen ? color.withAlpha(102) : color.withAlpha(51)),
                ),
                child: Text(node['name'] ?? '', style: TextStyle(color: isOpen ? color : color.withAlpha(200), fontSize: 10)),
              ),
            ),
          ]);
        }).toList()),
        // Flow summary
        if (_flowSummary.isNotEmpty) ...[
          const SizedBox(height: 8),
          const Divider(color: Color(0xFF1A1B20)),
          const SizedBox(height: 8),
          Text(_flowSummary, style: TextStyle(color: const Color(0xFFA855F7).withAlpha(200), fontSize: 10, height: 1.5)),
        ],
        // Expanded node cards
        ..._sorted.where((n) => _expanded.contains(n['id'])).map((node) => _buildNodeCard(node)),
      ]),
    );
  }

  Widget _buildNodeCard(Map<String, dynamic> node) {
    final type = node['node_type'] as String? ?? '';
    final groups = _normalizeShares(node['global_shares']);
    final subs = (node['substitutes'] as List<dynamic>?) ?? [];
    final sources = node['data_sources'] as Map<String, dynamic>? ?? {};
    final hasSources = sources.isNotEmpty;

    return Container(
      margin: const EdgeInsets.only(top: 12),
      decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
      child: Column(children: [
        // Header
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: const BoxDecoration(color: Color(0xFF111318), border: Border(bottom: BorderSide(color: Color(0xFF1A1B20)))),
          child: Row(children: [
            Container(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2), decoration: BoxDecoration(color: (_ctBg[type] ?? Colors.transparent), borderRadius: BorderRadius.circular(4), border: Border.all(color: (_ctColors[type] ?? const Color(0xFF6B7280)).withAlpha(102))),
              child: Text(type, style: TextStyle(color: _ctColors[type] ?? Colors.white, fontSize: 9))),
            const SizedBox(width: 8),
            Text(node['name'] ?? '', style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12, fontWeight: FontWeight.w500)),
            const Spacer(),
            GestureDetector(
              onTap: () => setState(() => _expanded.remove(node['id'])),
              child: const Icon(Icons.close, size: 14, color: Color(0xFF6B7280)),
            ),
          ]),
        ),
        // Body
        Padding(
          padding: const EdgeInsets.all(12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (node['description'] != null)
              Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(node['description'], style: const TextStyle(color: Color(0xFF6B7280), fontSize: 11, height: 1.5))),
            // Share groups
            if (groups.values.any((g) => g.isNotEmpty))
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(child: _shareGroupPanel('生产侧', groups['production']!, 'p', const Color(0xFFFBBF24), const Color(0xFFFBBF24), Icons.factory)),
                  const SizedBox(width: 8),
                  Expanded(child: _shareGroupPanel('供给侧', groups['supply']!, 'p_export_global', const Color(0xFF34D399), const Color(0xFF34D399), Icons.local_shipping)),
                  const SizedBox(width: 8),
                  Expanded(child: _shareGroupPanel('需求侧', groups['demand']!, 'd_import_global', const Color(0xFF38BDF8), const Color(0xFF38BDF8), Icons.shopping_cart)),
                ]),
              ),
            // Substitutes
            if (subs.isNotEmpty) ...[
              const Text('替代方案', style: TextStyle(color: Color(0xFF9CA3AF), fontSize: 10, fontWeight: FontWeight.w500)),
              const SizedBox(height: 6),
              ...subs.map((sub) {
                final s = sub is Map<String, dynamic> ? sub : <String, dynamic>{};
                final mat = s['maturity'] as String? ?? '';
                final matColor = mat.contains('商用') ? const Color(0xFF34D399) : mat.contains('中试') ? const Color(0xFFFBBF24) : const Color(0xFF9CA3AF);
                return Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: const Color(0xFF141518), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Text(s['node'] ?? '', style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 11, fontWeight: FontWeight.w500)),
                      const SizedBox(width: 6),
                      if (mat.isNotEmpty) Container(padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2), decoration: BoxDecoration(color: matColor.withAlpha(26), borderRadius: BorderRadius.circular(4)), child: Text(mat, style: TextStyle(color: matColor, fontSize: 8))),
                    ]),
                    if (s['trigger'] != null) ...[
                      const SizedBox(height: 2),
                      Text('触发：${s['trigger']}', style: const TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
                    ],
                    if (s['advantage'] != null || s['bottleneck'] != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Row(children: [
                          if (s['advantage'] != null) Expanded(child: Text('优势：${s['advantage']}', style: const TextStyle(color: Color(0xFF34D399), fontSize: 9))),
                          if (s['bottleneck'] != null) Expanded(child: Text('瓶颈：${s['bottleneck']}', style: const TextStyle(color: Color(0xFFF87171), fontSize: 9))),
                        ]),
                      ),
                  ]),
                );
              }),
            ],
            // Sources
            if (hasSources) ...[
              GestureDetector(
                onTap: () => setState(() {
                  final id = node['id'] as String;
                  if (_sourcesExpanded.contains(id)) { _sourcesExpanded.remove(id); } else { _sourcesExpanded.add(id); }
                }),
                child: Row(children: [
                  const Icon(Icons.storage, size: 10, color: Color(0xFF9CA3AF)),
                  const SizedBox(width: 4),
                  const Text('数据来源', style: TextStyle(color: Color(0xFF9CA3AF), fontSize: 10, fontWeight: FontWeight.w500)),
                  const SizedBox(width: 4),
                  Icon(_sourcesExpanded.contains(node['id']) ? Icons.expand_less : Icons.expand_more, size: 12, color: const Color(0xFF6B7280)),
                ]),
              ),
              if (_sourcesExpanded.contains(node['id'])) ...[
                const SizedBox(height: 4),
                Padding(
                  padding: const EdgeInsets.only(left: 16),
                  child: Column(children: sources.entries.map((e) =>
                    Padding(padding: const EdgeInsets.only(bottom: 2), child: Row(children: [
                      Text('${e.key}：', style: const TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
                      Flexible(child: Text('${e.value}', style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 9))),
                    ])),
                  ).toList()),
                ),
              ],
            ],
          ]),
        ),
      ]),
    );
  }

  Widget _shareGroupPanel(String title, List<Map<String, dynamic>> items, String highlightField, Color accentColor, Color barColor, IconData icon) {
    if (items.isEmpty) return const Text('暂无数据', style: TextStyle(color: Color(0xFF374151), fontSize: 9));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Icon(icon, size: 11, color: accentColor),
        const SizedBox(width: 4),
        Text(title, style: TextStyle(color: accentColor, fontSize: 9, fontWeight: FontWeight.w500)),
      ]),
      const SizedBox(height: 4),
      ...items.map((s) {
        final hl = (s[highlightField] as num?)?.toDouble() ?? 0;
        return Container(
          margin: const EdgeInsets.only(bottom: 4),
          padding: const EdgeInsets.all(6),
          decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(s['c'] as String? ?? '', style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 10, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis)),
              Text('${hl.toStringAsFixed(0)}%', style: TextStyle(color: accentColor, fontSize: 10, fontWeight: FontWeight.w600)),
            ]),
            const SizedBox(height: 4),
            Row(children: [
              Expanded(child: Container(
                height: 4, decoration: BoxDecoration(color: const Color(0xFF2A2B30), borderRadius: BorderRadius.circular(2)),
                child: FractionallySizedBox(
                  alignment: Alignment.centerLeft,
                  widthFactor: (hl / 100).clamp(0.0, 1.0),
                  child: Container(decoration: BoxDecoration(color: barColor, borderRadius: BorderRadius.circular(2))),
                ),
              )),
              const SizedBox(width: 6),
              Text('${hl.toStringAsFixed(0)}%', style: TextStyle(color: accentColor, fontSize: 10, fontWeight: FontWeight.w600)),
            ]),
          ]),
        );
      }),
    ]);
  }

  // ── AI Report ──
  Widget _buildReport() {
    return Container(
      decoration: const BoxDecoration(border: Border(right: BorderSide(color: Color(0xFF2A2B30)))),
      child: Column(children: [
        // Header
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF2A2B30)))),
          child: Row(children: [
            Container(width: 4, height: 12, decoration: BoxDecoration(color: const Color(0xFF34D399), borderRadius: BorderRadius.circular(2))),
            const SizedBox(width: 8),
            const Text('AI 产业链分析', style: TextStyle(color: Color(0xFF34D399), fontSize: 11, fontWeight: FontWeight.w500)),
            if (_reportFromCache) ...[
              const SizedBox(width: 8),
              const Text('（缓存）', style: TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
            ],
            const Spacer(),
            GestureDetector(
              onTap: _reportLoading ? null : () => _loadReport(force: true),
              child: Row(children: [
                const Icon(Icons.auto_awesome, size: 10, color: Color(0xFF6B7280)),
                const SizedBox(width: 4),
                Text('重新分析', style: TextStyle(color: _reportLoading ? const Color(0xFF374151) : const Color(0xFF6B7280), fontSize: 10)),
              ]),
            ),
          ]),
        ),
        // Content
        Expanded(
          child: _reportLoading
              ? const Center(child: Row(mainAxisSize: MainAxisSize.min, children: [
                  SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF6B7280))),
                  SizedBox(width: 8),
                  Text('正在生成分析报告...', style: TextStyle(color: Color(0xFF6B7280), fontSize: 12)),
                ]))
              : _reportError != null
                  ? Center(child: Text(_reportError!, style: const TextStyle(color: Color(0xFFF87171), fontSize: 12)))
                  : _report != null
                      ? SingleChildScrollView(padding: const EdgeInsets.all(16), child: MarkdownBody(
                          data: _report!.replaceAll(RegExp(r'^好的，[^。\n]+。\n\n'), '').replaceAll(RegExp(r'^以下为[^。]*报告[^。]*[。\n]\n*'), ''),
                          styleSheet: MarkdownStyleSheet(
                            p: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 12, height: 1.6),
                            h2: const TextStyle(color: Color(0xFFA855F7), fontSize: 13, fontWeight: FontWeight.w600),
                            strong: const TextStyle(color: Color(0xFFE5E7EB), fontWeight: FontWeight.w600),
                            listBullet: const TextStyle(color: Color(0xFF6B7280)),
                          ),
                        ))
                      : const Center(child: Text('暂无分析报告', style: TextStyle(color: Color(0xFF6B7280), fontSize: 12))),
        ),
      ]),
    );
  }

  // ── Chat ──
  Widget _buildChat() {
    return Column(children: [
      // Header
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF2A2B30)))),
        child: Row(children: [
          const Icon(Icons.chat_bubble_outline, size: 14, color: Color(0xFFA855F7)),
          const SizedBox(width: 8),
          const Text('智能答疑', style: TextStyle(color: Color(0xFFA855F7), fontSize: 11, fontWeight: FontWeight.w500)),
          const Spacer(),
          if (_chatMessages.isNotEmpty)
            GestureDetector(
              onTap: () => setState(() => _chatMessages.clear()),
              child: const Row(children: [
                Icon(Icons.cleaning_services, size: 11, color: Color(0xFF6B7280)),
                SizedBox(width: 4),
                Text('清空', style: TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
              ]),
            ),
        ]),
      ),
      // Messages
      Expanded(
        child: _chatMessages.isEmpty
            ? Center(
                child: Text('我是产业链分析助手，可以问我关于${widget.chainName}的全球格局、供应链风险、替代方案等问题',
                    style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10), textAlign: TextAlign.center),
              )
            : ListView.builder(
                controller: _scrollCtrl,
                padding: const EdgeInsets.all(12),
                itemCount: _chatMessages.length + (_chatLoading ? 1 : 0),
                itemBuilder: (ctx, i) {
                  if (i >= _chatMessages.length) {
                    return const Padding(padding: EdgeInsets.all(4), child: SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF6B7280))));
                  }
                  final m = _chatMessages[i];
                  final isUser = m['role'] == 'user';
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
                      children: [
                        Flexible(
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: isUser ? const Color(0xFF3B82F6).withAlpha(26) : const Color(0xFF1A1B20),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: isUser ? const Color(0xFF3B82F6).withAlpha(51) : const Color(0xFF2A2B30)),
                            ),
                            child: MarkdownBody(
                              data: m['content'] ?? '',
                              styleSheet: MarkdownStyleSheet(
                                p: TextStyle(color: isUser ? const Color(0xFFBFDBFE) : const Color(0xFFD1D5DB), fontSize: 11, height: 1.5),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
      ),
      // Input
      Container(
        padding: const EdgeInsets.all(12),
        decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFF2A2B30)))),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: _chatCtrl,
              style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 11),
              decoration: InputDecoration(
                hintText: '问一个关于这条产业链的问题...', hintStyle: const TextStyle(color: Color(0xFF6B7280), fontSize: 11),
                filled: true, fillColor: const Color(0xFF0B0C10),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              ),
              onSubmitted: (_) => _sendMessage(),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: _chatLoading || _chatCtrl.text.trim().isEmpty ? null : _sendMessage,
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: const Color(0xFFA855F7).withAlpha(26), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFFA855F7).withAlpha(51))),
              child: const Icon(Icons.send, size: 14, color: Color(0xFFA855F7)),
            ),
          ),
        ]),
      ),
    ]);
  }
}
