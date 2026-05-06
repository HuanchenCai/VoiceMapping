# VoiceMap 项目工作守则

> 本文件是 Claude Code 在本项目里干活时必须遵守的项目级规则。
> 与用户全局 `~/.claude/CLAUDE.md` 冲突时，本文件优先（项目规则覆盖全局规则）。

## 0. 软件身份

- **中文名**：嗓音声学品质多维分析图谱（注册软著用全称）
- **英文名 / 代号**：VoiceMap
- **类型**：Windows 桌面 GUI（tkinter）+ CLI 工具
- **目的**：声学/EGG 双通道分析，生成 Voice Range Profile + 多维 metric
- **注册主体**：个人（蔡寰宸）软著申请目标

❌ **不要**再写 "FonaDyn" 这个旧名，它是 KTH 的另一个 SuperCollider 项目，
撞名会让软著被驳回。**所有新代码、新文档、新 commit 一律用 VoiceMap**。

---

## 1. 当前阶段（重要）

**软著前冻结期**。除了 ROADMAP 的 A0/A1 项目，**不接任何新研究功能**。
M3-M9 的研究类增强（多聚类模型、人口统计、ML pipeline 等）一律推到拿证后。

如果用户突然提了一个研究功能（"加个 vibrato 频谱图"之类），
**先确认是不是 A0 软著线**，不是就告诉用户"这一项推到 M7+，软著拿证后做"。

---

## 2. 启动 / 测试 / 验证（必背命令）

```bash
# Conda 环境（这个项目唯一的 Python）
C:\Users\huanc\miniconda3\envs\fonadyn\python.exe

# GUI（主入口）
python main.py --gui
# 或双击根目录的 启动.bat（rename 后）

# CLI 单文件
python main.py audio/test_Voice_EGG.wav

# 验证 metric 正确性（必跑，48 PASS / 0 FAIL 是当前基准线）
python tests/validate_params.py audio/test_Voice_EGG.wav
```

**改完代码必须跑 `validate_params.py`**，红了就回滚，不要试图边写新代码边修验证失败。

---

## 3. 项目结构

### 3.1 当前（A0-1 完成后实际状态）

```
FonaDyn.py/                         ← 注：OS 目录名仍是旧名，重命名待 A0-5 前手动做
├── main.py                         ← 薄壳，9 行：sys.path + from voicemap.cli import main
├── requirements.txt                ← A0-3 会被 pyproject.toml 替代
├── voicemap/                       ← 主包（commit db8aceb 从 src/ 改名）
│   ├── __init__.py                 ← 只 re-export 高层 facade（VoiceMapAnalyzer / Config / 元数据）
│   ├── __version__.py              ← 版本/作者/版权单一来源
│   ├── config.py
│   ├── logger.py
│   ├── analyzer.py                 ← 主流程 + output_vrp_csv（A0-2 会拆出 csv_writer）
│   ├── metrics.py                  ← 所有 calculator
│   ├── metrics_registry.py
│   ├── plotter.py
│   ├── plot_overlay.py
│   ├── excel_export.py
│   ├── report.py
│   ├── cli.py                      ← 原 main.py
│   └── gui.py                      ← 原 gui.py（A0-2 会拆成 gui/ 子包）
├── tests/
│   └── validate_params.py          ← 集成回归（A0-2 后 rename 为 test_validation.py）
├── audio/test_Voice_EGG.wav
├── docs/
│   ├── UI_DESIGN.md                ← C 锁定 + D 报告
│   ├── UI_DESIGN_OPTIONS.md
│   └── mockups/
└── result/                         ← gitignored 输出
```

### 3.2 目标（A0 全部完成后）

```
VoiceMap/                           ← 项目根改名（A0-5 前做）
├── pyproject.toml                  ← 替代 requirements.txt
├── LICENSE
├── main.py                         ← 同上
├── voicemap/
│   ├── __init__.py
│   ├── __version__.py
│   ├── config.py
│   ├── logger.py
│   ├── i18n.py                     ← A0-4 加：字典翻译表 + tr() API
│   ├── analyzer.py
│   ├── csv_writer.py               ← A0-2 从 analyzer.output_vrp_csv 拆出
│   ├── metrics.py
│   ├── metrics_registry.py
│   ├── plotter.py
│   ├── plot_overlay.py
│   ├── excel_export.py
│   ├── report.py
│   ├── cli.py
│   └── gui/                        ← A0-2 拆 gui.py 成子包
│       ├── app.py
│       ├── theme.py                ← UI_DESIGN.md 的色板/字号 token 落地
│       ├── widgets.py
│       ├── dialogs.py              ← Settings / Compare / About
│       └── menubar.py
├── tests/
│   ├── test_validation.py
│   └── test_*.py                   ← A0-2 后补的单元测试
├── audio/
└── docs/
    ├── UI_DESIGN.md
    ├── 用户手册.md                ← A0-5 产出
    └── 设计说明书.md
```

### 新代码放哪里（决策树）

- **新 metric calculator** → `voicemap/metrics.py`，跟现有 calculator 同样模式（`__init__` + `calculate()`），同时在 `metrics_registry.py` 注册
- **新 GUI 对话框** → `voicemap/gui/dialogs.py`
- **新 GUI 子组件** → `voicemap/gui/widgets.py`
- **新主题色 / 字体** → `voicemap/gui/theme.py`
- **新 CSV 后处理** → `voicemap/csv_writer.py`
- **新 plot 类型** → `voicemap/plotter.py`
- **新一段 UI 文字** → 同时加到 `voicemap/i18n.py` 的 zh + en 两个 dict

❌ **不要**：
- 把 metric 散到 GUI 文件里
- 把 UI 文字散到 calculator 里
- 在 `gui/app.py` 写新业务逻辑（VoiceMapApp 已经太肥）
- 新建 `utils.py` / `helpers.py` —— 这是垃圾分类，要么属于具体模块，要么独立成模块

---

## 4. 命名 / 风格规范

- **类名**：`SomethingCalculator` / `SomethingDialog` / `SomethingApp`
- **函数名**：snake_case，私有方法前缀 `_`
- **常量**：UPPER_SNAKE，模块顶部
- **GUI 布局函数**：`_build_xxx`（如 `_build_top_bar`）
- **GUI 事件**：`_on_xxx`（如 `_on_metric_change`）
- **公开 API**：写 docstring。私有方法：`# 一行短注释` 即可

中文注释 OK，但**所有标识符、函数名、变量名必须英文**（软著审核员看代码会读，
中文标识符容易扣"代码风格"分）。

---

## 5. 日志

```python
from voicemap.logger import get_logger
logger = get_logger(__name__)
```

- 模块顶部 `logger = get_logger(__name__)`，**不要**用 `logging.getLogger("voicemap")` 硬编码名字
- `logger.info()` 用于流程节点（"Loading audio: ...", "Analysis done in 12s"）
- `logger.warning()` 用于可继续但需注意（"K-means cluster 4 was empty, rescued")
- `logger.error()` 用于功能失败但程序还能跑
- `logger.exception()` 用于 except 块里。**禁止** `except Exception: pass`，至少一行 `logger.exception("brief context")`

`setup_logger` 把 handler 装在 root logger 上（commit 09d17f9 之后），
所以 `analyzer / metrics / plotter / gui` 模块各自的 logger 都会自动输出。
**不要再像旧 GUI 那样手动给每个模块加 handler**。

---

## 6. 线程

GUI 把分析跑在 worker thread，主线程通过 `queue.Queue` 接日志/进度。

- **主线程**：tkinter 事件循环（`mainloop`）。所有 widget 操作必须在主线程
- **worker 线程**：分析（`analyzer.analyze_and_output_vrp` 等），通过 `self._msg_q.put(...)` 跟主线程通信
- **回调**：worker 不要直接 `widget.config(...)`，要 `self.after(0, lambda: widget.config(...))`
- **partial_cb**（两阶段分析）：worker 调用，主线程负责 schedule 渲染

---

## 7. 国际化 / i18n

A0-4 之后强制规则：

- **不要在 GUI 代码里写中文字面量**，所有用户可见字符串走 `tr("key")`
- **每加一段 UI 文字**：必须同时在 `i18n.py` 的 `zh` 和 `en` 两个 dict 里加 entry
- **专业术语**双语括号格式：`tr("聚类中心")` 中文返回 "聚类中心 (Centroid)"，英文返回 "Centroid"
- **log 字符串**：开发者可见，全英文，不走 i18n
- **error 对话框**：用户可见，走 i18n

---

## 8. 已知坑（踩过的，新人/新会话注意）

### 8.1 Windows .bat 文件编码
- 用户系统 OEM = CP936/GBK
- `.bat` 文件内容必须**纯 ASCII**（注释、echo 全英文）
- `chcp 65001` 放在文件顶部**没用**
- 真要中文：`@echo off` + `chcp 65001` + 文件存为带 BOM 的 UTF-8

### 8.2 tkinter overrideredirect popup
- 创建 borderless Toplevel 后立即 `geometry()` 不一定生效
- 正确套路：`withdraw()` → 设 geometry → `deiconify()`
- 多屏 / 高 DPI 下 `winfo_rootx()` 在父窗口未 layout 时会返 0
- **不要再造 Toplevel popup，用 `tk.Menu.tk_popup(x, y)`**（Windows 右键菜单同款机制，自带定位、点外消失）

### 8.3 ttk.Button + 自定义样式
- `ttk.Button(style="Xxx.TMenubutton")` 会让 ttk 把 Menubutton 的 layout 元素塞进 Button，事件分发被搅乱，`command=` 和 `<Button-1>` 都打不到回调
- 需要"按钮样式 + 弹菜单"：用 `tk.Button` + `tk.Menu.tk_popup`
- ttk 样式不能跨 widget 类型套用

### 8.4 tk.Menu 不支持鼠标滚轮
- 这是 tk 本身的局限，没法修
- 长列表用 cascade 拆分类，每个子菜单短到不需要滚

### 8.4.1 tk.Menu 在 Windows 11 上的"白边"是 OS 画的（不可消除）
Windows 11 DWM 给所有 popup（菜单 / tooltip / dropdown）强制画一圈 1-2 px
浅色描边 + 阴影。即便 Tk 端做到极致：

```python
option_add("*Menu.borderwidth",        0)
option_add("*Menu.relief",             "flat")
option_add("*Menu.activeBorderWidth",  0)
option_add("*Menu.highlightThickness", 0)
tk.Menu(..., bg=PANEL_HI, borderwidth=0, relief="flat",
        activeborderwidth=0, highlightthickness=0)
```

**还是会留 1 px 白边**。Tk 控制不到 OS 那一层。彻底消除只能改用
`Toplevel + overrideredirect=True` 自画 popup（旧 MetricPopup 路线），
代价是自己处理多屏定位 / 点外消失 / 焦点抢回。除非有强烈视觉要求，
**接受这条 OS 边**，软著截图也只会被认为是 Windows 原生菜单的正常样子。

### 8.5 Numba JIT 冷启动
- 第一次 import 后第一次调用会编译（数秒延迟）
- 如果第一次分析特别慢（>30s），看是不是 numba 在编译
- 不要在 GUI 启动路径上 import numba 函数（懒加载，等真正分析时再 import）

### 8.6 高 DPI awareness
```python
# gui.py 入口必须最早执行：
if sys.platform.startswith("win"):
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
```
**必须在任何 Tk / matplotlib 初始化之前**，否则 figure DPI 错乱。

### 8.7 K-means 空簇救援（已实现，不要破坏）
sklearn KMeans 可能让某簇为空。本项目有三层兜底：
1. UI：`Cluster N` / `cPhon N` 列即使全零也保留显示（让用户看到"这次该簇空"）
2. Calculator 内：检测空簇 → 抢最远点重赋
3. Aggregator：post-filter 时不删空 cluster 的列

不要"简化"掉这些。

### 8.8 Formant 带宽 FWHM 算法（已修，不要回滚）
commit 6527ea5：FWHM 走的左右边界用相邻 peak 限住，不能跨过去；
超过 800 Hz 判为伪值清零。这是对 27s np.roots 慢路径的取舍补救，
回滚会让 B1/B2/B3 跑出 5000 Hz 的伪带宽。

### 8.9 高 DPI tkinter 字体回退
中英文混排时 Segoe UI 对中文回退到默认中文字体，导致**有些字像加粗有些不像**。
全 GUI 强制 `Microsoft YaHei UI`（Windows 自带，中英都有专门字形）。

### 8.10 Logger handler 装在 root
不要再走 "给 voicemap / analyzer / metrics 每个 logger 加同一个 handler" 的老路。
`setup_logger` 已经在 root 装 handler，所有子 logger 自动继承。

---

## 9. Git 工作流

- **commit 频率**：高。每个独立改动一个 commit，不要积一坨
- **commit message**：第一行简体中文 + 英文混合 OK，body 用英文。前缀按 conventional commit：`feat: / fix: / refactor: / docs: / chore: / perf: / test:`
- **不要加** `Co-Authored-By: Claude` 之类的 trailer
- **PR 描述**：不要在 PR body 加 "🤖 Generated with Claude Code" 尾注

### 推送策略
- main 分支推送被仓库策略拦（要走 PR）。**不要试图绕过**
- 用户开放 main push 时再推；否则就让 commit 留在本地，告知用户

### 重构 commit 必走 validate_params 卡点
任何 A0 这种结构性变动 commit 之前**必须**：
```bash
python tests/validate_params.py audio/test_Voice_EGG.wav
# 看到 "PASS=48  WARN=4  FAIL=0" 才能 commit
```

---

## 10. 软著相关纪律

A0 阶段会产出：

- 一份能跑的 `VoiceMap.exe`（PyInstaller 产物）
- 用户手册.md → 用户手册.pdf
- 设计说明书.md → 设计说明书.pdf
- LICENSE（MIT）
- About 对话框里的版权声明
- README.md 的版权声明 + 作者信息

这些**不要**自动加 "Co-Authored-By Claude" 或类似的 AI 署名。
软著申请人是个人，作者署名只写 **蔡寰宸 / Huanchen Cai**。
邮箱：huanchen.se@gmail.com（用户全局 CLAUDE.md 已记录）。

---

## 11. 快速决策表

| 用户提的需求                | 第一反应                                                                 |
|----------------------------|--------------------------------------------------------------------------|
| 加新 metric                | A0 之前**不接**，A0 之后走 metrics.py + metrics_registry.py 标准模式      |
| 加新对话框                 | A0-2 之后放 gui/dialogs.py                                               |
| 加新 UI 文字               | i18n.py 双语 entry，禁止硬编码                                           |
| GUI 行为不正常             | 优先看 #8 已知坑列表（10 条以内基本能命中）                                |
| 性能问题                   | 先看 numba 是否冷启动；再看 metrics 是否 batched；最后看 matplotlib 是否 redraw       |
| "界面有点丑"               | A0 之前不动，A0 之后归 M4 主题                                           |
| "做个网页版"               | 拒绝，软著定位冲突。明确告诉用户                                           |
| 改 Qcontact/Icontact 公式 | 拒绝，是身份标识                                                          |
| "我们用 PyQt 重写吧"      | 拒绝，没研究价值                                                          |
| 验证失败                   | 立即回滚，不要"边查边写"                                                   |
