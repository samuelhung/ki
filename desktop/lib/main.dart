import 'dart:async';
import 'dart:convert';
import 'dart:io' as io;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';
import 'package:url_launcher/url_launcher.dart';

// ── 默认后端地址 + config 文件 ──
const _defaultBackendUrl = 'http://127.0.0.1:9120';
const _desktopVersion = '1.3.6';
final _configFile = io.File('${io.Platform.environment['HOME']}/.zhiji/config.json');

String _loadBackendUrl() {
  try {
    if (_configFile.existsSync()) {
      final data = jsonDecode(_configFile.readAsStringSync()) as Map<String, dynamic>;
      final url = data['backend_url'] as String?;
      if (url != null && url.isNotEmpty) return url;
    }
  } catch (_) {}
  return _defaultBackendUrl;
}

void _saveBackendUrl(String url) {
  _configFile.parent.createSync(recursive: true);
  var data = <String, dynamic>{};
  try {
    if (_configFile.existsSync()) {
      data = jsonDecode(_configFile.readAsStringSync()) as Map<String, dynamic>;
    }
  } catch (_) {}
  data['backend_url'] = url;
  _configFile.writeAsStringSync(jsonEncode(data));
}

// ── App 入口 ──
void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (!kIsWeb) {
    await windowManager.ensureInitialized();
    const minSize = Size(1440, 700);
    await windowManager.setMinimumSize(minSize);
    await windowManager.setSize(const Size(1440, 900));
    await windowManager.center();
    await windowManager.setTitle('知几');
    await windowManager.setPreventClose(true);
    await windowManager.show();

    try {
      final execDir = io.File(io.Platform.resolvedExecutable).parent.parent.path;
      final iconPath = '$execDir/Resources/AppIcon.icns';
      if (io.File(iconPath).existsSync()) {
        await trayManager.setIcon(iconPath);
      }
    } catch (_) {}
    await trayManager.setToolTip('知几');
    await trayManager.setContextMenu(Menu(items: [
      MenuItem(key: 'show', label: '显示知几'),
      MenuItem(key: 'quit', label: '退出知几'),
    ]));
  }

  runApp(const ZhijiShell());
}

// ── Shell Widget ──
class ZhijiShell extends StatefulWidget {
  const ZhijiShell({super.key});
  @override
  State<ZhijiShell> createState() => _ZhijiShellState();
}

class _ZhijiShellState extends State<ZhijiShell> with TrayListener, WindowListener {
  WebViewController? _webCtrl;
  String _backendUrl = _loadBackendUrl();
  bool _backendOnline = false;
  bool _checking = true;
  Timer? _healthTimer;
  static const _sparkleChannel = MethodChannel('com.zhiji.sparkle');
  final _urlController = TextEditingController();

  @override
  void initState() {
    super.initState();
    if (!kIsWeb) {
      trayManager.addListener(this);
      windowManager.addListener(this);
    }
    _urlController.text = _backendUrl;
    // 首次启动（无配置文件）→ 跳过健康检查，直接进连接设置页
    if (_hasConfig()) {
      _checkBackend();
      _healthTimer = Timer.periodic(const Duration(seconds: 15), (_) => _checkBackend());
    } else {
      setState(() { _checking = false; });
    }
  }

  bool _hasConfig() {
    try {
      return _configFile.existsSync();
    } catch (_) {
      return false;
    }
  }

  @override
  void dispose() {
    _healthTimer?.cancel();
    _urlController.dispose();
    if (!kIsWeb) {
      trayManager.removeListener(this);
      windowManager.removeListener(this);
    }
    super.dispose();
  }

  // ── 后端健康检查 ──
  Future<void> _checkBackend() async {
    final healthUrl = '$_backendUrl/api/health';
    try {
      final client = io.HttpClient();
      client.connectionTimeout = const Duration(seconds: 3);
      final req = await client.getUrl(Uri.parse(healthUrl));
      final resp = await req.close().timeout(const Duration(seconds: 3));
      final online = resp.statusCode == 200;
      if (mounted) setState(() { _backendOnline = online; _checking = false; });
      client.close();
    } catch (_) {
      if (mounted) setState(() { _backendOnline = false; _checking = false; });
    }
  }

  Future<void> _startBackend() async {
    setState(() { _checking = true; });
    try {
      await io.Process.run('launchctl', ['start', 'com.zhiji.backend']);
      await Future.delayed(const Duration(seconds: 3));
      await _checkBackend();
    } catch (_) {}
  }

  Future<void> _applyUrl() async {
    final url = _urlController.text.trim();
    if (url.isEmpty) return;
    final fixed = url.startsWith('http') ? url : 'http://$url';
    _saveBackendUrl(fixed);
    _backendUrl = fixed;
    _webCtrl = null;
    setState(() { _checking = true; });
    await _checkBackend();
    if (_backendOnline) {
      _initWebView();
      setState(() {});
    }
  }

  // ── 托盘 ──
  @override
  void onTrayMenuItemClick(MenuItem item) {
    switch (item.key) {
      case 'show':
        windowManager.show();
        windowManager.focus();
      case 'quit':
        trayManager.destroy();
        if (!kIsWeb) windowManager.destroy();
    }
  }

  @override
  void onTrayIconMouseDown() {
    windowManager.show();
    windowManager.focus();
  }

  @override
  void onWindowClose() => windowManager.hide();

  Uri _webViewUri() {
    final uri = Uri.parse(_backendUrl);
    final params = Map<String, String>.from(uri.queryParameters)
      ..['desktop_version'] = _desktopVersion
      ..['cache_bust'] = DateTime.now().millisecondsSinceEpoch.toString();
    return uri.replace(queryParameters: params);
  }

  // ── WebView (macOS: 不调 setBackgroundColor，避免 setOpaque bug) ──
  void _initWebView() {
    late final WebViewController ctrl;
    ctrl = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onNavigationRequest: (request) {
          final uri = Uri.tryParse(request.url);
          if (uri == null) return NavigationDecision.navigate;
          if (uri.host != '127.0.0.1' &&
              uri.host != 'localhost' &&
              !uri.host.startsWith('10.8.') &&
              (uri.scheme == 'http' || uri.scheme == 'https')) {
            launchUrl(uri);
            return NavigationDecision.prevent;
          }
          return NavigationDecision.navigate;
        },
        onPageFinished: (_) {
          ctrl.runJavaScript('window.__zhijiBackendStatus = true;');
        },
      ))
      ..addJavaScriptChannel('zhiji_openUrl',
        onMessageReceived: (msg) {
          final uri = Uri.tryParse(msg.message);
          if (uri != null) launchUrl(uri);
        },
      )
      ..addJavaScriptChannel('zhiji_checkUpdates',
        onMessageReceived: (_) async {
          try {
            await _sparkleChannel.invokeMethod('checkForUpdates');
          } catch (_) {}
        },
      );
    _webCtrl = ctrl;
    () async {
      try {
        await ctrl.clearCache();
        await ctrl.clearLocalStorage();
      } catch (_) {}
      await ctrl.loadRequest(_webViewUri());
    }();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '知几',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0B0C10),
      ),
      home: Scaffold(
        body: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_checking) {
      return Container(
        color: const Color(0xFF0B0C10),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('知几', style: TextStyle(
                color: Colors.white, fontSize: 28, fontWeight: FontWeight.w600, letterSpacing: 4,
              )),
              const SizedBox(height: 16),
              const SizedBox(
                width: 24, height: 24,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation(Color(0xFFA78BFA)),
                ),
              ),
              const SizedBox(height: 16),
              Text('正在连接 $_backendUrl ...',
                style: const TextStyle(color: Color(0xFF6B7280), fontSize: 13),
              ),
            ],
          ),
        ),
      );
    }

    if (_backendOnline) {
      if (_webCtrl == null) _initWebView();
      return WebViewWidget(controller: _webCtrl!);
    }

    return _offlineScreen();
  }

  Widget _offlineScreen() {
    return Container(
      color: const Color(0xFF0B0C10),
      child: Center(
        child: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off, size: 56, color: Color(0xFF6B7280)),
              const SizedBox(height: 24),
              const Text('无法连接到知几后端',
                style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Text('当前后端地址: $_backendUrl',
                style: const TextStyle(color: Color(0xFF9CA3AF), fontSize: 14),
              ),
              const SizedBox(height: 32),
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: const Color(0xFF1F2937),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFF374151)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('后端地址',
                      style: TextStyle(color: Color(0xFFD1D5DB), fontSize: 13, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _urlController,
                            style: const TextStyle(color: Colors.white, fontSize: 14),
                            decoration: InputDecoration(
                              hintText: 'http://127.0.0.1:9120',
                              hintStyle: const TextStyle(color: Color(0xFF4B5563)),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                              filled: true,
                              fillColor: const Color(0xFF111827),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: const BorderSide(color: Color(0xFF374151)),
                              ),
                              enabledBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: const BorderSide(color: Color(0xFF374151)),
                              ),
                              focusedBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: const BorderSide(color: Color(0xFFA78BFA)),
                              ),
                            ),
                            onSubmitted: (_) => _applyUrl(),
                          ),
                        ),
                        const SizedBox(width: 10),
                        SizedBox(
                          height: 42,
                          child: ElevatedButton(
                            onPressed: _applyUrl,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: const Color(0xFFA78BFA),
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            ),
                            child: const Text('连接', style: TextStyle(fontWeight: FontWeight.w600)),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'MacBook Pro 后端地址: http://10.8.0.105:9120',
                      style: TextStyle(color: Colors.grey[600], fontSize: 12),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  OutlinedButton.icon(
                    onPressed: _startBackend,
                    icon: const Icon(Icons.play_arrow, size: 18),
                    label: const Text('启动本机后端'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFFD1D5DB),
                      side: const BorderSide(color: Color(0xFF374151)),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                  ),
                  const SizedBox(width: 12),
                  OutlinedButton.icon(
                    onPressed: _checkBackend,
                    icon: const Icon(Icons.refresh, size: 18),
                    label: const Text('重试'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFFD1D5DB),
                      side: const BorderSide(color: Color(0xFF374151)),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
