import Foundation

/// 知几特权 Helper：以 root 身份运行，响应主 App 的 XPC 请求
class ZhijiHelper: NSObject, ZhijiHelperProtocol {

    /// 用 root 权限执行文件替换
    func replaceAppBinary(
        sourcePath: String,
        destinationPath: String,
        withReply reply: @escaping (Bool, String?) -> Void
    ) {
        let fm = FileManager.default

        // 安全校验：源文件必须存在
        guard fm.fileExists(atPath: sourcePath) else {
            reply(false, "源文件不存在: \(sourcePath)")
            return
        }

        // 安全校验：目标路径必须在 .app bundle 内
        guard destinationPath.contains(".app/") else {
            reply(false, "目标路径不在 .app bundle 内: \(destinationPath)")
            return
        }

        do {
            // 备份旧文件
            let backupPath = destinationPath + ".bak"
            if fm.fileExists(atPath: backupPath) {
                try fm.removeItem(atPath: backupPath)
            }
            if fm.fileExists(atPath: destinationPath) {
                try fm.copyItem(atPath: destinationPath, toPath: backupPath)
            }

            // 删除旧文件，复制新文件
            if fm.fileExists(atPath: destinationPath) {
                try fm.removeItem(atPath: destinationPath)
            }
            try fm.copyItem(atPath: sourcePath, toPath: destinationPath)

            // 设置可执行权限
            try fm.setAttributes(
                [.posixPermissions: 0o755],
                ofItemAtPath: destinationPath
            )

            reply(true, nil)
        } catch {
            reply(false, "替换失败: \(error.localizedDescription)")
        }
    }

    /// 返回 Helper 版本号
    func getVersion(withReply reply: @escaping (String) -> Void) {
        reply("1.0.0")
    }
}

/// XPC Listener Delegate
class ZhijiHelperDelegate: NSObject, NSXPCListenerDelegate {
    func listener(
        _ listener: NSXPCListener,
        shouldAcceptNewConnection newConnection: NSXPCConnection
    ) -> Bool {
        // 设置允许的接口
        newConnection.exportedInterface = NSXPCInterface(
            with: ZhijiHelperProtocol.self
        )
        newConnection.exportedObject = ZhijiHelper()

        // 安全策略：要求调用方也实现相同协议（双向校验）
        newConnection.remoteObjectInterface = NSXPCInterface(
            with: ZhijiHelperProtocol.self
        )

        newConnection.resume()
        return true
    }
}
