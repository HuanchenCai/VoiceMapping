# VoiceMap UI 设计规范 — 方案 C 锁定版

> **GUI 主界面**：方案 **C — Studio**（深灰 + amber，工作站布局）
> **导出报告样式**：方案 **D — Academic / Paper-First**（纯白 + 深色）
> 双语规则：中文版只显示中文，英文版只显示英文，参数符号（CPP / F0 / MIDI 等）保留原写法
> 软件名 — 中文：嗓音声学品质多维分析图谱；英文：VoiceMap
> 备选 A / B / D 见 `UI_DESIGN_OPTIONS.md`，渲染图见 `docs/mockups/`

---

## 1. 设计 token（A0-2 的 `theme.py` 落地为这个）

### 1.1 颜色（GUI 主界面 = 方案 C）

```python
# 背景层（深灰阶）
BG_APP        = "#0a0a0a"   # 整窗最底
BG_PANEL      = "#1a1a1a"   # 主要 panel 卡片
BG_ELEVATED   = "#2a2a2a"   # 选中行 / hover
BG_OVERLAY    = "#1a1a1a"   # popup / dialog（带 shadow）

# 边框
BORDER_SUB    = "#2a2a2a"   # 极弱分隔（背景过渡）
BORDER        = "#3a3a3a"   # 卡片边、focus
BORDER_STRONG = "#525252"   # 章节分隔、强调

# 文字
TEXT          = "#f5f5f5"   # 主文字、标题
TEXT_SEC      = "#a3a3a3"   # 副文字、说明
TEXT_MUTED    = "#737373"   # placeholder、disabled、caption
TEXT_INVERSE  = "#0a0a0a"   # accent 上的文字

# 强调色
ACCENT        = "#f59e0b"   # amber-500，唯一品牌色
ACCENT_HOVER  = "#fbbf24"   # amber-400
ACCENT_PRESS  = "#d97706"   # amber-600

# 语义色
SUCCESS       = "#84cc16"   # lime-500，"良好" / "GOOD" / 已分析
WARNING       = "#f59e0b"   # amber，跟 ACCENT 同色（"关注"）
ERROR         = "#ef4444"   # red-500
INFO          = "#3b82f6"
```

### 1.2 颜色（导出报告 = 方案 D）

```python
# 给 plotter / report.py 单独使用，独立于 GUI 主题
REPORT_BG          = "#ffffff"
REPORT_TEXT        = "#1a1a1a"
REPORT_TEXT_SEC    = "#525252"
REPORT_TEXT_MUTED  = "#737373"
REPORT_BORDER      = "#a3a3a3"
REPORT_ACCENT      = "#1e3a5f"   # 深藏青（学术风）
REPORT_GOOD        = "#15803d"
REPORT_NORMAL      = "#525252"
REPORT_WATCH       = "#a16207"
REPORT_ABNORM      = "#991b1b"
```

### 1.3 字体

```python
FONT_SANS  = ("Microsoft YaHei UI", 10)
FONT_SANS_B= ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")     # app bar 软件名
FONT_HEAD  = ("Microsoft YaHei UI", 11, "bold")     # 章节标题
FONT_SMALL = ("Microsoft YaHei UI",  9)
FONT_DATA  = ("Consolas", 11)                        # 数字、轨道编号
FONT_DATA_B= ("Consolas", 11, "bold")
FONT_HUGE  = ("Consolas", 24, "bold")                # CURRENT 大数字

# 报告专用（方案 D）
REPORT_TITLE_FONT  = ("SimSun", 22, "bold")         # 中文宋体
REPORT_BODY_FONT   = ("SimSun", 10)
REPORT_DATA_FONT   = ("Consolas", 10)
```

### 1.4 间距 + 圆角

```python
# 8px 栅格
SPACE_XS = 4
SPACE_S  = 8
SPACE_M  = 12
SPACE_L  = 16
SPACE_XL = 24
SPACE_XXL= 32

# 圆角（C 的录音棚风格圆角偏小）
RADIUS_SM = 0    # 默认直角（studio 风）
RADIUS_MD = 4    # button、card
RADIUS_LG = 6    # panel
```

### 1.5 关键尺寸

```python
APP_BAR_H        = 50      # 顶部软件名 + 当前文件 + 右上工具
TRACKS_PANEL_H   = 110     # 录音轨列表（最多放 3-4 个，更多滚动）
METRIC_BAR_H     = 36      # 指标选择条
CANVAS_MIN_W     = 600
INSPECTOR_W      = 360     # 右侧 CPP 详情栏（固定）
TOOLBAR_H        = 36
STATUS_BAR_H     = 30
WIN_MIN_W        = 1200
WIN_MIN_H        = 720
```

---

## 2. GUI 布局（result state — 方案 C）

```
┌────────────────────────────────────────────────────────────────────────┐
│ App Bar  BG_PANEL · 50px                                                │
│  嗓音声学品质多维分析图谱       ✓ test_Voice_EGG.wav      EN ⚙ ? ─    │
├────────────────────────────────────────────────────────────────────────┤
│ Tracks Panel  BG_PANEL · 110px                                          │
│  录音轨                                                                  │
│  ▌01 ✓ test_Voice_EGG.wav     44.1k Hz · 8.2s · 12,525 网格   ▓▓▓▓▓░  │
│   02 ○ recording_2.wav         44.1k Hz · 5.1s · 未分析        ▓░░░░░  │
│   03 ○ recording_3.wav         44.1k Hz · 6.7s · 未分析        ▓░░░░░  │
├────────────────────────────────────────────────────────────────────────┤
│ Metric Bar  BG_PANEL · 36px                                             │
│  指标   [ CPP ▾ ]   │  上一个 ←  下一个 →                              │
├────────────────────────────────────────────────────┬───────────────────┤
│                                                     │ Inspector         │
│         Heatmap Card   (white)                      │ BG_PANEL · 360px  │
│                                                     │                   │
│         CPP [dB]                                    │  CPP              │
│                                                     │  倒谱峰显著度       │
│         (matplotlib heatmap)                        │  单位 dB          │
│                                                     │                   │
│                                                     │  ┌─────────────┐ │
│                                                     │  │ 临床参考范围 │ │
│                                                     │  │ ≥14   良好 │ │
│                                                     │  │ 10-14 正常 │ │
│                                                     │  │ 6-10  关注 │ │
│                                                     │  │ <6    异常 │ │
│                                                     │  └─────────────┘ │
│                                                     │                   │
│                                                     │  ┌─────────────┐ │
│                                                     │  │ 本次值       │ │
│                                                     │  │ 16.79   dB  │ │
│                                                     │  │ ✓ 良好      │ │
│                                                     │  └─────────────┘ │
│                                                     │                   │
│                                                     │  [ 导出 Excel  ] │
│                                                     │  [ 生成报告    ] │
│                                                     │  [ 对比录音    ] │
├────────────────────────────────────────────────────┴───────────────────┤
│ Toolbar  BG_PANEL · 36px                                                │
│  [拟合▾]  [标注]  [复位]  [复制图片]  [保存▾]                          │
├────────────────────────────────────────────────────────────────────────┤
│ Status Bar  BG_PANEL · 30px                                             │
│  ● 文件 01 · 12,525 网格 · k=5 · 3,420 个周期 · 耗时 12.6 秒           │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 三屏共通

- **App Bar 顶部固定**：左 = 软件中文/英文全称，中 = 当前文件名 + 状态符号，右 = 语言切换 + 设置 + 帮助 + 最小化
- **Tracks Panel 第二行**：录音轨列表（替代传统 file sidebar）。左侧轨道编号 + 状态符号 + 文件名 + 元数据，右侧 mini-waveform 装饰条
- **Metric Bar 第三行**：指标下拉 + 键盘提示
- **主区分割**：左 Canvas（heatmap card），右 Inspector（固定 360px，包含临床范围卡 + 当前值卡 + 操作按钮）
- **Toolbar 倒数第二行**：仅作图相关工具（拟合 / 标注 / 复位 / 复制 / 保存）
- **Status Bar 永远在最底**：当前文件 + 网格数 + k + 周期 + 耗时

### 2.2 Empty state 变体

无文件时：
- Tracks Panel 显示 "录音轨" 标题 + 空白区域中央 "拖入 .wav 文件开始 / Drag a .wav file to begin"
- Metric Bar 全部 disabled（灰）
- Canvas 显示之前实现的占位画面（白底 + MIDI/SPL 坐标系 + ♪ 提示）
- Inspector 显示 "选中文件后查看详情 / Select a file to view details"
- 操作按钮全 disabled

### 2.3 Analyzing state 变体

- Tracks Panel 当前轨左侧 ▌从 amber 变成脉动 amber（accent_hover ↔ accent）
- Status Bar 实时滚 cycles 数 + 耗时
- Inspector 整列变进度卡片：阶段 N/12 + 进度条 + 当前阶段名
- 两阶段：phase A 完成 → 立刻填第一张热图，inspector 切回正常布局并继续显示后续指标 "正在计算"

### 2.4 Compare state 变体

- Tracks Panel 同时高亮 2 个轨道（A / B）
- Heatmap Card 拆 3 列：A | B | A−B（matplotlib subplot 1×3）
- Inspector 改为差异统计卡片（A 平均 / B 平均 / Δ / 重叠率）

---

## 3. 双语规则（关键）

### 3.1 中文模式

- **App Bar 软件名**："嗓音声学品质多维分析图谱"（不显示 "VoiceMap"）
- **所有 UI 文字 100% 中文**
- **唯一例外是参数符号**：CPP / CPPS / F0 / MIDI / SPL / Hz / dB / OQ / CIQ / SPQ 等保留原写法
- **临床档位**：良好 / 正常 / 关注 / 异常
- **Tracks 单位**："44.1k Hz · 8.2s · 12,525 网格" / "未分析"
- **键盘提示**："上一个 ←  下一个 →"

### 3.2 英文模式

- **App Bar 软件名**："VoiceMap"
- **所有 UI 文字 100% 英文**
- **临床档位**：GOOD / NORMAL / WATCH / ABNORM
- **Tracks 单位**："44.1k Hz · 8.2s · 12,525 cells" / "not analyzed"
- **键盘提示**："Prev ←  Next →"

### 3.3 实现要点

- `voicemap/i18n.py` 持有 STRINGS dict：`{"zh": {...}, "en": {...}}`
- API：`tr("key")` 返回当前语言下的字符串
- 切换：菜单栏 / 顶栏右侧"中" ↔ "EN" 一键切换
- 持久化：当前语言写到 `~/.voicemap/config.json`，下次启动恢复
- 切换动作：trigger 全局重建 — `app.event_generate("<<LangChanged>>")`，所有 widget 监听该事件并重读自己的字符串

### 3.4 不双语化的内容

- 文件名（test_Voice_EGG.wav）
- 数值（16.79、12,525）
- 单位符号（Hz、dB、kHz、s）
- 参数符号（CPP、CPPS、F0、MIDI、SPL）
- 时间戳（2026-05-06）
- 邮箱（huanchen.se@gmail.com）
- 版本号（V1.0）
- log 文件内容（开发者可见，全英文）

---

## 4. 导出报告样式（方案 D）

报告由 `voicemap/report.py` 生成 .md，再用 PyInstaller 时打包 weasyprint / reportlab / 或纯 matplotlib 渲染为 PDF。

### 4.1 视觉规范

- 纯白底，黑字
- 居中标题：中文 "嗓音声学品质多维分析图谱"（宋体 22pt bold），副标题 "VoiceMap V1.0"
- 章节按论文 figure 风格：`▸ CPP — 倒谱峰显著度` 章节标题
- 数字用 Consolas 等宽（包括统计 "Mean / Std / Min / Max / n"）
- 临床参考范围横排 4 档（良好 / 正常 / 关注 / 异常）
- 页脚：左 "嗓音声学品质多维分析图谱  V1.0  ·  © 2026 蔡焕晨  ·  邮箱"，右 "导出于 2026-05-06"

### 4.2 报告结构（按指标 chapter）

```
[标题]               居中，宋体 22pt
[副标题]             居中，灰，VoiceMap V1.0
─────分隔线─────
[音频文件]           标签 + 元数据
[分析指标]           ▸ CPP — 倒谱峰显著度
[Figure 1]           VRP 热图
[图说]              图 1.   CPP 在 MIDI × SPL 网格上的 ...
[统计摘要]           均值 / 标准差 / 最小值 / 最大值 / 样本数（5 列）
[临床参考范围]       良好 / 正常 / 关注 / 异常（4 列）+ 本次结果 + 状态标
─────分隔线─────
[页脚]              软件名 · 版权 · 邮箱 | 导出于 日期
```

### 4.3 文件格式

- **.md** （主交付）：human-readable 中文 markdown
- **.pdf** （A0-5 阶段做）：印刷友好，A4 单页或多页
- **报告里的图**全部走方案 D 配色（不是 GUI 的暗色），保证学术发表 / 印刷双友好

---

## 5. 组件规范

### 5.1 Button 四档

```
Primary    bg=ACCENT  fg=TEXT_INVERSE  font=FONT_SANS_B
           border=none  radius=4  padding=(8,16)
           hover: bg=ACCENT_HOVER
           主操作。每屏 ≤ 1 个

Secondary  bg=BG_ELEVATED  fg=TEXT
           border=1px ACCENT  radius=4  padding=(6,12)
           hover: bg=BG_ELEVATED + glow
           Inspector 里的"导出 Excel / 生成报告 / 对比"用此

Ghost      bg=BG_ELEVATED  fg=TEXT
           border=1px BORDER  radius=4  padding=(4,8)
           hover: bg=BORDER
           Toolbar 按钮（拟合 / 标注 / 复位 / 复制 / 保存）

Icon       32x32  bg=transparent  fg=TEXT_SEC
           hover: bg=BG_ELEVATED  fg=TEXT
           App Bar 右上的 ⚙ ? ─ 三个图标
```

### 5.2 Track Item

```
高度 32px，bg = BG_PANEL（默认）/ BG_ELEVATED（选中）
选中时左侧 4px ACCENT 竖条
左到右：编号(02) · 状态(○/✓/⏵) · 文件名 · 元数据 · mini-waveform

字段          字体        颜色             宽度
编号          FONT_DATA   TEXT_MUTED       40px
状态          symbol      SUCCESS / MUTED  20px
文件名        FONT_SANS   TEXT             弹性
元数据        FONT_SMALL  TEXT_SEC         260px
waveform      —          ACCENT/MUTED     280px (右浮)

hover：整行 bg=BG_ELEVATED，cursor=hand
单击：切换为当前轨（trigger 重绘 heatmap + Inspector）
右键：上下文菜单（M5.5 阶段做）
```

### 5.3 Metric Dropdown（保留 cascade 子菜单）

依然走 commit e824dc7 的实现：tk.Menu cascade，分类（声学 / EGG / 唱歌 / 聚类 / 密度），每类 add_radiobutton 绑 metric_var。配色按本规范的暗色主题。

### 5.4 Inspector Cards

三张卡片纵向堆叠在 Inspector 列：

**卡 1 — 当前指标**（无 panel，纯文字）
- CPP（24pt bold ACCENT）
- 中文/英文全名（10pt TEXT_SEC）
- 单位（9pt TEXT_MUTED）

**卡 2 — 临床参考范围**
- 标题 "临床参考范围"（9pt bold ACCENT）
- 4 行：值范围（Consolas）+ 档位 label（彩色 bold）

**卡 3 — 本次值**
- 标题 "本次值"（9pt bold ACCENT）
- 大数字 16.79（Consolas 24pt bold ACCENT_HOVER）+ 单位 dB（10pt MUTED）
- 状态标 ✓ 良好 / ✗ 异常（11pt bold 语义色）

### 5.5 Status Pills

```
✓ 良好     fg=SUCCESS  font=FONT_SANS_B
· 正常     fg=TEXT_SEC font=FONT_SANS
! 关注     fg=WARNING  font=FONT_SANS_B
✗ 异常     fg=ERROR    font=FONT_SANS_B
```

不画 pill 边框（暗色背景下），靠颜色 + 符号识别。

---

## 6. 渐进交付（A0 落地路径）

| A0 步骤 | 这份设计中落实哪几条 |
|---------|----------------------|
| A0-1    | rename + 目录搬，UI 不动 |
| A0-2    | 拆 gui.py 时引入 `theme.py`，色板 + 字体 + 间距 token 全部按本规范定义；初步切换主题（暗色）但 layout 仍是旧的 |
| A0-3    | About 对话框做样板：amber accent + dark panel + 卡片化布局 |
| A0-4    | i18n.py 上线，全部 UI 字符串清出来。同时把 layout 切到本规范的 Tracks Panel + Metric Bar + Inspector 三段式 |
| A0-5    | report.py 切到方案 D 配色 + layout（之前是 Markdown 普通输出）；PyInstaller 打包；用户手册截图基于 layout 完成态拍摄 |

---

## 7. 验收标准

- [ ] App Bar 50px，软件名 + 文件 + 右侧工具，配色 BG_PANEL
- [ ] Tracks Panel 显示当前文件 + 选中状态左侧 4px amber 竖条
- [ ] Metric Bar 36px，下拉 + 键盘提示
- [ ] Inspector 360px 固定，三张卡片堆叠
- [ ] Toolbar 36px，5 个 Ghost 按钮
- [ ] Status Bar 30px，永远显示当前数据元信息
- [ ] 中文模式：所有 UI 字符串无英文（参数符号除外）
- [ ] 英文模式：所有 UI 字符串无中文
- [ ] 切换语言 < 200ms 完成（widget textvariable + 事件广播）
- [ ] 报告 .md 走方案 D 排版，热图配色非暗色
- [ ] 中英文切换持久化到 ~/.voicemap/config.json
- [ ] App Bar 永远显示软件全称（非缩写）
- [ ] Color tokens 全部从 theme.py 取，禁止硬编码 #xxxxxx
