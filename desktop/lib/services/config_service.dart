import 'dart:convert';
import 'dart:io' as io;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path/path.dart' as p;

/// 桌面端本地配置服务（Web 端降级为内存存储）
/// 配置文件: ~/.zhiji/desktop_config.json
class ConfigService {
  static const _configFileName = 'desktop_config.json';
  static Map<String, dynamic>? _webCache;

  /// Web 降级：内存存储
  static Map<String, dynamic> get _memoryStore {
    _webCache ??= <String, dynamic>{};
    return _webCache!;
  }

  static Future<Map<String, dynamic>> load() async {
    if (kIsWeb) return Map<String, dynamic>.from(_memoryStore);

    try {
      final home = io.Platform.environment['HOME'] ??
          io.Platform.environment['USERPROFILE'] ?? '.';
      final file = io.File(p.join(home, '.zhiji', _configFileName));
      if (await file.exists()) {
        return jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      }
    } catch (_) {}
    return <String, dynamic>{};
  }

  static Future<void> save(Map<String, dynamic> config) async {
    if (kIsWeb) {
      _memoryStore
        ..clear()
        ..addAll(config);
      return;
    }

    try {
      final home = io.Platform.environment['HOME'] ??
          io.Platform.environment['USERPROFILE'] ?? '.';
      final zhijiDir = io.Directory(p.join(home, '.zhiji'));
      if (!await zhijiDir.exists()) {
        await zhijiDir.create(recursive: true);
      }
      final file = io.File(p.join(zhijiDir.path, _configFileName));
      await file.writeAsString(
        const JsonEncoder.withIndent('  ').convert(config),
      );
    } catch (_) {}
  }

  /// 读取后端地址，默认 http://127.0.0.1:9120
  static Future<String> getBackendUrl() async {
    final config = await load();
    return config['backend_url'] as String? ?? 'http://127.0.0.1:9120';
  }

  /// 保存后端地址
  static Future<void> setBackendUrl(String url) async {
    final config = await load();
    config['backend_url'] = url;
    await save(config);
  }
}
