# Roadmap

按软著优先级 + 依赖关系组织。完成一个在 `DEV_LOG.md` 标 ✅ 并打勾这里对应条目。

## 总目标

发软著（中国版权保护中心）→ 拿证 → 解冻继续做研究功能。

软著前优先级最高的是 **A0（架构改造 + 中英文化 + 打包）**，其次 **A1（申请材料）**。
M3-M7 这些研究/科研增强项**全部推到拿证后**做。

## 软著线（必做，按顺序）

### A0 — 软著前置改造（重构 + i18n + 包装）

完成顺序按下面 5 步走，**每一步独立 commit + 跑 `validate_params.py` 卡点**，
绿了再做下一步，红了立刻回滚。

#### A0-1 架构重排 + 全局 rename

- [ ] 项目目录 `FonaDyn.py/` → `VoiceMap/`（**OS 层 rename，需要用户在关闭所有终端后手动改名**）
- [x] 包目录 `src/` → `voicemap/`（commit db8aceb）
- [x] 入口拆分：`gui.py` → `voicemap/gui.py`、`main.py` → `voicemap/cli.py`、根目录新增薄壳 `main.py`
- [x] FonaDyn 字面量全部改 VoiceMap（软件名占用全部清理；剩余 FonaDyn 全是上游 KTH 项目引用，保留）
- [x] 类名 `FonaDynApp` → `VoiceMapApp`
- [x] CSV header `# FonaDyn cluster centroids` → `# VoiceMap cluster centroids`（loader 兼容旧格式）
- [x] 窗口标题 `Voice Mapping` → `嗓音声学品质多维分析图谱`
- [x] 新增 `voicemap/__version__.py`（版本/作者/版权单一来源）
- [x] 整理 `voicemap/__init__.py`（只 re-export 高层 facade：`VoiceMapAnalyzer` / `VoiceMapConfig` / `__version__` 等元数据；不再 re-export 单个 calculator）
- [x] 内部 sibling import (`from config import`) 全改成绝对包路径 (`from voicemap.config import`)
- [x] `tests/validate_params.py` 适配新结构

**验证**：`validate_params.py` 仍 48 PASS / 0 FAIL ✓；`main.py --gui` 能起 ✓；`main.py audio/test_Voice_EGG.wav` CLI 能跑 ✓。

#### A0-2 god 类拆分

- [x] **gui.py 拆分**（2096 行 → 5 个文件）：
  - [x] `voicemap/gui/__init__.py`：转出 `VoiceMapApp` / `main`（10 行）
  - [x] `voicemap/gui/theme.py`：颜色 + 字体 + `_METRIC_SECTIONS`（~80 行）
  - [x] `voicemap/gui/widgets.py`：`MetricPopup` + `QueueHandler`（~250 行）
  - [x] `voicemap/gui/dialogs.py`：`SettingsDialog` / `CompareDialog` / `ProgressDialog` / `AboutDialog`（新，~370 行）
  - [x] `voicemap/gui/app.py`：`VoiceMapApp` + `main`（剩 1505 行；类本身的进一步拆分留给 A0-4）
  - [x] 帮助菜单加 "关于..." → AboutDialog
- [x] **analyzer.py 拆分**：`output_vrp_csv()` (253 行) → `voicemap/csv_writer.py:write_vrp()`；analyzer 留 15 行 shim 保持 API 不变
- [x] **保持 metrics.py 不拆**：按计划

**验证**（A0-2 完成时）：
- `validate_params.py`：48 PASS / 4 WARN / 0 FAIL ✓
- `main.py audio/test_Voice_EGG.wav --plot-mode none`：12s 跑完 ✓
- GUI 启动 + 关于对话框可弹出 ✓

#### A0-3 工程化 + 软著元数据

- [x] 新增 `pyproject.toml`（声明依赖 / entry point `voicemap = voicemap.cli:main` / 动态版本读自 `voicemap/__version__.py`）；`requirements.txt` 留作 conda/IDE 兼容
- [x] 新增 `LICENSE`（MIT + 上游 KTH FonaDyn 致谢段）
- [x] "关于" 对话框（A0-2 已加，菜单 帮助 → 关于...）—— A0-4 视觉打磨
- [x] 每个 .py 顶部加 `# -*- coding: utf-8 -*-`（13 个文件补齐，8 个已有）
- [x] **GUI 调色板切到 option C**（`voicemap/gui/theme.py`）：BG 深灰 / ACCENT amber，对应 `docs/UI_DESIGN.md` 设计稿。旧常量名 `BG` / `PANEL` / `ACCENT` 等保留以免改 widget 代码；新增 spec-verbatim 别名 `BG_APP` / `BG_PANEL` / `BG_ELEVATED` / `TEXT_SEC` / `ACCENT_HOVER` 等供新代码使用

**验证**：
- `validate_params.py`：48 PASS / 4 WARN / 0 FAIL ✓
- `pip install -e .`：成功，`import voicemap; voicemap.__version__` 可读 ✓
- GUI 启动 + palette 切换可见：amber 强调色 + 深灰底

#### A0-4 中英双语 + i18n 框架 + option-C 布局重排

- [x] **`voicemap/i18n.py`** dict-based 翻译表（160+ 键 zh/en 对称），`tr(key, **kw)` API + `set_language` + `subscribe` + `~/.voicemap/config.json` 持久化
- [x] **顶部菜单 帮助/Help → 语言/Language → 中文/English** 一键切换
- [x] **运行时即时切换**：menubar 整体重建、popup 工厂在每次点开时重读 `tr()`、persistent widgets 通过 `_safe_text` 助手批量更新
- [x] **全 UI 字符串入表**：顶部菜单、Tracks 标题、Metric Bar、Inspector（详情/单位/临床/当前值/三个 action 按钮）、Status Bar、4 个 Dialog（Settings/Compare/Progress/About）、25+ 条 log 消息、filedialog 标题
- [x] **option-C 布局重排**（commits 42bd9da → 3c5360b）：
  - 菜单栏 → 1px 分隔线 → Header (PANEL 同色，无黑纹) → Tracks Panel → Metric Bar → 主区(Canvas + Inspector 360px) → Status Bar
  - **Inspector**：metric 大字 + 描述 + 单位（独立行）+ 临床范围卡（滚动）+ Current value 卡（pinned，永久可见）+ 3 个 action 按钮（pinned）
  - **Hover 探测**：鼠标在画布任意 cell → Inspector 当前值实时更新（含 MIDI/SPL/数值/严重度色）
  - **多文件 Tracks Panel**：TrackEntry dataclass + 行格式（编号 + 状态符号 + 文件名 + 元数据 + Unicode block 波形）+ 点击切换 active + 已分析自动缓存
  - **日志移出**：从 Inspector 拆出，View → 日志面板独立 Toplevel
  - **窗口最小尺寸**：1280×800 默认 / 1200×720 minsize
  - **字体 token 化**：FONT_CAPTION/SMALL/UI/UI_B/SUB/DROP/H2/TITLE/DISPLAY/MONO/MONO_B 9 级，硬编码字体全清
- [x] **专业术语保留括号英文**："聚类中心 (Centroid)" 等

**验证**：启动后切英 → 全 UI 立即英文；切回中 → 立即中文；重启后保留上次选择 ✓
`validate_params.py`：48 PASS / 4 WARN / 0 FAIL

#### A0-5 打包 + 用户文档

- [x] **PyInstaller 配置**：`VoiceMap.spec`（one-folder 布局，commit 9254fde）
  - 收齐 numba / sv-ttk / tkinterdnd2 / matplotlib / soundfile 数据
  - 显式 hidden imports 列出所有 voicemap.* 子模块（避免延迟导入漏掉）
  - excludes 砍掉 PyQt / pytest / parselmouth / Jupyter 减体积
  - **构建命令**：`build_exe.bat` 双击，输出 `dist/VoiceMap/VoiceMap.exe`
  - **未实际跑过构建**：等本机首次执行时验证；spec 是契约
- [x] Inno Setup 脚本 → `VoiceMap_v1.0.0_setup.exe`（commit 4ee54f3）
- [x] **`docs/用户手册.md`**（commit ef3002d，~360 行 markdown）
  - 软件概述 / 系统要求 / 启动方式
  - 5 区域 UI tour（菜单栏 / 标题 / Tracks / Metric Bar / 主区 / Status Bar / Inspector）
  - 单文件 + 多文件操作流程
  - 设置 / 临床阈值速查 / CLI 用法 / 故障排查
- [x] **`docs/设计说明书.md`**（commit ef3002d，~360 行）
  - 分层架构 + 依赖图 + 项目目录
  - 3 个数据流图（单文件 / hover 探测 / 多文件切换）
  - 11 个模块逐个说明
  - 6 个关键设计决策
  - 性能基准 / 验证基准 / PyInstaller 配方 / 致谢
- [ ] **核心截图 8-10 张**：等 v1.0.0 截屏会话产出，用户手动跑

**验证**：`dist/VoiceMap.exe` 在干净 Windows 上能启动、能跑分析、能切语言（首次构建后跑）。

#### A0-完成判据 / 当前状态

| 判据 | 状态 |
|------|------|
| A0-1 架构重排 + rename | ✅ commit 10e921e |
| A0-2 god 类拆分 | ✅ commit 56172ad |
| A0-3 工程化 + 软著元数据 | ✅ commit 4f1188e + 后续 |
| A0-4 中英双语 + option-C 布局 | ✅ commit ec11ddb（5 个 wave 累计） |
| A0-5 打包 + 用户文档 | ✅ exe 构建 + 启动验证；installer + 截图待跑 |
| `validate_params.py` 全绿 | ✅ 48 PASS / 4 WARN / 0 FAIL（贯穿） |
| 中英文 UI 截图各一组 | 🟡 待人工跑 GUI 截屏 |
| 一个能跑的 `VoiceMap.exe` | ✅ `dist/VoiceMap/VoiceMap.exe` 17.0 MB exe / 350 MB folder，双击启动正常 |
| 用户手册 + 设计说明书定稿 | ✅ commit ef3002d |
| git tag `v1.0.0` | 🟡 上述都验证后打 |

剩下两件需要人工 session：
1. 跑一次 `ISCC.exe installer.iss` 验证 Inno Setup（需先安装 Inno Setup 6）
2. 截 8-10 张 v1.0.0 截图（中英文各一组）

完成后即可打 `v1.0.0` tag 然后进 A1（软著申请材料包）。

---

### A1 — 软著申请材料包

A0 全部完成后做。**期间不要再合任何 PR / 加任何功能**，分支冻结。

- [ ] 软件源代码打印件（前 30 + 后 30 页 PDF，行号 + 文件名页眉）
- [ ] 用户手册定稿（A0-5 的 .md → PDF）
- [ ] 设计说明书定稿（A0-5 的 .md → PDF）
- [ ] 运行截图 8-10 张（A0-5 已经为用户手册截过，复用）
- [ ] 申请书 / 鉴别材料填写
- [ ] 提交中国版权保护中心
- [ ] 拿证（30-60 工作日）

---

## 软著拿证后（解冻）

按下面顺序继续。每一项都假设 v1.0.0 软著版本已锁定，新功能在 v1.1 起的次版本里释放。

### M3 — 研究功能：多聚类模型

- [ ] 多聚类引擎切换（GMM、Hierarchical、DBSCAN、Spectral、BIRCH）
- [ ] 正交分析：聚类结果与各 metric 的相关分析
- [ ] Cluster 个数自动选择（silhouette / BIC 曲线）

### M4 — 主题 / 视觉

- [ ] 色彩主题：Default / Colorblind-safe / Print-friendly / High-contrast
- [ ] 暗色 / 亮色 GUI 主题切换

### M5 — 场景预设

- [ ] 使用场景预设：普通 / 语音专家 / 医疗 / 歌手 / TTS / 戏曲（不同预设 = Clarity 阈值 / 默认 metric / 输出列不同）

### M5.5 — Audition 式文件管理面板

让 GUI 从"一次拖一个 wav"升级到"批量管理 + 切换"工作流。

- 左侧 / 顶部新增 **Files** 面板：当前 session 加载的所有音频，每条显示文件名 + 采样率 + 时长 + 分析状态 ✓ / ○
- 拖一批 .wav 进来 → 全部入列，第一个自动分析，其余排队
- 单击列表项 → 切换右侧 voice map（已分析的从内存恢复 DataFrame；没分析的就地分析）
- 右键 → 上下文菜单：分析 / 重分析 / 导出 CSV / 导出 Excel / 移除 / 资源管理器 / 加入对比集
- Ctrl+click 多选 → 批量分析、批量导出、跨文件叠加 voice map
- 持久化 session：关 GUI 时保存最近文件 + 当前选中

### M6 — UI / UX 完善

- [ ] 状态栏：当前选中文件元数据（采样率 / 通道数 / 时长 / cycles 数 / 分析耗时）
- [ ] 最近文件：drop zone 旁加 "最近分析过的 wav"
- [ ] 全局快捷键：Ctrl+O / Ctrl+S / Ctrl+E / 方向键切 metric
- [ ] 配置持久化：所有 Settings 项 + 当前语言 + 最近文件存 `~/.voicemap/config.json`

### M7 — 方法学提升 / 数据质量

减少现有 ⚠️ 方法差异，让输出更接近教科书 / Praat 标准。

- [ ] Formant 方法切换：LPC spectrum peak-picking (FWHM, 当前) vs LPC root-finding (Praat 方式)
- [ ] OQ 阈值法（3/7 或 25%）作为 derivative 法的对照，输出 `OQ_threshold` 列
- [ ] cPhon 特征权重：让用户勾选哪些维度参与 z-score / 给维度加权
- [ ] 空簇救援换 K-means++ 距离采样
- [ ] Vibrato 规则性 / 抖动：rate / extent 之外加 vibrato jitter（已经在 M1 加了，确认实现）
- [ ] Singer's formant band 可配（2.5-3.5 kHz vs 2.8-3.4 kHz）
- [ ] M1 P2 列指标（频谱衍生 / 倒谱 / 韵律 / Formant 衍生 / EGG 高级 / 唱歌进阶 / 临床合成 / 非线性 / CAPE-V）

### M8 — 研究工作流

- [ ] Cluster 命名持久化：分析完后给 maxCluster 标 label（"breathy" / "pressed" / "modal"），写到 centroid CSV header
- [ ] 多录音统计视图：批量导入 N 个 CSV → 每 metric 的箱线图 / 散点
- [ ] 人口分层 VRP：按标签（年龄、性别、行当）叠加多 VRP，算平均 / 标准差
- [ ] 临床报告自动导出：一页 PDF（VRP 缩略图 + 核心指标 + 参考范围标红）
- [ ] Segment 选择：拖入长录音后波形上框选片段再分析
- [ ] 实时分析：麦克风 + EGG 流式读取，每 1s 更新 VRP
- [ ] SC centroid 互通：写 SC `cEGG.csv` ↔ 本工具格式转换脚本

### M9 — ML 方向（长期）

- [ ] 跨受试者标准化（per-subject z-score）
- [ ] 深度学习 phonation classifier（用 cPhon 标签训 1D-CNN，替代 K-means）
- [ ] 大规模数据集 benchmark（Saarbruecken Voice Database、AVSpoof）

---

## Milestone 1 — 回填未测试功能验证（与 A0 并行可做）

`DEV_LOG.md` 里 🟡 untested 一栏清零。code 已有，只需人工跑一遍。

- [ ] 多 wav 联合 centroid 训练端到端：2 段不同录音 → 联合训练 → 用产物 CSV 跑第三段
- [ ] `CompareDialog` 工作流：2 个 VRP CSV 逐 metric 看 Δ
- [ ] 真的导出一个 `.xlsx` → Excel/WPS 打开 → 40+ sheets 中文列名无乱码
- [ ] 批处理：`audio/{a,b,c}.wav` → `python main.py --batch audio/`
- [x] `--plot-mode combined`（commit ce85204 后再跑一次，2.3 MB 总览 PNG 正常）
- [x] Centroid 加载后**只分类**路径："Classified against N preloaded centroids"（commit 09d17f9）

---

## 不做（明确拒绝）

- ❌ **修改 FonaDyn 特有的 Qcontact / Icontact / HRFegg / Entropy 公式** —— 与 SuperCollider 原版一致是身份标识。需要 Praat 版本的用户该用 Praat
- ❌ **替换 tkinter 为 PyQt / Tauri** —— 当前 GUI 够用，切引擎不带来论文价值
- ❌ **EGG 周期检测改成语音自相关** —— 那就变 Praat 了
- ❌ **浏览器版本（PyScript / Streamlit）** —— 软著定位是桌面软件，浏览器版与名称冲突。如未来要做，作为独立项目立项
- ❌ **改名回 FonaDyn** —— 撞 KTH 项目名
