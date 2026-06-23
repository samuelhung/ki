import 'dart:convert';
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
      final data = resp.data;
      if (data is! Map<String, dynamic>) {
        print('[Update] _getLatestTag: 响应类型异常 (${data.runtimeType})，无法解析');
        return null;
      }
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

      // 3. 下载 manifest.json（手动 JSON 解析，绕过重定向后 responseType 丢失的问题）
      final manifestResp = await _dio.get(
        _assetUrl(tag, 'manifest.json'),
        options: Options(responseType: ResponseType.plain),
      );
      final body = manifestResp.data;
      if (body is! String) {
        print('[Update] manifest.json 响应类型异常: ${body.runtimeType}');
        return UpdateCheckResult.error('manifest.json 响应异常');
      }
      final remote = jsonDecode(body);
      if (remote is! Map<String, dynamic>) {
        print('[Update] manifest.json 解析后非 Map: ${remote.runtimeType}');
        return UpdateCheckResult.error('manifest.json 格式异常');
      }
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
      Map<String, dynamic> patch, String tag,
      {void Function(String)? onLog}) async {
    final patchUrl = patch['url'] as String;
    final downloadUrl = patchUrl.startsWith('http')
        ? patchUrl
        : _assetUrl(tag, patchUrl);

    final tmpDir = Directory.systemTemp.createTempSync('zhiji_update_');
    try {
      _plog(onLog, '临时目录: ${tmpDir.path}');

      // 下载补丁（绕过 Dio 直接用 HttpClient — Dio 在沙箱 302 重定向后可能挂起不返回）
      final patchFile = File(p.join(tmpDir.path, 'update.bsdiff'));
      final expectedSize = patch['size'] as int? ?? 0;
      _plog(onLog, '开始下载补丁: $downloadUrl (预期 ${(expectedSize / 1024).toStringAsFixed(0)} KB)');

      final client = HttpClient()..badCertificateCallback = (_, __, ___) => true;
      try {
        final request = await client.getUrl(Uri.parse(downloadUrl));
        final response = await request.close().timeout(const Duration(seconds: 120));
        _plog(onLog, '服务端响应: ${response.statusCode}');
        final bytes = await response
            .fold<List<int>>(<int>[], (prev, chunk) => prev..addAll(chunk))
            .timeout(const Duration(seconds: 120));
        client.close();

        _plog(onLog, '下载完成: ${bytes.length} 字节 (${(bytes.length / 1024).toStringAsFixed(0)} KB)');
        if (bytes.isEmpty) {
          _plog(onLog, '下载数据为空 (statusCode=${response.statusCode})');
          return false;
        }
        if (expectedSize > 0 && bytes.length != expectedSize) {
          _plog(onLog, '下载大小不匹配: 预期 $expectedSize, 实际 ${bytes.length}');
          return false;
        }
        await patchFile.writeAsBytes(bytes);
        _plog(onLog, '补丁已写入: ${patchFile.path}');
      } catch (e) {
        client.close();
        throw e;
      }

      // 找到当前 App.framework/App
      final appPath = _findAppFrameworkBinary();
      if (appPath == null) {
        _plog(onLog, '找不到 App.framework/App');
        return false;
      }
      _plog(onLog, 'App 二进制路径: $appPath');

      // 备份当前文件
      final backupPath = '$appPath.bak';
      await File(appPath).copy(backupPath);
      _plog(onLog, '已备份到: $backupPath');

      // 应用 bspatch
      final newPath = '$appPath.new';
      _plog(onLog, '执行 bspatch $appPath $newPath ${patchFile.path}');
      final result = await Process.run('bspatch', [
        appPath,
        newPath,
        patchFile.path,
      ]);
      _plog(onLog, 'bspatch exitCode=${result.exitCode}');

      if (result.exitCode != 0) {
        _plog(onLog, 'bspatch stderr: ${result.stderr}');
        _plog(onLog, 'bspatch stdout: ${result.stdout}');
        // 检查新文件是否部分写入
        try {
          final newFile = File(newPath);
          if (newFile.existsSync()) {
            _plog(onLog, '新文件部分存在: ${newFile.lengthSync()} 字节');
          }
        } catch (_) {}
        // 恢复备份
        await File(backupPath).rename(appPath);
        _plog(onLog, '已恢复备份');
        return false;
      }

      // 替换文件
      final newFile = File(newPath);
      _plog(onLog, '新 App 二进制大小: ${newFile.lengthSync()} 字节');
      await newFile.rename(appPath);
      _plog(onLog, '已替换 App 二进制');

      // 清理
      tmpDir.deleteSync(recursive: true);
      _plog(onLog, '补丁应用完成');

      return true;
    } catch (e, stack) {
      _plog(onLog, '更新失败: $e');
      _plog(onLog, '堆栈: $stack');
      try {
        tmpDir.deleteSync(recursive: true);
      } catch (_) {}
      return false;
    }
  }

  void _plog(void Function(String)? onLog, String msg) {
    print('[Update] $msg');
    onLog?.call(msg);
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
