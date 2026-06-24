import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';
import '../../main.dart';

class SystemDocPage extends StatefulWidget {
  const SystemDocPage({super.key});
  @override
  State<SystemDocPage> createState() => _SystemDocPageState();
}

class _SystemDocPageState extends State<SystemDocPage> {
  String _tab = 'arch';

  // Update state
  final _updateMgr = UpdateManager();

  // Database state
  Map<String, dynamic>? _dbInfo;
  bool _dbLoading = false;

  // Logs state
  List<Map<String, dynamic>> _logEntries = [];
  int _logTotal = 0;
  bool _logLoading = false;
  String _logLevel = 'INFO';
  final _logSearch = TextEditingController();
  Timer? _logDebounce;

  @override
  void initState() {
    super.initState();
    _updateMgr.addListener(() { if (mounted) setState(() {}); });
  }

  @override
  void dispose() {
    _updateMgr.dispose();
    _logSearch.dispose();
    _logDebounce?.cancel();
    super.dispose();
  }

  void _onTabChanged(String tab) {
    setState(() => _tab = tab);
    if (tab == 'database') _loadDbInfo();
    if (tab == 'logs') _loadLogs();
  }

  Future<void> _loadDbInfo() async {
    setState(() => _dbLoading = true);
    try {
      final data = await ApiClient().getDatabaseInfo();
      if (mounted) setState(() { _dbInfo = data; _dbLoading = false; });
    } catch (_) {
      if (mounted) setState(() => _dbLoading = false);
    }
  }

  Future<void> _loadLogs() async {
    setState(() => _logLoading = true);
    try {
      final data = await ApiClient().getLogs(
        level: _logLevel,
        search: _logSearch.text.isNotEmpty ? _logSearch.text : null,
      );
      if (mounted) {
        setState(() {
          _logEntries = (data['entries'] as List<dynamic>?)
                  ?.cast<Map<String, dynamic>>() ??
              [];
          _logTotal = data['total'] as int? ?? 0;
          _logLoading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() { _logEntries = []; _logLoading = false; });
    }
  }

  static const _tabs = [
    {'key': 'arch', 'label': '数据架构'},
    {'key': 'flow', 'label': '数据流'},
    {'key': 'features', 'label': '功能体系'},
    {'key': 'changelog', 'label': '版本更新'},
    {'key': 'database', 'label': '数据库'},
    {'key': 'logs', 'label': '系统日志'},
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(32, 24, 32, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.menu_book, size: 28, color: AppTheme.accent),
                      const SizedBox(width: 12),
                      const Text('系统说明', style: TextStyle(color: AppTheme.textPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
                      const SizedBox(width: 12),
                      _buildVersionBadge(),
                      const SizedBox(width: 8),
                      _buildUpdateButton(),
                    ],
                  ),
                  const SizedBox(height: 4),
                  const Text('知几其神乎，见微知著', style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // Tab bar
            SizedBox(
              height: 44,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 24),
                children: _tabs.map((t) {
                  final active = _tab == t['key'];
                  return GestureDetector(
                    onTap: () => _onTabChanged(t['key']!),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        border: Border(bottom: BorderSide(color: active ? AppTheme.accent : Colors.transparent, width: 2)),
                      ),
                      child: Text(t['label']!, style: TextStyle(
                        color: active ? AppTheme.textPrimary : AppTheme.textMuted,
                        fontSize: 14, fontWeight: active ? FontWeight.w600 : FontWeight.w400)),
                    ),
                  );
                }).toList(),
              ),
            ),
            const Divider(height: 1, color: AppTheme.border),
            // Content
            Expanded(child: _buildTabContent()),
          ],
        ),
      ),
    );
  }

  Widget _buildTabContent() {
    switch (_tab) {
      case 'arch': return _buildArchTab();
      case 'flow': return _buildFlowTab();
      case 'features': return _buildFeaturesTab();
      case 'changelog': return _buildChangelogTab();
      case 'database': return _buildDatabaseTab();
      case 'logs': return _buildLogsTab();
      default: return const SizedBox();
    }
  }

  // ── 数据架构 ──
  Widget _buildArchTab() {
    return ListView(padding: const EdgeInsets.all(24), children: [
      _sectionCard('目录结构', _codeBlock(
        'data/\n│\n│  📊 intelligence.sqlite                ← SQLite 主库\n│\n├── ingest/                              ← 摄入管线产物\n│   ├── transcripts/   evt-ingest-{id}.md\n│   ├── summaries/     evt-ingest-{id}.md\n│   ├── videos/        evt-ingest-{id}.mp4\n│   ├── audio/         evt-ingest-{id}.ext\n│   └── documents/     evt-ingest-{id}.ext\n│\n├── brainstorm/        {question_id}.md\n├── concepts/          evt-concept-{id}.md\n├── digests/           YYYY-MM-DD.md\n├── events/            YYYY-MM-DD.jsonl\n└── state/             rss-{source}.json',
      )),
      const SizedBox(height: 16),
      _sectionCard('双写对照', _dataTable(
        ['内容', '文件系统', 'SQLite 列', '写入时机'],
        [
          ['转写正文', 'transcripts/{id}.md', 'events.raw_summary', '管线完成时'],
          ['AI 总结', 'summaries/{id}.md', 'events.ai_summary', '总结完成时'],
          ['原始视频', 'videos/{id}.mp4', 'events.video_path', '仅存路径'],
          ['原始音频', 'audio/{id}.ext', 'events.audio_path', '仅存路径'],
          ['原始文档', 'documents/{id}.ext', 'events.document_path', '仅存路径'],
          ['概念文档', 'concepts/{id}.md', 'events.ai_summary', '概念创建/沉淀时'],
          ['问答记录', 'brainstorm/{qid}.md', 'brainstorm_questions.content_md', '创建+每次回答'],
          ['每日摘要', 'digests/YYYY-MM-DD.md', 'digests.markdown', '每日 8:00'],
        ],
      )),
    ]);
  }

  // ── 数据流 ──
  Widget _buildFlowTab() {
    return ListView(padding: const EdgeInsets.all(24), children: [
      _sectionCard('摄入管线', _codeBlock(
        '抖音分享 → 解析链接 → 下载视频 → 提取音频 → 语音转写 → AI 总结 → 入库\n上传视频 →                → 提取音频 → 语音转写 → AI 总结 → 入库\n上传音频 →                             → 语音转写 → AI 总结 → 入库\n上传文档 →                                          → 文档解析 → 入库\n\n全部类型 → 认知分类（格局/财富/认知/前瞻）→ 持久化任务队列 → SQLite+MD 双写',
      )),
      const SizedBox(height: 16),
      _sectionCard('定时链路', Padding(
        padding: const EdgeInsets.all(8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _flowItem('每6h', 'RSS 采集链', '采集所有 RSS → 标记翻译 → 并发翻译 30 条 → 生成即时快报'),
          const SizedBox(height: 12),
          _flowItem('8:00', '每日摘要 + 深度日报', '取当天所有事件 → DeepSeek 生成结构化 MD → 双写 SQLite + .md'),
        ]),
      )),
      const SizedBox(height: 16),
      _sectionCard('凝神静思 — 双向缓存', const Padding(
        padding: EdgeInsets.all(12),
        child: Text(
          '内容详情和问题详情共享同一张 brainstorm_contemplate_cache 表。在任一侧触发凝神静思后，对侧打开即显示关联度标签，不再重复调用 AI。已关联配对自动排除，低关联结果也缓存避免重判。\n\n沉淀后的概念通过 brainstorm_event_links 建立反向索引，事件详情→关联问题 tab 直接查询，无需 AI。',
          style: TextStyle(color: AppTheme.textSecondary, fontSize: 13, height: 1.7),
        ),
      )),
    ]);
  }

  Widget _flowItem(String time, String title, String desc) {
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2), decoration: BoxDecoration(color: AppTheme.accent.withOpacity(0.15), borderRadius: BorderRadius.circular(4)), child: Text(time, style: const TextStyle(color: AppTheme.accent, fontSize: 12, fontWeight: FontWeight.w600))),
      const SizedBox(width: 12),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 4),
        Text(desc, style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
      ])),
    ]);
  }

  // ── 功能体系 ──
  Widget _buildFeaturesTab() {
    return ListView(padding: const EdgeInsets.all(24), children: [
      _sectionCard('核心模块', _featureGrid([
        _feat('仪表盘', '热力图 + 指标卡 + 事件总览'),
        _feat('内容采集', '抖音/文件摄入，4 认知 tab，即时快报'),
        _feat('专题系列', 'AI 聚类发现，候选审核→保存，结构化总结，论文分析'),
        _feat('沉淀概念', '手工录入 + 脑暴总结沉淀，AI 结构化补全'),
        _feat('头脑风暴', '手工创建问题，多文档 AI 综合回答，多轮对话'),
        _feat('综合事务', '纯手动输入事务，AI 结构化判断，关联内容展示'),
        _feat('每日摘要', 'AI 生成要闻 + QA 对 + 可拓展问题'),
        _feat('事件列表', 'FTS5 全文检索 + 分页 + 批量操作'),
        _feat('信息源管理', '8 源 RSS，采集页卡片 + 弹窗启停'),
        _feat('知识图谱', '实体关系提取、力导向图可视化、深度分析'),
        _feat('辅导中心', '教材PDF上传→逐课解读，孩子版/家长版/教材解读'),
        _feat('工具箱', '贷款利率换算、金融计算、格式转换'),
      ])),
      const SizedBox(height: 16),
      _sectionCard('技术栈', _techGrid([
        _tech('后端', 'FastAPI + SQLite'),
        _tech('前端 Web', 'React + Vite + Tailwind'),
        _tech('前端桌面', 'Flutter + Dart'),
        _tech('AI', 'DeepSeek'),
        _tech('语音', '火山引擎 ASR'),
        _tech('搜索', 'FTS5 全文检索'),
        _tech('分发', 'GitHub Releases'),
      ])),
    ]);
  }

  Widget _feat(String name, String desc) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8), border: Border.all(color: AppTheme.border.withOpacity(0.5))),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(name, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
      const SizedBox(height: 4),
      Text(desc, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
    ]),
  );

  Widget _tech(String label, String value) => Container(
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
      const SizedBox(height: 2),
      Text(value, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
    ]),
  );

  Widget _featureGrid(List<Widget> items) => LayoutBuilder(builder: (ctx, constraints) {
    const double gap = 10;
    final itemW = (constraints.maxWidth - gap) / 2;
    return Wrap(spacing: gap, runSpacing: gap, children: items.map((w) => SizedBox(width: itemW, child: w)).toList());
  });
  Widget _techGrid(List<Widget> items) => LayoutBuilder(builder: (ctx, constraints) {
    const double gap = 10;
    const int cols = 4;
    final itemW = (constraints.maxWidth - (cols - 1) * gap) / cols;
    return Wrap(spacing: gap, runSpacing: gap, children: items.map((w) => SizedBox(width: itemW, child: w)).toList());
  });

  // ── 版本更新 ──
  Widget _buildChangelogTab() {
    return FutureBuilder<String>(
      future: rootBundle.loadString('changelog.json'),
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator(color: AppTheme.accent));
        }
        final data = jsonDecode(snapshot.data!) as Map<String, dynamic>;
        final versions = (data['versions'] as List<dynamic>).cast<Map<String, dynamic>>();

        return ListView(padding: const EdgeInsets.all(24), children: versions.map((v) {
          final version = v['version'] as String;
          final date = v['date'] as String;
          final title = v['title'] as String;
          final sections = (v['sections'] as List<dynamic>).cast<Map<String, dynamic>>();

          return Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: _sectionCard('', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2), decoration: BoxDecoration(color: AppTheme.accent.withOpacity(0.15), borderRadius: BorderRadius.circular(4)), child: Text('v$version', style: const TextStyle(color: AppTheme.accent, fontSize: 11, fontWeight: FontWeight.w600))),
                const SizedBox(width: 8),
                Text(date, style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                const SizedBox(width: 8),
                Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
              ]),
              const SizedBox(height: 12),
              ...sections.map((sec) {
                final icon = sec['icon'] as String? ?? '';
                final label = sec['label'] as String? ?? '';
                final items = (sec['items'] as List<dynamic>).cast<String>();
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('$icon $label', style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 4),
                    ...items.map((item) => Padding(
                      padding: const EdgeInsets.only(bottom: 4, left: 8),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('•  ', style: TextStyle(color: AppTheme.accent, fontSize: 12)),
                        Expanded(child: Text(item, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12, height: 1.5))),
                      ]),
                    )),
                  ]),
                );
              }),
            ])),
          );
        }).toList());
      },
    );
  }

  // ── 数据库 ──
  Widget _buildDatabaseTab() {
    if (_dbLoading) return const Center(child: CircularProgressIndicator(color: AppTheme.accent));
    if (_dbInfo == null) {
      return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.storage, size: 40, color: AppTheme.textMuted),
        const SizedBox(height: 12),
        const Text('无法加载数据库信息', style: TextStyle(color: AppTheme.textMuted)),
        const SizedBox(height: 12),
        ElevatedButton(onPressed: _loadDbInfo, child: const Text('重试')),
      ]));
    }

    final db = _dbInfo!['database'] as Map<String, dynamic>;
    final tables = (db['tables'] as Map<String, dynamic>?) ?? {};
    final files = (_dbInfo!['files'] as Map<String, dynamic>?) ?? {};
    final maxCount = tables.values.fold<int>(0, (m, v) => (v['count'] as int) > m ? (v['count'] as int) : m);

    return ListView(padding: const EdgeInsets.all(24), children: [
      // 库概览 — 2行×3 撑满
      _sectionCard('数据库概览', LayoutBuilder(builder: (ctx, constraints) {
        const int cols = 3;
        const double gap = 10;
        final itemW = (constraints.maxWidth - (cols - 1) * gap) / cols;
        return Wrap(spacing: gap, runSpacing: gap, children: [
          _statCard('文件路径', '${db['file']}', Icons.folder, width: itemW),
          _statCard('文件大小', '${db['size_display']}', Icons.save, accent: true, width: itemW),
          _statCard('WAL 模式', '${db['journal_mode']}', Icons.check_circle, accent: true, width: itemW),
          _statCard('页数', '${db['page_count']}', Icons.grid_view, width: itemW),
          _statCard('页大小', '${db['page_size']} B', Icons.memory, width: itemW),
          _statCard('逻辑大小', '${db['total_mb']} MB', Icons.dns, accent: true, width: itemW),
        ]);
      }), icon: Icons.storage, iconColor: AppTheme.purple),
      const SizedBox(height: 16),
      // 表统计 — 满宽自适应（仿 web w-full table-fixed）
      _sectionCard('表统计', Column(children: [
        // 表头
        Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppTheme.border))),
          child: const Row(children: [
            Expanded(child: Text('表名', style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
            Expanded(child: Text('说明', style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
            SizedBox(width: 64, child: Text('行数', textAlign: TextAlign.right, style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
            SizedBox(width: 64),
          ]),
        ),
        // 数据行
        ...(() sync* {
          final sorted = tables.entries.toList()..sort((a, b) => (b.value['count'] as int).compareTo(a.value['count'] as int));
          for (final e in sorted) {
            final count = e.value['count'] as int;
            final ratio = maxCount > 0 ? count / maxCount : 0.0;
            yield Container(
              padding: const EdgeInsets.symmetric(vertical: 7),
              decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Color(0xFF1A1B20)))),
              child: Row(children: [
                Expanded(child: Text(e.key, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontFamily: 'monospace'))),
                Expanded(child: Text('${e.value['desc']}', style: const TextStyle(color: AppTheme.textMuted, fontSize: 11), overflow: TextOverflow.ellipsis)),
                SizedBox(width: 64, child: Text('$count', textAlign: TextAlign.right, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12, fontFamily: 'monospace'))),
                SizedBox(width: 64, child: Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    width: 60, height: 6,
                    decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(3)),
                    child: FractionallySizedBox(
                      widthFactor: ratio.clamp(0.0, 1.0),
                      child: Container(decoration: BoxDecoration(color: AppTheme.accent.withOpacity(0.6), borderRadius: BorderRadius.circular(3))),
                    ),
                  ),
                )),
              ]),
            );
          }
        })(),
      ]), icon: Icons.table_chart, iconColor: AppTheme.cyan),
      const SizedBox(height: 16),
      // 存储产物 — 2行×4 撑满
      _sectionCard('存储产物', LayoutBuilder(builder: (ctx, constraints) {
        const int cols = 4;
        const double gap = 10;
        final itemW = (constraints.maxWidth - (cols - 1) * gap) / cols;
        return Wrap(spacing: gap, runSpacing: gap, children: files.entries.map((e) => SizedBox(
          width: itemW,
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${e.value['label']}', style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
              const SizedBox(height: 4),
              Text('${e.value['count']}', style: const TextStyle(color: AppTheme.textPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
            ]),
          ),
        )).toList());
      }), icon: Icons.disc_full, iconColor: AppTheme.amber),
    ]);
  }

  Widget _statCard(String label, String value, IconData icon, {bool accent = false, double? width}) => SizedBox(
    width: width,
    child: Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8)),
      child: Row(children: [
        Icon(icon, size: 18, color: accent ? AppTheme.accent : AppTheme.textMuted),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: const TextStyle(color: AppTheme.textMuted, fontSize: 10), overflow: TextOverflow.ellipsis),
          Text(value, style: TextStyle(color: accent ? AppTheme.textPrimary : AppTheme.textSecondary, fontSize: 14, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis),
        ])),
      ]),
    ),
  );

  // ── 系统日志 ──
  Widget _buildLogsTab() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(children: [
        // Controls
        Row(children: [
          // Level filter
          ...['DEBUG', 'INFO', 'WARNING', 'ERROR'].map((lv) => Padding(
            padding: const EdgeInsets.only(right: 4),
            child: GestureDetector(
              onTap: () { setState(() => _logLevel = lv); _loadLogs(); },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _logLevel == lv ? AppTheme.accent.withOpacity(0.15) : AppTheme.panel,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: _logLevel == lv ? AppTheme.accent.withOpacity(0.3) : AppTheme.border),
                ),
                child: Text(lv, style: TextStyle(color: _logLevel == lv ? AppTheme.accent : AppTheme.textMuted, fontSize: 11, fontWeight: FontWeight.w500)),
              ),
            ),
          )),
          const SizedBox(width: 8),
          // Search
          SizedBox(
            width: 200,
            height: 32,
            child: TextField(
              controller: _logSearch,
              style: const TextStyle(color: AppTheme.textPrimary, fontSize: 12),
              decoration: InputDecoration(
                hintText: '搜索日志...',
                hintStyle: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
                contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                filled: true, fillColor: AppTheme.panel,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: const BorderSide(color: AppTheme.border)),
              ),
              onChanged: (_) {
                _logDebounce?.cancel();
                _logDebounce = Timer(const Duration(milliseconds: 400), _loadLogs);
              },
            ),
          ),
          const SizedBox(width: 8),
          IconButton(icon: const Icon(Icons.refresh, size: 18), color: AppTheme.textMuted, onPressed: _loadLogs),
          const Spacer(),
          Text('$_logTotal 条', style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        ]),
        const SizedBox(height: 12),
        // Log entries
        Expanded(child: Container(
          decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.border)),
          child: _logLoading
              ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
              : _logEntries.isEmpty
                  ? const Center(child: Text('暂无日志', style: TextStyle(color: AppTheme.textMuted, fontSize: 13)))
                  : ListView.separated(
                      itemCount: _logEntries.length,
                      separatorBuilder: (_, __) => const Divider(height: 1, color: AppTheme.border),
                      itemBuilder: (_, i) {
                        final e = _logEntries[i];
                        final level = e['level'] as String? ?? '';
                        final color = _levelColor(level);
                        return Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          child: Row(children: [
                            Container(padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2), decoration: BoxDecoration(color: color.withOpacity(0.15), borderRadius: BorderRadius.circular(4)), child: Text(level, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w600))),
                            const SizedBox(width: 8),
                            SizedBox(width: 130, child: Text('${e['timestamp']}', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10, fontFamily: 'monospace'))),
                            if (e['module'] != null) ...[
                              Text('${e['module']}:${e['line_no']}', style: const TextStyle(color: AppTheme.textMuted, fontSize: 10, fontFamily: 'monospace')),
                              const SizedBox(width: 8),
                            ],
                            Expanded(child: Text('${e['message']}', style: TextStyle(color: level == 'ERROR' || level == 'CRITICAL' ? AppTheme.error : AppTheme.textSecondary, fontSize: 11, fontFamily: 'monospace'), maxLines: 2, overflow: TextOverflow.ellipsis)),
                          ]),
                        );
                      },
                    ),
        )),
      ]),
    );
  }

  Color _levelColor(String level) {
    switch (level) {
      case 'ERROR': case 'CRITICAL': return AppTheme.error;
      case 'WARNING': return AppTheme.warning;
      case 'INFO': return AppTheme.info;
      default: return AppTheme.textMuted;
    }
  }

  // ── Shared widgets ──
  Widget _buildVersionBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(color: AppTheme.accent.withOpacity(0.15), borderRadius: BorderRadius.circular(6)),
      child: Text('v${_updateMgr.version}', style: const TextStyle(color: AppTheme.accent, fontSize: 11, fontWeight: FontWeight.w500)),
    );
  }

  Widget _buildUpdateButton() {
    final s = _updateMgr.status;
    final msg = _updateMgr.message;
    final busy = _updateMgr.isBusy;

    Color bg;
    IconData icon;
    String label;

    switch (s) {
      case 'latest':
        bg = AppTheme.success.withOpacity(0.15);
        icon = Icons.check_circle;
        label = '已最新';
        break;
      case 'error':
        bg = AppTheme.error.withOpacity(0.15);
        icon = Icons.error_outline;
        label = '失败';
        break;
      case 'checking':
        bg = AppTheme.info.withOpacity(0.15);
        icon = Icons.refresh;
        label = '检查中';
        break;
      case 'downloading':
        bg = AppTheme.info.withOpacity(0.15);
        icon = Icons.download;
        label = '${_updateMgr.percent.toInt()}%';
        break;
      case 'installing':
        bg = AppTheme.warning.withOpacity(0.15);
        icon = Icons.restart_alt;
        label = '安装中';
        break;
      default:
        bg = AppTheme.textMuted.withOpacity(0.1);
        icon = Icons.system_update;
        label = '检查更新';
    }

    return GestureDetector(
      onTap: () {
        if (s == 'latest' || s == 'error') {
          _showUpdateDialog(context);
        } else if (busy) {
          _showUpdateDialog(context);
        } else {
          _updateMgr.checkForUpdates();
        }
      },
      child: Tooltip(
        message: msg.isNotEmpty ? msg : '检查更新',
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (busy)
              const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.info))
            else
              Icon(icon, size: 12, color: s == 'latest' ? AppTheme.success : s == 'error' ? AppTheme.error : AppTheme.textSecondary),
            const SizedBox(width: 4),
            Text(label, style: TextStyle(color: s == 'latest' ? AppTheme.success : s == 'error' ? AppTheme.error : AppTheme.textSecondary, fontSize: 11, fontWeight: FontWeight.w500)),
          ]),
        ),
      ),
    );
  }

  void _showUpdateDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => ListenableBuilder(
        listenable: _updateMgr,
        builder: (ctx, _) {
    return AlertDialog(
        backgroundColor: AppTheme.panel,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: AppTheme.border)),
        insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
        title: Row(children: [
          Icon(Icons.system_update, size: 20, color: _updateMgr.isBusy ? AppTheme.info : _updateMgr.status == 'error' ? AppTheme.error : AppTheme.success),
          const SizedBox(width: 8),
          Text('更新检查', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
        ]),
        content: SizedBox(
          width: 560,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            // 概要行
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(10)),
              child: Row(children: [
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  _infoRow('桌面版本', 'v${_updateMgr.version}', AppTheme.accent),
                  const SizedBox(height: 6),
                  _infoRow('最新版本', _updateMgr.isBusy ? '检查中...' : _updateMgr.remoteVersion != null ? 'v${_updateMgr.remoteVersion}' : '—', 
                      _updateMgr.isBusy ? AppTheme.info : _updateMgr.remoteVersion != null ? AppTheme.emerald : AppTheme.textMuted),
                ])),
                const SizedBox(width: 24),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: _updateMgr.isBusy ? AppTheme.info.withValues(alpha: 0.12) 
                        : _updateMgr.status == 'error' ? AppTheme.error.withValues(alpha: 0.12)
                        : _updateMgr.status == 'latest' ? AppTheme.success.withValues(alpha: 0.12)
                        : AppTheme.textMuted.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    if (_updateMgr.isBusy)
                      const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.info))
                    else
                      Icon(
                        _updateMgr.status == 'error' ? Icons.error_outline : _updateMgr.status == 'latest' ? Icons.check_circle : Icons.info_outline,
                        size: 16,
                        color: _updateMgr.status == 'error' ? AppTheme.error : _updateMgr.status == 'latest' ? AppTheme.success : AppTheme.info,
                      ),
                    const SizedBox(width: 8),
                    Text(_updateMgr.message, style: TextStyle(
                        color: _updateMgr.isBusy ? AppTheme.info : _updateMgr.status == 'error' ? AppTheme.error : AppTheme.success,
                        fontSize: 12, fontWeight: FontWeight.w600)),
                  ]),
                ),
              ]),
            ),
            // 日志面板
            if (_updateMgr.logs.isNotEmpty) ...[
              const SizedBox(height: 14),
              Row(children: [
                const Text('检查日志', style: TextStyle(color: AppTheme.textMuted, fontSize: 11, fontWeight: FontWeight.w500)),
                const Spacer(),
                GestureDetector(
                  onTap: () {
                    Clipboard.setData(ClipboardData(text: _updateMgr.logs.join('\n')));
                    ScaffoldMessenger.of(ctx).showSnackBar(
                      const SnackBar(content: Text('已复制到剪贴板'), duration: Duration(seconds: 1), behavior: SnackBarBehavior.floating, width: 160),
                    );
                  },
                  child: const Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.copy, size: 13, color: AppTheme.textMuted),
                    SizedBox(width: 4),
                    Text('复制日志', style: TextStyle(color: AppTheme.textMuted, fontSize: 11)),
                  ]),
                ),
              ]),
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                constraints: const BoxConstraints(maxHeight: 260),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFF0A0B0E),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: AppTheme.border.withValues(alpha: 0.5)),
                ),
                child: Builder(builder: (ctx) {
                  final scrollCtrl = ScrollController();
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    if (scrollCtrl.hasClients && scrollCtrl.position.maxScrollExtent > 0) {
                      scrollCtrl.animateTo(scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 150), curve: Curves.easeOut);
                    }
                  });
                  return ListView.builder(
                    controller: scrollCtrl,
                    shrinkWrap: true,
                    itemCount: _updateMgr.logs.length,
                    itemBuilder: (_, i) {
                      final log = _updateMgr.logs[i];
                      Color logColor = AppTheme.textSecondary;
                      if (log.startsWith('✓')) logColor = AppTheme.success;
                      if (log.startsWith('✗')) logColor = AppTheme.error;
                      if (log.startsWith('⏳')) logColor = AppTheme.info; 
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 2),
                        child: Text(log, style: TextStyle(color: logColor, fontSize: 11, fontFamily: 'monospace', height: 1.6)),
                      );
                    },
                  );
                }),
              ),
            ],
            // 提示
            if (!_updateMgr.isBusy && _updateMgr.status == 'latest' && _updateMgr.version == _updateMgr.remoteVersion) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: AppTheme.success.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(8)),
                child: const Row(children: [
                  Icon(Icons.check, size: 14, color: AppTheme.success),
                  SizedBox(width: 8),
                  Text('当前已是最新版本，无需更新', style: TextStyle(color: AppTheme.success, fontSize: 12)),
                ]),
              ),
            ],
            if (_updateMgr.status == 'error' && !_updateMgr.isBusy) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: AppTheme.error.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(8)),
                child: const Row(children: [
                  Icon(Icons.warning_amber, size: 14, color: AppTheme.error),
                  SizedBox(width: 8),
                  Expanded(child: Text('检查失败，可能是网络问题或 GitHub API 限流', style: TextStyle(color: AppTheme.error, fontSize: 12))),
                ]),
              ),
            ],
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('关闭', style: TextStyle(color: AppTheme.textMuted, fontSize: 12))),
          if (!_updateMgr.isBusy || _updateMgr.status == 'checking')
            TextButton(
              onPressed: _updateMgr.isBusy ? null : () => _updateMgr.checkForUpdates(),
              child: _updateMgr.isBusy
                  ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.info))
                  : const Text('重新检查', style: TextStyle(color: AppTheme.info, fontSize: 12)),
            ),
        ],
      ); // end AlertDialog
    },
  ),
);
  }

  Widget _infoRow(String label, String value, Color color) => Row(children: [
    SizedBox(width: 70, child: Text(label, style: const TextStyle(color: AppTheme.textMuted, fontSize: 12))),
    Text(value, style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w600, fontFamily: 'monospace')),
  ]);

  Widget _sectionCard(String title, Widget child, {IconData? icon, Color? iconColor}) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(color: AppTheme.panel, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.border)),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (title.isNotEmpty) ...[
        Row(children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: iconColor ?? AppTheme.textMuted),
            const SizedBox(width: 8),
          ],
          Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
        ]),
        const SizedBox(height: 12),
      ],
      child,
    ]),
  );

  Widget _codeBlock(String code) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(color: AppTheme.background, borderRadius: BorderRadius.circular(8)),
    child: Text(code, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontFamily: 'monospace', height: 1.7)),
  );

  Widget _dataTable(List<String> headers, List<List<String>> rows) => Column(children: [
    // 表头
    Container(
      padding: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.border.withOpacity(0.3),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(8)),
      ),
      child: Row(children: [
        Expanded(child: _th(headers[0])),
        Expanded(flex: 2, child: _th(headers[1])),
        Expanded(flex: 2, child: _th(headers[2])),
        Expanded(child: _th(headers[3])),
      ]),
    ),
    // 数据行
    ...rows.asMap().entries.map((e) {
      final i = e.key;
      final r = e.value;
      return Container(
        padding: const EdgeInsets.symmetric(vertical: 7),
        decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: i < rows.length - 1 ? const Color(0xFF1A1B20) : Colors.transparent)),
        ),
        child: Row(children: [
          Expanded(child: Text(r[0], style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11))),
          Expanded(flex: 2, child: Text(r[1], style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontFamily: 'monospace'), overflow: TextOverflow.ellipsis)),
          Expanded(flex: 2, child: Text(r[2], style: const TextStyle(color: AppTheme.accent, fontSize: 11, fontFamily: 'monospace'), overflow: TextOverflow.ellipsis)),
          Expanded(child: Text(r[3], style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11))),
        ]),
      );
    }),
  ]);

  Widget _th(String text) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 8),
    child: Text(text, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11, fontWeight: FontWeight.w600)),
  );
}
