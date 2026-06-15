# HNGD 前端样式规范

## 布局

左侧边栏(220px) + 右侧主内容，`display:flex; height:100vh; overflow:hidden`。主内容背景 `#f2f6fa`。

---

## 配色

### 主色
| 用途 | 色值 |
|---|---|
| 品牌色 / 按钮 | `#2a5aa8` |
| 深色（悬停） | `#1e4a8a` |
| 标题强调 | `#1a3a7e` |

**侧边栏渐变**：`linear-gradient(180deg, #0f2a5e 0%, #1a3a7e 40%, #0d2050 100%)`  
**主按钮渐变**：`linear-gradient(135deg, #1a3a7e, #2a5aa8)`

### 文字
- 正文主色：`#1a2a4a`
- 次级/描述：`#7a8aaa` / `#8a9ab8`
- 占位符：`#b0bcd0`
- 链接/操作：`#2a5aa8`

### 背景
- 页面底色：`#f2f6fa`
- 卡片/输入：`white`
- 浅蓝区：`#eef2f8`
- AI 气泡：`#f4f7fc`

### 边框
- 卡片：`rgba(220,230,245,0.7)`
- 输入框：`#d0dae8` / `#d8e4f0`
- 分割线：`#f0f4f8`

### 功能色
成功 `#2a9a5a` · 警告 `#e06a20` · 危险 `#c0392b` · 紫色 `#7a42d8`

---

## 侧边栏

```css
width: 220px;
background: linear-gradient(180deg, #0f2a5e 0%, #1a3a7e 40%, #0d2050 100%);
box-shadow: 2px 0 16px rgba(10,30,80,0.18);
```

- **导航项**：`padding:9px 12px; border-radius:8px; color:rgba(255,255,255,0.6); font-size:13px`
  - 悬停：`rgba(255,255,255,0.08)` · 激活：`rgba(255,255,255,0.15); color:white`
- **新建对话按钮**：`border:1.5px dashed rgba(255,255,255,0.2); background:rgba(255,255,255,0.08)`
- **用户头像**：`32px` 圆形，`rgba(255,255,255,0.18)`
- **退出按钮**：`rgba(255,255,255,0.38)`，悬停变红

---

## 顶栏

```css
height: 56px; padding: 0 32px;
background: rgba(242,246,250,0.95); backdrop-filter: blur(8px);
border-bottom: 1px solid rgba(200,215,230,0.5);
position: sticky; top: 0;
```

---

## 卡片

```css
background: white; border-radius: 12px; padding: 24px;
border: 1px solid rgba(220,230,245,0.7);
box-shadow: 0 2px 8px rgba(26,58,110,0.04);
/* 悬停 */ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(26,58,110,0.1);
```

功能图标容器 `38×38px / border-radius:9px`，配色：蓝`#e8f0fc`·绿`#e8f8f0`·紫`#f0e8fc`·橙`#fff0e8`

---

## 输入框

```css
border: 1.5px solid #d8e4f4; border-radius: 7px;
padding: 9px 12px; font-size: 13.5px; color: #1a2a4a;
/* 聚焦 */ border-color: #2a5aa8; box-shadow: 0 0 0 3px rgba(42,90,168,0.1);
```

聊天输入框额外：`border-radius:12px; padding:14px 16px`

---

## 按钮

**主按钮**
```css
background: linear-gradient(135deg, #1a3a7e, #2a5aa8); color: white;
border-radius: 8px; padding: 8px 20px; font-weight: 600;
box-shadow: 0 2px 8px rgba(42,90,168,0.28);
/* 悬停 */ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(42,90,168,0.38);
```

**次要按钮**：`background:white; border:1.5px solid #d0dae8; color:#5a6a8a; border-radius:7px`  
**停止态**：`linear-gradient(135deg, #c0506a, #a8425a)`

---

## 消息气泡

| | AI | 用户 |
|---|---|---|
| 背景 | `#f4f7fc` | `linear-gradient(135deg,#1a3a7e,#2a5aa8)` |
| 圆角 | `4px 10px 10px 10px` | `10px 4px 10px 10px` |
| 边框 | `1px solid #e4ecf5` | 无 |
| 头像 | 蓝色渐变白字 | `#e8f0fc` 蓝字 |

---

## 模态框

```css
background: white; border-radius: 14px; width: 420px;
box-shadow: 0 8px 40px rgba(10,30,80,0.18);
/* 遮罩 */ background: rgba(10,30,80,0.32); backdrop-filter: blur(3px);
/* 入场 */ translateY(-14px) → translateY(0), 0.22s
```

表单反馈：错误`#fff0f0/#c0392b` · 成功`#f0fff6/#1a7a45` · 信息`#f0f5ff/#2a5aa8`

---

## 动画 & 过渡

- 通用悬停：`transition: all 0.2s`
- 快速：`0.15s`
- 弹性弹窗：`cubic-bezier(0.34, 1.18, 0.64, 1)`
- 模式切换滑块：`cubic-bezier(0.34, 1.15, 0.64, 1)`
- 滚动条：`scrollbar-width:thin; scrollbar-color:#d0dae8 transparent; width:3~4px`

---

## 字体 & 文字

字体栈：`'PingFang SC', 'Microsoft YaHei', '微软雅黑', sans-serif`

| 层级 | 大小 | 字重 |
|---|---|---|
| 页面标题 | `22px` | `700` |
| 区块/卡片标题 | `15~16px` | `600~700` |
| 正文/输入 | `13.5px` | `400~500` |
| 次要/辅助 | `12px` / `10~11px` | `400` |

---

## 其他组件

**Chip**：`border:1.5px solid #d8e4f0; border-radius:20px; padding:5px 13px; color:#3a5a8e`，悬停 `background:#e8f0fc`

**Toggle**：`44×24px; 激活色#2a5aa8; 轨道#d0dae8`

**上传区**：`border:2px dashed #d8e4f4; background:#f8fafd`，悬停 `border-color:#2a5aa8; background:#f0f5ff`

---

## 动效规范

主缓动曲线（回弹）：`cubic-bezier(0.34, 1.15, 0.64, 1)`  
入场时长 `0.35~0.62s` · hover/点击 `0.15~0.22s` · 背景循环 `26~32s`  
所有动画仅用 `transform` / `opacity`，零布局位移。

### 关键帧库
```css
@keyframes fadeInUp  { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
@keyframes fadeInX   { from { opacity:0; transform:translateX(-12px); } to { opacity:1; transform:translateX(0); } }
@keyframes cardPop   { from { opacity:0; transform:translateY(16px) scale(0.96); } to { opacity:1; transform:translateY(0) scale(1); } }
@keyframes msgInL    { from { opacity:0; transform:translateX(-14px) translateY(4px); } to { opacity:1; transform:translateX(0) translateY(0); } }
@keyframes msgInR    { from { opacity:0; transform:translateX(14px) translateY(4px); } to { opacity:1; transform:translateX(0) translateY(0); } }
@keyframes iconBounce{ 0%{transform:translateY(0);} 40%{transform:translateY(-5px) scale(1.08);} 70%{transform:translateY(1px);} 100%{transform:translateY(0);} }
@keyframes rippleAnim{ to { transform:scale(2.6); opacity:0; } }
@keyframes orbFloat  { 0%{transform:translate(0,0) scale(1);} 50%{transform:translate(40px,-30px) scale(1.12);} 100%{transform:translate(0,0) scale(1);} }
@keyframes shake     { 0%,100%{transform:translateX(0);} 20%{transform:translateX(-8px);} 40%{transform:translateX(7px);} 60%{transform:translateX(-5px);} 80%{transform:translateX(3px);} }
```

### 入场（错峰 stagger）
列表/卡片用 `animation-delay` 每项递增 `60~80ms` 依次出现：
- 侧边栏导航项 / 对话项：`fadeInX`
- 功能卡片：`cardPop`（回弹曲线）
- 标题/问候语/chip：`fadeInUp`
- 消息气泡：AI `msgInL`（左入）· 用户 `msgInR`（右入），动态追加自动触发

### 点击反馈
- **Ripple 波纹**：按钮 `position:relative; overflow:hidden`，JS 在点击坐标插入 `.ripple` span，`rippleAnim 0.6s` 后移除
  ```css
  .ripple { position:absolute; border-radius:50%; transform:scale(0);
            background:rgba(255,255,255,0.45); pointer-events:none;
            animation:rippleAnim 0.6s ease-out; }
  ```
- **按下缩放**：`:active { transform: scale(0.94~0.97); }`

### Hover 装饰
- **高光扫过**：元素 `overflow:hidden` + `::after` 斜向高光，hover 时 `left: -75% → 135%`，`transition: left 0.6~0.65s`
  ```css
  .el::after { content:''; position:absolute; top:0; left:-75%; width:50%; height:100%;
    background:linear-gradient(120deg, transparent, rgba(255,255,255,0.5), transparent);
    transform:skewX(-20deg); transition:left 0.65s ease; pointer-events:none; }
  .el:hover::after { left:135%; }
  ```
- **图标弹跳**：`hover` 时子图标触发 `iconBounce 0.55s`
- **chip 浮起**：`hover { transform: translateY(-2px); }`

### 输入框聚焦
图标随聚焦变色放大：`.form-group:focus-within .field-icon { color:#2a5aa8; transform:translateY(-50%) scale(1.15); }`

### 背景漂浮光斑（登录页）
柔光圆斑 `filter:blur(48px); opacity:0.5`，`orbFloat` 26~32s 缓慢循环，`pointer-events:none` 置于内容下层。

### 错误反馈
表单出错时容器加 `.shake` class 触发 `shake 0.45s`；重复触发前需 `classList.remove` + 强制重排（`void el.offsetWidth`）重启动画。

### 无障碍降级（必加）
```css
@media (prefers-reduced-motion: reduce) {
  *, .feature-card, .msg-row, .nav-item { animation: none !important; transition: none !important; }
}
```
