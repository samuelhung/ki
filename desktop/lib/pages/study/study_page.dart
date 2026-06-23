import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

class StudyPage extends StatelessWidget {
  const StudyPage({super.key});

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
                  const Icon(Icons.school, color: AppTheme.amber, size: 24),
                  const SizedBox(width: 12),
                  const Text('辅导中心', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
            const Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.menu_book, size: 48, color: AppTheme.textMuted),
                    SizedBox(height: 12),
                    Text('教材 OCR 与智能讲题', style: TextStyle(color: AppTheme.textMuted, fontSize: 14)),
                    SizedBox(height: 4),
                    Text('上传教材图片开始辅导', style: TextStyle(color: AppTheme.textMuted, fontSize: 12)),
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
