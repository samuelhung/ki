import Foundation

/// 知几特权 Helper 入口
/// 创建一个 XPC Mach Service Listener，等待主 App 连接
class HelperMain {
    static func main() {
        let delegate = ZhijiHelperDelegate()
        let listener = NSXPCListener(machServiceName: "com.zhiji.zhijiDesktop.helper")

        listener.delegate = delegate
        listener.resume()

        // 保持 run loop 运行
        RunLoop.current.run()
    }
}

HelperMain.main()
