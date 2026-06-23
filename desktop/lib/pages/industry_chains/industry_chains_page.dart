import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

class IndustryChainsPage extends StatelessWidget {
  const IndustryChainsPage({super.key});

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
                  const Icon(Icons.link, color: AppTheme.emerald, size: 24),
                  const SizedBox(width: 12),
                  const Text('产业链', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
            const Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.account_tree_outlined, size: 48, color: AppTheme.textMuted),
                    SizedBox(height: 12),
                    Text('产业链 DAG 视图', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
                    SizedBox(height: 4),
                    Text('上下游关系可视化（开发中）', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
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
