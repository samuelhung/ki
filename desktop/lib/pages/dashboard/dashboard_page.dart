import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';
import '../../widgets/heatmap_chart.dart';
import '../../widgets/usage_widget.dart';
import '../../widgets/sources_modal.dart';

// ---- 数据模型 ----
class DashboardSummary {
  final int sourcesEnabled;
  final int todayNew;
  final int ingestTotal;
  final int brainstormTotal;
  final int taskTodo;
  final int taskOverdue;
  final int taskTotal;

  const DashboardSummary({
    this.sourcesEnabled = 0,
    this.todayNew = 0,
    this.ingestTotal = 0,
    this.brainstormTotal = 0,
    this.taskTodo = 0,
    this.taskOverdue = 0,
    this.taskTotal = 0,
  });
}

// ---- 页面 ----
class DashboardPage extends ConsumerStatefulWidget {
  const DashboardPage({super.key});

  @override
  ConsumerState<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends ConsumerState<DashboardPage> {
  DashboardSummary _summary = const DashboardSummary();
  List<Map<String, dynamic>> _events = [];
  bool _loading = true;
  String? _error;
  int _eventPage = 1;
  int _eventTotal = 0;
  static const int _eventPageSize = 6;

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = ApiClient();
      final results = await Future.wait([
        api.getDashboardSummary(),
        api.getEvents(offset: 0, limit: _eventPageSize, includeCount: true),
        api.getTaskStats(),
      ]);

      final summary = results[0] as Map<String, dynamic>;
      final eventsResp = results[1] as Map<String, dynamic>;
      final taskStats = results[2] as Map<String, dynamic>;

      final items = eventsResp['items'] as List<dynamic>? ?? [];
      final total = eventsResp['total'] as int? ?? items.length;

      if (mounted) {
        setState(() {
          _summary = DashboardSummary(
            sourcesEnabled: (summary['sources_enabled'] as int?) ?? 0,
            todayNew: (summary['today_new'] as int?) ?? 0,
            ingestTotal: (summary['ingest_total'] as int?) ?? 0,
            brainstormTotal: (summary['brainstorm_total'] as int?) ?? 0,
            taskTodo: (taskStats['todo'] as int?) ?? 0,
            taskOverdue: (taskStats['overdue'] as int?) ?? 0,
            taskTotal: (taskStats['total'] as int?) ?? 0,
          );
          _events = items.cast<Map<String, dynamic>>();
          _eventTotal = total;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() { _error = e.toString(); _loading = false; });
      }
    }
  }

  Future<void> _loadEvents(int page) async {
    setState(() => _eventPage = page);
    try {
      final api = ApiClient();
      final resp = await api.getEvents(offset: (page - 1) * _eventPageSize, limit: _eventPageSize, includeCount: true);
      final items = (resp['items'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
      final total = resp['total'] as int? ?? items.length;
      if (mounted) {
        setState(() { _events = items; _eventTotal = total; });
      }
    } catch (_) {}
  }

  String _greeting() {
    final hour = DateTime.now().hour;
    if (hour < 6) return '夜深了';
    if (hour < 12) return '上午好';
    if (hour < 18) return '下午好';
    return '晚上好';
  }

  void _openSourcesModal() {
    showDialog(
      useRootNavigator: true,
      context: context,
      builder: (_) => const SourcesModal(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
            : _buildContent(),
      ),
    );
  }

  Widget _buildContent() {
    return CustomScrollView(
      slivers: [
        // Header
        SliverToBoxAdapter(child: _buildHeader()),

        // Error
        if (_error != null)
          SliverToBoxAdapter(child: _buildError()),

        // Metric cards
        SliverToBoxAdapter(child: _buildMetricCards()),

        // Heatmap
        SliverToBoxAdapter(child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 0, 32, 16),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1152),
              child: const HeatmapChartWidget(),
            ),
          ),
        )),

        // AI Usage
        SliverToBoxAdapter(child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 0, 32, 16),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1152),
              child: const UsageWidget(),
            ),
          ),
        )),

        // Events list
        _events.isEmpty
            ? SliverToBoxAdapter(
                child: Container(
                  margin: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                  child: const Center(
                    child: Text('暂无事件', style: TextStyle(color: AppTheme.textMuted)),
                  ),
                ),
              )
            : SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, index) => _buildEventRow(_events[index]),
                  childCount: _events.length,
                ),
              ),

        // Pagination
        SliverToBoxAdapter(child: _buildPagination()),

        // Bottom spacing
        const SliverToBoxAdapter(child: SizedBox(height: 32)),
      ],
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.fromLTRB(32, 24, 32, 8),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: AppTheme.accent.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.dashboard, color: AppTheme.accent, size: 24),
          ),
          const SizedBox(width: 16),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _greeting(),
                style: const TextStyle(
                  color: AppTheme.textPrimary,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 2),
              const Text(
                '今天也是汲取智慧的一天',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 14),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildError() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32, vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.error.withOpacity(0.1),
        border: Border.all(color: AppTheme.error.withOpacity(0.2)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppTheme.error, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(_error!, style: const TextStyle(color: AppTheme.error, fontSize: 13)),
          ),
          TextButton(
            onPressed: _loadAll,
            child: const Text('重试', style: TextStyle(color: AppTheme.error, fontSize: 13)),
          ),
        ],
      ),
    );
  }

  Widget _buildMetricCards() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 24, 32, 16),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1152),
          child: Row(
            children: [
          Expanded(child: _MetricCard(
            icon: Icons.rss_feed,
            label: '信息源',
            value: '${_summary.sourcesEnabled}',
            subtitle: '已启用 RSS 源',
            color: AppTheme.cyan,
            onTap: () => _openSourcesModal(),
          )),
          const SizedBox(width: 16),
          Expanded(child: _MetricCard(
            icon: Icons.auto_awesome,
            label: '今日新增',
            value: '${_summary.todayNew}',
            subtitle: '内容采集 + 新增问题',
            color: AppTheme.purple,
          )),
          const SizedBox(width: 16),
          Expanded(child: _MetricCard(
            icon: Icons.upload_file,
            label: '内容采集',
            value: '${_summary.ingestTotal}',
            subtitle: '累计采集内容',
            color: AppTheme.rose,
          )),
          const SizedBox(width: 16),
          Expanded(child: _MetricCard(
            icon: Icons.lightbulb,
            label: '头脑风暴',
            value: '${_summary.brainstormTotal}',
            subtitle: '累计提出问题',
            color: AppTheme.amber,
          )),
          const SizedBox(width: 16),
          Expanded(child: _MetricCard(
            icon: Icons.checklist,
            label: '待办事务',
            value: '${_summary.taskTotal}',
            subtitle: '${_summary.taskTodo} 待处理 · ${_summary.taskOverdue} 逾期',
            color: AppTheme.blue,
          )),
        ],
          ),
        ),
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 16, 32, 8),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1152),
          child: Text(
            title,
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEventRow(Map<String, dynamic> event) {
    final title = (event['title'] as String?) ?? '(无标题)';
    final source = (event['source_name'] as String?) ?? '';
    final createdAt = (event['created_at'] as String?) ?? '';
    final eventId = event['id'];

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32, vertical: 1),
      decoration: const BoxDecoration(
        color: AppTheme.panel,
        border: Border(bottom: BorderSide(color: AppTheme.border, width: 0.5)),
      ),
      child: InkWell(
        onTap: () {
          // Navigate to event detail
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AppTheme.textPrimary,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        if (source.isNotEmpty)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppTheme.panelActive.withOpacity(0.5),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              source,
                              style: const TextStyle(color: AppTheme.textMuted, fontSize: 11),
                            ),
                          ),
                        if (source.isNotEmpty && createdAt.isNotEmpty) const SizedBox(width: 8),
                        if (createdAt.isNotEmpty)
                          Text(
                            _formatDate(createdAt),
                            style: const TextStyle(color: AppTheme.textMuted, fontSize: 11),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppTheme.textMuted, size: 18),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPagination() {
    final totalPages = (_eventTotal / _eventPageSize).ceil();
    if (totalPages <= 1) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      decoration: const BoxDecoration(
        color: AppTheme.panel,
        border: Border(top: BorderSide(color: AppTheme.border)),
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(12),
          bottomRight: Radius.circular(12),
        ),
      ),
      child: Row(
        children: [
          Text(
            '共 $_eventTotal 条',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
          ),
          const Spacer(),
          IconButton(
            onPressed: _eventPage > 1 ? () => _loadEvents(_eventPage - 1) : null,
            icon: const Icon(Icons.chevron_left, size: 16),
            color: AppTheme.textSecondary,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
          ),
          Text(
            '$_eventPage / $totalPages',
            style: const TextStyle(color: AppTheme.textMuted, fontSize: 12),
          ),
          IconButton(
            onPressed: _eventPage < totalPages ? () => _loadEvents(_eventPage + 1) : null,
            icon: const Icon(Icons.chevron_right, size: 16),
            color: AppTheme.textSecondary,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
          ),
        ],
      ),
    );
  }

  String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso).add(const Duration(hours: 8));
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      return iso;
    }
  }
}

// ---- 指标卡片 ----
class _MetricCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final String subtitle;
  final Color color;
  final VoidCallback? onTap;

  const _MetricCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.subtitle,
    required this.color,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        border: Border.all(color: AppTheme.border),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: color),
              const SizedBox(width: 8),
              Text(label, style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            value,
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 28,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text(subtitle, style: const TextStyle(color: AppTheme.textMuted, fontSize: 11)),
        ],
      ),
      ),
    );
  }
}
