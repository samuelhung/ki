import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;

/// 桌面端本地配置服务
/// 配置文件: ~/.zhiji/desktop_config.json
class ConfigService {
  static const _configFileName = 'desktop_config.json';

  static Future<File> _configFile() async {
    final home = Platform.environment['HOME'] ??
        Platform.environment['USERPROFILE'] ??
        '.';
    final zhijiDir = Directory(p.join(home, '.zhiji'));
    if (!await zhijiDir.exists()) {
      await zhijiDir.create(recursive: true);
    }
    return File(p.join(zhijiDir.path, _configFileName));
  }

  /// 读取完整配置
  static Future<Map<String, dynamic>> load() async {
    final file = await _configFile();
    if (await file.exists()) {
      try {
        return jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      } catch (_) {}
    }
    return <String, dynamic>{};
  }

  /// 保存完整配置
  static Future<void> save(Map<String, dynamic> config) async {
    final file = await _configFile();
    await file.writeAsString(
      const JsonEncoder.withIndent('  ').convert(config),
    );
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
