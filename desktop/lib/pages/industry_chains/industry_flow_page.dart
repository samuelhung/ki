import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../../services/api_client.dart';

// ── Constants ──
const _levelX = {'原材料': 80.0, '中间品': 380.0, '零部件': 680.0, '终端': 980.0};
const _typeColorMap = {
  '原材料': '#f59e0b',
  '中间品': '#a855f7',
  '零部件': '#3b82f6',
  '终端': '#10b981',
};
const _chainPalette = [
  '#eab308', '#06b6d4', '#f59e0b', '#22c55e',
  '#a855f7', '#ef4444', '#f97316', '#ec4899',
];
final _chainColorIdx = <String, int>{};
String _getChainColor(String chain) {
  _chainColorIdx.putIfAbsent(chain, () => _chainColorIdx.length);
  return _chainPalette[_chainColorIdx[chain]! % _chainPalette.length];
}

// Cross-chain edges defined by node name
const _crossLinks = [
  {'from': '工业硅/硅料', 'to': '硅晶圆', 'label': '电子级多晶硅'},
  {'from': '光伏银浆', 'to': '封装测试', 'label': '导电浆料共通'},
  {'from': '负极材料（石墨/硅碳）', 'to': '硅晶圆', 'label': '高纯石墨耗材'},
  {'from': '封装测试', 'to': '组件', 'label': '层压封装共通'},
  {'from': '碳酸锂/氢氧化锂', 'to': '光伏玻璃', 'label': '锂盐添加剂'},
];

class IndustryFlowPage extends StatefulWidget {
  const IndustryFlowPage({super.key});
  @override
  State<IndustryFlowPage> createState() => _IndustryFlowPageState();
}

class _IndustryFlowPageState extends State<IndustryFlowPage> {
  final _api = ApiClient();
  WebViewController? _webCtrl;
  bool _loading = true;
  List<Map<String, dynamic>> _allNodes = [];
  bool _webReady = false;

  @override
  void initState() {
    super.initState();
    _fetchData();
  }

  Future<void> _fetchData() async {
    setState(() => _loading = true);
    try {
      final data = await _api.getChainNodes();
      final nodes = (data['nodes'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
      setState(() { _allNodes = nodes; _loading = false; });
      if (_webReady) _render();
    } catch (_) {
      setState(() => _loading = false);
    }
  }

  void _render() {
    if (_allNodes.isEmpty || _webCtrl == null) return;
    // Build graph data: nodes + edges
    final nameToId = <String, String>{};
    for (final n in _allNodes) { nameToId[n['name'] as String] = n['id'] as String; }

    // Group by chain
    final chains = <String, List<Map<String, dynamic>>>{};
    for (final n in _allNodes) {
      chains.putIfAbsent(n['chain'] as String, () => []).add(n);
    }
    final chainOrder = chains.keys.toList()..sort();

    final visNodes = <Map<String, dynamic>>[];
    final visEdges = <Map<String, dynamic>>[];
    double y = 0;

    for (final chainName in chainOrder) {
      final chainNodes = chains[chainName]!;
      chainNodes.sort((a, b) => (a['sort_order'] as int? ?? 0) - (b['sort_order'] as int? ?? 0));
      final chainColor = _getChainColor(chainName);

      for (final n in chainNodes) {
        final type = n['node_type'] as String? ?? '原材料';
        final x = _levelX[type] ?? 80;
        visNodes.add({
          'id': n['id'],
          'label': n['name'],
          'x': x,
          'y': y,
          'fixed': {'x': true, 'y': false},
          'color': {'background': _typeColorMap[type] ?? '#6b7280', 'border': chainColor, 'hover': {'background': _typeColorMap[type] ?? '#6b7280', 'border': '#ffffff'}},
          'font': {'color': '#e5e7eb', 'size': 11},
          'borderWidth': 2,
          'shape': 'box',
          'size': 16,
          'chain': chainName,
          'nodeType': type,
        });
        y += 80;
      }
      y += 40; // gap between chains
    }

    // Intra-chain edges
    for (final n in _allNodes) {
      final upstreamIds = <String>[];
      final raw = n['upstream_ids'];
      try {
        if (raw is String) {
          final parsed = jsonDecode(raw);
          if (parsed is List) upstreamIds.addAll(parsed.cast<String>());
        } else if (raw is List) {
          upstreamIds.addAll(raw.cast<String>());
        }
      } catch (_) {}
      final chainColor = _getChainColor(n['chain'] as String? ?? '');
      for (final uid in upstreamIds) {
        visEdges.add({
          'id': 'intra-$uid-${n['id']}',
          'from': uid,
          'to': n['id'],
          'arrows': 'to',
          'color': {'color': chainColor, 'highlight': '#a855f7'},
          'width': 1.5,
          'smooth': {'type': 'cubicBezier'},
        });
      }
    }

    // Cross-chain edges
    for (var i = 0; i < _crossLinks.length; i++) {
      final link = _crossLinks[i];
      final fromId = nameToId[link['from'] as String];
      final toId = nameToId[link['to'] as String];
      if (fromId != null && toId != null) {
        visEdges.add({
          'id': 'cross-$i',
          'from': fromId,
          'to': toId,
          'label': link['label'],
          'arrows': 'to',
          'color': {'color': '#a855f7', 'highlight': '#c084fc'},
          'width': 1.5,
          'dashes': true,
          'smooth': {'type': 'cubicBezier'},
          'font': {'color': '#a78bfa', 'size': 9, 'strokeWidth': 0},
        });
      }
    }

    _webCtrl!.runJavaScript('''
      window.renderFlow(${jsonEncode(visNodes)}, ${jsonEncode(visEdges)});
    ''');
  }

  // Helper to normalize shares
  String _normalizeShares(dynamic raw) {
    try {
      final data = raw is String ? jsonDecode(raw) : raw;
      if (data is Map && data['groups'] != null) {
        return jsonEncode(data['groups']);
      }
      return jsonEncode(data ?? []);
    } catch (_) {
      return '{"production":[],"supply":[],"demand":[]}';
    }
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
      if (data['type'] == 'back') {
        Navigator.pop(context);
      } else if (data['type'] == 'select') {
        setState(() {
          if (data['node'] != null) {
            // Parse shares for display
            final nodesList = _allNodes;
            final nodeId = data['nodeId'] as String?;
            // Detail panel handled in JS
          }
        });
      }
    });
    ctrl.setNavigationDelegate(NavigationDelegate(
      onPageFinished: (_) {
        setState(() => _webReady = true);
        if (_allNodes.isNotEmpty) _render();
      },
    ));
    ctrl.loadHtmlString(_buildHtml());
    return ctrl;
  }

  String _buildHtml() {
    return '''
<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;overflow:hidden;background:#0B0C10;font-family:system-ui,sans-serif}
#graph{width:100%;height:100%}
.floating{position:absolute;z-index:20}
.btn{background:#141518;border:1px solid #2A2B30;border-radius:8px;color:#6B7280;cursor:pointer;font-size:12px;padding:6px 12px;display:flex;align-items:center;gap:4px;text-decoration:none;box-shadow:0 8px 32px rgba(0,0,0,0.4)}
.btn:hover{color:#e5e7eb;border-color:#3A3B40}
.search-bar{background:#141518;border:1px solid #2A2B30;border-radius:8px;display:flex;align-items:center;gap:8px;padding:6px 12px;box-shadow:0 8px 32px rgba(0,0,0,0.4)}
.search-bar input{background:transparent;border:none;outline:none;font-size:13px;color:#e5e7eb;width:224px}
.search-bar input::placeholder{color:#6B7280}
</style>
<script src="https://unpkg.com/vis-network@9.1.6/dist/vis-network.min.js"></script>
<script src="https://unpkg.com/vis-data@7.1.9/standalone/umd/vis-data.min.js"></script>
</head><body>
<div id="graph"></div>

<!-- Back button -->
<a href="#" onclick="window.flutterChannel.postMessage(JSON.stringify({type:'back'}));return false" class="floating btn" style="top:16px;left:16px">← 返回产业链</a>

<!-- Search -->
<div class="floating search-bar" style="top:16px;left:50%;transform:translateX(-50%)">
  <input type="text" id="searchInput" placeholder="搜索节点、类型、产业链..." oninput="doSearch()" />
  <span id="matchCount" style="font-size:11px;color:#6B7280;display:none"></span>
  <button onclick="clearSearch()" style="background:none;border:none;color:#6B7280;cursor:pointer;font-size:14px;display:none" id="clearBtn">×</button>
</div>

<!-- Legend -->
<div class="floating" style="bottom:16px;left:16px;background:#141518;border:1px solid #2A2B30;border-radius:8px;padding:12px">
  <div style="font-size:10px;font-weight:500;color:#6B7280;margin-bottom:8px">产业链颜色</div>
  <div id="legend"></div>
  <div style="display:flex;align-items:center;gap:8px;margin-top:4px">
    <div style="width:12px;height:2px;border-radius:2px;border-top:1.5px dashed #a855f7"></div>
    <span style="font-size:10px;color:#a855f7">跨链连接</span>
  </div>
</div>

<!-- Detail panel -->
<div id="detailPanel" class="floating" style="top:16px;right:16px;width:320px;max-height:80vh;overflow-y:auto;background:#141518;border:1px solid #2A2B30;border-radius:12px;padding:16px;box-shadow:0 16px 64px rgba(0,0,0,0.5);display:none"></div>

<script>
var network = null, allNodes = [], allVisNodes = [];

window.renderFlow = function(visNodes, visEdges) {
  allVisNodes = visNodes;
  var dsNodes = new vis.DataSet(visNodes);
  var dsEdges = new vis.DataSet(visEdges);

  if (network) network.destroy();
  network = new vis.Network(document.getElementById('graph'), {nodes: dsNodes, edges: dsEdges}, {
    physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -80, centralGravity: 0.005, springLength: 200, springConstant: 0.05 }, stabilization: { iterations: 80 } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true, dragNodes: true },
    nodes: { font: { face: 'system-ui, sans-serif' } },
    layout: { hierarchical: false },
    edges: { smooth: { type: 'cubicBezier' } },
    physics: { enabled: false },
  });

  network.on('click', function(params) {
    if (params.nodes.length > 0) {
      var node = visNodes.find(function(n) { return n.id === params.nodes[0]; });
      if (node) showDetail(node);
    } else {
      document.getElementById('detailPanel').style.display = 'none';
    }
  });

  // Build legend
  var chains = [...new Set(visNodes.map(function(n) { return n.chain; }))].sort();
  var legendHtml = '';
  chains.forEach(function(c) {
    var color = visNodes.find(function(n) { return n.chain === c; }).color.border;
    legendHtml += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px"><div style="width:12px;height:2px;border-radius:2px;background:' + color + '"></div><span style="font-size:10px;color:#6B7280">' + c.replace('产业链','') + '</span></div>';
  });
  document.getElementById('legend').innerHTML = legendHtml;

  network.fit({animation: true});
};

function showDetail(node) {
  window.flutterChannel.postMessage(JSON.stringify({type:'select', nodeId: node.id, nodeName: node.label}));
}

function doSearch() {
  var q = document.getElementById('searchInput').value.trim().toLowerCase();
  var countEl = document.getElementById('matchCount');
  var clearBtn = document.getElementById('clearBtn');

  if (!q) {
    countEl.style.display = 'none';
    clearBtn.style.display = 'none';
    if (network) network.fit({animation: true});
    return;
  }

  clearBtn.style.display = 'block';
  var matchCount = 0;
  allVisNodes.forEach(function(n) {
    var match = (n.label||'').toLowerCase().includes(q) || (n.nodeType||'').toLowerCase().includes(q) || (n.chain||'').toLowerCase().includes(q);
    if (match) matchCount++;
    network.body.data.nodes.update({id: n.id, opacity: match ? 1 : 0.1});
  });
  countEl.style.display = 'block';
  countEl.textContent = matchCount + ' 个匹配';
}

function clearSearch() {
  document.getElementById('searchInput').value = '';
  doSearch();
}
</script>
</body></html>''';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0C10),
      body: SafeArea(
        child: Stack(children: [
          if (_loading)
            const Center(child: CircularProgressIndicator(color: Color(0xFF6B7280))),
          WebViewWidget(controller: _controller),
          // Refresh
          Positioned(
            top: 16, right: 16,
            child: GestureDetector(
              onTap: _fetchData,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(color: const Color(0xFF141518), borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFF2A2B30))),
                child: const Icon(Icons.refresh, size: 16, color: Color(0xFF6B7280)),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}
