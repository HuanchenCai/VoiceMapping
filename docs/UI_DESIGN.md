# VoiceMap UI Design Specification

> 整体设计语言：**Modern Web Dashboard**（Linear / Notion / Datadog 风格）
> 实现技术：tkinter + matplotlib（不是浏览器，但视觉风格一致）
> 双语：中英文一键切换（A0-4）

---

## 1. 设计原则

### 借鉴 Web Design 的部分
1. **Card-based layout** — 内容用卡片承载，圆角 + 微阴影，比传统 Win32 frame 现代
2. **Sidebar 主导航** — 左侧导航栏（Linear / Slack 模式），不是 Win32 menubar 主导
3. **Spacing rhythm** — 8px 基础栅格（4/8/12/16/24/32），不再是随手 `pady=3`
4. **Subtle borders** — `1px solid` 内分隔，不用 3D `relief=ridge`
5. **Hover / active states** — 所有可交互元素有视觉反馈
6. **Empty states** — 没数据时不只是空白，要有插画 + 引导文字 + CTA
7. **Pills / badges** — 状态用小圆标签，不用文字加括号

### 不照搬的部分
1. ❌ **响应式断点** — 桌面单端，最小 1200×720 已是底线
2. ❌ **动画过渡** — tkinter 做动画很挣扎，只在窗口出现/消失用最克制的 fade
3. ❌ **字体外加载** — 全部用系统自带 Microsoft YaHei UI / Consolas
4. ❌ **复杂 SVG 图标** — 用 Unicode 符号 + emoji 已够（◀ ▶ ♪ ⚙ ✓ ○ ⏵ ⏸）

---

## 2. 视觉语言

### 2.1 色板（Dark Theme，默认）

```
背景层（从底到顶）
  --bg-app         #0a0e13   ← 整个窗口最底层
  --bg-panel       #131922   ← 主要 panel
  --bg-elevated    #1a212d   ← hover、当前选中
  --bg-overlay     #1e2733   ← popup / dialog

边框
  --border-subtle  #1f2733   ← 默认分隔
  --border-strong  #2a3340   ← 卡片边、focus

文字
  --text-primary   #e4eaf2   ← 标题、主文字
  --text-secondary #94a3b8   ← 副标题、说明
  --text-muted     #64748b   ← placeholder、disabled
  --text-inverse   #0a0e13   ← accent 上的文字

强调色（信号色）
  --accent         #00d9ff   ← 唯一品牌色，cyan
  --accent-hover   #38e2ff
  --accent-press   #00b8e0
  --accent-glow    rgba(0, 217, 255, 0.15)

语义色
  --success        #4ade80   ← 分析完成 / PASS
  --warning        #fbbf24   ← 警告 / WARN
  --error          #f87171   ← 失败 / FAIL
  --info           #60a5fa
```

### 2.2 色板（Light Theme，A0-4 之后做）

```
  --bg-app         #f8fafc
  --bg-panel       #ffffff
  --bg-elevated    #f1f5f9
  --border-subtle  #e2e8f0
  --border-strong  #cbd5e1
  --text-primary   #0f172a
  --text-secondary #475569
  --accent         #0891b2   ← 同 cyan，深一档
```

打印 / 学术发表场景默认走 Light，截图存档走 Dark。

### 2.3 排版

```
字体族（CSS 风格 fallback chain）
  --font-sans      "Microsoft YaHei UI", "Inter", "Segoe UI", system-ui, sans-serif
  --font-mono      "Cascadia Code", "JetBrains Mono", "Consolas", monospace

字号
  --text-display   24px / bold      ← 软件主标题
  --text-h1        18px / bold      ← page heading
  --text-h2        15px / semibold  ← section heading
  --text-body      13px / regular   ← 默认正文
  --text-small     12px / regular   ← 辅助说明
  --text-caption   11px / regular   ← 时间戳、单位

行高
  正文 1.5  ·  标题 1.3  ·  caption 1.4
```

### 2.4 间距与圆角

```
间距阶梯（8px 栅格）
  4 / 8 / 12 / 16 / 24 / 32 / 48 / 64

圆角
  --r-sm   4px    ← input、tag
  --r-md   8px    ← button、card
  --r-lg   12px   ← panel
  --r-xl   16px   ← dialog

阴影（dark theme，弱）
  --shadow-sm   0 1px 2px   rgba(0,0,0,0.40)
  --shadow-md   0 4px 12px  rgba(0,0,0,0.50)
  --shadow-lg   0 12px 32px rgba(0,0,0,0.60)
  --shadow-glow 0 0 16px    rgba(0,217,255,0.15)
```

---

## 3. 布局系统

### 三栏 Dashboard

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │   App Bar  (高 48px)                                                      │
 │   logo  ·  当前文件名 ▾  ·  状态 pill                          ⚙   ?  ⌐ │
 ├────────┬─────────────────────────────────────────────┬───────────────────┤
 │        │                                              │                  │
 │ Nav    │   Canvas Area                                │ Inspector        │
 │        │   (主图表 / 占位 / 比较视图)                 │ (元数据 / 详情)  │
 │ 220px  │   弹性                                        │ 280px (可折叠)   │
 │        │                                              │                  │
 │        │                                              │                  │
 │        │                                              │                  │
 ├────────┴─────────────────────────────────────────────┴───────────────────┤
 │   Status Bar  (高 28px)                                                   │
 │   ✓ 12,525 cells  ·  Clarity ≥ 0.97  ·  EGG cycles: 3,420  ·  12.6s     │
 └──────────────────────────────────────────────────────────────────────────┘
```

### 列宽

- **Sidebar**：固定 220px。手动可拖到 180-320，不可隐藏
- **Inspector**：固定 280px，按 `Ctrl+\` 可折叠（折叠后 0px，content 区抢空间）
- **Canvas**：弹性，最小 600px（小于这就给"窗口太小"提示）
- **App Bar**：48px，信息密度高，1-line
- **Status Bar**：28px，用 caption 字号

### 响应（窗口缩放）

- 全宽 ≥ 1400px：三栏全开
- 1100-1400px：Inspector 默认折叠
- < 1100px：Sidebar 折叠为 48px 图标条
- < 800px：禁用拖动 sash，画 hint 让用户拉大窗口

---

## 4. 组件库

### 4.1 Button

四档：

```
Primary（accent 填充）           [  分析  ]   ← 主操作，每屏只有 1 个
                                 bg=accent  fg=text-inverse
                                 hover: bg=accent-hover

Secondary（轮廓）                [  设置  ]   ← 次操作
                                 bg=transparent  border=1px border-strong
                                 hover: bg=elevated

Ghost（无边框）                  [  取消  ]   ← 三级操作
                                 bg=transparent  fg=text-secondary
                                 hover: bg=elevated  fg=text-primary

Icon-only                        [ ⚙ ]       ← 工具栏图标
                                 32×32  bg=transparent
                                 hover: bg=elevated
```

所有 button：圆角 8px，padding 8/16，font-body，cursor=hand。

### 4.2 Pill / Badge

```
状态                  ○ 未分析       gray pill
                      ⏵ 分析中       accent pill (脉动动画)
                      ✓ 已完成       success pill

严重度（来自 report）  ✓ 良好         success
                      · 正常         secondary
                      ! 关注         warning
                      ✗ 异常         error
```

实现：圆角 4px，padding 2/8，font-caption。

### 4.3 Card

```
┌─────────────────────────────────────┐
│ Card Title                       ⋯  │  ← 标题行 + 可选操作
├─────────────────────────────────────┤
│                                     │
│ Card body                           │
│                                     │
└─────────────────────────────────────┘

bg-panel  ·  border-subtle  ·  radius-lg  ·  padding-16
```

### 4.4 Input / Select

```
Label                                       text-secondary  caption
[ value............................. ▾ ]   bg-elevated  border-subtle
                                           focus: border=accent + glow
```

### 4.5 List Item（用于 Files panel、Metric 列表）

```
┌─────────────────────────────────────┐
│ ✓  test_Voice_EGG.wav        12.6s  │  ← 当前选中：bg-elevated + accent 左框
│    44.1 kHz · 8.2s · 12,525 cells   │
└─────────────────────────────────────┘
│                                     │
│ ○  recording_2.wav                  │  ← 未分析：透明 + 灰文字
│    44.1 kHz · 5.1s                  │
└─────────────────────────────────────┘
```

---

## 5. 关键界面

### 5.1 Empty State（首次启动）

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  VoiceMap                                          [中文] [⚙] [?] [⌐]    │
 ├────────┬─────────────────────────────────────────────┬───────────────────┤
 │        │                                              │                  │
 │ FILES  │                                              │  没有选中文件     │
 │ +      │     ┌─────────────────────────────────┐     │                  │
 │        │     │                                 │     │  拖入或打开 wav  │
 │        │     │              ♪                  │     │  开始分析。      │
 │        │     │                                 │     │                  │
 │        │     │       拖入 .wav 文件开始        │     │                  │
 │        │     │                                 │     │                  │
 │        │     │   立体声  Ch1=麦克风 Ch2=EGG    │     │                  │
 │        │     │                                 │     │                  │
 │ 还没有 │     │       [    打开文件    ]        │     │                  │
 │ 文件   │     │                                 │     │                  │
 │        │     └─────────────────────────────────┘     │                  │
 │        │                                              │                  │
 ├────────┴─────────────────────────────────────────────┴───────────────────┤
 │  就绪                                                                     │
 └──────────────────────────────────────────────────────────────────────────┘
```

要点：
- 占位区是"虚线圆角卡片"（FancyBboxPatch 已有，保留）
- 中央 ♪ 大字符 + 主文字 + 副说明
- 主 CTA "打开文件" 按钮（不只是文字提示）
- 整窗大量留白，不要塞日志、不要塞参数

### 5.2 Analyzing State

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  VoiceMap   ⏵ test_Voice_EGG.wav             [中文] [⚙] [?] [⌐]          │
 ├────────┬─────────────────────────────────────────────┬───────────────────┤
 │        │                                              │ 当前文件          │
 │ FILES  │     ┌─────────────────────────────────┐     │  test_Voice_EGG  │
 │ +      │     │                                 │     │  44.1 kHz · 8.2s │
 │ ──┐    │     │   ▓▓▓▓▓▓▓▓▓░░░░░░░░░ 60%       │     │                  │
 │ │⏵│    │     │                                 │     │ ─────────────    │
 │ test_  │     │   正在分析 EGG 周期...          │     │ 进度              │
 │ Voice  │     │                                 │     │  1. 加载    ✓    │
 │ _EGG   │     │  阶段 5/12                      │     │  2. SPL     ✓    │
 │        │     │                                 │     │  3. CPP     ✓    │
 │        │     │  已用 4.3s / 预计 12s           │     │  4. SpecBal ✓    │
 │        │     │                                 │     │  5. EGG    ⏵     │
 │        │     │                                 │     │  6. Cluster ○    │
 │        │     └─────────────────────────────────┘     │  ...             │
 │        │                                              │                  │
 ├────────┴─────────────────────────────────────────────┴───────────────────┤
 │  ⏵ 分析中…  ·  4.3s  ·  3,420 cycles                                     │
 └──────────────────────────────────────────────────────────────────────────┘
```

要点：
- App bar 状态 pill 变 ⏵（脉动）
- Canvas 中央放进度卡片，不再用 modal dialog（modal 阻塞窗口很丑）
- Inspector 显示 step-by-step 进度（已经在 analyzer 有 _step 钩子）
- 两阶段分析：完成 phase A 后中央替换成第一张热图（partial_cb 已实现），右上角 inspector 持续更新剩余进度
- Status bar 实时滚动 cycles 数

### 5.3 Result State（主工作界面）

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  VoiceMap   ✓ test_Voice_EGG.wav             [中文] [⚙] [?] [⌐]          │
 ├────────┬─────────────────────────────────────────────┬───────────────────┤
 │        │ ◉ 指标 (Metric)                             │ ⓘ 详情            │
 │ FILES  │ ┌────────────┐ ┌─────────┐ ┌───┐ ┌──────┐  │                  │
 │ +      │ │声学(Acoustic│ │EGG      │ │... │ │更多▾│  │ 当前指标         │
 │ ──┐    │ └────────────┘ └─────────┘ └───┘ └──────┘  │   CPP            │
 │ │✓│    │                                              │   倒谱峰显著度    │
 │ test_  │ ┌──────────────────────────────────────────┐│                  │
 │ Voice  │ │                                          ││ 单位 dB          │
 │ _EGG   │ │                                          ││                  │
 │ ──┐    │ │       VRP Heatmap                        ││ 临床范围         │
 │ │○│    │ │                                          ││  ✓ 良好 ≥ 14    │
 │ rec_2  │ │  ◀                                  ▶   ││  · 正常 10-14    │
 │ ──┐    │ │                                          ││  ! 关注 6-10     │
 │ │○│    │ │                                          ││  ✗ 异常 < 6     │
 │ rec_3  │ │                                          ││                  │
 │        │ └──────────────────────────────────────────┘│ 本次值           │
 │        │                                              │   16.79 dB ✓    │
 │ ──┐    │ ┌──────────────────────────────────────────┐│                  │
 │ │ ⊕ │  │ │ 拟合 ▾  · 标注 · 复位 · 复制图片 · 保存 ▾││ ─────────────    │
 │ │新增│  │ └──────────────────────────────────────────┘│ 操作              │
 │ └──┘   │                                              │  导出 Excel      │
 │        │                                              │  生成报告        │
 │        │                                              │  比对 2 段       │
 ├────────┴─────────────────────────────────────────────┴───────────────────┤
 │  ✓ 12,525 cells  ·  Clarity ≥ 0.97  ·  3,420 cycles  ·  12.6s            │
 └──────────────────────────────────────────────────────────────────────────┘
```

要点：
- Sidebar：文件列表（M5.5 时启用多文件，A0 阶段先做单文件，但 sidebar 占位留好）
- Canvas 顶部：metric 选择条（5 个分类按钮 + "更多 ▾"），点开是 cascade 子菜单
- Canvas 中央：matplotlib 热图，左右两侧 ◀ ▶ 半透明箭头（hover 显形）
- Canvas 底部：plot toolbar 一行，统一 ghost button
- Inspector：当前 metric 详情卡片
  - 顶部：metric 中英名 + 单位
  - 中部：临床范围 4 档（来自 report.py 的 `_THRESHOLDS`）+ 当前值用 pill 标显
  - 底部：导出/报告/对比 三个 ghost button（不再塞左侧 panel）
- 没了：左下"日志面板" → 软著截图时日志区不专业，挪到 `查看 → 日志面板` 单独窗口

### 5.4 Compare State（对比 2 段录音）

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  VoiceMap   ▦ Compare: A vs B                  [中文] [⚙] [?] [⌐]        │
 ├────────┬─────────────────────────────────────────────┬───────────────────┤
 │        │ 指标 [CPP ▾]                               │ 差异统计           │
 │ FILES  │                                              │                  │
 │ ──┐    │ ┌──────────┐ ┌──────────┐ ┌────────────┐  │ A 平均  16.79    │
 │ │A│    │ │   A      │ │   B      │ │   A − B    │  │ B 平均  14.21    │
 │ test_A │ │          │ │          │ │            │  │ Δ 平均  +2.58 ✓ │
 │ ──┐    │ │  heatmap │ │  heatmap │ │  diff map  │  │                  │
 │ │B│    │ │          │ │          │ │            │  │ A cells 12,525   │
 │ test_B │ │          │ │          │ │            │  │ B cells 11,210   │
 │        │ └──────────┘ └──────────┘ └────────────┘  │                  │
 │        │                                              │ 重叠率  86%      │
 │        │ ┌────────────────────────────────────────┐  │                  │
 │        │ │ 保存 ▾   切换到单文件视图              │  │                  │
 │        │ └────────────────────────────────────────┘  │                  │
 ├────────┴─────────────────────────────────────────────┴───────────────────┤
 │  ▦ Compare mode  ·  两个文件已加载                                        │
 └──────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 交互模式

### 6.1 全局快捷键

```
Ctrl + O      打开文件
Ctrl + S      保存当前 metric 为 PNG
Ctrl + E      导出 Excel
Ctrl + R      生成报告
Ctrl + ,      打开设置
Ctrl + \      折叠 / 展开 Inspector
Ctrl + /      命令面板（M6 阶段做，类似 Linear ⌘K）
←  →           上一个 / 下一个 metric
1-5            快速切到对应分类的第一个 metric
Esc            关闭 popup / dialog
```

### 6.2 焦点态

- Tab 顺序：sidebar → metric 条 → canvas → toolbar → inspector
- focus ring：accent 1.5px outline + glow（不要 default 黑色虚线）

### 6.3 反馈

- 操作完成：右下角 toast 1.5s 自动消失（"已保存到 result/...png"）
- 错误：toast 红底，3s，可手动关
- 不要 popup MessageBox，除非需要用户决策（"未保存的改动是否丢弃"）

### 6.4 拖放反馈

- 拖到窗口任意位置：drop zone 整体高亮（accent border + glow）
- 释放：占位区瞬间替换为"已加载 ✓ + 准备分析"

---

## 7. 当前实现 vs 目标设计的差距

| 当前                         | 目标                                | 工作量 |
|------------------------------|-------------------------------------|---------|
| 左 panel 塞了 设置 / CSV / 按钮 / 日志 / 进度 | sidebar 只放文件列表，其余进 inspector / status bar | M |
| Centroid bar + plot toolbar 两条 | 合并到 Canvas 底部一行 toolbar | S |
| ◀ ▶ 边栏 42px 固定占空间 | 浮在 canvas 上，hover 显形 | S |
| 日志区在主界面 | 移到独立窗口 / 折叠面板 | S |
| 设置走 modal dialog | 改为右滑入式 panel（Linear 风格） | M |
| 进度走单独 progress bar | 进度+步骤进度合并到 Inspector | M |
| Metric 用按钮 + 5 cascade 菜单 | 顶部 metric 条 5 个分类按钮，点开 cascade | S（已有基础） |
| 没有 Status bar | 加 status bar，永远显示当前数据元信息 | S |
| 没有 Inspector | 新增右栏，放 metric 详情 + 临床范围 + 操作 | M |
| 没有 i18n | A0-4 加 | M |

总工作量在 A0-2（god class 拆分）+ A0-3（pyproject + about）+ A0-4（i18n）阶段一并消化。
不是单独立项。

---

## 8. tkinter 实现要点

### 能直接做的
- 颜色 / 字体 / 圆角矩形（Canvas widget 画 rect with `tk.Canvas` 或 ttk style border）
- Sidebar / Inspector / Status bar：纯 Frame layout，pack/grid 即可
- Hover state：`widget.bind("<Enter>", ...)` / `<Leave>`
- Button 的 ghost / outline / primary 三档：自定义 ttk style
- Pill / badge：`tk.Label` + `bg` + `padx=8` + 圆角靠 `relief=flat` + 自描边

### 难做但有解
- **真正的 box-shadow**：tkinter 没有，用底层多 frame 错位 1-2px 模拟（"投影"靠浅色 border）
- **平滑动画**：`after()` 30 fps tween，但 widget 重绘有卡顿，只用在 panel 滑入
- **focus ring with glow**：用 highlightthickness + highlightcolor 模拟，不能真"glow"
- **真圆角**：tkinter widget 不支持。卡片视觉上靠 padding + border + bg 错位营造
- **Toast**：自创 `tk.Toplevel` + after 倒计时销毁，参考已有 MetricPopup

### 改不动 / 接受妥协
- ❌ 真正的 frosted glass / blur
- ❌ 渐变填充（accent 只能纯色，不能 gradient）
- ❌ 滚动惯性
- ❌ 系统级 dark mode 跟随（除非检测注册表，太麻烦）

### 字体一致性
所有 widget 强制 `Microsoft YaHei UI`，避免 Segoe UI 对中文回退导致的"某些字像加粗"。
代码字体强制 `Cascadia Code` (Win 自带) → fallback Consolas。

---

## 9. 渐进交付路径（怎么把它落地）

设计稿不一次到位，按 A0 子步骤分批落：

| A0 步骤 | 这份设计中落实哪几条                                            |
|---------|-----------------------------------------------------------------|
| A0-1    | 仅做 rename + 目录搬，UI 先不动                                  |
| A0-2    | gui.py 拆分时引入 `theme.py`（色板/字号常量），让后面可一次换皮 |
| A0-3    | About dialog 用新设计语言（accent button + card layout）         |
| A0-4    | i18n 顺带把所有 hardcode 字符串清出 → 趁机重排版                 |
| A0-5    | 截图前最后一遍视觉打磨：sidebar / inspector / status bar 上线    |

A0-2 引入 `theme.py` 后，后续任何 widget 都从 theme 取色，**禁止再硬编码 `#xxxxxx`**。
这是大改造的关键钩子。

---

## 10. 验收标准（A0 完成后）

- [ ] 4 张关键截图各一份（empty / analyzing / result / compare），中英文各一份 = 8 张
- [ ] 8px 间距栅格全程贯彻，没有 `pady=3` 这种随手数字
- [ ] 没有 `relief=ridge / groove / sunken` 这种 Win95 视觉
- [ ] 所有 button 有 hover 反馈
- [ ] 焦点用 accent ring，没有黑色 dotted line 默认 focus
- [ ] 日志区从主界面消失（移到独立窗口或折叠面板）
- [ ] Inspector 在 result state 显示当前 metric 详情卡片
- [ ] Status bar 永远显示数据元信息
- [ ] Empty state 有 ♪ 图 + 引导文字 + 主 CTA
- [ ] 全 UI 无 "FonaDyn" 字面量
- [ ] 中英切换 < 200ms 完成
