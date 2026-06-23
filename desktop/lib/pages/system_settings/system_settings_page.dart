import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../services/config_service.dart';
import '../../theme/app_theme.dart';

// ── 中文 tab 标签 ──
const _TAB_LABELS = <String, String>{
  'params_info': '参数说明',
  'general': '通用配置',
  'ingest_pipeline': '内容采集',
  'series': '专题引擎',
  'brainstorm': '头脑风暴',
  'digest_briefing': '摘要快报',
  'tasks': '待办事务',
  'concept': '概念沉淀',
  'knowledge_graph': '知识图谱',
  'connection': '连接',
};

const _TASK_NAMES = <String, Map<String, String>>{
  'ingest_pipeline': {'summarize': '内容总结', 'classify': '认知分类', 'tag': '实体标注', 'translate': '英文翻译'},
  'series': {'discover': '发现专题', 'intro': '专题导言', 'summary': '结构化总结', 'paper': '论文分析', 'auto_suggest': '即时匹配'},
  'brainstorm': {'answer': '综合回答', 'summary': '对话总结', 'contemplate': '凝神静思', 'concept_extract': '概念提取'},
  'digest_briefing': {'digest': '每日摘要', 'briefing_quick': '即时快报', 'briefing_daily': '深度日报'},
  'tasks': {'judge': '事务判断'},
  'concept': {'auto_complete': 'AI 补全'},
  'knowledge_graph': {'entity_insight': '实体深度分析'},
};

class SystemSettingsPage extends StatefulWidget {
  const SystemSettingsPage({super.key});
  @override
  State<SystemSettingsPage> createState() => _SystemSettingsPageState();
}

class _SystemSettingsPageState extends State<SystemSettingsPage> {
  Map<String, dynamic>? _config;
  bool _loading = true;
  String? _error;
  String _tab = 'params_info';

  // Prompt templates state
  Map<String, dynamic>? _prompts;
  bool _promptsLoading = false;

  // Connection tab state
  final _backendController = TextEditingController();
  bool _backendSaving = false;
  String? _backendStatus;
  bool _connSaved = false;
  String _urlMode = 'auto';
  Map<String, dynamic>? _health;
  int _latencyMs = 0;
  String? _healthError;
  Timer? _healthTimer;

  @override
  void initState() {
    super.initState();
    _loadConfig();
    _loadBackendUrl();
    _startHealthPolling();
  }

  @override
  void dispose() {
    _backendController.dispose();
    _healthTimer?.cancel();
    super.dispose();
  }

  void _startHealthPolling() {
    _checkHealth();
    _healthTimer = Timer.periodic(const Duration(seconds: 5), (_) => _checkHealth());
  }

  Future<void> _checkHealth() async {
    final t0 = DateTime.now().millisecondsSinceEpoch;
    try {
      final data = await ApiClient().checkHealth();
      if (mounted) {
        final lat = DateTime.now().millisecondsSinceEpoch - t0;
        // checkHealth just returns bool, we need the full health response
        // Let's get it from the dio directly
        try {
          final resp = await ApiClient().dio.get('/api/health');
          if (resp.statusCode == 200) {
            setState(() { _health = resp.data; _latencyMs = lat; _healthError = null; });
          }
        } catch (_) {
          setState(() { _health = null; _latencyMs = 0; _healthError = '连接失败'; });
        }
      }
    } catch (e) {
      if (mounted) setState(() { _health = null; _healthError = e.toString(); });
    }
  }

  Future<void> _loadBackendUrl() async {
    final url = await ConfigService.getBackendUrl();
    _backendController.text = url;
    setState(() => _urlMode = url == 'http://127.0.0.1:9120' ? 'auto' : 'manual');
  }

  Future<void> _loadConfig() async {
    setState(() { _loading = true; _error = null; });
    try {
      final data = await ApiClient().getSystemConfig();
      if (mounted) setState(() { _config = data; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  Future<void> _saveConfig() async {
    if (_config == null) return;
    try {
      final ok = await ApiClient().saveSystemConfig(_config!);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(ok ? '保存成功，下次 AI 调用生效' : '保存失败'),
          backgroundColor: ok ? AppTheme.success : AppTheme.error,
        ));
      }
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('保存失败'), backgroundColor: AppTheme.error));
    }
  }

  Future<void> _saveBackendUrl() async {
    final url = _backendController.text.trim();
    if (url.isEmpty) return;
    setState(() { _backendSaving = true; _backendStatus = null; });
    try {
      await ApiClient().setBackendUrl(url);
      if (mounted) {
        setState(() { _backendSaving = false; _backendStatus = '已连接'; _connSaved = true; });
        _checkHealth();
        Future.delayed(const Duration(seconds: 3), () { if (mounted) setState(() => _connSaved = false); });
      }
    } catch (e) {
      if (mounted) setState(() { _backendSaving = false; _backendStatus = '连接失败'; });
    }
  }

  void _updateGeneral(String key, dynamic value) {
    if (_config == null) return;
    setState(() {
      final general = Map<String, dynamic>.from(_config!['general'] as Map<String, dynamic>);
      general[key] = value;
      _config!['general'] = general;
    });
  }

  void _updateTaskConfig(String module, String task, Map<String, dynamic> value) {
    if (_config == null) return;
    setState(() {
      final mod = Map<String, dynamic>.from(_config![module] as Map<String, dynamic>? ?? {});
      mod[task] = value;
      _config![module] = mod;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(backgroundColor: AppTheme.background, body: Center(child: CircularProgressIndicator(color: AppTheme.accent)));
    if (_error != null) return Scaffold(backgroundColor: AppTheme.background, body: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Icon(Icons.cloud_off, size: 48, color: AppTheme.textMuted),
      const SizedBox(height: 16),
      Text(_error!, style: const TextStyle(color: AppTheme.error)),
      const SizedBox(height: 16),
      ElevatedButton(onPressed: _loadConfig, child: const Text('重试')),
    ])));

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(children: [
          // Header
          Padding(
            padding: const EdgeInsets.fromLTRB(32, 24, 32, 0),
            child: Row(children: [
              const Icon(Icons.settings, size: 28, color: AppTheme.accent),
              const SizedBox(width: 12),
              const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('系统设置', style: TextStyle(color: AppTheme.textPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
                Text('AI 模型参数与业务模块专属配置', style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
              ])),
              _tab != 'params_info' && _tab != 'connection' ? ElevatedButton.icon(
                onPressed: _saveConfig,
                icon: const Icon(Icons.save, size: 16),
                label: const Text('保存配置'),
                style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accent, foregroundColor: Colors.white, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
              ) : const SizedBox(),
            ]),
          ),
          const SizedBox(height: 16),
          // Tabs
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 24),
              children: _TAB_LABELS.entries.map((e) {
                final active = _tab == e.key;
                return GestureDetector(
                  onTap: () => _onTabChanged(e.key),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                    alignment: Alignment.center,
                    decoration: BoxDecoration(border: Border(bottom: BorderSide(color: active ? AppTheme.accent : Colors.transparent, width: 2))),
                    child: Text(e.value, style: TextStyle(color: active ? AppTheme.textPrimary : AppTheme.textMuted, fontSize: 13, fontWeight: active ? FontWeight.w600 : FontWeight.w400)),
                  ),
                );
              }).toList(),
            ),
          ),
          const Divider(height: 1, color: AppTheme.border),
          Expanded(child: _buildTabContent()),
        ]),
      ),
    );
  }

  Widget _buildTabContent() {
    if (_config == null) return const SizedBox();
    switch (_tab) {
      case 'params_info': return _buildParamsInfo();
      case 'general': return _buildGeneralTab();
      case 'connection': return _buildConnectionTab();
      default: return _buildModuleTab(_tab);
    }
  }

  void _onTabChanged(String key) {
    setState(() => _tab = key);
    // Load prompts for business module tabs
    if (!['params_info', 'general', 'connection'].contains(key)) {
      _loadPrompts(key);
    }
  }

  Future<void> _loadPrompts(String module) async {
    if (_promptsLoading) return;
    setState(() => _promptsLoading = true);
    try {
      final data = await ApiClient().getPrompts();
      if (mounted) setState(() { _prompts = data['modules']; _promptsLoading = false; });
    } catch (_) {
      if (mounted) setState(() => _promptsLoading = false);
    }
  }

  // ── 参数说明 ──
  Widget _buildParamsInfo() => ListView(padding: const EdgeInsets.all(24), children: [
    _section('DeepSeek 模型规格', _modelSpecsTable()),
    const SizedBox(height: 16),
    _section('参数详解', _paramsDoc()),
    const SizedBox(height: 16),
    _section('各任务单次调用成本估算（V4 Pro）', _costTable()),
  ]);

  Widget _modelSpecsTable() => Column(children: [
    _tableHeader(['参数', 'V4 Flash', 'V4 Pro（当前）'], flex: [2, 2, 2]),
    ..._modelSpecRows(),
  ]);

  List<Widget> _modelSpecRows() {
    final rows = [
      ['上下文长度', '1M token', '1M token'],
      ['最大输出', '384K token', '384K token'],
      ['思考模式', '支持', '支持'],
      ['JSON Output', '✓', '✓'],
      ['FIM 补全', '非思考模式', '非思考模式'],
      ['输入价格（缓存未命中）', '1 元/百万 token', '3 元/百万 token'],
      ['输入价格（缓存命中）', '0.02 元/百万 token', '0.025 元/百万 token'],
      ['输出价格', '2 元/百万 token', '6 元/百万 token'],
    ];
    return rows.asMap().entries.map((e) {
      final i = e.key; final r = e.value;
      final isLast = i == rows.length - 1;
      return Container(
        padding: const EdgeInsets.symmetric(vertical: 7),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: isLast ? Colors.transparent : const Color(0xFF1A1B20)))),
        child: Row(children: [
          Expanded(flex: 2, child: Text(r[0], style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11))),
          Expanded(flex: 2, child: Text(r[1], style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11))),
          Expanded(flex: 2, child: Text(r[2], style: TextStyle(color: ['1M token', '384K token', '0.025 元/百万 token'].contains(r[2]) ? AppTheme.success : AppTheme.textSecondary, fontSize: 11))),
        ]),
      );
    }).toList();
  }

  Widget _paramsDoc() => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    _paramDoc('temperature 随机度', '控制输出的随机性和创造性。取值 0–2。\n0：完全确定性，同样 prompt 永远同样输出，适合分类/标注/数学。\n0.1–0.3：轻微发散，适合摘要/翻译/事实性问答。\n0.4–0.6：适度创造，适合论文/导言/综合回答。\n0.7+：高度随机，创意写作/头脑风暴，但可能胡言乱语。'),
    const SizedBox(height: 16),
    _paramDoc('max_tokens 最大输出', 'AI 一次最多输出多少个 token。1 中文字 ≈ 1.5 token，4096 token ≈ 2700 汉字。模型上限 384K（约 25 万汉字），实际按任务需求设置即可。设太小会导致回答被截断；设太大浪费 token 且 AI 可能啰嗦。'),
    const SizedBox(height: 16),
    _paramDoc('thinking 思考模式', '开启后 AI 先内部推理再输出答案，推理过程不收费但会看到更长延迟。适合：复杂多步推理、论文级分析、需要引用支撑的论证。不适合：简单分类/标注/翻译。'),
    const SizedBox(height: 16),
    _paramDoc('reasoning_effort 推理强度', '仅在开启思考模式时生效。控制 AI 内部推理的步数和深度。high：标准推理链，适合大多数场景。max：更长的推理链，数学证明/复杂逻辑可能需要。'),
    const SizedBox(height: 16),
    _paramDoc('上下文硬盘缓存', 'DeepSeek 的云端缓存机制。相同 system prompt + 消息历史触达缓存时，输入价格从 3 元/百万 token 降至 0.025 元/百万 token（节省 99%）。KI 的摘要、快报等定时任务 prompt 高度重复，强烈建议开启。'),
  ]);

  Widget _paramDoc(String title, String desc) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(title, style: const TextStyle(color: AppTheme.accent, fontSize: 12, fontWeight: FontWeight.w600)),
    const SizedBox(height: 4),
    Text(desc, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12, height: 1.6)),
  ]);

  Widget _costTable() => Column(children: [
    _tableHeader(['任务', 'max_tokens', '≈ 汉字', '输出成本'], flex: [3, 2, 2, 2]),
    ..._costRows(),
  ]);

  List<Widget> _costRows() {
    final rows = [
      ['内容总结 summarize', '3072', '2000', '0.02 元'],
      ['认知分类 classify', '256', '170', '<0.01 元'],
      ['实体标注 tag', '512', '340', '<0.01 元'],
      ['英文翻译 translate', '2048', '1300', '0.01 元'],
      ['发现专题 discover', '4096', '2700', '0.02 元'],
      ['专题导言 intro', '1024', '680', '<0.01 元'],
      ['结构化总结 summary', '3072', '2000', '0.02 元'],
      ['论文分析 paper', '16384', '11000', '0.10 元'],
      ['即时匹配 auto_suggest', '256', '170', '<0.01 元'],
      ['综合回答 answer', '8192', '5500', '0.05 元'],
      ['对话总结 summary', '3000', '2000', '0.02 元'],
      ['凝神静思 contemplate', '800', '530', '<0.01 元'],
      ['概念提取 concept_extract', '2048', '1300', '0.01 元'],
      ['每日摘要 digest', '8192', '5500', '0.05 元'],
      ['即时快报 briefing_quick', '3072', '2000', '0.02 元'],
      ['深度日报 briefing_daily', '8192', '5500', '0.05 元'],
      ['AI 补全 auto_complete', '1500', '1000', '0.01 元'],
      ['事务判断 judge', '16384', '11000', '0.10 元'],
      ['实体深度分析 entity_insight', '2048', '1300', '0.01 元'],
    ];
    return rows.asMap().entries.map((e) {
      final i = e.key; final r = e.value;
      final isLast = i == rows.length - 1;
      return Container(
        padding: const EdgeInsets.symmetric(vertical: 7),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: isLast ? Colors.transparent : const Color(0xFF1A1B20)))),
        child: Row(children: [
          Expanded(flex: 3, child: Text(r[0], style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11))),
          Expanded(flex: 2, child: Text(r[1], style: const TextStyle(color: AppTheme.textPrimary, fontSize: 11))),
          Expanded(flex: 2, child: Text(r[2], style: const TextStyle(color: AppTheme.textMuted, fontSize: 11))),
          Expanded(flex: 2, child: Text(r[3], style: const TextStyle(color: AppTheme.success, fontSize: 11))),
        ]),
      );
    }).toList();
  }

  Widget _tableHeader(List<String> headers, {List<int>? flex}) => Container(
    padding: const EdgeInsets.symmetric(vertical: 8),
    decoration: BoxDecoration(
      color: AppTheme.border.withOpacity(0.3),
      borderRadius: const BorderRadius.vertical(top: Radius.circular(8)),
    ),
    child: Row(children: headers.asMap().entries.map((e) {
      final f = flex != null && e.key < flex.length ? flex[e.key] : 1;
      return Expanded(flex: f, child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        child: Text(e.value, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11, fontWeight: FontWeight.w600)),
      ));
    }).toList()),
  );

  // ── 通用配置 ──
  Widget _buildGeneralTab() {
    final g = _config!['general'] as Map<String, dynamic>;
    return ListView(padding: const EdgeInsets.all(24), children: [
      _section('模型与连接', Column(children: [
        _rowSelect('选用模型', g['model'] as String? ?? 'deepseek-v4-pro', ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat'], (v) => _updateGeneral('model', v)),
        _rowInput('接口地址', g['base_url'] as String? ?? '', (v) => _updateGeneral('base_url', v)),
        _rowPassword('API 密钥', g['api_key'] as String? ?? '', (v) => _updateGeneral('api_key', v)),
      ])),
      const SizedBox(height: 16),
      _section('缓存与全局默认', Column(children: [
        _toggleRow('上下文硬盘缓存', (g['disk_cache'] as bool?) ?? false, (v) => _updateGeneral('disk_cache', v), hint: '建议开启'),
        _rowSelect('推理强度', g['reasoning_effort'] as String? ?? 'high', ['high', 'max'], (v) => _updateGeneral('reasoning_effort', v)),
      ])),
      const SizedBox(height: 16),
      _section('全局默认值', Column(children: [
        _numRow('temperature', (g['default_temperature'] as num?)?.toDouble() ?? 0.3, (v) => _updateGeneral('default_temperature', v), hint: '建议 0.3'),
        _numRow('max_tokens', (g['default_max_tokens'] as num?)?.toDouble() ?? 2048, (v) => _updateGeneral('default_max_tokens', v), min: 64, max: 32768, hint: '建议 2048'),
      ])),
    ]);
  }

  // ── 连接 ──
  Widget _buildConnectionTab() {
    final url = ApiClient().backendUrl;
    final desktopVersion = _readDesktopVersion();

    return ListView(padding: const EdgeInsets.all(24), children: [
      // ── 连接状态卡片 ──
      _section('连接状态', _healthError != null
          ? Column(children: [
              Container(padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: AppTheme.error.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(10), border: Border.all(color: AppTheme.error.withValues(alpha: 0.2))),
                child: Row(children: [
                  const Icon(Icons.wifi_off, color: AppTheme.error, size: 22),
                  const SizedBox(width: 16),
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('未连接', style: TextStyle(color: AppTheme.error, fontSize: 14, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    Text('目标: $url', style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                  ])),
                ]),
              ),
              const SizedBox(height: 12),
              _connGrid([
                _connCard('桌面版本', 'v$desktopVersion', Icons.desktop_windows, AppTheme.accent),
                _connCard('后端版本', '—', Icons.dns, AppTheme.textMuted),
              ]),
            ])
          : _health != null
              ? Column(children: [
                  // Header row: connected status
                  Container(padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: AppTheme.success.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(10), border: Border.all(color: AppTheme.success.withValues(alpha: 0.15))),
                    child: Row(children: [
                      const Icon(Icons.wifi, color: AppTheme.success, size: 22),
                      const SizedBox(width: 16),
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('已连接', style: TextStyle(color: AppTheme.success, fontSize: 14, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 4),
                        Text(url, style: const TextStyle(color: AppTheme.textMuted, fontSize: 12, fontFamily: 'monospace')),
                      ])),
                    ]),
                  ),
                  const SizedBox(height: 12),
                  // Stat cards grid
                  _connGrid([
                    _connCard('桌面版本', 'v$desktopVersion', Icons.desktop_windows, AppTheme.accent),
                    _connCard('后端版本', 'v${_health!['version']}', Icons.dns, AppTheme.info),
                    _connCard('响应延迟', '${_latencyMs}ms', Icons.speed, AppTheme.amber),
                    _connCard('运行时长', _formatUptime((_health!['uptime_sec'] as num?)?.toDouble() ?? 0), Icons.timer, AppTheme.textSecondary),
                  ]),
                  const SizedBox(height: 10),
                  _dbStatusRow(_health!['database'] as Map<String, dynamic>?),
                ])
              : Container(padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(10)),
                  child: const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.accent)),
                    SizedBox(width: 12),
                    Text('检测中...', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
                  ])),
      ),
      const SizedBox(height: 20),
      // ── 后端地址配置 ──
      _section('后端地址', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _radioChip('自动检测', _urlMode == 'auto', () => setState(() => _urlMode = 'auto')),
          const SizedBox(width: 12),
          _radioChip('手动指定', _urlMode == 'manual', () => setState(() => _urlMode = 'manual')),
        ]),
        const SizedBox(height: 12),
        _urlMode == 'manual'
            ? Row(children: [
                Expanded(child: TextField(controller: _backendController, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                  decoration: InputDecoration(hintText: 'http://10.8.0.105:9120', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 13), contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10), filled: true, fillColor: AppTheme.background, border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: const BorderSide(color: AppTheme.border)))),
                ),
                const SizedBox(width: 8),
                ElevatedButton(onPressed: _backendSaving ? null : _saveBackendUrl, style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accent, foregroundColor: Colors.white, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))), child: _backendSaving ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('连接')),
                if (_urlMode == 'manual') ...[
                  const SizedBox(width: 8),
                  TextButton(onPressed: () { setState(() { _urlMode = 'auto'; _backendController.text = 'http://127.0.0.1:9120'; }); }, child: const Text('恢复默认', style: TextStyle(fontSize: 12))),
                ],
              ])
            : Row(children: [
                Expanded(child: Container(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10), decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8), border: Border.all(color: AppTheme.border)), child: const Text('http://127.0.0.1:9120（自动）', style: TextStyle(color: AppTheme.textMuted, fontSize: 13)))),
              ]),
        const SizedBox(height: 14),
        // 说明文字放在地址栏下方
        _modeDescription(),
        if (_backendStatus != null) ...[
          const SizedBox(height: 8),
          Text(_backendStatus!, style: TextStyle(color: _backendStatus == '已连接' ? AppTheme.success : AppTheme.error, fontSize: 12)),
        ],
        if (_connSaved) const Padding(padding: EdgeInsets.only(top: 8), child: Text('✓ 已保存', style: TextStyle(color: AppTheme.success, fontSize: 12))),
      ])),
    ]);
  }

  /// Read desktop version from app bundle Info.plist (macOS only)
  String _readDesktopVersion() {
    try {
      if (!Platform.isMacOS) return '?';
      // Walk up from the executable to find the .app bundle
      var dir = Directory(File(Platform.resolvedExecutable).parent.path);
      while (dir.path != '/' && !dir.path.endsWith('.app')) {
        dir = Directory(dir.parent.path);
      }
      if (!dir.path.endsWith('.app')) return '?';
      final plistPath = '${dir.path}/Contents/Info.plist';
      final result = Process.runSync(
          'plutil', ['-extract', 'CFBundleShortVersionString', 'raw', plistPath]);
      if (result.exitCode == 0) return result.stdout.toString().trim();
    } catch (_) {}
    return '?';
  }

  Widget _connGrid(List<Widget> cards) => LayoutBuilder(builder: (ctx, constraints) {
    const double gap = 10;
    const int cols = 4;
    final itemW = (constraints.maxWidth - (cols - 1) * gap) / cols;
    return Wrap(spacing: gap, runSpacing: gap, children: cards.map((c) => SizedBox(width: itemW, child: c)).toList());
  });

  Widget _connCard(String label, String value, IconData icon, Color color) => Container(
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppTheme.border.withValues(alpha: 0.5))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 8),
        Text(label, style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
      ]),
      const SizedBox(height: 8),
      Text(value, style: TextStyle(color: color == AppTheme.textMuted ? AppTheme.textMuted : AppTheme.textPrimary, fontSize: 17, fontWeight: FontWeight.w700, fontFamily: 'monospace')),
    ]),
  );

  Widget _dbStatusRow(Map<String, dynamic>? db) {
    if (db == null) return const SizedBox();
    final ok = db['ok'] as bool? ?? false;
    return Container(padding: const EdgeInsets.all(10), decoration: BoxDecoration(
      color: ok ? AppTheme.success.withOpacity(0.08) : AppTheme.error.withOpacity(0.08),
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: ok ? AppTheme.success.withOpacity(0.15) : AppTheme.error.withOpacity(0.15)),
    ), child: Row(children: [
      Icon(ok ? Icons.dns : Icons.dns_outlined, size: 14, color: ok ? AppTheme.success : AppTheme.error),
      const SizedBox(width: 8),
      Text('数据库：${ok ? "正常" : "异常"}', style: TextStyle(color: ok ? AppTheme.success : AppTheme.error, fontSize: 11)),
      if (ok) ...[
        const Text('  |  ', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        Text('${db['event_count']} 条事件', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
        const Text('  |  ', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        Text('${db['size_mb']} MB', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
      ],
    ]));
  }

  String _formatUptime(double sec) {
    if (sec < 60) return '${sec.floor()}秒';
    if (sec < 3600) return '${(sec / 60).floor()}分';
    if (sec < 86400) return '${(sec / 3600).floor()}时${((sec % 3600) / 60).floor()}分';
    return '${(sec / 86400).floor()}天${((sec % 86400) / 3600).floor()}时';
  }

  // ── 业务模块 tab ──
  Widget _buildModuleTab(String key) {
    final mod = (_config![key] as Map<String, dynamic>?) ?? {};
    final tasks = _TASK_NAMES[key] ?? {};
    final modulePrompts = (_prompts as Map<String, dynamic>?)?[key] as Map<String, dynamic>?;

    return ListView(padding: const EdgeInsets.all(24), children: [
      _section('${_TAB_LABELS[key]} — 任务参数',
        LayoutBuilder(builder: (ctx, constraints) {
          const double gap = 10;
          final itemW = (constraints.maxWidth - gap) / 2;
          return Wrap(spacing: gap, runSpacing: gap, children: mod.entries.map((e) {
            final cfg = e.value as Map<String, dynamic>;
            final taskPrompts = modulePrompts?[e.key] as Map<String, dynamic>?;
            return SizedBox(width: itemW, child: _taskCard(e.key, tasks[e.key] ?? e.key, cfg, taskPrompts));
          }).toList());
        }),
      ),
    ]);
  }

  Widget _taskCard(String taskKey, String cnName, Map<String, dynamic> cfg, Map<String, dynamic>? prompts) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('$cnName', style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12, fontWeight: FontWeight.w600)),
      Text('($taskKey)', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
      const SizedBox(height: 8),
      _numRowSmall('temperature', (cfg['temperature'] as num?)?.toDouble() ?? 0.3, (v) => _updateTaskConfig(_tab, taskKey, {...cfg, 'temperature': v})),
      _numRowSmall('max_tokens', (cfg['max_tokens'] as num?)?.toDouble() ?? 2048, (v) => _updateTaskConfig(_tab, taskKey, {...cfg, 'max_tokens': v}), min: 64, max: 32768),
      _toggleRowSmall('thinking', (cfg['thinking'] as bool?) ?? false, (v) => _updateTaskConfig(_tab, taskKey, {...cfg, 'thinking': v})),
      if (prompts != null && prompts.isNotEmpty) ...[
        const SizedBox(height: 8),
        const Divider(height: 1, color: AppTheme.border),
        const SizedBox(height: 6),
        Text('Prompt 模板', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10, fontWeight: FontWeight.w500)),
        const SizedBox(height: 4),
        ...prompts.entries.map((p) {
          final content = p.value.toString();
          final preview = content.length > 200 ? '${content.substring(0, 200)}...' : content;
          return Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 4),
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(color: const Color(0xFF0A0B0E), borderRadius: BorderRadius.circular(6), border: Border.all(color: AppTheme.border.withOpacity(0.3))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(p.key, style: const TextStyle(color: AppTheme.accent, fontSize: 10, fontFamily: 'monospace')),
              const SizedBox(height: 2),
              Text(preview, style: const TextStyle(color: AppTheme.textMuted, fontSize: 10, fontFamily: 'monospace', height: 1.4)),
            ]),
          );
        }),
      ],
    ]),
  );

  // ── Shared widgets ──
  Widget _section(String title, Widget child) => Container(
    width: double.infinity, padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.border)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
      const SizedBox(height: 12), child,
    ]),
  );

  Widget _rowSelect(String label, String value, List<String> options, Function(String) onChange) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(children: [
      SizedBox(width: 100, child: Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12))),
      const Spacer(),
      Container(padding: const EdgeInsets.symmetric(horizontal: 8), decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(6), border: Border.all(color: AppTheme.border)),
        child: DropdownButtonHideUnderline(child: DropdownButton<String>(
          value: options.contains(value) ? value : options.first,
          dropdownColor: AppTheme.panel,
          style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
          items: options.map((o) => DropdownMenuItem(value: o, child: Text(o, style: const TextStyle(fontSize: 12)))).toList(),
          onChanged: (v) { if (v != null) onChange(v); },
        )),
      ),
    ]),
  );

  Widget _rowInput(String label, String value, Function(String) onChange) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(children: [
      SizedBox(width: 100, child: Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12))),
      Expanded(child: SizedBox(height: 32, child: TextField(
        controller: TextEditingController(text: value)..selection = TextSelection.collapsed(offset: value.length),
        style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
        textAlign: TextAlign.right,
        decoration: InputDecoration(contentPadding: const EdgeInsets.symmetric(horizontal: 8), filled: true, fillColor: AppTheme.background, border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: AppTheme.border))),
        onChanged: onChange,
      ))),
    ]),
  );

  Widget _rowPassword(String label, String value, Function(String) onChange) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Row(children: [
      SizedBox(width: 100, child: Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12))),
      Expanded(child: SizedBox(height: 32, child: TextField(
        obscureText: true,
        controller: TextEditingController(text: value)..selection = TextSelection.collapsed(offset: value.length),
        style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
        textAlign: TextAlign.right,
        decoration: InputDecoration(hintText: value.isNotEmpty ? '已设置（••••）' : '未设置', hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12), contentPadding: const EdgeInsets.symmetric(horizontal: 8), filled: true, fillColor: AppTheme.background, border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: AppTheme.border))),
        onChanged: onChange,
      ))),
    ]),
  );

  Widget _toggleRow(String label, bool value, Function(bool) onChange, {String? hint}) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(children: [
      Expanded(child: Text.rich(TextSpan(children: [
        TextSpan(text: label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
        if (hint != null) TextSpan(text: '（$hint）', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
      ]))),
      GestureDetector(
        onTap: () => onChange(!value),
        child: Container(
          width: 40, height: 22,
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(11), color: value ? AppTheme.accent : AppTheme.border),
          child: AnimatedAlign(duration: const Duration(milliseconds: 150), alignment: value ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(margin: const EdgeInsets.symmetric(horizontal: 2), width: 18, height: 18, decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white)),
          ),
        ),
      ),
    ]),
  );

  Widget _numRow(String label, double value, Function(double) onChange, {double min = 0, double max = 2, double step = 0.1, String? hint}) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(children: [
      Expanded(child: Text.rich(TextSpan(children: [
        TextSpan(text: label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
        if (hint != null) TextSpan(text: '（$hint）', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10)),
      ]))),
      SizedBox(width: 80, height: 30, child: TextField(
        controller: TextEditingController(text: value.toStringAsFixed(1))..selection = TextSelection.collapsed(offset: value.toStringAsFixed(1).length),
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
        textAlign: TextAlign.right,
        decoration: InputDecoration(contentPadding: const EdgeInsets.symmetric(horizontal: 6), filled: true, fillColor: AppTheme.background, border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: AppTheme.border))),
        onChanged: (v) { final n = double.tryParse(v); if (n != null) onChange(n.clamp(min, max)); },
      )),
    ]),
  );

  // Small variants for task cards
  Widget _numRowSmall(String label, double value, Function(double) onChange, {double min = 0, double max = 2, double step = 0.1}) => Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Row(children: [
      Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
      const Spacer(),
      SizedBox(width: 70, height: 26, child: TextField(
        controller: TextEditingController(text: max > 100 ? value.toStringAsFixed(0) : value.toStringAsFixed(1))..selection = TextSelection.collapsed(offset: max > 100 ? value.toStringAsFixed(0).length : value.toStringAsFixed(1).length),
        keyboardType: TextInputType.number,
        style: const TextStyle(color: AppTheme.textPrimary, fontSize: 11), textAlign: TextAlign.right,
        decoration: InputDecoration(isDense: true, contentPadding: const EdgeInsets.symmetric(horizontal: 4), filled: true, fillColor: AppTheme.panel, border: OutlineInputBorder(borderRadius: BorderRadius.circular(4), borderSide: const BorderSide(color: AppTheme.border))),
        onChanged: (v) { final n = double.tryParse(v); if (n != null) onChange(n.clamp(min, max)); },
      )),
    ]),
  );

  Widget _toggleRowSmall(String label, bool value, Function(bool) onChange) => Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Row(children: [
      Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
      const Spacer(),
      GestureDetector(
        onTap: () => onChange(!value),
        child: Container(width: 34, height: 20, decoration: BoxDecoration(borderRadius: BorderRadius.circular(10), color: value ? AppTheme.accent : AppTheme.border),
          child: AnimatedAlign(duration: const Duration(milliseconds: 150), alignment: value ? Alignment.centerRight : Alignment.centerLeft,
            child: Container(margin: const EdgeInsets.symmetric(horizontal: 2), width: 16, height: 16, decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white)),
          ),
        ),
      ),
    ]),
  );

  Widget _radioChip(String label, bool selected, VoidCallback onTap) => GestureDetector(
    onTap: onTap,
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 16, height: 16, decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: selected ? AppTheme.accent : AppTheme.textMuted, width: 2)),
        child: selected ? Center(child: Container(width: 8, height: 8, decoration: const BoxDecoration(shape: BoxShape.circle, color: AppTheme.accent))) : null),
      const SizedBox(width: 6),
      Text(label, style: TextStyle(color: selected ? AppTheme.textPrimary : AppTheme.textMuted, fontSize: 12)),
    ]),
  );

  Widget _modeDescription() => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: AppTheme.background,
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: AppTheme.border.withOpacity(0.4)),
    ),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _modeRow('🏠', '本地模式', '后端运行在本机 ', '127.0.0.1:9120', '，数据存在本地。'),
      const SizedBox(height: 8),
      _modeRow('🌐', '远程模式', '填入 VPN 地址（如 ', 'http://10.8.0.105:9120', '），多设备共享同一后端和数据。切换后即刻生效。'),
    ]),
  );

  Widget _modeRow(String icon, String title, String before, String addr, String after) =>
    Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(icon, style: const TextStyle(fontSize: 13)),
      const SizedBox(width: 8),
      Expanded(child: RichText(text: TextSpan(
        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12, height: 1.6),
        children: [
          TextSpan(text: title, style: const TextStyle(fontWeight: FontWeight.w600, color: AppTheme.textPrimary)),
          const TextSpan(text: '：'),
          TextSpan(text: before),
          TextSpan(text: addr, style: const TextStyle(color: AppTheme.accent, fontFamily: 'monospace', fontWeight: FontWeight.w500)),
          TextSpan(text: after),
        ],
      ))),
    ]);
}
