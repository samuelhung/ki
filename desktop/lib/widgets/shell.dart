import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../theme/app_theme.dart';
import '../services/api_client.dart';

// ---- 侧栏导航项 ----
class _NavItem {
  final String path;
  final IconData icon;
  final Color color;
  final String label;
  const _NavItem(this.path, this.icon, this.color, this.label);
}

const _navItems = [
  _NavItem('/', Icons.dashboard, AppTheme.blue, '仪表盘'),
  _NavItem('/ingest', Icons.upload_file, AppTheme.emerald, '内容采集'),
  _NavItem('/brainstorm', Icons.lightbulb, AppTheme.amber, '头脑风暴'),
  _NavItem('/series', Icons.layers, AppTheme.purple, '专题系列'),
  _NavItem('/knowledge-graph', Icons.account_tree, AppTheme.cyan, '知识图谱'),
  _NavItem('/chains', Icons.link, AppTheme.emerald, '产业链'),
  _NavItem('/tasks', Icons.checklist, AppTheme.sky, '待办事务'),
  _NavItem('/tools', Icons.build, AppTheme.orange, '工具箱'),
  _NavItem('/digest', Icons.article, AppTheme.rose, '摘要'),
  _NavItem('/study', Icons.school, AppTheme.amber, '辅导中心'),
];

// ---- 应用壳: 左侧栏 + 右侧内容 ----
class AppShell extends ConsumerStatefulWidget {
  final Widget child;
  const AppShell({super.key, required this.child});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _taskCount = 0;
  int _chainHintCount = 0;

  @override
  void initState() {
    super.initState();
    _loadBadges();
  }

  Future<void> _loadBadges() async {
    final api = ApiClient();
    try {
      final taskStats = await api.getTaskStats();
      final hintCount = await api.getChainHintsCount();
      if (mounted) {
        setState(() {
          _taskCount = (taskStats['todo'] as int?) ?? 0;
          _chainHintCount = (hintCount['pending'] as int?) ?? 0;
        });
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.toString();

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: Row(
        children: [
          // ---- 侧栏 ----
          Container(
            width: 272,
            color: AppTheme.panel,
            child: Column(
              children: [
                // Logo 区
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: const BoxDecoration(
                    border: Border(bottom: BorderSide(color: AppTheme.border)),
                  ),
                  child: const Column(
                    children: [
                      Text(
                        '知几',
                        style: TextStyle(
                          color: AppTheme.textPrimary,
                          fontSize: 24,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 2,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        '知几其神乎\n见微知著',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: AppTheme.textMuted,
                          fontSize: 10,
                          height: 1.3,
                        ),
                      ),
                      SizedBox(height: 4),
                    ],
                  ),
                ),

                // 导航区
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 16),
                    children: _navItems.map((item) {
                      final isActive = _isActive(location, item.path);
                      return _NavButton(
                        item: item,
                        isActive: isActive,
                        badge: item.path == '/tasks' && _taskCount > 0
                            ? '$_taskCount'
                            : item.path == '/chains' && _chainHintCount > 0
                                ? '$_chainHintCount'
                                : null,
                        badgeAnimating: item.path == '/chains' && _chainHintCount > 0,
                      );
                    }).toList(),
                  ),
                ),

                // 底部
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                  decoration: const BoxDecoration(
                    border: Border(top: BorderSide(color: AppTheme.border)),
                  ),
                  child: Column(
                    children: [
                      _NavButton(
                        item: const _NavItem('/settings', Icons.settings, AppTheme.textMuted, '系统设置'),
                        isActive: location == '/settings',
                      ),
                      const SizedBox(height: 4),
                      _NavButton(
                        item: const _NavItem('/system', Icons.menu_book, AppTheme.teal, '系统说明'),
                        isActive: location == '/system',
                      ),

                    ],
                  ),
                ),
              ],
            ),
          ),

          // 分割线
          const VerticalDivider(width: 1, color: AppTheme.border),

          // ---- 内容区 ----
          Expanded(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1152),
                child: widget.child,
              ),
            ),
          ),
        ],
      ),
    );
  }

  bool _isActive(String current, String target) {
    if (target == '/') return current == '/' || current == '';
    return current.startsWith(target);
  }
}

class _NavButton extends StatelessWidget {
  final _NavItem item;
  final bool isActive;
  final String? badge;
  final bool badgeAnimating;

  const _NavButton({
    required this.item,
    required this.isActive,
    this.badge,
    this.badgeAnimating = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: InkWell(
        onTap: () => context.go(item.path),
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: isActive ? AppTheme.panelActive : null,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            children: [
              Icon(item.icon, size: 18, color: isActive ? item.color : AppTheme.textMuted),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  item.label,
                  style: TextStyle(
                    color: isActive ? AppTheme.textPrimary : AppTheme.textSecondary,
                    fontSize: 14,
                  ),
                ),
              ),
              if (badge != null)
                AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: badgeAnimating ? AppTheme.warning : AppTheme.error,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    badge!,
                    style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
