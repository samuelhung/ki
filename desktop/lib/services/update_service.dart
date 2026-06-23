import 'dart:io';
import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:path/path.dart' as p;

/// 桌面端增量更新服务
class UpdateService {
  static final UpdateService _instance = UpdateService._();
  factory UpdateService() => _instance;
  UpdateService._();

  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 120),
  ))
    ..httpClientAdapter = _createAdapter();

  static IOHttpClientAdapter _createAdapter() {
    return IOHttpClientAdapter(
      createHttpClient: () {
        final client = HttpClient();
        // 信任所有证书（仅用于 GitHub API — macOS 沙箱可能不走系统信任库）
        client.badCertificateCallback = (_, __, ___) => true;
        return client;
      },
    );
  }

  static const String _repo = 'samuelhung/ki';
  static const String _apiLatest =
      'https://api.github.com/repos/$_repo/releases/latest';

  /// 从 GitHub Releases 获取最新版本 tag
  Future<String?> _getLatestTag() async {
    try {
      final resp = await _dio.get(
        _apiLatest,
        options: Options(headers: {
          'Accept': 'application/vnd.github+json',
          'User-Agent': 'zhiji-desktop-updater',
        }),
      );
      final data = resp.data as Map<String, dynamic>;
      return data['tag_name'] as String?;
    } catch (e) {
      print('[Update] _getLatestTag 失败: $e');
      return null;
    }
  }

  /// 构建 Release asset 直链 URL（避免 /latest/download/ 的重定向缓存问题）
  String _assetUrl(String tag, String filename) {
    return 'https://github.com/$_repo/releases/download/$tag/$filename';
  }

  /// 检查更新
  Future<UpdateCheckResult> checkForUpdates(String currentVersion) async {
    try {
      // 1. 先获取最新版本 tag（API）
      final tag = await _getLatestTag();
      if (tag == null) {
        return UpdateCheckResult.error('无法获取最新版本信息');
      }

      final remoteVersion = tag.replaceFirst('v', '');

      // 2. 比较版本
      if (_compareVersions(remoteVersion, currentVersion) <= 0) {
        return UpdateCheckResult.upToDate(version: remoteVersion);
      }

      // 3. 下载 manifest.json（直链）
      final manifestResp = await _dio.get(_assetUrl(tag, 'manifest.json'));
      final remote = manifestResp.data as Map<String, dynamic>;
      final remoteHash = remote['app_hash'] as String? ?? '';

      return UpdateCheckResult.hasUpdate(
        version: remoteVersion,
        hash: remoteHash,
        tag: tag,
        patches: (remote['patches'] as List<dynamic>?)
                ?.cast<Map<String, dynamic>>() ??
            [],
      );
    } catch (e) {
      return UpdateCheckResult.error(e.toString());
    }
  }

  /// 下载补丁并应用
  Future<bool> downloadAndApplyPatch(
      Map<String, dynamic> patch, String tag) async {
    final patchUrl = patch['url'] as String;
    final downloadUrl = patchUrl.startsWith('http')
        ? patchUrl
        : _assetUrl(tag, patchUrl);

    final tmpDir = Directory.systemTemp.createTempSync('zhiji_update_');
    try {
      // 下载补丁
      final patchFile = File(p.join(tmpDir.path, 'update.bsdiff'));
      await _dio.download(downloadUrl, patchFile.path);

      // 找到当前 App.framework/App
      final appPath = _findAppFrameworkBinary();
      if (appPath == null) {
        print('[Update] 找不到 App.framework/App');
        return false;
      }

      // 备份当前文件
      final backupPath = '$appPath.bak';
      await File(appPath).copy(backupPath);

      // 应用 bspatch
      final newPath = '$appPath.new';
      final result = await Process.run('bspatch', [
        appPath,
        newPath,
        patchFile.path,
      ]);

      if (result.exitCode != 0) {
        print('[Update] bspatch 失败: ${result.stderr}');
        // 恢复备份
        await File(backupPath).rename(appPath);
        return false;
      }

      // 替换文件
      await File(newPath).rename(appPath);

      // 清理
      tmpDir.deleteSync(recursive: true);

      return true;
    } catch (e) {
      print('[Update] 更新失败: $e');
      try {
        tmpDir.deleteSync(recursive: true);
      } catch (_) {}
      return false;
    }
  }

  /// 重启应用
  Future<void> restartApp() async {
    // macOS: 用 open 命令重新启动 .app
    if (Platform.isMacOS) {
      final appPath = _findAppBundlePath();
      if (appPath != null) {
        await Process.start('open', ['-n', appPath]);
        exit(0);
      }
    }
  }

  /// 找到 App.framework/App 的路径
  String? _findAppFrameworkBinary() {
    final appPath = _findAppBundlePath();
    if (appPath == null) return null;
    final frameworkPath = p.join(
      appPath,
      'Contents',
      'Frameworks',
      'App.framework',
      'Versions',
      'A',
      'App',
    );
    return File(frameworkPath).existsSync() ? frameworkPath : null;
  }

  /// 找到 .app bundle 路径
  String? _findAppBundlePath() {
    // 从可执行文件路径向上找 .app（必须用 resolvedExecutable，不能用 Directory.current）
    var dir = Directory(File(Platform.resolvedExecutable).parent.path);
    while (dir.path != '/' && !dir.path.endsWith('.app')) {
      dir = Directory(p.dirname(dir.path));
    }
    return dir.path.endsWith('.app') ? dir.path : null;
  }

  /// 简单语义版本比较
  int _compareVersions(String a, String b) {
    final aParts = _parseVersion(a);
    final bParts = _parseVersion(b);
    for (var i = 0; i < 3; i++) {
      if (aParts[i] > bParts[i]) return 1;
      if (aParts[i] < bParts[i]) return -1;
    }
    return 0;
  }

  List<int> _parseVersion(String v) {
    final parts = v.split('.').map((s) => int.tryParse(s) ?? 0).toList();
    while (parts.length < 3) {
      parts.add(0);
    }
    return parts;
  }
}

class UpdateCheckResult {
  final bool hasUpdate;
  final String? newVersion;
  final String? newHash;
  final String? tag;
  final List<Map<String, dynamic>> patches;
  final String? error;

  UpdateCheckResult._({
    required this.hasUpdate,
    this.newVersion,
    this.newHash,
    this.tag,
    this.patches = const [],
    this.error,
  });

  factory UpdateCheckResult.upToDate({String? version}) =>
      UpdateCheckResult._(hasUpdate: false, newVersion: version);

  factory UpdateCheckResult.hasUpdate({
    required String version,
    required String hash,
    required String tag,
    required List<Map<String, dynamic>> patches,
  }) =>
      UpdateCheckResult._(
        hasUpdate: true,
        newVersion: version,
        newHash: hash,
        tag: tag,
        patches: patches,
      );

  factory UpdateCheckResult.error(String msg) =>
      UpdateCheckResult._(hasUpdate: false, error: msg);
}
