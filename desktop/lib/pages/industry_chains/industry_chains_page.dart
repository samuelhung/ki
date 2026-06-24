import 'dart:convert';
import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';
import '../../services/api_client.dart';

// ── Constants ──

const List<String> _typeOptions = ['原材料', '中间品', '零部件', '终端'];

const Map<String, Color> _typeColors = {
  '原材料': Color(0xFFF59E0B),
  '中间品': Color(0xFFA855F7),
  '零部件': Color(0xFF3B82F6),
  '终端': Color(0xFF10B981),
};

Color _typeColorFor(String type) {
  return _typeColors[type] ?? const Color(0xFF6B7280);
}

const Map<String, Color> _typeBg = {
  '原材料': Color(0x26F59E0B),
  '中间品': Color(0x26A855F7),
  '零部件': Color(0x263B82F6),
  '终端': Color(0x2610B981),
};

Color _typeBgFor(String type) {
  return _typeBg[type] ?? Colors.transparent;
}

// ── Helper: get icon + color for chain name ──

class _ChainIconResult {
  final IconData icon;
  final Color color;
  const _ChainIconResult(this.icon, this.color);
}

_ChainIconResult _getChainIcon(String chainName, [String? apiIcon]) {
  const kwMap = <List<String>, _ChainIconResult>{
    ['锂', '电池', '电芯', '储能', '新能源']: _ChainIconResult(Icons.bolt, Color(0xFFFBBF24)),
    ['光伏', '太阳']: _ChainIconResult(Icons.wb_sunny, Color(0xFFFACC15)),
    ['芯片', '半导体', '晶圆', '集成电路']: _ChainIconResult(Icons.memory, Color(0xFF22D3EE)),
    ['石油', '天然气', '煤炭']: _ChainIconResult(Icons.local_fire_department, Color(0xFFFB923C)),
    ['钢铁', '金属', '铝', '铜', '稀土']: _ChainIconResult(Icons.hardware, Color(0xFF9CA3AF)),
    ['纺织', '服装']: _ChainIconResult(Icons.checkroom, Color(0xFF818CF8)),
    ['汽车', '交通', '物流']: _ChainIconResult(Icons.local_shipping, Color(0xFF60A5FA)),
    ['航空', '飞机']: _ChainIconResult(Icons.flight, Color(0xFF38BDF8)),
    ['船', '航运']: _ChainIconResult(Icons.sailing, Color(0xFF60A5FA)),
    ['医疗', '医药', '健康']: _ChainIconResult(Icons.favorite, Color(0xFFFB7185)),
    ['建筑', '建材', '水泥']: _ChainIconResult(Icons.apartment, Color(0xFFFCD34D)),
    ['互联网', '软件', '云', '数据']: _ChainIconResult(Icons.cloud, Color(0xFF38BDF8)),
    ['金融', '银行', '证券']: _ChainIconResult(Icons.attach_money, Color(0xFFFACC15)),
    ['环保', '碳', '绿色']: _ChainIconResult(Icons.eco, Color(0xFF34D399)),
    ['军工', '国防']: _ChainIconResult(Icons.shield, Color(0xFF94A3B8)),
    ['通信', '5g', '5G', '6g', '6G']: _ChainIconResult(Icons.wifi, Color(0xFF2DD4BF)),
    ['农业', '粮食']: _ChainIconResult(Icons.grass, Color(0xFFFBBF24)),
    ['化工', '制药']: _ChainIconResult(Icons.science, Color(0xFF9CA3AF)),
  };

  final lower = chainName.toLowerCase();
  for (final entry in kwMap.entries) {
    if (entry.key.any((kw) => lower.contains(kw.toLowerCase()))) {
      return entry.value;
    }
  }
  return const _ChainIconResult(Icons.link, Color(0xFF9CA3AF));
}

// ── Trade tag ──

class _TradeTag {
  final String label;
  final Color color;
  final Color bg;
  const _TradeTag(this.label, this.color, this.bg);
}

_TradeTag? _getTradeTag(Map<String, dynamic> s) {
  final p = (s['p'] as num?)?.toDouble() ?? 0;
  final ratio = (s['d_import_ratio'] as num?)?.toDouble() ?? 0;
  final expRatio = (s['p_export_ratio'] as num?)?.toDouble() ?? 0;
  final impGlobal = (s['d_import_global'] as num?)?.toDouble() ?? 0;
  if (ratio > 50 || impGlobal > 15) {
    return _TradeTag('严重依赖进口', const Color(0xFFF87171), const Color(0x1AEF4444));
  }
  if (ratio > 30 || impGlobal > 8) {
    return _TradeTag('中度依赖进口', const Color(0xFFFB923C), const Color(0x1AF97316));
  }
  if (expRatio > 50 && p > 20) {
    return _TradeTag('出口导向', const Color(0xFF60A5FA), const Color(0x1A3B82F6));
  }
  if (p > 25 && ratio < 15) {
    return _TradeTag('自给自足', const Color(0xFF34D399), const Color(0x1A10B981));
  }
  if (p > 30) {
    return _TradeTag('全球主产国', const Color(0xFFA78BFA), const Color(0x1A7C3AED));
  }
  return null;
}

// ── Upstream IDs parsing: handles both JSON string and raw List ──

List<String> _parseUpstreamIds(dynamic val) {
  if (val == null) return [];
  if (val is List) return val.map((e) => e.toString()).toList();
  if (val is String) {
    try {
      final decoded = jsonDecode(val);
      if (decoded is List) return decoded.map((e) => e.toString()).toList();
    } catch (_) {}
    return [val];
  }
  return [];
}

// ── Share normalization: handles both grouped and flat formats ──

Map<String, List<Map<String, dynamic>>> _normalizeShares(dynamic raw) {
  try {
    final data = raw is String ? jsonDecode(raw) : raw;
    if (data is Map && data['groups'] != null) {
      return {
        'production': (data['groups']['production'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [],
        'supply': (data['groups']['supply'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [],
        'demand': (data['groups']['demand'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [],
      };
    }
    if (data is List) {
      return {
        'production': data.cast<Map<String, dynamic>>(),
        'supply': [],
        'demand': [],
      };
    }
  } catch (_) {}
  return {'production': [], 'supply': [], 'demand': []};
}

// ══════════════════════════════════════════════════════════════════════
// _HintsReviewDialog — step-through hints review
// ══════════════════════════════════════════════════════════════════════

class _HintsReviewDialog extends StatefulWidget {
  final List<Map<String, dynamic>> hints;
  final VoidCallback onResolved;

  const _HintsReviewDialog({required this.hints, required this.onResolved});

  @override
  State<_HintsReviewDialog> createState() => _HintsReviewDialogState();
}

class _HintsReviewDialogState extends State<_HintsReviewDialog> {
  int _idx = 0;
  bool _resolving = false;
  String _editedValue = '';
  final _api = ApiClient();

  Map<String, dynamic> get _hint => widget.hints[_idx];

  Color get _confidenceColor {
    final conf = (_hint['confidence'] as num?)?.toDouble() ?? 0;
    if (conf >= 0.8) return const Color(0xFF34D399);
    if (conf >= 0.5) return const Color(0xFFFBBF24);
    return const Color(0xFFF87171);
  }

  Future<void> _resolve(String action) async {
    setState(() => _resolving = true);
    try {
      await _api.resolveChainHint(
        _hint['id'] as String? ?? '',
        action,
        editedValue: action == 'accept' ? _editedValue : '',
      );
      if (_idx + 1 < widget.hints.length) {
        setState(() {
          _idx++;
          _editedValue = '';
          _resolving = false;
        });
      } else {
        widget.onResolved();
      }
    } catch (_) {
      setState(() => _resolving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hintName = _hint['node_name'] as String? ?? '';
    final hintChain = _hint['chain'] as String? ?? '';
    final hintConfidence = (_hint['confidence'] as num?)?.toDouble() ?? 0;
    final hintField = _hint['field'] as String? ?? '';
    final hintCurrent = _hint['current_value'] as String? ?? '';
    final hintSuggested = _hint['suggested_value'] as String? ?? '';
    final hintQuote = _hint['source_quote'] as String? ?? '';

    return AlertDialog(
      backgroundColor: const Color(0xFF141518),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: Color(0xFF2A2B30)),
      ),
      contentPadding: EdgeInsets.zero,
      content: SizedBox(
        width: 480,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Header
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              decoration: const BoxDecoration(
                border: Border(bottom: BorderSide(color: Color(0xFF2A2B30))),
              ),
              child: Row(children: [
                const Icon(Icons.notifications, size: 16, color: Color(0xFFFBBF24)),
                const SizedBox(width: 8),
                const Text('数据更新审核',
                    style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
                const SizedBox(width: 8),
                Text('${_idx + 1} / ${widget.hints.length}',
                    style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
                const Spacer(),
                GestureDetector(
                  onTap: () => Navigator.pop(context),
                  child: const Icon(Icons.close, size: 16, color: Color(0xFF6B7280)),
                ),
              ]),
            ),
            // Body
            Padding(
              padding: const EdgeInsets.all(20),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text(hintName,
                      style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12, fontWeight: FontWeight.w500)),
                  const Text(' · ', style: TextStyle(color: Color(0xFF6B7280), fontSize: 12)),
                  Text(hintChain, style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 12)),
                  const Text(' · ', style: TextStyle(color: Color(0xFF6B7280), fontSize: 12)),
                  Text('置信度 ${(hintConfidence * 100).toInt()}%',
                      style: TextStyle(color: _confidenceColor, fontSize: 12, fontWeight: FontWeight.w500)),
                ]),
                const SizedBox(height: 16),
                const Text('更新字段',
                    style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
                const SizedBox(height: 4),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                      color: const Color(0xFF0B0C10),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFF2A2B30))),
                  child: Text(hintField, style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 13)),
                ),
                if (hintCurrent.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  const Text('当前值',
                      style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 4),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                        color: const Color(0xFF0B0C10),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFF2A2B30))),
                    child: Text(hintCurrent,
                        style: const TextStyle(
                            color: Color(0xFF9CA3AF), fontSize: 13, decoration: TextDecoration.lineThrough)),
                  ),
                ],
                const SizedBox(height: 12),
                const Text('建议值',
                    style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
                const SizedBox(height: 4),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                      color: const Color(0xFF0B0C10),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFF34D399).withAlpha(51))),
                  child: TextField(
                    controller: TextEditingController(text: _editedValue.isEmpty ? hintSuggested : _editedValue),
                    onChanged: (v) => _editedValue = v,
                    style: const TextStyle(color: Color(0xFF34D399), fontSize: 13),
                    decoration: const InputDecoration(border: InputBorder.none, isDense: true, contentPadding: EdgeInsets.zero),
                  ),
                ),
                if (hintQuote.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  const Text('原文引用',
                      style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 4),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                        color: const Color(0xFF0B0C10),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFF2A2B30))),
                    child: Text('"$hintQuote"',
                        style: const TextStyle(color: Color(0xFF6B7280), fontSize: 11, fontStyle: FontStyle.italic, height: 1.5)),
                  ),
                ],
              ]),
            ),
            // Footer
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFF2A2B30)))),
              child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                GestureDetector(
                  onTap: _resolving ? null : () => _resolve('reject'),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFEF4444).withAlpha(51))),
                    child: const Row(children: [
                      Icon(Icons.delete, size: 12, color: Color(0xFFF87171)),
                      SizedBox(width: 6),
                      Text('拒绝',
                          style: TextStyle(color: Color(0xFFF87171), fontSize: 12, fontWeight: FontWeight.w500)),
                    ]),
                  ),
                ),
                Row(children: [
                  if (_idx > 0)
                    GestureDetector(
                      onTap: () {
                        setState(() { _idx--; _editedValue = ''; });
                      },
                      child: const Padding(
                        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        child: Text('上一条', style: TextStyle(color: Color(0xFF9CA3AF), fontSize: 12)),
                      ),
                    ),
                  GestureDetector(
                    onTap: _resolving ? null : () => _resolve('accept'),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF34D399).withAlpha(26),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFF34D399).withAlpha(51)),
                      ),
                      child: Row(children: [
                        if (_resolving)
                          const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF34D399)))
                        else
                          const Icon(Icons.check, size: 12, color: Color(0xFF34D399)),
                        const SizedBox(width: 6),
                        const Text('接受',
                            style: TextStyle(color: Color(0xFF34D399), fontSize: 12, fontWeight: FontWeight.w500)),
                      ]),
                    ),
                  ),
                ]),
              ]),
            ),
          ],
        ),
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════════
// _EditDialog — 5-tab node editor (raw Maps throughout)
// ══════════════════════════════════════════════════════════════════════

class _EditDialog extends StatefulWidget {
  final Map<String, dynamic>? node;
  final List<Map<String, dynamic>> allNodes;
  final String? defaultChain;
  final VoidCallback onSaved;

  const _EditDialog({this.node, required this.allNodes, this.defaultChain, required this.onSaved});

  @override
  State<_EditDialog> createState() => _EditDialogState();
}

class _EditDialogState extends State<_EditDialog> {
  final _api = ApiClient();
  late String _tab;
  late Map<String, dynamic> _form;
  bool _saving = false;
  final _aiTextCtrl = TextEditingController();
  bool _aiLoading = false;
  String _aiResult = '';

  bool get _isNew => widget.node == null;

  @override
  void initState() {
    super.initState();
    _tab = 'basic';

    if (widget.node != null) {
      _form = Map<String, dynamic>.from(widget.node!);
      // Flatten grouped shares into flat list for editing
      _form['global_shares'] = _loadSharesForEditing(widget.node!);
      // Parse upstream_ids from either JSON string or List
      _form['upstream_ids'] = _parseUpstreamIds(widget.node!['upstream_ids']);
      // Ensure data_sources is a proper map
      if (_form['data_sources'] is! Map<String, dynamic>) {
        _form['data_sources'] = <String, String>{};
      }
    } else {
      _form = <String, dynamic>{
        'id': '',
        'chain': widget.defaultChain ?? '光伏产业链',
        'name': '',
        'node_type': '原材料',
        'description': '',
        'global_shares': <Map<String, dynamic>>[],
        'substitutes': <Map<String, dynamic>>[],
        'upstream_ids': <String>[],
        'data_sources': <String, String>{},
        'sort_order': 0,
      };
    }
  }

  List<Map<String, dynamic>> _loadSharesForEditing(Map<String, dynamic> node) {
    final raw = node['global_shares'];
    if (raw is List) {
      return (raw).map((e) => Map<String, dynamic>.from(e as Map)).toList();
    }
    final groups = _normalizeShares(raw);
    final all = <Map<String, dynamic>>[];
    for (final g in groups.values) {
      for (final s in g) {
        all.add(Map<String, dynamic>.from(s));
      }
    }
    return all;
  }

  List<Map<String, dynamic>> get _sameChainNodes {
    return widget.allNodes.where((n) => n['chain'] == _form['chain'] && n['id'] != _form['id']).toList();
  }

  // ── helpers to get typed values from _form ──

  List<Map<String, dynamic>> get _formShares => (_form['global_shares'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
  List<Map<String, dynamic>> get _formSubs => (_form['substitutes'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
  List<String> get _formUpstreamIds => (_form['upstream_ids'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [];
  Map<String, String> get _formSources => (_form['data_sources'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v.toString())) ?? {};

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final data = Map<String, dynamic>.from(_form);
      data['upstream_names'] = _sameChainNodes
          .where((n) => _formUpstreamIds.contains(n['id'] as String?))
          .map((n) => n['name'])
          .toList();
      await _api.saveChainNode(data, id: _isNew ? null : _form['id'] as String?);
      widget.onSaved();
    } catch (_) {
    } finally {
      setState(() => _saving = false);
    }
  }

  Future<void> _delete() async {
    if (_isNew) return;
    try {
      await _api.deleteChainNode(_form['id'] as String);
      widget.onSaved();
    } catch (_) {}
  }

  Future<void> _aiUpdate() async {
    final text = _aiTextCtrl.text.trim();
    if (text.isEmpty) return;
    setState(() { _aiLoading = true; _aiResult = ''; });
    try {
      _aiResult = '⚠ AI 提取功能需要通过 API 扩展支持';
    } catch (e) {
      _aiResult = '❌ $e';
    }
    setState(() => _aiLoading = false);
  }

  void _addShare() {
    final shares = List<Map<String, dynamic>>.from(_formShares);
    shares.add(<String, dynamic>{
      'c': '', 'p': 0, 'p_export_global': 0, 'p_export_ratio': 0, 'p_export_national': 0,
      'd': 0, 'd_import_global': 0, 'd_import_ratio': 0, 'd_import_national': 0,
    });
    setState(() { _form['global_shares'] = shares; });
  }

  void _updateShare(int idx, Map<String, dynamic> patch) {
    final shares = List<Map<String, dynamic>>.from(_formShares);
    shares[idx] = Map<String, dynamic>.from(shares[idx])..addAll(patch);
    setState(() { _form['global_shares'] = shares; });
  }

  void _removeShare(int idx) {
    final shares = List<Map<String, dynamic>>.from(_formShares)..removeAt(idx);
    setState(() { _form['global_shares'] = shares; });
  }

  void _addSub() {
    final subs = List<Map<String, dynamic>>.from(_formSubs);
    subs.add(<String, dynamic>{'node': '', 'maturity': '', 'trigger': '', 'advantage': '', 'bottleneck': ''});
    setState(() { _form['substitutes'] = subs; });
  }

  void _updateSub(int idx, Map<String, String?> patch) {
    final subs = List<Map<String, dynamic>>.from(_formSubs);
    final updated = Map<String, dynamic>.from(subs[idx]);
    patch.forEach((k, v) { if (v != null) updated[k] = v; });
    subs[idx] = updated;
    setState(() { _form['substitutes'] = subs; });
  }

  void _removeSub(int idx) {
    final subs = List<Map<String, dynamic>>.from(_formSubs)..removeAt(idx);
    setState(() { _form['substitutes'] = subs; });
  }

  void _addSource() {
    final sources = Map<String, String>.from(_formSources);
    sources[''] = '';
    setState(() { _form['data_sources'] = sources; });
  }

  void _updateSourceKey(String oldKey, String newKey) {
    final sources = Map<String, String>.from(_formSources);
    final val = sources.remove(oldKey) ?? '';
    sources[newKey] = val;
    setState(() { _form['data_sources'] = sources; });
  }

  void _updateSourceVal(String key, String val) {
    final sources = Map<String, String>.from(_formSources);
    sources[key] = val;
    setState(() { _form['data_sources'] = sources; });
  }

  void _removeSource(String key) {
    final sources = Map<String, String>.from(_formSources);
    sources.remove(key);
    setState(() { _form['data_sources'] = sources; });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: const Color(0xFF141518),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: Color(0xFF2A2B30))),
      contentPadding: EdgeInsets.zero,
      content: SizedBox(
        width: 640,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          // Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF2A2B30)))),
            child: Row(children: [
              Text(_isNew ? '新建节点' : '编辑：${_form['name'] ?? ''}',
                  style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
              const Spacer(),
              GestureDetector(
                onTap: () => Navigator.pop(context),
                child: const Icon(Icons.close, size: 16, color: Color(0xFF6B7280)),
              ),
            ]),
          ),
          // Tabs
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF2A2B30)))),
            child: Row(
              children: ['basic', 'shares', 'subs', 'sources', 'ai'].map((t) {
                final labels = {'basic': '基本信息', 'shares': '全球份额', 'subs': '替代方案', 'sources': '数据来源', 'ai': 'AI更新'};
                return GestureDetector(
                  onTap: () => setState(() => _tab = t),
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
                    decoration: BoxDecoration(
                      border: Border(bottom: BorderSide(color: _tab == t ? const Color(0xFFA855F7) : Colors.transparent, width: 2)),
                    ),
                    child: Text(labels[t]!,
                        style: TextStyle(color: _tab == t ? const Color(0xFFA855F7) : const Color(0xFF6B7280), fontSize: 12, fontWeight: FontWeight.w500)),
                  ),
                );
              }).toList(),
            ),
          ),
          // Tab content
          Flexible(
            child: SingleChildScrollView(padding: const EdgeInsets.all(20), child: _buildTabContent()),
          ),
          // Footer
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFF2A2B30)))),
            child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              if (!_isNew)
                GestureDetector(
                  onTap: () {
                    showDialog(
                      context: context,
                      builder: (ctx) => AlertDialog(
                        backgroundColor: const Color(0xFF141518),
                        title: const Text('确认删除', style: TextStyle(color: Colors.white, fontSize: 14)),
                        content: Text('确认删除「${_form['name'] ?? ''}」？此操作不可撤销。',
                            style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 12)),
                        actions: [
                          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消', style: TextStyle(color: Color(0xFF9CA3AF)))),
                          TextButton(
                            onPressed: () { Navigator.pop(ctx); _delete(); },
                            child: const Text('删除', style: TextStyle(color: Color(0xFFF87171))),
                          ),
                        ],
                      ),
                    );
                  },
                  child: const Row(children: [
                    Icon(Icons.delete_outline, size: 12, color: Color(0xFFF87171)),
                    SizedBox(width: 4),
                    Text('删除', style: TextStyle(color: Color(0xFFF87171), fontSize: 12)),
                  ]),
                )
              else
                const SizedBox(),
              Row(children: [
                GestureDetector(
                  onTap: () => Navigator.pop(context),
                  child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    child: Text('取消', style: TextStyle(color: Color(0xFF9CA3AF), fontSize: 12)),
                  ),
                ),
                GestureDetector(
                  onTap: _saving ? null : _save,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFA855F7).withAlpha(26),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFFA855F7).withAlpha(51)),
                    ),
                    child: Row(children: [
                      if (_saving)
                        const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFA78BFA)))
                      else
                        const Icon(Icons.save, size: 14, color: Color(0xFFA78BFA)),
                      const SizedBox(width: 6),
                      const Text('保存', style: TextStyle(color: Color(0xFFA78BFA), fontSize: 12, fontWeight: FontWeight.w500)),
                    ]),
                  ),
                ),
              ]),
            ]),
          ),
        ]),
      ),
    );
  }

  Widget _buildTabContent() {
    switch (_tab) {
      case 'basic': return _buildBasicTab();
      case 'shares': return _buildSharesTab();
      case 'subs': return _buildSubsTab();
      case 'sources': return _buildSourcesTab();
      case 'ai': return _buildAiTab();
      default: return const SizedBox();
    }
  }

  Widget _buildBasicTab() {
    final formName = _form['name'] as String? ?? '';
    final formChain = _form['chain'] as String? ?? '';
    final formNodeType = _form['node_type'] as String? ?? '原材料';
    final formDesc = _form['description'] as String? ?? '';

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('产业链', style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(6), border: Border.all(color: const Color(0xFF2A2B30))),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: formChain,
                dropdownColor: const Color(0xFF141518),
                style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12),
                isExpanded: true,
                items: const ['光伏产业链', '锂电产业链', '芯片产业链', '石油产业链', '钢铁产业链'].map((c) {
                  return DropdownMenuItem(value: c, child: Text(c));
                }).toList(),
                onChanged: (v) {
                  if (v != null) setState(() { _form['chain'] = v; _form['upstream_ids'] = <String>[]; });
                },
              ),
            ),
          ),
        ])),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('类型', style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(6), border: Border.all(color: const Color(0xFF2A2B30))),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: formNodeType,
                dropdownColor: const Color(0xFF141518),
                style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12),
                isExpanded: true,
                items: _typeOptions.map((t) => DropdownMenuItem(value: t, child: Text(t))).toList(),
                onChanged: (v) { if (v != null) setState(() => _form['node_type'] = v); },
              ),
            ),
          ),
        ])),
      ]),
      const SizedBox(height: 12),
      const Text('名称', style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
      const SizedBox(height: 4),
      TextField(
        controller: TextEditingController(text: formName),
        onChanged: (v) => _form['name'] = v,
        style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12),
        decoration: InputDecoration(
          filled: true, fillColor: const Color(0xFF0B0C10),
          contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF7C3AED))),
        ),
      ),
      const SizedBox(height: 12),
      const Text('描述', style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
      const SizedBox(height: 4),
      TextField(
        controller: TextEditingController(text: formDesc),
        onChanged: (v) => _form['description'] = v,
        style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12),
        decoration: InputDecoration(
          filled: true, fillColor: const Color(0xFF0B0C10),
          contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: Color(0xFF7C3AED))),
        ),
      ),
      const SizedBox(height: 12),
      const Text('上游节点（可多选）', style: TextStyle(color: Color(0xFF6B7280), fontSize: 10, fontWeight: FontWeight.w500)),
      const SizedBox(height: 6),
      Wrap(spacing: 6, runSpacing: 6, children: _sameChainNodes.map((n) {
        final nId = n['id'] as String? ?? '';
        final nName = n['name'] as String? ?? '';
        final selected = _formUpstreamIds.contains(nId);
        return GestureDetector(
          onTap: () {
            setState(() {
              final ids = List<String>.from(_formUpstreamIds);
              if (selected) {
                ids.remove(nId);
              } else {
                ids.add(nId);
              }
              _form['upstream_ids'] = ids;
            });
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: selected ? const Color(0xFFA855F7).withAlpha(51) : const Color(0xFF0B0C10),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: selected ? const Color(0xFFA855F7).withAlpha(102) : const Color(0xFF2A2B30)),
            ),
            child: Text(nName,
                style: TextStyle(color: selected ? const Color(0xFFA78BFA) : const Color(0xFF6B7280), fontSize: 10)),
          ),
        );
      }).toList()),
    ]);
  }

  Widget _buildSharesTab() {
    final shares = _formShares;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ...shares.asMap().entries.map((entry) {
        final idx = entry.key;
        final s = entry.value;
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(
                child: TextField(
                  controller: TextEditingController(text: s['c'] as String? ?? ''),
                  onChanged: (v) => _updateShare(idx, {'c': v}),
                  style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12),
                  decoration: const InputDecoration(hintText: '国家/地区', hintStyle: TextStyle(color: Color(0xFF6B7280), fontSize: 12), border: InputBorder.none, isDense: true, contentPadding: EdgeInsets.zero),
                ),
              ),
              GestureDetector(onTap: () => _removeShare(idx), child: const Icon(Icons.close, size: 12, color: Color(0xFF6B7280))),
            ]),
            const SizedBox(height: 8),
            const Text('生产侧', style: TextStyle(color: Color(0xFFFBBF24), fontSize: 9, fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            _shareFieldRow('全球产量', (s['p'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'p': v})),
            _shareFieldRow('出口/全球出口', (s['p_export_global'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'p_export_global': v})),
            _shareFieldRow('出口/产量', (s['p_export_ratio'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'p_export_ratio': v})),
            _shareFieldRow('占本国总出口', (s['p_export_national'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'p_export_national': v})),
            const SizedBox(height: 8),
            const Text('需求侧', style: TextStyle(color: Color(0xFF60A5FA), fontSize: 9, fontWeight: FontWeight.w500)),
            const SizedBox(height: 4),
            _shareFieldRow('全球消费', (s['d'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'d': v})),
            _shareFieldRow('进口/全球进口', (s['d_import_global'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'d_import_global': v})),
            _shareFieldRow('进口/消费', (s['d_import_ratio'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'d_import_ratio': v})),
            _shareFieldRow('占本国总进口', (s['d_import_national'] as num?)?.toDouble() ?? 0, (v) => _updateShare(idx, {'d_import_national': v})),
          ]),
        );
      }),
      GestureDetector(
        onTap: _addShare,
        child: Container(
          width: double.infinity, padding: const EdgeInsets.symmetric(vertical: 6),
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(6), border: Border.all(color: const Color(0xFF2A2B30), strokeAlign: BorderSide.strokeAlignInside)),
          child: const Text('+ 添加国家/地区', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
        ),
      ),
    ]);
  }

  Widget _shareFieldRow(String label, double value, ValueChanged<double> onChanged) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(children: [
        SizedBox(width: 80, child: Text(label, style: const TextStyle(color: Color(0xFF6B7280), fontSize: 9))),
        Expanded(
          child: Container(
            height: 28,
            decoration: BoxDecoration(color: const Color(0xFF1A1B20), borderRadius: BorderRadius.circular(4), border: Border.all(color: const Color(0xFF2A2B30))),
            child: TextField(
              controller: TextEditingController(text: value > 0 ? value.toStringAsFixed(2) : ''),
              onChanged: (v) => onChanged(double.tryParse(v) ?? 0),
              keyboardType: TextInputType.number,
              style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 9),
              decoration: const InputDecoration(border: InputBorder.none, isDense: true, contentPadding: EdgeInsets.symmetric(horizontal: 4)),
            ),
          ),
        ),
        const SizedBox(width: 4),
        const Text('%', style: TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
      ]),
    );
  }

  Widget _buildSubsTab() {
    final subs = _formSubs;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ...subs.asMap().entries.map((entry) {
        final idx = entry.key;
        final sub = entry.value;
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
          child: Column(children: [
            Row(children: [
              Expanded(
                child: TextField(
                  controller: TextEditingController(text: sub['node'] as String? ?? ''),
                  onChanged: (v) => _updateSub(idx, {'node': v}),
                  style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12),
                  decoration: const InputDecoration(hintText: '替代品名称', hintStyle: TextStyle(color: Color(0xFF6B7280), fontSize: 12), border: InputBorder.none, isDense: true, contentPadding: EdgeInsets.zero),
                ),
              ),
              GestureDetector(onTap: () => _removeSub(idx), child: const Icon(Icons.close, size: 12, color: Color(0xFF6B7280))),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: _subFieldRow('成熟度', sub['maturity'] as String? ?? '', (v) => _updateSub(idx, {'maturity': v}))),
              const SizedBox(width: 8),
              Expanded(child: _subFieldRow('触发条件', sub['trigger'] as String? ?? '', (v) => _updateSub(idx, {'trigger': v}))),
            ]),
            const SizedBox(height: 6),
            Row(children: [
              Expanded(child: _subFieldRow('优势', sub['advantage'] as String? ?? '', (v) => _updateSub(idx, {'advantage': v}))),
              const SizedBox(width: 8),
              Expanded(child: _subFieldRow('瓶颈', sub['bottleneck'] as String? ?? '', (v) => _updateSub(idx, {'bottleneck': v}))),
            ]),
          ]),
        );
      }),
      GestureDetector(
        onTap: _addSub,
        child: Container(
          width: double.infinity, padding: const EdgeInsets.symmetric(vertical: 6),
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(6), border: Border.all(color: const Color(0xFF2A2B30), strokeAlign: BorderSide.strokeAlignInside)),
          child: const Text('+ 添加替代方案', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
        ),
      ),
    ]);
  }

  Widget _subFieldRow(String label, String value, ValueChanged<String> onChanged) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
      const SizedBox(height: 2),
      Container(
        height: 28,
        decoration: BoxDecoration(color: const Color(0xFF1A1B20), borderRadius: BorderRadius.circular(4), border: Border.all(color: const Color(0xFF2A2B30))),
        child: TextField(
          controller: TextEditingController(text: value),
          onChanged: onChanged,
          style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 9),
          decoration: const InputDecoration(border: InputBorder.none, isDense: true, contentPadding: EdgeInsets.symmetric(horizontal: 4)),
        ),
      ),
    ]);
  }

  Widget _buildSourcesTab() {
    final sources = _formSources;
    final entries = sources.entries.toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('标注每个数据指标的来源，方便追溯和下次更新。', style: TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
      const SizedBox(height: 12),
      ...entries.asMap().entries.map((e) {
        final kv = e.value;
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(children: [
            Expanded(
              child: TextField(
                controller: TextEditingController(text: kv.key),
                onChanged: (v) => _updateSourceKey(kv.key, v),
                style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 10),
                decoration: InputDecoration(
                  hintText: '指标名', hintStyle: const TextStyle(color: Color(0xFF6B7280), fontSize: 10),
                  filled: true, fillColor: const Color(0xFF0B0C10),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 2,
              child: TextField(
                controller: TextEditingController(text: kv.value),
                onChanged: (v) => _updateSourceVal(kv.key, v),
                style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 10),
                decoration: InputDecoration(
                  hintText: '来源（如 USGS 2025）', hintStyle: const TextStyle(color: Color(0xFF6B7280), fontSize: 10),
                  filled: true, fillColor: const Color(0xFF0B0C10),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
                ),
              ),
            ),
            GestureDetector(onTap: () => _removeSource(kv.key), child: const Icon(Icons.close, size: 12, color: Color(0xFF6B7280))),
          ]),
        );
      }),
      GestureDetector(
        onTap: _addSource,
        child: Container(
          width: double.infinity, padding: const EdgeInsets.symmetric(vertical: 6),
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(6), border: Border.all(color: const Color(0xFF2A2B30), strokeAlign: BorderSide.strokeAlignInside)),
          child: const Text('+ 添加来源条目', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
        ),
      ),
    ]);
  }

  Widget _buildAiTab() {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('粘贴 USGS 报告摘要、行业新闻等文本，AI 将自动提取结构化数据。', style: TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
      const SizedBox(height: 12),
      TextField(
        controller: _aiTextCtrl, maxLines: 6,
        style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12),
        decoration: InputDecoration(
          hintText: '粘贴来源文本...', hintStyle: const TextStyle(color: Color(0xFF6B7280), fontSize: 12),
          filled: true, fillColor: const Color(0xFF0B0C10),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: Color(0xFF2A2B30))),
        ),
      ),
      const SizedBox(height: 12),
      GestureDetector(
        onTap: (_aiLoading || _aiTextCtrl.text.trim().isEmpty) ? null : _aiUpdate,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: const Color(0xFFA855F7).withAlpha(51),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: const Color(0xFFA855F7).withAlpha(77)),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (_aiLoading)
              const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFA78BFA)))
            else
              const Icon(Icons.auto_awesome, size: 14, color: Color(0xFFA78BFA)),
            const SizedBox(width: 6),
            const Text('提取数据', style: TextStyle(color: Color(0xFFA78BFA), fontSize: 12, fontWeight: FontWeight.w500)),
          ]),
        ),
      ),
      if (_aiResult.isNotEmpty) ...[
        const SizedBox(height: 12),
        Container(
          width: double.infinity, padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8)),
          child: Text(_aiResult, style: const TextStyle(color: Color(0xFFD1D5DB), fontSize: 11)),
        ),
      ],
    ]);
  }
}

// ══════════════════════════════════════════════════════════════════════
// _MergeFlowLegendChip
// ══════════════════════════════════════════════════════════════════════

class _MergeFlowLegendChip extends StatelessWidget {
  final String text;
  final Color color;
  const _MergeFlowLegendChip({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(color: color.withAlpha(26), borderRadius: BorderRadius.circular(4)),
      child: Text(text, style: TextStyle(color: color, fontSize: 9)),
    );
  }
}

// ══════════════════════════════════════════════════════════════════════
// IndustryChainsPage — main page (raw Maps everywhere)
// ══════════════════════════════════════════════════════════════════════

class IndustryChainsPage extends StatefulWidget {
  const IndustryChainsPage({super.key});

  @override
  State<IndustryChainsPage> createState() => _IndustryChainsPageState();
}

class _IndustryChainsPageState extends State<IndustryChainsPage> {
  final _api = ApiClient();

  List<Map<String, dynamic>> _nodes = [];
  bool _loading = true;
  Map<String, String> _chainIconMap = {};
  Map<String, String> _chainFlowSummaryMap = {};

  // Hints
  List<Map<String, dynamic>> _hints = [];

  // Suggestions
  List<Map<String, dynamic>> _suggestions = [];
  int _suggestionsCount = 0;

  // Overlap
  List<Map<String, dynamic>> _overlaps = [];
  bool _overlapOpen = false;
  bool _checkingOverlap = false;
  String? _mergingOverlap;
  Map<String, dynamic>? _mergedFlow;

  // View tab
  String _viewTab = 'chains';

  // Collecting state
  String? _collectingNode;
  String? _collectingChain;

  @override
  void initState() {
    super.initState();
    _fetchAll();
  }

  Future<void> _fetchAll() async {
    _fetchData();
    _fetchHints();
    _fetchSuggestions();
  }

  Future<void> _fetchData() async {
    try {
      final results = await Future.wait([_api.getChainNodes(), _api.getChains()]);
      final nd = results[0];
      final ch = results[1];

      // Parse nodes as raw Map<String, dynamic> — no typed classes
      final nodes = (nd['nodes'] as List<dynamic>?)
              ?.map((e) => e as Map<String, dynamic>)
              .toList() ??
          [];

      final iconMap = <String, String>{};
      final summaryMap = <String, String>{};
      (ch['chains'] as List<dynamic>?)?.forEach((c) {
        final cm = c as Map<String, dynamic>;
        final name = cm['chain'] as String? ?? '';
        if (cm['icon'] != null) iconMap[name] = cm['icon'] as String;
        if (cm['flow_summary'] != null) summaryMap[name] = cm['flow_summary'] as String;
      });

      setState(() {
        _nodes = nodes;
        _chainIconMap = iconMap;
        _chainFlowSummaryMap = summaryMap;
        _loading = false;
      });
    } catch (_) {
      setState(() => _loading = false);
    }
  }

  Future<void> _fetchHints() async {
    try {
      final data = await _api.getChainHints(status: 'pending', limit: 50);
      final hints = (data['hints'] as List<dynamic>?)
              ?.map((e) => e as Map<String, dynamic>)
              .toList() ??
          [];
      setState(() => _hints = hints);
    } catch (_) {}
  }

  Future<void> _fetchSuggestions() async {
    try {
      final results = await Future.wait([_api.getChainSuggestions(status: 'pending'), _api.getChainSuggestionsCount()]);
      final data = results[0];
      final cnt = results[1];
      final suggestions = (data['suggestions'] as List<dynamic>?)
              ?.map((e) => e as Map<String, dynamic>)
              .toList() ??
          [];
      setState(() {
        _suggestions = suggestions;
        _suggestionsCount = (cnt['pending'] as int?) ?? 0;
      });
    } catch (_) {}
  }

  Future<void> _handleCollectNode(String nodeId) async {
    setState(() => _collectingNode = nodeId);
    try {
      final d = await _api.collectNode(nodeId);
      if (d['ok'] == true) _fetchData();
    } catch (_) {
    } finally {
      setState(() => _collectingNode = null);
    }
  }

  Future<void> _handleCollectChain(String chainName) async {
    final chainNodes = _chainsMap[chainName] ?? [];
    if (chainNodes.isEmpty) return;
    final refNode = chainNodes.firstWhere((n) {
      final groups = _normalizeShares(n['global_shares']);
      return groups['production']!.isEmpty && groups['supply']!.isEmpty && groups['demand']!.isEmpty;
    }, orElse: () => chainNodes.first);
    setState(() => _collectingChain = chainName);
    try {
      final d = await _api.collectChain(refNode['id'] as String? ?? '');
      if (d['ok'] == true) _fetchData();
    } catch (_) {
    } finally {
      setState(() => _collectingChain = null);
    }
  }

  Map<String, List<Map<String, dynamic>>> get _chainsMap {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final n in _nodes) {
      final chain = n['chain'] as String? ?? '';
      map.putIfAbsent(chain, () => []);
      map[chain]!.add(n);
    }
    return map;
  }

  Future<void> _handleMerge(String chainA, String chainB, String into) async {
    final key = '$chainA|||$chainB|||$into';
    setState(() => _mergingOverlap = key);
    try {
      final d = await _api.mergeChains(chainA, chainB, into);
      if (d['ok'] != true) return;
      setState(() => _mergedFlow = d);
      await _fetchData();
      setState(() { _overlapOpen = false; _overlaps = []; _mergingOverlap = null; });
    } catch (_) {
      setState(() => _mergingOverlap = null);
    }
  }

  Future<void> _checkOverlap() async {
    setState(() => _checkingOverlap = true);
    try {
      final d = await _api.overlapCheckChains();
      setState(() {
        _overlaps = (d['overlaps'] as List<dynamic>?)?.map((e) => e as Map<String, dynamic>).toList() ?? [];
        _overlapOpen = true;
        _checkingOverlap = false;
      });
    } catch (_) {
      setState(() => _checkingOverlap = false);
    }
  }

  void _showHintsReviewDialog() {
    if (_hints.isEmpty) return;
    showDialog(
      context: context,
      builder: (ctx) => _HintsReviewDialog(
        hints: _hints,
        onResolved: () {
          Navigator.pop(ctx);
          _fetchHints();
          _fetchData();
        },
      ),
    );
  }

  void _showEditDialog({Map<String, dynamic>? node, String? defaultChain}) {
    showDialog(
      context: context,
      builder: (ctx) => _EditDialog(
        node: node,
        allNodes: _nodes,
        defaultChain: defaultChain,
        onSaved: () {
          Navigator.pop(ctx);
          _fetchData();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: Color(0xFF6B7280)))
            : SingleChildScrollView(
                padding: const EdgeInsets.all(32),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  _buildHeader(),
                  const SizedBox(height: 8),
                  const Text(
                    '手工录入的产业链节点数据，包含全球份额分布与替代材料判断，为 AI 影响分析提供领域知识',
                    style: TextStyle(color: Color(0xFF6B7280), fontSize: 13),
                  ),
                  const SizedBox(height: 24),
                  if (_hints.isNotEmpty) _buildHintsBanner(),
                  if (_overlapOpen) _buildOverlapResults(),
                  if (_mergedFlow != null) _buildMergedFlowResult(),
                  if (_viewTab == 'chains') _buildChainsGrid() else _buildSuggestionsView(),
                  const SizedBox(height: 32),
                  const Divider(color: Color(0xFF2A2B30)),
                  const SizedBox(height: 24),
                  const Center(
                    child: Text(
                      '数据手工维护 · 8 维贸易指标 · 覆盖锂电、光伏、芯片 · 支持编辑与 AI 辅助更新',
                      style: TextStyle(color: Color(0xFF6B7280), fontSize: 12),
                    ),
                  ),
                ]),
              ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(children: [
      const Icon(Icons.account_tree, size: 24, color: AppTheme.emerald),
      const SizedBox(width: 12),
      const Text('产业链知识底座',
          style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
      const SizedBox(width: 12),
      GestureDetector(
        onTap: () => Navigator.pushNamed(context, '/industry-flow'),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: const Color(0xFFA855F7).withAlpha(26),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: const Color(0xFFA855F7).withAlpha(51)),
          ),
          child: const Text('全景流向图 →',
              style: TextStyle(color: Color(0xFFA78BFA), fontSize: 12, fontWeight: FontWeight.w500)),
        ),
      ),
      const Spacer(),
      // Tab switcher
      Container(
        decoration: BoxDecoration(color: const Color(0xFF1A1B20), borderRadius: BorderRadius.circular(8)),
        padding: const EdgeInsets.all(2),
        child: Row(children: [
          GestureDetector(
            onTap: () => setState(() => _viewTab = 'chains'),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: _viewTab == 'chains' ? const Color(0xFF2A2B30) : Colors.transparent,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text('已有产业链',
                  style: TextStyle(
                      color: _viewTab == 'chains' ? Colors.white : const Color(0xFF6B7280),
                      fontSize: 12,
                      fontWeight: FontWeight.w500)),
            ),
          ),
          GestureDetector(
            onTap: () => setState(() => _viewTab = 'suggestions'),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: _viewTab == 'suggestions' ? const Color(0xFF2A2B30) : Colors.transparent,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(children: [
                Text('建议新建',
                    style: TextStyle(
                        color: _viewTab == 'suggestions' ? Colors.white : const Color(0xFF6B7280),
                        fontSize: 12,
                        fontWeight: FontWeight.w500)),
                if (_suggestionsCount > 0)
                  Container(
                    margin: const EdgeInsets.only(left: 6),
                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                    decoration: const BoxDecoration(color: Color(0xFFA855F7), shape: BoxShape.circle),
                    child: Text('$_suggestionsCount',
                        style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w600)),
                  ),
              ]),
            ),
          ),
        ]),
      ),
      const SizedBox(width: 8),
      GestureDetector(
        onTap: () => _showEditDialog(),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: const Color(0xFF10B981).withAlpha(26),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: const Color(0xFF10B981).withAlpha(51)),
          ),
          child: const Row(children: [
            Icon(Icons.add, size: 12, color: Color(0xFF34D399)),
            SizedBox(width: 4),
            Text('新节点',
                style: TextStyle(color: Color(0xFF34D399), fontSize: 12, fontWeight: FontWeight.w500)),
          ]),
        ),
      ),
      const SizedBox(width: 8),
      GestureDetector(
        onTap: _checkingOverlap ? null : _checkOverlap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: const Color(0xFFF59E0B).withAlpha(26),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: const Color(0xFFF59E0B).withAlpha(51)),
          ),
          child: Row(children: [
            if (_checkingOverlap)
              const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFFFBBF24)))
            else
              const Icon(Icons.call_merge, size: 12, color: Color(0xFFFBBF24)),
            const SizedBox(width: 4),
            const Text('检测重叠',
                style: TextStyle(color: Color(0xFFFBBF24), fontSize: 12, fontWeight: FontWeight.w500)),
          ]),
        ),
      ),
    ]);
  }

  Widget _buildHintsBanner() {
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFF59E0B).withAlpha(13),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFF59E0B).withAlpha(51)),
      ),
      child: Row(children: [
        const Icon(Icons.notifications, size: 20, color: Color(0xFFFBBF24)),
        const SizedBox(width: 16),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('检测到 ${_hints.length} 条产业链数据更新待确认',
                style: const TextStyle(color: Color(0xFFFBBF24), fontSize: 14, fontWeight: FontWeight.w500)),
            const SizedBox(height: 2),
            const Text('从采集内容中自动识别，请审核后决定是否应用',
                style: TextStyle(color: Color(0xFF6B7280), fontSize: 11)),
          ]),
        ),
        GestureDetector(
          onTap: _showHintsReviewDialog,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFFF59E0B).withAlpha(26),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFF59E0B).withAlpha(51)),
            ),
            child: const Text('立即审核',
                style: TextStyle(color: Color(0xFFFBBF24), fontSize: 12, fontWeight: FontWeight.w500)),
          ),
        ),
      ]),
    );
  }

  Widget _buildOverlapResults() {
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _overlaps.isNotEmpty ? const Color(0xFFA855F7).withAlpha(13) : const Color(0xFF6B7280).withAlpha(13),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _overlaps.isNotEmpty ? const Color(0xFFA855F7).withAlpha(51) : const Color(0xFF6B7280).withAlpha(51)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(Icons.call_merge, size: 20, color: _overlaps.isNotEmpty ? const Color(0xFFA78BFA) : const Color(0xFF6B7280)),
        const SizedBox(width: 16),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
              _overlaps.isNotEmpty ? '检测到 ${_overlaps.length} 组产业链重叠' : '未检测到产业链重叠',
              style: TextStyle(
                color: _overlaps.isNotEmpty ? const Color(0xFFA78BFA) : const Color(0xFF9CA3AF),
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            if (_overlaps.isNotEmpty) ...[
              const SizedBox(height: 12),
              ..._overlaps.map((ov) {
                final chainA = ov['chain_a'] as String? ?? '';
                final chainB = ov['chain_b'] as String? ?? '';
                final score = (ov['overlap_score'] as num?)?.toDouble() ?? 0;
                final reason = ov['reason'] as String? ?? '';
                final fuzzyShared = (ov['fuzzy_shared'] as List<dynamic>?)?.map((e) => e as String).toList() ?? [];
                return Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Text(chainA, style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12, fontWeight: FontWeight.w600)),
                      const Padding(padding: EdgeInsets.symmetric(horizontal: 8), child: Icon(Icons.call_merge, size: 10, color: Color(0xFFA78BFA))),
                      Text(chainB, style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12, fontWeight: FontWeight.w600)),
                      const Spacer(),
                      Text('重叠度 ${(score * 100).toInt()}%',
                          style: const TextStyle(color: Color(0xFFA78BFA), fontSize: 10, fontWeight: FontWeight.w500)),
                    ]),
                    if (reason.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(reason, style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10, height: 1.4)),
                    ],
                    if (fuzzyShared.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 4,
                        runSpacing: 4,
                        children: fuzzyShared.map((fs) {
                          return Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: const Color(0xFFA855F7).withAlpha(26),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: const Color(0xFFA855F7).withAlpha(51)),
                            ),
                            child: Text(fs, style: const TextStyle(color: Color(0xFFA78BFA), fontSize: 9)),
                          );
                        }).toList(),
                      ),
                    ],
                    // Merge actions
                    Container(
                      margin: const EdgeInsets.only(top: 10),
                      padding: const EdgeInsets.only(top: 8),
                      decoration: const BoxDecoration(border: Border(top: BorderSide(color: Color(0xFF2A2B30)))),
                      child: Row(children: [
                        const Text('合并方式:', style: TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
                        const SizedBox(width: 8),
                        GestureDetector(
                          onTap: () => _handleMerge(chainA, chainB, 'a'),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: const Color(0xFF3B82F6).withAlpha(26),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: const Color(0xFF3B82F6).withAlpha(51)),
                            ),
                            child: Text('并入「$chainA」', style: const TextStyle(color: Color(0xFF60A5FA), fontSize: 9)),
                          ),
                        ),
                        const SizedBox(width: 6),
                        GestureDetector(
                          onTap: () => _handleMerge(chainA, chainB, 'b'),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: const Color(0xFF10B981).withAlpha(26),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: const Color(0xFF10B981).withAlpha(51)),
                            ),
                            child: Text('并入「$chainB」', style: const TextStyle(color: Color(0xFF34D399), fontSize: 9)),
                          ),
                        ),
                        const SizedBox(width: 6),
                        _buildNewChainMerge(chainA, chainB),
                      ]),
                    ),
                  ]),
                );
              }),
            ],
          ]),
        ),
        GestureDetector(
          onTap: () => setState(() { _overlapOpen = false; _overlaps = []; }),
          child: const Icon(Icons.close, size: 16, color: Color(0xFF6B7280)),
        ),
      ]),
    );
  }

  Widget _buildNewChainMerge(String chainA, String chainB) {
    final key = '$chainA|||$chainB|||new:';
    final busy = _mergingOverlap != null && _mergingOverlap!.startsWith(key);
    final newNameCtrl = TextEditingController();
    return Row(mainAxisSize: MainAxisSize.min, children: [
      SizedBox(
        width: 96, height: 24,
        child: TextField(
          controller: newNameCtrl,
          style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 9),
          decoration: InputDecoration(
            hintText: '新链名...', hintStyle: const TextStyle(color: Color(0xFF6B7280), fontSize: 9),
            filled: true, fillColor: const Color(0xFF0B0C10),
            contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: Color(0xFF3A3B40))),
          ),
          onSubmitted: (val) { if (val.trim().isNotEmpty) _handleMerge(chainA, chainB, 'new:$val'); },
        ),
      ),
      const SizedBox(width: 4),
      GestureDetector(
        onTap: busy
            ? null
            : () {
                final val = newNameCtrl.text.trim();
                if (val.isNotEmpty) _handleMerge(chainA, chainB, 'new:$val');
              },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: const Color(0xFFA855F7).withAlpha(26),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: const Color(0xFFA855F7).withAlpha(51)),
          ),
          child: Text(busy ? '...' : '确定', style: TextStyle(color: busy ? const Color(0xFF6B7280) : const Color(0xFFA78BFA), fontSize: 9)),
        ),
      ),
    ]);
  }

  Widget _buildMergedFlowResult() {
    final target = _mergedFlow!['target_chain'] as String? ?? '';
    final nodeCount = _mergedFlow!['node_count'] as int? ?? 0;
    final flow = (_mergedFlow!['flow'] as List<dynamic>?) ?? [];
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF10B981).withAlpha(13),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF10B981).withAlpha(51)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.call_merge, size: 18, color: Color(0xFF34D399)),
          const SizedBox(width: 8),
          Text('「$target」合并完成 · $nodeCount 个节点',
              style: const TextStyle(color: Color(0xFF34D399), fontSize: 14, fontWeight: FontWeight.w600)),
          const Spacer(),
          GestureDetector(
            onTap: () => setState(() => _mergedFlow = null),
            child: const Icon(Icons.close, size: 16, color: Color(0xFF6B7280)),
          ),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 6, runSpacing: 6, children: flow.asMap().entries.map((e) {
          final fi = e.key;
          final f = e.value as Map<String, dynamic>;
          final fType = f['type'] as String? ?? '';
          final fName = f['name'] as String? ?? '';
          final tc = _typeColorFor(fType);
          return Row(mainAxisSize: MainAxisSize.min, children: [
            if (fi > 0)
              const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 2),
                  child: Text('→', style: TextStyle(color: Color(0xFF6B7280), fontSize: 8))),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(color: tc.withAlpha(26), borderRadius: BorderRadius.circular(20), border: Border.all(color: tc.withAlpha(51))),
              child: Text(fName, style: TextStyle(color: tc, fontSize: 10)),
            ),
          ]);
        }).toList()),
        const SizedBox(height: 10),
        Row(children: const [
          _MergeFlowLegendChip(text: '原材料', color: Color(0xFFFBBF24)),
          SizedBox(width: 8),
          _MergeFlowLegendChip(text: '中间品', color: Color(0xFF60A5FA)),
          SizedBox(width: 8),
          _MergeFlowLegendChip(text: '零部件', color: Color(0xFFA78BFA)),
          SizedBox(width: 8),
          _MergeFlowLegendChip(text: '终端', color: Color(0xFF34D399)),
        ]),
      ]),
    );
  }

  Widget _buildChainsGrid() {
    final entries = _chainsMap.entries.toList();
    if (entries.isEmpty) {
      return const Center(
        child: Padding(padding: EdgeInsets.all(48), child: Text('暂无产业链数据', style: TextStyle(color: Color(0xFF6B7280), fontSize: 14))),
      );
    }
    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: entries.map((entry) => _buildChainCard(entry.key, entry.value)).toList(),
    );
  }

  Widget _buildChainCard(String chainName, List<Map<String, dynamic>> chainNodes) {
    final typeCounts = <String, int>{};
    var totalCountries = 0;
    for (final n in chainNodes) {
      final nodeType = n['node_type'] as String? ?? '';
      typeCounts[nodeType] = (typeCounts[nodeType] ?? 0) + 1;
      final groups = _normalizeShares(n['global_shares']);
      final names = <String>{};
      for (final s in groups['production']!) {
        final c = s['c'] as String? ?? '';
        if (c.isNotEmpty) names.add(c);
      }
      for (final s in groups['supply']!) {
        final c = s['c'] as String? ?? '';
        if (c.isNotEmpty) names.add(c);
      }
      for (final s in groups['demand']!) {
        final c = s['c'] as String? ?? '';
        if (c.isNotEmpty) names.add(c);
      }
      totalCountries += names.length;
    }
    final avgCountries = chainNodes.isNotEmpty ? (totalCountries / chainNodes.length).toStringAsFixed(1) : '0';
    final iconRes = _getChainIcon(chainName, _chainIconMap[chainName]);

    return SizedBox(
      width: 540,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF141518),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFF2A2B30)),
        ),
        child: GestureDetector(
          onTap: () {
            Navigator.pushNamed(context, '/chain-detail', arguments: {
              'chainName': chainName,
              'chainNodes': chainNodes,
              'chainIcon': _chainIconMap[chainName],
              'flowSummary': _chainFlowSummaryMap[chainName] ?? '',
              'allNodes': _nodes,
            });
          },
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Icon(iconRes.icon, size: 20, color: iconRes.color),
              const SizedBox(width: 10),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Text(chainName,
                        style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
                    const SizedBox(width: 8),
                    Text('${chainNodes.length}节点',
                        style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
                  ]),
                  const SizedBox(height: 4),
                  Row(children: [
                    ...typeCounts.entries.map((tc) {
                      return Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: Text('${tc.key}×${tc.value}',
                            style: const TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
                      );
                    }),
                    if (totalCountries > 0) ...[
                      const Icon(Icons.public, size: 9, color: Color(0xFF6B7280)),
                      const SizedBox(width: 2),
                      Text('均${avgCountries}国', style: const TextStyle(color: Color(0xFF6B7280), fontSize: 9)),
                    ],
                  ]),
                ]),
              ),
              const Spacer(),
              GestureDetector(
                onTap: () => _handleCollectChain(chainName),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: const Color(0xFF38BDF8).withAlpha(26),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: const Color(0xFF38BDF8).withAlpha(51)),
                  ),
                  child: Row(children: [
                    if (_collectingChain == chainName)
                      const SizedBox(width: 10, height: 10, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF38BDF8)))
                    else
                      const Icon(Icons.search, size: 10, color: Color(0xFF38BDF8)),
                    const SizedBox(width: 4),
                    const Text('联网采集',
                        style: TextStyle(color: Color(0xFF38BDF8), fontSize: 10, fontWeight: FontWeight.w500)),
                  ]),
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }

  Widget _buildSuggestionsView() {
    if (_suggestions.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(64),
          child: Text('暂无新链建议。采集到涉及新产业的内容后，AI 会自动在此建议。',
              style: TextStyle(color: Color(0xFF6B7280), fontSize: 14), textAlign: TextAlign.center),
        ),
      );
    }
    return Column(
      children: _suggestions.map((sug) {
        final sugChainName = sug['chain_name'] as String? ?? '';
        final sugConfidence = (sug['confidence'] as num?)?.toDouble() ?? 0;
        final sugReason = sug['reason'] as String? ?? '';
        final sugQuote = sug['source_quote'] as String? ?? '';
        final sugNodesJson = (sug['nodes_json'] as List<dynamic>?)
                ?.map((e) => e as Map<String, dynamic>)
                .toList() ??
            [];

        return Container(
          margin: const EdgeInsets.only(bottom: 16),
          decoration: BoxDecoration(color: const Color(0xFF141518), borderRadius: BorderRadius.circular(12), border: Border.all(color: const Color(0xFF2A2B30))),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Text(sugChainName,
                          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600)),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(4)),
                        child: Text('置信度 ${(sugConfidence * 100).toInt()}%',
                            style: const TextStyle(color: Color(0xFF6B7280), fontSize: 11)),
                      ),
                    ]),
                    if (sugReason.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(sugReason, style: const TextStyle(color: Color(0xFF6B7280), fontSize: 11, height: 1.5)),
                    ],
                  ]),
                ),
                const SizedBox(width: 12),
                Row(children: [
                  GestureDetector(
                    onTap: () async {
                      try {
                        await _api.dismissChainSuggestion(sug['id'] as String? ?? '');
                        _fetchSuggestions();
                      } catch (_) {}
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFFEF4444).withAlpha(51))),
                      child: const Text('忽略', style: TextStyle(color: Color(0xFFF87171), fontSize: 12)),
                    ),
                  ),
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: () async {
                      try {
                        final d = await _api.adoptChainSuggestion(sug['id'] as String? ?? '');
                        if (d['ok'] == true) {
                          _fetchSuggestions();
                          _fetchData();
                        }
                      } catch (_) {}
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                      decoration: BoxDecoration(
                        color: const Color(0xFFA855F7).withAlpha(26),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFA855F7).withAlpha(51)),
                      ),
                      child: const Text('采用',
                          style: TextStyle(color: Color(0xFFA78BFA), fontSize: 12, fontWeight: FontWeight.w500)),
                    ),
                  ),
                ]),
              ]),
              if (sugQuote.isNotEmpty) ...[
                const SizedBox(height: 12),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8)),
                  child: Text('"$sugQuote"',
                      style: const TextStyle(color: Color(0xFF6B7280), fontSize: 11, fontStyle: FontStyle.italic)),
                ),
              ],
              if (sugNodesJson.isNotEmpty) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: sugNodesJson.map((n) {
                    final nType = n['node_type'] as String? ?? '';
                    return Container(
                      width: 180,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(color: const Color(0xFF0B0C10), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Text(n['name'] as String? ?? '',
                              style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 12, fontWeight: FontWeight.w500)),
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: _typeBgFor(nType),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: _typeColorFor(nType).withAlpha(102)),
                            ),
                            child: Text(nType, style: TextStyle(color: _typeColorFor(nType), fontSize: 9)),
                          ),
                        ]),
                        if (n['description'] != null) ...[
                          const SizedBox(height: 4),
                          Text(n['description'] as String? ?? '',
                              style: const TextStyle(color: Color(0xFF6B7280), fontSize: 10)),
                        ],
                        if (n['initial_data'] != null) ...[
                          const SizedBox(height: 4),
                          Text('📊 ${n['initial_data']}', style: const TextStyle(color: Color(0xFF34D399), fontSize: 10)),
                        ],
                      ]),
                    );
                  }).toList(),
                ),
              ],
            ]),
          ),
        );
      }).toList(),
    );
  }
}
