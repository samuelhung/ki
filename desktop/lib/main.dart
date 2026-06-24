import 'dart:io' as io;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:window_manager/window_manager.dart'
    if (dart.library.html) 'services/window_stub.dart';
import 'theme/app_theme.dart';
import 'router/app_router.dart';
import 'services/api_client.dart';

/// 全局更新管理器 — 桌面端通过 Sparkle MethodChannel 驱动原生更新
/// Web 端仅提供占位，不执行实际操作
class UpdateManager extends ChangeNotifier {
  static final UpdateManager _instance = UpdateManager._();
  factory UpdateManager() => _instance;
  UpdateManager._();

  String _status = 'idle';
  String _message = '就绪';
  final List<String> _logs = [];
  double _percent = 0;

  String? get remoteVersion => null;
  String get version => _bundleVersion;
  String get status => _status;
  String get message => _message;
  List<String> get logs => _logs;
  double get percent => _percent;
  bool get isBusy =>
      _status == 'checking' || _status == 'downloading' || _status == 'installing';

  /// 版本号：桌面端读 Info.plist，Web 端返回固定值
  static String get _bundleVersion {
    if (kIsWeb) return '1.0.0';
    try {
      final exePath = io.Platform.resolvedExecutable;
      final appIdx = exePath.indexOf('.app/');
      if (appIdx == -1) return '0.0.0';
      final plistPath = '${exePath.substring(0, appIdx + 4)}/Contents/Info.plist';
      final result = io.Process.runSync(
          'defaults', ['read', plistPath, 'CFBundleShortVersionString']);
      if (result.exitCode == 0) return result.stdout.toString().trim();
    } catch (_) {}
    return '0.0.0';
  }

  /// 触发更新检查（仅桌面端有效；Web 端空操作）
  Future<void> checkForUpdates() async {
    if (kIsWeb || isBusy) return;

    _status = 'checking';
    _message = '正在检查更新...';
    _logs.clear();
    notifyListeners();

    try {
      const channel = MethodChannel('com.zhiji.sparkle');
      final result = await channel.invokeMethod('checkForUpdates');
      if (result == 'up-to-date') {
        _status = 'latest';
        _message = '已是最新版本';
        _logs.add('✓ 已是最新版本');
      } else if (result == 'update-available') {
        _status = 'sparkle';
        _message = 'Sparkle 已接管更新流程';
        _logs.add('✓ 发现新版本，由 Sparkle 接管');
      } else {
        _status = 'sparkle';
        _message = '检查完成';
        _logs.add('✓ Sparkle 更新检查已触发');
      }
    } catch (e) {
      _status = 'error';
      _message = '检查失败: ${e.toString()}';
      _logs.add('✗ $message');
    }
    notifyListeners();
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await ApiClient().initialize();

  if (!kIsWeb) {
    await windowManager.ensureInitialized();
    await windowManager.setTitle('知几');
    await windowManager.setSize(const Size(1280, 800));
    await windowManager.setMinimumSize(const Size(1440, 700));
    await windowManager.center();
    await windowManager.show();
  }

  runApp(const ProviderScope(child: ZhijiApp()));
}

class ZhijiApp extends StatelessWidget {
  const ZhijiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: '知几',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.darkTheme,
      routerConfig: appRouter,
    );
  }
}
