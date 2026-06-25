import 'dart:async';
import 'dart:io' as io;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';
import 'package:url_launcher/url_launcher.dart';

const _backendUrl = 'http://127.0.0.1:9120';
const _healthUrl = '$_backendUrl/api/health';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (!kIsWeb) {
    await windowManager.ensureInitialized();

    const minSize = Size(1440, 700);
    await windowManager.setMinimumSize(minSize);
    await windowManager.setSize(const Size(1440, 900));
    await windowManager.center();
    await windowManager.setTitle('知几');

    // 关闭按钮 → 隐藏到托盘
    await windowManager.setPreventClose(true);

    await windowManager.show();

    // 托盘
    await trayManager.setIcon('assets/icon.png');
    await trayManager.setToolTip('知几');
    final menu = Menu(
      items: [
        MenuItem(
          key: 'show',
          label: '显示知几',
        ),
        MenuItem(
          key: 'quit',
          label: '退出知几',
        ),
      ],
    );
    await trayManager.setContextMenu(menu);
  }

  runApp(const ZhijiShell());
}

class ZhijiShell extends StatefulWidget {
  const ZhijiShell({super.key});

  @override
  State<ZhijiShell> createState() => _ZhijiShellState();
}

class _ZhijiShellState extends State<ZhijiShell> with TrayListener, WindowListener {
  InAppWebViewController? _webView;
  bool _backendOnline = false;
  bool _checking = true;
  Timer? _healthTimer;

  @override
  void initState() {
    super.initState();
    if (!kIsWeb) {
      trayManager.addListener(this);
      windowManager.addListener(this);
    }
    _checkBackend();
    _healthTimer = Timer.periodic(const Duration(seconds: 15), (_) => _checkBackend());
  }

  @override
  void dispose() {
    _healthTimer?.cancel();
    if (!kIsWeb) {
      trayManager.removeListener(this);
      windowManager.removeListener(this);
    }
    super.dispose();
  }

  // ---- 后端健康检查 ----
  Future<void> _checkBackend() async {
    try {
      final client = io.HttpClient();
      client.connectionTimeout = const Duration(seconds: 3);
      final req = await client.getUrl(Uri.parse(_healthUrl));
      final resp = await req.close().timeout(const Duration(seconds: 3));
      final online = resp.statusCode == 200;
      if (mounted) {
        setState(() { _backendOnline = online; _checking = false; });
      }
      client.close();
    } catch (_) {
      if (mounted) {
        setState(() { _backendOnline = false; _checking = false; });
      }
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

  // ---- 托盘事件 ----
  @override
  void onTrayMenuItemClick(MenuItem menuItem) {
    switch (menuItem.key) {
      case 'show':
        windowManager.show();
        windowManager.focus();
        break;
      case 'quit':
        trayManager.destroy();
        if (!kIsWeb) windowManager.destroy();
        break;
    }
  }

  @override
  void onTrayIconMouseDown() {
    windowManager.show();
    windowManager.focus();
  }

  // ---- 窗口事件 ----
  @override
  void onWindowClose() {
    // 最小化到托盘而不是退出
    windowManager.hide();
  }

  // ---- WebView 创建 ----
  InAppWebViewSettings get _webViewSettings => InAppWebViewSettings(
    javaScriptEnabled: true,
    domStorageEnabled: true,
    allowsInlineMediaPlayback: true,
    mediaPlaybackRequiresUserGesture: false,
    useShouldOverrideUrlLoading: true,
    // 允许文件访问（拖放导入用）
    allowFileAccessFromFileURLs: true,
    allowUniversalAccessFromFileURLs: true,
  );

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
        body: Stack(
          children: [
            // ---- WebView 内容 ----
            Positioned.fill(
              child: InAppWebView(
                initialUrlRequest: URLRequest(url: WebUri(_backendUrl)),
                initialSettings: _webViewSettings,
                onWebViewCreated: (controller) {
                  _webView = controller;

                  // JS Bridge: 注册 handler 供 Web 前端调用
                  controller.addJavaScriptHandler(
                    handlerName: 'openUrl',
                    callback: (args) {
                      if (args.isNotEmpty) {
                        launchUrl(Uri.parse(args[0].toString()));
                      }
                    },
                  );
                },
                onLoadStop: (controller, url) async {
                  // 注入后端状态
                  controller.evaluateJavascript(
                    source: 'window.__zhijiBackendStatus = $_backendOnline;',
                  );
                },
                shouldOverrideUrlLoading: (controller, navigationAction) async {
                  final uri = navigationAction.request.url;
                  if (uri != null) {
                    final scheme = uri.scheme;
                    // 拦截外部链接
                    if (scheme == 'mailto' || scheme == 'tel') {
                      final launched = await launchUrl(uri);
                      return NavigationActionPolicy.CANCEL;
                    }
                    // 拦截 http/https 外部域（非本地、非 VPN）
                    if ((scheme == 'http' || scheme == 'https') &&
                        uri.host != '127.0.0.1' &&
                        uri.host != 'localhost' &&
                        !uri.host.startsWith('10.8.')) {
                      await launchUrl(uri);
                      return NavigationActionPolicy.CANCEL;
                    }
                  }
                  return NavigationActionPolicy.ALLOW;
                },
              ),
            ),

            // ---- 后端离线提示 ----
            if (!_checking && !_backendOnline)
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: Container(
                  color: const Color(0xE6D97706),
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.wifi_off, size: 14, color: Colors.white),
                      const SizedBox(width: 8),
                      const Text(
                        '后端未连接 — 部分功能不可用',
                        style: TextStyle(color: Colors.white, fontSize: 12),
                      ),
                      const SizedBox(width: 12),
                      GestureDetector(
                        onTap: _startBackend,
                        child: const Text(
                          '启动',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 12,
                            decoration: TextDecoration.underline,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

            // ---- 启动加载 ----
            if (_checking)
              const Positioned.fill(
                child: ColoredBox(
                  color: Color(0xFF0B0C10),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '知几',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 28,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 4,
                          ),
                        ),
                        SizedBox(height: 12),
                        SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation(Color(0xFFA78BFA)),
                          ),
                        ),
                        SizedBox(height: 16),
                        Text(
                          '正在连接后端...',
                          style: TextStyle(color: Color(0xFF6B7280), fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
