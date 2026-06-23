import 'dart:convert';
import 'dart:io';
import 'package:intl/intl.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:window_manager/window_manager.dart';
import 'theme/app_theme.dart';
import 'router/app_router.dart';
import 'services/update_service.dart';
import 'services/api_client.dart';

/// 全局更新管理器 — 供 system_doc_page 手动触发
class UpdateManager extends ChangeNotifier {
  static final UpdateManager _instance = UpdateManager._();
  factory UpdateManager() => _instance;
  UpdateManager._();

  String _version = '...';

  String get version => _version;

  String _status = 'idle'; // idle | checking | latest | downloading | installing | error
  String _message = '';
  double _percent = 0;
  String? _remoteVersion;
  final List<String> _logs = [];

  String? get remoteVersion => _remoteVersion;
  List<String> get logs => List.unmodifiable(_logs);

  String get status => _status;
  String get message => _message;
  double get percent => _percent;
  bool get isBusy => _status == 'checking' || _status == 'downloading' || _status == 'installing';

  void _addLog(String msg) {
    final ts = DateFormat('HH:mm:ss').format(DateTime.now());
    _logs.add('[$ts] $msg');
    notifyListeners();
  }

  Future<void> checkForUpdates() async {
    if (isBusy) return;

    _logs.clear();
    _status = 'checking';
    _message = '正在检查更新...';
    _remoteVersion = null;
    notifyListeners();

    try {
      _addLog('⏳ 步骤 1/4: 读取本地版本号...');
      final currentVersion = _readAppVersion();
      _version = currentVersion;
      _addLog('   本地版本: v$currentVersion');
      print('[UPDATE] 当前版本: $currentVersion');

      _addLog('⏳ 步骤 2/4: 查询 GitHub 最新版本...');
      final result = await UpdateService().checkForUpdates(currentVersion);
      _remoteVersion = result.newVersion;
      if (result.error != null) {
        _addLog('   ✗ 查询失败: ${result.error}');
      } else if (_remoteVersion != null) {
        _addLog('   远程最新: v$_remoteVersion');
      }
      print('[UPDATE] 远程版本: $_remoteVersion, hasUpdate: ${result.hasUpdate}, error: ${result.error}');

      if (!result.hasUpdate || result.patches.isEmpty) {
        if (result.error != null) {
          _addLog('✗ 检查出错');
          _status = 'error';
          _message = result.error!;
        } else {
          _addLog('✓ 当前已是最新版本，无需更新');
          _status = 'latest';
          _message = '已是最新版本';
        }
        notifyListeners();
        return;
      }

      _addLog('✓ 发现新版本 v${result.newVersion}');
      _addLog('   可用补丁: ${result.patches.length} 个');

      final match = result.patches.firstWhere(
        (p) => p['from_version'] == _version,
        orElse: () => result.patches.first,
      );
      final patchFrom = match['from_version'] ?? '?';
      final patchSize = match['size'] ?? 0;

      _addLog('⏳ 步骤 3/4: 下载补丁');
      _addLog('   来源: v$patchFrom → v${result.newVersion}');
      _addLog('   大小: ${(patchSize / 1024).toStringAsFixed(0)} KB');

      _status = 'downloading';
      _message = '发现 v${result.newVersion}，下载中...';
      notifyListeners();

      final ok = await UpdateService().downloadAndApplyPatch(
          match, result.tag!,
          onLog: _addLog,
      );

      if (ok) {
        _addLog('✓ 步骤 4/4: 补丁应用成功');
        _addLog('   即将重启...');
        _status = 'installing';
        _message = '更新完成，即将重启...';
        notifyListeners();
        await Future.delayed(const Duration(milliseconds: 500));
        await UpdateService().restartApp();
      } else {
        _addLog('✗ 补丁应用失败');
        _status = 'error';
        _message = '更新失败，请重试';
        notifyListeners();
      }
    } catch (e) {
      _addLog('✗ 异常: ${e.toString().length > 80 ? '\${e.toString().substring(0, 80)}...' : e}');
      _status = 'error';
      _message = e.toString().length > 60 ? '\${e.toString().substring(0, 60)}...' : e.toString();
      notifyListeners();
    }
  }
}

/// 从 macOS app bundle 的 Info.plist 读取版本号
String _readAppVersion() {
  if (Platform.isMacOS) {
    try {
      // Platform.resolvedExecutable -> .../zhiji_desktop.app/Contents/MacOS/zhiji_desktop
      var dir = Directory(File(Platform.resolvedExecutable).parent.path);
      while (dir.path != '/' && !dir.path.endsWith('.app')) {
        dir = dir.parent;
      }
      if (dir.path.endsWith('.app')) {
        final plistPath = '${dir.path}/Contents/Info.plist';
        final result = Process.runSync(
            'plutil', ['-convert', 'json', '-o', '-', plistPath],
            runInShell: true);
        if (result.exitCode == 0) {
          final plist =
              jsonDecode(result.stdout as String) as Map<String, dynamic>;
          return plist['CFBundleShortVersionString'] as String? ?? '0.0.0';
        }
      }
    } catch (_) {}
  }
  return '0.0.0';
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await ApiClient().initialize();

  await windowManager.ensureInitialized();
  await windowManager.setTitle('知几');
  await windowManager.setSize(const Size(1280, 800));
  await windowManager.setMinimumSize(const Size(900, 600));
  await windowManager.center();
  await windowManager.show();

  runApp(const ProviderScope(child: ZhijiApp()));

  // 后台自动检查更新（不依赖后端连通性）
  UpdateManager().checkForUpdates();
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
