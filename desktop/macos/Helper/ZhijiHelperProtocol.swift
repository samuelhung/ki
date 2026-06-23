import Foundation

/// XPC 协议：知几特权 Helper 暴露给主 App 的接口
@objc protocol ZhijiHelperProtocol {
    /// 用 root 权限替换 App 二进制文件（用于增量更新）
    /// - Parameters:
    ///   - sourcePath: 新二进制的临时路径（bspatch 输出）
    ///   - destinationPath: /Applications/知几.app 内的目标路径
    ///   - reply: (成功标志, 错误描述)
    func replaceAppBinary(
        sourcePath: String,
        destinationPath: String,
        withReply reply: @escaping (Bool, String?) -> Void
    )

    /// 获取 Helper 自身版本（调试用）
    func getVersion(withReply reply: @escaping (String) -> Void)
}
