import 'package:flutter/material.dart';
import '../../services/api_client.dart';
import '../../theme/app_theme.dart';

class TasksPage extends StatefulWidget {
  const TasksPage({super.key});
  @override
  State<TasksPage> createState() => _TasksPageState();
}

class _TasksPageState extends State<TasksPage> {
  List<Map<String, dynamic>> _tasks = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadTasks();
  }

  Future<void> _loadTasks() async {
    setState(() { _loading = true; _error = null; });
    try {
      final api = ApiClient();
      final resp = await api.getTasks(offset: 0, limit: 200);
      if (mounted) {
        setState(() {
          _tasks = (resp['items'] as List<dynamic>?)?.cast<Map<String, dynamic>>() ?? [];
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() { _error = e.toString(); _loading = false; });
    }
  }

  String _statusLabel(String? status) {
    switch (status) {
      case 'todo': return '待处理';
      case 'in_progress': return '进行中';
      case 'done': return '已完成';
      default: return status ?? '未知';
    }
  }

  Color _statusColor(String? status) {
    switch (status) {
      case 'todo': return AppTheme.sky;
      case 'in_progress': return AppTheme.amber;
      case 'done': return AppTheme.emerald;
      default: return AppTheme.textMuted;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(32, 24, 32, 16),
              child: Row(
                children: [
                  const Icon(Icons.checklist, color: AppTheme.sky, size: 24),
                  const SizedBox(width: 12),
                  const Text('待办事务', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text('${_tasks.length} 项', style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                ],
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.accent))
                  : _error != null
                      ? Center(child: Text(_error!, style: const TextStyle(color: AppTheme.error)))
                      : _tasks.isEmpty
                          ? const Center(child: Text('暂无事务', style: TextStyle(color: AppTheme.textMuted)))
                          : ListView.builder(
                              padding: const EdgeInsets.symmetric(horizontal: 32),
                              itemCount: _tasks.length,
                              itemBuilder: (_, i) => _buildTaskRow(_tasks[i]),
                            ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTaskRow(Map<String, dynamic> t) {
    final title = t['title'] as String? ?? '(无标题)';
    final status = t['status'] as String?;
    final priority = t['priority'] as String?;

    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.border, width: 0.5),
      ),
      child: Row(
        children: [
          Container(
            width: 8, height: 8,
            decoration: BoxDecoration(
              color: _statusColor(status),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 14)),
          ),
          const SizedBox(width: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: _statusColor(status).withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              _statusLabel(status),
              style: TextStyle(color: _statusColor(status), fontSize: 11, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}
