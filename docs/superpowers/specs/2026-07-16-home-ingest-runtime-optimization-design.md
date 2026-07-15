# 首页与内容采集常驻运行时优化设计

## 目标

在不改变首页与内容采集现有视觉、布局和交互的前提下，建立可复用的常驻电影化页面运行时，并降低内容采集的重复渲染、无效请求和后台资源消耗。

本轮覆盖：

- `/#/` 首页
- `/#/ingest` 内容采集
- 两页共用的顶部导航、GooeyNav、搜索入口、底部 Dock 和 Three.js 背景

旧版验收路由继续保留，不纳入常驻运行时。

## 成功标准

1. 首页与内容采集之间切换时不销毁并重建 WebGL Renderer。
2. 当前背景、首页一秒点亮、文字刷出和 GooeyNav 粒子效果保持一致。
3. 浏览器切到后台时停止渲染，恢复后时间基准正常，不出现白光或高速旋转。
4. 内容采集搜索不再逐字请求，过期列表响应不能覆盖新结果。
5. 处理队列关闭且没有活跃处理任务时，不进行三秒轮询。
6. 搜索、弹窗输入、详情 Tab 和队列状态变化不再导致全部列表行重绘。
7. 当前场景测试、构建和 2560x1440、1440x900、1180x820 视觉基线通过。

## 方案选择

采用常驻共享壳与单 Renderer、多场景运行时。

不采用双 Canvas 常驻方案，因为它会增加 GPU 内存和 WebGL Context 数量；不采用仅请求优化方案，因为它无法解决页面切换时场景销毁重建和大组件渲染边界问题。

## 架构

### 共享路由壳

新增 `KiCinematicRouteShell`，作为首页和内容采集的 React Router 父路由。它持有：

- 顶部品牌与主导航
- 顶部搜索插槽
- 底部全局 Dock
- 全局操作弹窗层
- 常驻 `CinematicBackdropHost`
- 当前子页面的 `Outlet`

首页和内容采集只渲染各自的中部舞台内容。两页切换时共享壳不卸载，因此导航、Dock、Canvas 和 WebGL Renderer 保持稳定。

### 常驻背景运行时

将 `CinematicScene.tsx` 中 500 多行的场景创建和帧循环拆成两个边界：

- `CinematicBackdropHost.tsx`：React 生命周期、路由配置、Canvas、可见性和 Context 恢复。
- `cinematicSceneRuntime.ts`：Renderer、Scene、Camera、Geometry、Material、帧更新和资源释放。

Host 只创建一个 `THREE.WebGLRenderer`。运行时按 `today`、`ingest` 配置懒创建并缓存场景对象，路由切换时只切换当前 Scene 和 Camera，不重新创建 Renderer。

每个场景运行时暴露：

```ts
interface CinematicSceneRuntime {
  resize(width: number, height: number, pixelRatio: number): void;
  update(deltaSeconds: number, elapsedSeconds: number, pointer: PointerState): void;
  render(renderer: THREE.WebGLRenderer): void;
  resetClock(): void;
  dispose(): void;
}
```

首页仍使用 `today` 配置，内容采集仍使用 `ingest + laserPrimary` 配置。粒子数量、强度、位置、颜色和最大帧率保持现值。

### 生命周期与恢复

- `document.hidden` 时取消帧调度，不保留空转的 RAF。
- 页面恢复时重置时钟，不累计后台时间。
- Canvas 不可见或尺寸为零时暂停渲染。
- 监听 `webglcontextlost`，阻止默认销毁流程并停止帧循环。
- 监听 `webglcontextrestored`，重建 Renderer 和缓存场景。
- Provider 卸载时统一释放 Geometry、Material、Texture 和 Renderer。
- ResizeObserver 只观察常驻 Canvas，不再同时绑定重复的 window resize 处理。

### 首页动画边界

首页点亮与文字刷出继续属于 DOM/CSS 页面动画，不写入 Three.js 运行时：

- 背景点亮：1 秒
- 文字刷出：背景完成后开始，0.5 秒
- 返回首页时通过页面内容挂载重新播放
- WebGL Renderer 和 Scene 不重建

这保证动画可重播，同时避免用重建 GPU 资源模拟页面入场。

## 内容采集拆分

`Ingest.tsx` 保留业务编排和旧版非嵌入布局，新增以下嵌入式组件：

- `EmbeddedIngestWorkspace.tsx`：左右舞台组合和搜索 Portal。
- `EmbeddedIngestTopicTabs.tsx`：格局、财富、认知、前瞻和快报切换。
- `EmbeddedIngestList.tsx`：加载、错误、空状态和事件列表。
- `EmbeddedBriefingList.tsx`：即时快报列表。
- `EmbeddedIngestRow.tsx`：单条内容，使用 `React.memo`。

列表行接收稳定的标量属性和稳定回调，不直接接收整个 `details` 对象。选中项变化时只更新旧选中行与新选中行。

详情区继续复用 `ContentDetailPanel`，但通过 `useMemo` 构造 Tab 和动作参数，避免表单输入导致详情树无意义重建。

## 请求与数据流

### 搜索

- 输入状态即时更新。
- 使用现有 `useDebouncedValue`，延迟 250 毫秒请求。
- 查询依赖改为 `historyTab + page + debouncedSearch`。
- 每次列表请求生成序号；只有最新序号可以更新列表、总数、错误和加载状态。
- 切换分类或搜索时重置页码，但不清空当前详情，除非当前选中项已不在新结果中。

### 统计

统计数据在页面首次加载时请求一次。只有提交、上传、删除、采集完成等会改变统计的动作才主动刷新，不再随搜索和翻页重复请求。

### 处理队列

- 打开队列弹窗时立即请求。
- 队列弹窗打开，或当前存在 `pending/running` 任务时，每三秒轮询。
- 弹窗关闭且没有活跃任务时停止轮询。
- 页面隐藏时停止轮询，恢复后按当前条件决定是否立即刷新。
- 保留现有删除墓碑和连续删除保护逻辑。

### 详情请求

继续使用现有请求序号防止旧详情覆盖新详情。组件拆分后，列表更新不改变当前 `activeEventId` 时，不重新请求详情。

## GooeyNav

- 保留选中项挂载后生成 15 个粒子的行为。
- 粒子配置使用模块级常量，避免父组件更新时创建新数组。
- ResizeObserver 只在导航容器尺寸实际变化时更新特效位置。
- 组件卸载时清理粒子节点、Timeout 和待执行 RAF。

## 错误与空状态

- 常驻背景 Context 恢复失败时显示静态背景，不阻断页面功能。
- 列表请求失败保留当前成功数据，并显示可重试状态。
- 搜索结果为空与首次无内容使用不同文案。
- 队列轮询失败不清空现有任务，下一轮继续尝试。

## 测试

### 单元与组合测试

- 首页和内容采集属于同一个共享路由壳。
- 页面切换不卸载 `CinematicBackdropHost`。
- 场景运行时只创建一个 Renderer，并能切换缓存 Scene。
- hidden、context lost 和 restore 正确暂停、恢复和释放。
- 搜索使用 250 毫秒防抖，旧响应不能覆盖新响应。
- 统计不跟随搜索和分页请求。
- 队列轮询满足开启和停止条件。
- 嵌入式列表行使用 memo，并接收稳定回调。

### 浏览器验证

- 首页到内容采集往返十次，WebGL Context 数量保持不变。
- 观察 Canvas backing size、当前最大帧率和粒子数量符合场景配置。
- 后台停留一分钟后恢复，球体速度正常且无白光。
- 搜索连续输入中文时只产生一次最终列表请求。
- 关闭队列弹窗且无活跃任务时，十秒内没有队列请求。
- 2560x1440、1440x900、1180x820 截图无布局和视觉回归。

## 实施顺序

1. 建立性能与生命周期回归测试。
2. 提取 Three.js 场景运行时。
3. 建立共享路由壳并迁移首页、内容采集。
4. 保持首页 CSS 动画与当前时序一致。
5. 拆分内容采集嵌入式组件。
6. 收敛搜索、统计和队列请求。
7. 完整测试、构建、浏览器性能验证和多尺寸截图。

## 非目标

- 不改变首页或内容采集的视觉设计。
- 不修改旧版验收页面。
- 不在本轮迁移系统中枢等其他页面到共享路由壳。
- 不更换 Three.js 或引入新的渲染框架。
- 不改变后端 API 契约。
