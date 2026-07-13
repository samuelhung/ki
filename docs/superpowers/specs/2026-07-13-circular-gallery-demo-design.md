# Circular Gallery Demo Design

## Goal

在 KI 前端增加独立的 Circular Gallery 演示页，视觉与交互参考 React Bits Circular Gallery，并固定使用 `borderRadius=0.1`、`scrollSpeed=2.7`、`scrollEase=0.12`。

## Scope

- 独立路由 `/#/demo/circular-gallery`，不接入业务数据和导航菜单。
- 使用项目已有 `ogl`，不增加运行时依赖。
- 支持滚轮、触控板、鼠标拖拽、触摸拖拽、惯性缓动和无限循环。
- 使用稳定的演示图片与短标题，图片加载失败时显示可读占位色。
- 全屏画廊作为第一视觉，不放入卡片容器。
- 保持当前业务页面和远端 API 行为不变。

## Architecture

- `CircularGallery.tsx` 管理 OGL renderer、camera、geometry、media planes、输入事件和动画循环。
- `CircularGalleryDemo.tsx` 只负责全屏页面、演示数据和参数传递。
- `circular-gallery.css` 负责固定画布尺寸、标题文字和响应式边界。
- 组件在页面不可见时暂停动画，并限制恢复后的帧增量，避免后台切回出现高速旋转。

## Verification

- 单元测试约束循环位置计算、插值和路由组成。
- `npm run build` 必须通过。
- 在 `2560x1440`、`1440x900`、`1180x820` 检查画布非空、画廊居中、文字不溢出。
- 用浏览器验证滚轮后画廊位置发生变化，拖拽结束后平滑减速。
