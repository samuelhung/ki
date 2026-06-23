import Cocoa
import FlutterMacOS

/// XPC 协议（与 Helper/ZhijiHelperProtocol.swift 保持一致）
@objc protocol ZhijiHelperProtocol {
    func replaceAppBinary(
        sourcePath: String,
        destinationPath: String,
        withReply reply: @escaping (Bool, String?) -> Void
    )
    func getVersion(withReply reply: @escaping (String) -> Void)
}

/// 知几 Helper 插件：注册 Flutter MethodChannel，管理 XPC 连接
class ZhijiHelperPlugin: NSObject, FlutterPlugin {
    private var helperConnection: NSXPCConnection?
    private let helperMachName = "com.zhiji.zhijiDesktop.helper"

    static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(
            name: "com.zhiji.helper",
            binaryMessenger: registrar.messenger
        )
        let instance = ZhijiHelperPlugin()
        registrar.addMethodCallDelegate(instance, channel: channel)
    }

    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "installHelper":
            installHelper(result: result)

        case "replaceAppBinary":
            guard let args = call.arguments as? [String: String],
                  let source = args["source"],
                  let destination = args["destination"] else {
                result(FlutterError(code: "INVALID_ARGS", message: "需要 source 和 destination", details: nil))
                return
            }
            replaceAppBinary(source: source, destination: destination, result: result)

        case "helperInstalled":
            result(helperInstalled())

        case "getHelperVersion":
            getHelperVersion(result: result)

        default:
            result(FlutterMethodNotImplemented)
        }
    }

    // MARK: - Helper 安装（osascript 一次授权，之后 XPC 静默）

    private func helperInstalled() -> Bool {
        let helperPath = "/Library/PrivilegedHelperTools/\(helperMachName)"
        let plistPath = "/Library/LaunchDaemons/\(helperMachName).plist"
        return FileManager.default.fileExists(atPath: helperPath) &&
               FileManager.default.fileExists(atPath: plistPath)
    }

    /// 找到 App bundle 内嵌的 Helper 路径
    private func bundledHelperPath() -> String? {
        guard let appPath = Bundle.main.bundlePath as String? else { return nil }
        let helperPath = "\(appPath)/Contents/Library/LaunchServices/\(helperMachName)"
        return FileManager.default.fileExists(atPath: helperPath) ? helperPath : nil
    }

    private func installHelper(result: @escaping FlutterResult) {
        if helperInstalled() {
            setupHelperConnection()
            result(true)
            return
        }

        guard let bundledHelper = bundledHelperPath() else {
            result(FlutterError(code: "HELPER_MISSING", message: "App 内未找到 Helper", details: nil))
            return
        }

        // 用 osascript 提权执行安装脚本（一次弹窗）
        let helperDest = "/Library/PrivilegedHelperTools/\(helperMachName)"
        let plistDest = "/Library/LaunchDaemons/\(helperMachName).plist"
        let plistContent = launchdPlistContent()

        // 构建安装脚本：复制 helper + 写入 plist + 加载 launchd
        let script = """
        mkdir -p /Library/PrivilegedHelperTools
        cp -f '\(bundledHelper)' '\(helperDest)'
        chmod 755 '\(helperDest)'
        cat > '\(plistDest)' << 'PLISTEOF'
        \(plistContent)
        PLISTEOF
        chmod 644 '\(plistDest)'
        launchctl unload '\(plistDest)' 2>/dev/null || true
        launchctl load '\(plistDest)'
        """

        let task = Process()
        task.launchPath = "/usr/bin/osascript"
        task.arguments = ["-e", "do shell script \"\(script.replacingOccurrences(of: "\"", with: "\\\""))\" with administrator privileges with prompt \"知几需要权限来安装更新助手（仅此一次）\""]

        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe

        do {
            try task.run()
            task.waitUntilExit()

            if task.terminationStatus == 0 {
                // 稍等片刻让 launchd 启动 helper
                Thread.sleep(forTimeInterval: 0.5)
                setupHelperConnection()
                result(true)
            } else {
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8) ?? ""
                if output.contains("-60005") || output.contains("cancel") {
                    result(FlutterError(code: "USER_CANCELLED", message: "用户取消了授权", details: nil))
                } else {
                    result(FlutterError(code: "INSTALL_FAILED", message: "Helper 安装失败", details: output))
                }
            }
        } catch {
            result(FlutterError(code: "INSTALL_ERROR", message: error.localizedDescription, details: nil))
        }
    }

    /// 生成 launchd plist 内容
    private func launchdPlistContent() -> String {
        let helperPath = "/Library/PrivilegedHelperTools/\(helperMachName)"
        return """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>\(helperMachName)</string>
            <key>MachServices</key>
            <dict>
                <key>\(helperMachName)</key>
                <true/>
            </dict>
            <key>ProgramArguments</key>
            <array>
                <string>\(helperPath)</string>
            </array>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <true/>
        </dict>
        </plist>
        """
    }

    // MARK: - XPC

    private func setupHelperConnection() {
        helperConnection?.invalidate()
        helperConnection = nil
        guard helperInstalled() else { return }

        let connection = NSXPCConnection(
            machServiceName: helperMachName,
            options: .privileged
        )
        connection.remoteObjectInterface = NSXPCInterface(with: ZhijiHelperProtocol.self)
        connection.invalidationHandler = { [weak self] in
            print("[Helper] XPC 连接断开")
            self?.helperConnection = nil
        }
        connection.resume()
        helperConnection = connection
    }

    private func getHelperProxy(result: @escaping FlutterResult) -> ZhijiHelperProtocol? {
        if helperConnection == nil { setupHelperConnection() }
        guard let connection = helperConnection else {
            result(FlutterError(code: "HELPER_NOT_INSTALLED", message: "Helper 未安装", details: nil))
            return nil
        }
        let proxy = connection.remoteObjectProxyWithErrorHandler { error in
            print("[Helper] XPC 错误: \(error.localizedDescription)")
        }
        guard let helper = proxy as? ZhijiHelperProtocol else {
            result(FlutterError(code: "XPC_FAILED", message: "无法连接 Helper", details: nil))
            return nil
        }
        return helper
    }

    // MARK: - Operations

    private func replaceAppBinary(source: String, destination: String, result: @escaping FlutterResult) {
        guard let helper = getHelperProxy(result: result) else { return }
        helper.replaceAppBinary(sourcePath: source, destinationPath: destination) { success, errorMsg in
            DispatchQueue.main.async {
                if success {
                    result(true)
                } else {
                    result(FlutterError(code: "REPLACE_FAILED", message: errorMsg ?? "替换失败", details: nil))
                }
            }
        }
    }

    private func getHelperVersion(result: @escaping FlutterResult) {
        guard let helper = getHelperProxy(result: result) else { return }
        helper.getVersion { version in
            DispatchQueue.main.async { result(version) }
        }
    }
}

@main
class AppDelegate: FlutterAppDelegate {
    override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
}
