import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)

    RegisterGeneratedPlugins(registry: flutterViewController)

    // 注册自定义 Helper 插件（SMJobBless + XPC）
    let registrar = flutterViewController.registrar(forPlugin: "ZhijiHelperPlugin")
    ZhijiHelperPlugin.register(with: registrar)

    super.awakeFromNib()
  }
}
