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

- [ ] **gui.py 拆分**（1429 行 → ~4 个文件，每个 ~350 行）：
  - `voicemap/gui/app.py`：`VoiceMapApp` 主类，仅协调
  - `voicemap/gui/theme.py`：颜色 / 字体 / ttk style
  - `voicemap/gui/widgets.py`：`MetricPopup` / 自定义 widget
  - `voicemap/gui/dialogs.py`：`SettingsDialog` / `CompareDialog` / `AboutDialog`（新）
- [ ] **analyzer.py 拆分**：把 `output_vrp_csv()` (252 行) 抽到 `voicemap/csv_writer.py`
- [ ] **保持 metrics.py 不拆**：内部已按 calculator 类组织得不错，硬拆反而增风险

**验证**：同 A0-1。

#### A0-3 工程化 + 软著元数据

- [ ] 新增 `pyproject.toml`（替代 `requirements.txt`，定义 entry point、版本、deps）
- [ ] 新增 `LICENSE`（MIT，软著申请材料里要附）
- [ ] 新增"关于" 对话框（菜单 帮助 → 关于）：软件名 / 版本号 / 作者 蔡焕晨 / 邮箱 / 版权声明
- [ ] 每个 .py 顶部加标准 header（`# -*- coding: utf-8 -*-` + 模块说明 + 版权 + 作者）

**验证**：同 A0-1，加 `pip install -e .` 能装上。

#### A0-4 中英双语 + i18n 框架（关键）

- [ ] 新增 `voicemap/i18n.py`：极简 dict-based 翻译表（不用 gettext，避免 .mo 编译麻烦）
  - 结构：`STRINGS = {"zh": {...}, "en": {...}}`
  - API：`tr("key")` 根据当前语言返回字符串
- [ ] 新增 `LanguageVar` 全局 StringVar，绑定到所有 UI 文字
- [ ] 菜单：`帮助/Help → 语言/Language → 中文/English` 切换
- [ ] 切换后立即生效（widget textvariable + 重建菜单），不需重启
- [ ] 持久化：当前语言写到 `~/.voicemap/config.json`，下次启动恢复
- [ ] 全 UI 字符串扫描入表（顶栏菜单、按钮、状态、log 关键提示、错误对话框、报告标题）
- [ ] **专业术语保留括号英文**："聚类中心 (Centroid)"、"清晰度 (Clarity)"、"指标 (Metric)"

**验证**：启动后切英 → 全 UI 立即英文；切回中 → 立即中文；重启后保留上次选择。

#### A0-5 打包 + 用户文档

- [ ] PyInstaller 配置：`pyinstaller --onefile --windowed --icon=... voicemap/cli.py`
  - 处理 numba / scikit-learn / tkinterdnd2 / matplotlib 隐式依赖（`--hidden-import` / `--collect-all`）
  - 输出 `dist/VoiceMap.exe`（标的：< 200 MB）
- [ ] Inno Setup 脚本 → `VoiceMap_v1.0.0_setup.exe`
- [ ] **用户手册.md**（双语，10-30 页 PDF）：截图 + 步骤说明
  - 核心截图 8-10 张：初始界面、拖入 wav、分析中、完成、各 metric 切换、设置、对比、报告、关于
- [ ] **设计说明书.md**（双语，10-30 页 PDF）：架构图 + 模块说明 + 数据流图

**验证**：`dist/VoiceMap.exe` 在干净 Windows 上能启动、能跑分析、能切语言。

#### A0-完成判据

- 所有 5 步打勾
- `validate_params.py`：48 PASS / 0 FAIL
- 中英文 UI 截图各一组
- 一个能跑的 `VoiceMap.exe`
- 用户手册 + 设计说明书定稿
- git tag `v1.0.0`

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
