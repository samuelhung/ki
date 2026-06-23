import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

class IngestPage extends StatelessWidget {
  const IngestPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(32),
          children: [
            Row(
              children: [
                const Icon(Icons.upload_file, color: AppTheme.emerald, size: 24),
                const SizedBox(width: 12),
                const Text('内容采集', style: TextStyle(color: AppTheme.textPrimary, fontSize: 20, fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 24),
            // Upload zone
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(40),
              decoration: BoxDecoration(
                color: AppTheme.panel,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.border, width: 1, strokeAlign: BorderSide.strokeAlignInside),
              ),
              child: Column(
                children: [
                  Container(
                    width: 64, height: 64,
                    decoration: BoxDecoration(
                      color: AppTheme.emerald.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(Icons.cloud_upload_outlined, size: 32, color: AppTheme.emerald),
                  ),
                  const SizedBox(height: 16),
                  const Text('拖放文件到此处导入', style: TextStyle(color: AppTheme.textPrimary, fontSize: 16, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 4),
                  const Text('支持音视频、文档、图片格式', style: TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: () {},
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('选择文件'),
                    style: FilledButton.styleFrom(
                      backgroundColor: AppTheme.accent,
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            // Supported formats
            _buildSection('支持格式', const [
              _FormatGroup('音频', Icons.mic, AppTheme.amber, 'MP3, WAV, M4A, AAC, OGG, FLAC'),
              _FormatGroup('视频', Icons.videocam, AppTheme.blue, 'MP4, MOV, AVI, MKV, WebM'),
              _FormatGroup('文档', Icons.description, AppTheme.purple, 'PDF, DOCX, TXT, MD, HTML, EPUB, MOBI'),
              _FormatGroup('图片', Icons.image, AppTheme.emerald, 'PNG, JPG, JPEG, WebP'),
            ]),
          ],
        ),
      ),
    );
  }

  Widget _buildSection(String title, List<_FormatGroup> groups) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.panel,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 15, fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          ...groups.map((g) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                Icon(g.icon, size: 16, color: g.color),
                const SizedBox(width: 8),
                SizedBox(width: 48, child: Text(g.label, style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13))),
                Expanded(child: Text(g.formats, style: const TextStyle(color: AppTheme.textMuted, fontSize: 12))),
              ],
            ),
          )),
        ],
      ),
    );
  }
}

class _FormatGroup {
  final String label;
  final IconData icon;
  final Color color;
  final String formats;
  const _FormatGroup(this.label, this.icon, this.color, this.formats);
}
