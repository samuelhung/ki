# 工具箱 — 贷款利率换算器

## 目标
KI 新增「工具箱」独立模块，首期上线贷款利率换算器。

## 功能
- 正向：金额 + 期数 + 月分期利率 → 月供、总利息、名义年化、IRR真实年化、名义/实际月息厘
- 反向：金额 + 期数 + 月供 → 推算月分期利率、IRR真实年化、实际月息厘
- 对比表格：销售说的 vs 真实成本，差异用红/绿色高亮
- 一句话人话总结
- 实时计算（onChange 触发，不点按钮）
- IRR 牛顿迭代，精度 0.000001，结果保留 2 位小数

## 文件
- `app/frontend/src/pages/Toolbox.tsx` — 新页面
- `app/frontend/src/App.tsx` — +路由
- `app/frontend/src/components/Sidebar.tsx` — +导航入口
- `app/frontend/src/components/BottomTabBar.tsx` — +移动端入口
- `app/frontend/src/style.css` — +样式（如有特殊需要）

## 技术
- 纯前端 JS 计算，无需后端
- IRR 牛顿迭代法：f(r) = 月供/PV * (1 - (1+r)^-n) - r = 0
- 正向：直接算月供；反向：二分法求月利率
- 精度保留 2 位小数，显示时 `toFixed(2)`
