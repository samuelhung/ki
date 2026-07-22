import Cocoa
import FlutterMacOS
import Sparkle

@main
class AppDelegate: FlutterAppDelegate {
    private var sparkleUpdater: SPUStandardUpdaterController?
    private var sparkleChannel: FlutterMethodChannel?

    override func applicationDidFinishLaunching(_ notification: Notification) {
        // 初始化 Sparkle 自动更新
        sparkleUpdater = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )

        // 注册 Flutter 可调用的 Sparkle 方法
        if let controller = mainFlutterWindow?.contentViewController as? FlutterViewController {
            sparkleChannel = FlutterMethodChannel(
                name: "com.zhiji.sparkle",
                binaryMessenger: controller.engine.binaryMessenger
            )
            sparkleChannel?.setMethodCallHandler { [weak self] (call, result) in
                switch call.method {
                case "checkForUpdates":
                    self?.sparkleUpdater?.checkForUpdates(nil)
                    result(true)
                default:
                    result(FlutterMethodNotImplemented)
                }
            }
        }

        super.applicationDidFinishLaunching(notification)
    }
    // 托盘模式：关闭窗口不退出应用
    override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false
    }

    // Dock 图标被点击时，恢复被关闭按钮隐藏或最小化到 Dock 的窗口
    override func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        for window in NSApp.windows {
            if window.isMiniaturized {
                window.deminiaturize(self)
            }
            if !window.isVisible {
                window.setIsVisible(true)
            }
            window.makeKeyAndOrderFront(self)
        }
        NSApp.activate(ignoringOtherApps: true)
        return true
    }

    override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
}
