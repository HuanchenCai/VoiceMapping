# VoiceMap UI Design Specification — 方案 B 锁定版

> 选定方向：**B. Clinical Workstation**（浅色 + navy/teal，传统专业医疗软件风格）。
> 视觉调性参照 Tableau Health / Epic / Praat 表格视图。
> 决策依据：6 轴评分软著适配 10 / 临床场景 10 / 学术发表 9 三个最重要维度满分。
> 备选 A / C / D 见 `UI_DESIGN_OPTIONS.md`，渲染图见 `docs/mockups/`。

---

## 1. 设计 token（A0-2 的 `theme.py` 落地为这个）

### 1.1 颜色

```python
# 背景层
BG_APP        = "#f8fafc"   # 整窗最底
BG_PANEL      = "#ffffff"   # 主要 panel 卡片
BG_ELEVATED   = "#f1f5f9"   # 选中行 / hover
BG_OVERLAY    = "#ffffff"   # popup / dialog（带 shadow）

# 边框
BORDER_SUB    = "#e2e8f0"   # 默认分隔，hairline
BORDER        = "#cbd5e1"   # 卡片边、focus
BORDER_STRONG = "#94a3b8"   # 章节分隔，强调

# 文字
TEXT          = "#0f172a"   # 主文字、标题
TEXT_SEC      = "#475569"   # 副文字、说明
TEXT_MUTED    = "#64748b"   # placeholder、disabled、caption
TEXT_INVERSE  = "#ffffff"   # accent 上的文字

# 强调色（信号色）
ACCENT        = "#0891b2"   # 唯一品牌色，cyan-700
ACCENT_HOVER  = "#0e7490"
ACCENT_PRESS  = "#155e75"

# 顶部标题栏深色变体（让 banner 区跟内容区有层次）
HEADER_BG     = "#0891b2"   # accent 同色作为顶部标题栏
HEADER_FG     = "#ffffff"

# 语义色
SUCCESS       = "#059669"   # 良好 / PASS
WARNING       = "#d97706"   # 关注 / WARN
ERROR         = "#dc2626"   # 异常 / FAIL
INFO          = "#2563eb"
```

### 1.2 字体

```python
FONT_SANS  = ("Microsoft YaHei UI", 10)              # 默认
FONT_SANS_B= ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 14, "bold")      # 章节标题
FONT_SMALL = ("Microsoft YaHei UI",  9)              # 副文字
FONT_DATA  = ("Consolas", 10)                        # 数字 / 表格
FONT_DATA_B= ("Consolas", 10, "bold")
FONT_HEADER= ("Microsoft YaHei UI", 11, "bold")      # title bar
```

### 1.3 间距 + 圆角

```python
# 8px 栅格
SPACE_XS = 4
SPACE_S  = 8
SPACE_M  = 12
SPACE_L  = 16
SPACE_XL = 24
SPACE_XXL= 32

# 圆角（B 走传统 layout，圆角偏小）
RADIUS_SM = 2    # input
RADIUS_MD = 4    # button、card
RADIUS_LG = 6    # panel
```

---

## 2. 布局（result state）

```
┌──────────────────────────────────────────────────────────────────────┐
│ Title Bar  HEADER_BG (cyan-700)  · 高 36px                            │
│  VoiceMap V1.0 — 嗓音声学品质多维分析图谱                            │
├──────────────────────────────────────────────────────────────────────┤
│ Menubar  BG_PANEL · 高 28px                                           │
│  文件(F)  编辑(E)  视图(V)  分析(A)  工具(T)  帮助(H)                │
├──────┬───────────────────────────────────────────────────────────────┤
│      │ File metadata strip  BG_PANEL · 高 56px (2 行)                │
│ Side │  文件: test.wav │ 44.1kHz │ 8.2s │ 2 ch                     │
│ bar  │  状态: ✓ 已分析 │ 周期 3,420 │ 12.6s │ Clarity 0.97 │ k=5 │
│      ├──────────────────────┬────────────────────────────────────────┤
│ 220px│ Metric Table         │ Heatmap Card                           │
│      │ 30%                   │ 65%                                    │
│ 文件 │ ┌─────────────────┐ │ ┌─────────────────────────┐            │
│ 列表 │ │ Metric  数值 范围 状态│ │      VRP Heatmap        │            │
│      │ │ ─────────────── │ │ │                         │            │
│ ✓ … │ │ Clarity 0.997 ✓│ │ │  (matplotlib canvas)    │            │
│ ○ … │ │ CPP    16.79  ✓ │ │ │                         │            │
│ ○ … │ │ ...             │ │ │                         │            │
│      │ │                  │ │ │                         │            │
│      │ └─────────────────┘ │ └─────────────────────────┘            │
│      ├──────────────────────┴────────────────────────────────────────┤
│      │ Toolbar  BG_PANEL · 高 36px                                    │
│      │  拟合▾  标注  复位  复制图片  保存▾  │ 导出 Excel  生成报告  对比 │
│      ├───────────────────────────────────────────────────────────────┤
│      │ Reference Card · 高 140px                                      │
│      │  当前指标 · CPP — Cepstral Peak Prominence                    │
│      │  倒谱峰显著度 · 单位 dB                                         │
│      │  临床参考范围                                                   │
│      │  ≥14 良好  10-14 正常  6-10 关注  <6 异常                     │
│      │  本次值: 16.79 dB ✓ 良好    n=12,525  范围内 96.9%            │
├──────┴───────────────────────────────────────────────────────────────┤
│ Status Bar  BG_ELEVATED · 高 26px                                     │
│  就绪 · Clarity 阈值=0.97 · k=5 · n_harm=10        © 2026 蔡焕晨 V1.0 │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 列宽 / 高度

- **Title bar**：36px
- **Menubar**：28px
- **Sidebar**：220px 固定，右侧 1px hairline border
- **File metadata strip**：56px（2 行，第一行 title + meta，第二行 status + 分析 meta）
- **Metric table**：Sidebar 右侧 30% 宽，顶部到 toolbar
- **Heatmap card**：剩余宽度（约 65%），顶部到 toolbar
- **Toolbar**：36px
- **Reference card**：140px（4 块横排：单位 + 临床参考 + 本次值 + 统计）
- **Status bar**：26px

### 2.2 三屏共通元素

- **Title bar 永远在最顶**（不随窗口滚动），cyan-700 底 + 白字 + 软件中文全称
- **Status bar 永远在最底**，左侧当前操作 / 参数，右侧版权信息
- **Sidebar 永远在最左**（A0 阶段先做单文件占位，M5.5 启用多文件）

---

## 3. 关键状态变体

### 3.1 Empty state（首次启动）

主区域不放 metric table，整片是大占位区：
- 中央居中"♪"图标（accent 60% 透明）
- 提示文字"拖入 .wav 文件开始 / Drag a .wav file to begin"
- 副说明"立体声  Ch1=麦克风  Ch2=EGG"
- 一个 primary button "打开文件" 在文字下方

Sidebar 还在，但内容是"还没有文件 / No files yet"灰色提示。

### 3.2 Analyzing state

主区域被进度卡片占用：
- 中央 progress bar（accent 色）
- 上方文字 "正在分析 EGG 周期..."
- 下方阶段进度 "阶段 5/12  · 已用 4.3s · 预计 12s"
- Title bar 状态 pill 变 ⏵（脉动 accent）
- Status bar 实时滚 cycles 数

两阶段分析：phase A 完成后中央替换成第一张热图（partial_cb 已实现），右侧 metric table 边填边亮。

### 3.3 Compare state

整窗布局换：
- Sidebar 上半文件 A，下半文件 B（拖另一个 wav 进 sidebar 即激活 compare）
- Heatmap card 拆成 3 列：A | B | A−B
- Reference card 换成"差异统计"（A 平均 / B 平均 / Δ / 重叠率）

---

## 4. 组件规范

### 4.1 Button 四档

```
Primary    bg=ACCENT  fg=TEXT_INVERSE                  font-bold
           border=none  radius=4  padding=(8,16)
           hover: bg=ACCENT_HOVER
           主操作。每屏 ≤ 1 个

Secondary  bg=BG_PANEL  fg=TEXT
           border=1px BORDER  radius=4  padding=(6,12)
           hover: bg=BG_ELEVATED
           次操作。toolbar / dialog 默认按钮

Ghost      bg=transparent  fg=TEXT_SEC
           radius=4  padding=(4,8)
           hover: bg=BG_ELEVATED  fg=TEXT
           三级 / 工具栏按钮

Icon       32x32  bg=transparent
           radius=4
           hover: bg=BG_ELEVATED
           sidebar / toolbar 图标按钮
```

### 4.2 Pill / Badge

```
Status pill：
  ✓ 良好     bg=#dcfce7  fg=SUCCESS  radius=10  padding=(2,8)
  · 正常     bg=#f1f5f9  fg=TEXT_SEC
  ! 关注     bg=#fef3c7  fg=WARNING
  ✗ 异常     bg=#fee2e2  fg=ERROR
```

### 4.3 Metric table 行

```
┌──────────────────────────────────────────────┐
│ CPP [dB]                  16.79   良好    ✓  │  ← bg=BG_PANEL
├──────────────────────────────────────────────┤
│ CPPS [dB]                 16.79   良好    ✓  │  ← bg=BG_ELEVATED 隔行
├──────────────────────────────────────────────┤

字段              字体           对齐   占比
metric 名          FONT_SANS      左    50%
数值              FONT_DATA      右    20%
范围 label         FONT_SANS      右    15%
mark              FONT_DATA_B   右    15%

行高 26px，hover 整行 bg=BG_ELEVATED + 左侧 3px ACCENT 竖条
单击 → 切右侧 heatmap 到该 metric
```

### 4.4 File list 行

```
┌──────────────────────────────────────────────┐
│ ▌ ✓ test_Voice_EGG.wav                       │  ← 选中：左 3px accent + bg=BG_ELEVATED
│   44.1 kHz · 8.2s · 12,525 cells             │
├──────────────────────────────────────────────┤
│   ○ recording_2.wav                          │  ← 透明 bg
│   44.1 kHz · 5.1s                            │
└──────────────────────────────────────────────┘
```

---

## 5. 交互规范

### 5.1 全局快捷键

```
Ctrl + O      打开文件
Ctrl + S      保存当前 metric 为 PNG
Ctrl + E      导出 Excel
Ctrl + R      生成报告
Ctrl + ,      打开设置
←  →           上一个 / 下一个 metric
1-5            快速切到对应分类的第一个 metric
F1            帮助
Esc           关闭 dialog
```

### 5.2 焦点态

- focus ring：1.5px ACCENT outline + 4px ACCENT 5% bg halo
- 没有 default 黑色 dotted line

### 5.3 反馈

- toast：右下角 BG_OVERLAY + ACCENT 边，1.5s 自动消失
- error：红色 toast，3s，可手动关
- 不要 modal MessageBox（除非需要决策）

### 5.4 拖放

- 拖到窗口任意位置：占位区高亮（ACCENT 边 + 5% halo）
- 释放：占位区瞬间替换为"分析中"卡片

---

## 6. tkinter 实现 cheat sheet

### 6.1 主窗口 + Title bar

```python
root = TkinterDnD.Tk()
root.configure(bg=BG_APP)

# Title bar（自定义彩色 banner）
title_bar = tk.Frame(root, bg=HEADER_BG, height=36)
title_bar.pack(side="top", fill="x")
tk.Label(title_bar, text="VoiceMap V1.0 — 嗓音声学品质多维分析图谱",
         bg=HEADER_BG, fg=HEADER_FG,
         font=FONT_HEADER).pack(side="left", padx=12, pady=6)

# Menubar 走 root.config(menu=...) 已经做了
```

### 6.2 卡片（圆角 + 边）

```python
def card(parent, **pack_kwargs):
    """A panel with subtle border + radius (radius simulated via internal padding)."""
    outer = tk.Frame(parent, bg=BORDER_SUB)
    inner = tk.Frame(outer, bg=BG_PANEL)
    inner.pack(padx=1, pady=1, fill="both", expand=True)
    outer.pack(**pack_kwargs)
    return inner
```

### 6.3 Metric table

不用 ttk.Treeview（太多视觉无法控制）。用 Canvas + 手画行：

```python
canvas = tk.Canvas(parent, bg=BG_PANEL, highlightthickness=0)
sb = ttk.Scrollbar(parent, command=canvas.yview)
canvas.configure(yscrollcommand=sb.set)

# 每行用 frame 包住 4 个 label，第一列左对齐，后三列右对齐
def add_row(metric, value, label, mark, color, even):
    bg = BG_ELEVATED if even else BG_PANEL
    row = tk.Frame(scroll_frame, bg=bg, height=26)
    tk.Label(row, text=metric, ...).pack(side="left")
    ...
```

### 6.4 Status pill

```python
def pill(parent, text, kind="normal"):
    bg, fg = {
        "good":   ("#dcfce7", SUCCESS),
        "normal": ("#f1f5f9", TEXT_SEC),
        "watch":  ("#fef3c7", WARNING),
        "abnorm": ("#fee2e2", ERROR),
    }[kind]
    return tk.Label(parent, text=text, bg=bg, fg=fg,
                     font=FONT_SMALL, padx=8, pady=2,
                     borderwidth=0)
```

---

## 7. 落地路径（按 A0 子步骤）

| A0 步骤 | 这份设计中落实哪几条                                         |
|---------|--------------------------------------------------------------|
| A0-1    | 仅 rename + 目录搬，UI 不动                                   |
| A0-2    | 引入 `voicemap/gui/theme.py`，把上述 token 集中。**所有现有硬编码 `#xxx` 一次性改成 `theme.X`**。同时把 god 类拆分 |
| A0-3    | 新增 About dialog 用新设计语言（cyan banner + sidebar + content + button row） |
| A0-4    | 加 i18n 时把所有 hardcode 字符串清出。**这一步顺带把 metric table 用上述 4.3 规范重做**（之前 metric 没表格视图） |
| A0-5    | 截图前最后视觉打磨：title bar / status bar 上线、整体微调      |

---

## 8. A0 完成后验收

- [ ] 4 张关键截图各一份（empty / analyzing / result / compare），中英各一份 = 8 张
- [ ] 8px 间距栅格全程贯彻，没有 `pady=3` 散数
- [ ] 没有 `relief=ridge / groove / sunken`（Win95 视觉）
- [ ] 所有 button 有 hover 反馈，焦点用 ACCENT ring
- [ ] 主界面没有日志区（移到独立窗口或折叠面板）
- [ ] Metric table + heatmap 同时可见（不是切换视图）
- [ ] Reference card 显示当前 metric 的临床范围和本次值
- [ ] Status bar 永远显示参数
- [ ] Title bar 永远显示软件中文全称
- [ ] 全 UI 无 "FonaDyn" 字面量
- [ ] 中英切换 < 200ms，所有 widget 即时刷新
