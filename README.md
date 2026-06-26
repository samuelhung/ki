# 知几

知几是一个本地优先的知识情报中心：把 RSS 情报、视频/音频/文档摄入、AI 摘要、专题系列、头脑风暴、综合事务、知识图谱和辅导中心整合到同一个桌面/Web 系统里。

## 当前架构

```text
macOS 知几.app
  → Flutter WebView 壳（窗口、托盘、连接设置、Sparkle 更新桥接）
    → React + Vite + Tailwind 前端
      → FastAPI 后端 :9120
        → SQLite + data/ 文件系统双写
```

- 桌面端是 Flutter WebView 壳，业务页面全部由 React 前端渲染。
- 后端由 launchd `com.zhiji.backend` 托管，开机自启并崩溃重启。
- Web 与 API 在生产形态共用 `:9120`；远程后端地址可配置为 `http://10.8.0.105:9120`。
- 自动更新使用 Sparkle 2：appcast 走 `raw.githubusercontent.com`，DMG 走 GitHub Release。
- 发布物只保留全量 DMG：不再使用 bsdiff、manifest.json、install_helper.sh。

## 核心模块

- 仪表盘：热力图、指标卡、事件总览。
- 内容采集：抖音/视频/音频/文档摄入，转写、总结、四类认知分类。
- RSS 情报：采集、翻译、即时快报、每日摘要。
- 专题系列：AI 聚类、候选审核、结构化总结、深度分析。
- 头脑风暴：人工录入问题、多文档综合回答、多轮追问、概念沉淀。
- 综合事务：手工事务输入、AI 结构化判断、关联内容展示。
- 知识图谱：实体关系提取、vis-network 可视化、实体深度分析。
- 辅导中心：教材 PDF 上传、逐课解读、孩子版/家长版/教材解读模式。
- 系统说明：架构、数据流、功能体系、版本更新、数据库、日志查看。

## 常用命令

```bash
# 后端
zhiji serve

# 前端开发
cd app/frontend && npm run dev

# 前端构建
cd app/frontend && npm run build

# 桌面端构建
export PATH="/Users/mrh/flutter/bin:$PATH"
cd desktop && flutter build macos --release

# 发布打包
cd /Users/mrh/Documents/Projects/zhiji
python3 scripts/build_release.py --skip-build
python3 scripts/release-check.py X.Y.Z
```

## 发布原则

功能性代码改动发版前必须同步：版本号、`desktop/changelog.json`、系统说明/架构文档、前端构建版本 hash、Flutter WebView `desktop_version`。发版后必须验证远端 appcast 首条与 GitHub Release asset 对齐，再做实机安装/更新提示验证。

## 重要约束

`data/` 目录下的视频、音频、文档、转写、摘要和脑暴记录不得随意删除；删除前必须先列出清单并等待确认。