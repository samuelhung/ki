import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

class KnowledgeGraphPage extends StatelessWidget {
  const KnowledgeGraphPage({super.key});

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
                  const Icon(Icons.account_tree, color: AppTheme.cyan, size: 24),
                  const SizedBox(width: 12),
                  const Text('知识图谱', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
            const Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.hub, size: 48, color: AppTheme.textMuted),
                    SizedBox(height: 12),
                    Text('知识图谱视图', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
                    SizedBox(height: 4),
                    Text('实体关系可视化（开发中）', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
