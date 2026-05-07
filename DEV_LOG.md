# 开发日志 Development Log

Purpose: 记录每一轮做了什么、测过没，未测试的功能单独标出来方便回头补验证。
新改动请**按时间倒序**追加到顶部。每条标注状态：

- ✅ **tested** — 用户在 GUI / CLI 里真实走过一遍，确认符合预期
- 🟡 **implemented, untested** — 代码写完、单元冒烟通过，但没有端到端人工验证
- ⚠️ **known issue** — 已知问题 / 方法学差异 / 需要下轮改
- 📝 **doc** — 仅文档 / 重构，无功能变化

---

## 2026-05-07 (深夜3)  i18n 大补 + 波形换 Canvas + Inspector 加宽

用户回报三个具体问题：
1. metric 描述全英文（"(T - GOI) / T from dEGG peaks." 等）—— 中文模式下尤其刺眼
2. 本次值 pill 里 "MIDI 60 · SPL 75 dB" + "watch" 都是英文
3. OQ / Hammarberg 等长 zh label 在 Inspector 360 px 宽度下被截
4. Tracks panel 的 Unicode-block 波形看不出形状（commit 4495871）

### ✅ tested

**i18n 大补**（commit 4495871）：
- `voicemap/i18n.py` 新增 80+ `metric.desc.<KEY>` 键，zh + en 各一份对称
  - 每个 metric 的 description 走 `tr(f"metric.desc.{name}")`，键缺失才
    fallback 到 `metrics_registry` 的英文 spec.description
  - 切换语言后 metric 详情立刻跟着切（`_on_language_changed` 已经会调
    `_update_inspector`）
- 严重度标签入表：`severity.good/normal/watch/abnormal` →
  zh: 优 / 正常 / 注意 / 异常；en 保留原文
- 坐标 pill 入表：`inspector.coords` →
  zh: '音高 60 · 声压 75 dB'；en: 'MIDI 60 · SPL 75 dB'

**Inspector 加宽 + 默认窗口** (commit 4495871)：
- Inspector 360 → **420 px**（band-label 列从 ~257 px 加到 ~330 px，
  zh 长 label 不再被截）
- 默认 geometry 1500×1180 → **1600×1180**
- min 1280×900 → 1380×900
- metric_desc wraplength 300 → 370 配合新宽度

**波形从 Unicode block 换 tk.Canvas 柱状**（commit 4495871）：
- 旧的 ' ▁▂▃▄▅▆▇█' 字符在 voice 录音上几乎全是 ▁（多数样本远小于峰值），
  渲染成稀疏短横线，看着像断线
- 新方案：`_track_waveform_amps` 读 wav → 110 桶 peak-bucket → 归一化 [0,1]；
  `_draw_waveform_canvas` 在 220×36 px tk.Canvas 上画居中柱状，floor 1 px
  让安静段也有线，看着像真波形包络
- `_waveform_cache` 从 str 换成 (n_buckets, np.ndarray) tuple
- 单测 `test_tracks.py` 跟进：`test_waveform_blocks` → `test_waveform_amps`

**对齐 docs/UI_DESIGN.md FONT_HUGE**（commit f31a1a2）：
- 之前为了在小窗口塞下内容，把 value pill 大数字从 22pt 强行压到 18pt，
  违背 spec 'Consolas 24pt bold ACCENT_HOVER 大数字'
- 现在窗口已经够大，恢复到 FONT_MONO_B (22pt bold)
- 验证：1600×1180 下 VibratoRate 5-band 最坏情况，pad 419/392 px，
  6 行 actual=req=36 px 零裁切

### ⚠️ 还没修

- `_THRESHOLDS` 里的临床带 label（"开商正常 (0.4-0.7, 模态)" 等）只有 zh
  版，en 模式下也显示中文。这是反向 i18n 漏，不影响主用户场景，先放着
- spec 里 FONT_TITLE 13pt vs 实现 18pt 的差异 —— 改了影响整窗视觉，等用
  户明确要求再动

---

## 2026-05-07 (深夜2)  Inspector 尺寸定型 — 默认 1500×1180 零裁切

### ✅ tested

用户反馈："右边天然就藏着数值看不见，必须拉大窗口才行" → "做一个标准的尺寸，
可以大一点，但是任何信息都不能被裁掉"。

**根因诊断**：1280×800 默认尺寸下，Inspector 实际只有 ~417 px 纵向，但
最坏 metric（VibratoRate 5 临床带 + 名+描述+单位+pinned value pill）
内容需求 ~830 px。content > frame 直接被裁。
具体：临床带行 wraplength=200 把 label 强 wrap 成 2-3 行（66 px/行），
5 带共 ~330 px；pad 用 fill=x 没拿到剩余纵向空间。

**修复（commit 0903afe）**：
1. 默认 geometry 1280×800 → **1500×1180**，min 1200×720 → 1280×900
2. pad pack 从 fill=x 改 fill=both expand=True，拿到 inspector 剩余纵向
3. 临床带行去 wraplength=200（200 < 可用宽 250+），强行 wrap 退化成
   单行 36 px；5 带从 ~330 px 压到 ~220 px
4. 临床带 range 列字号 FONT_MONO 10→9pt，width 12→10
5. value pill 字号 FONT_MONO_B 22→18pt，pady 10→6（净缩 ~20 px）
6. header / tracks / metric_bar 三处 chrome pady 各砍 2-4 px

**验证**：1500×1180 下 VibratoRate（最坏 5 带）pad 拿到 434 px / req 422 px，
heading + 5 bands 全部 actual=req=36 px，零裁切。
`pyinstaller --noconfirm --clean VoiceMap.spec` 重建 → 双击 exe 启动正常。

---

## 2026-05-07 (深夜)  v1.0.0 出包前的最后一轮抛光

承上一条 Inspector 修复后，跑了一轮端到端 + 静态扫描，把找到的小毛病一并清掉。

### ✅ tested

- **bundled exe 端到端** — `dist/VoiceMap/VoiceMap.exe audio/test_Voice_EGG.wav --plot-mode=per-metric`
  跑完 42.96s，输出 79 张 PNG + CSV；`--excel --report` 一并干净，无 DLL/import 报错。
- **i18n 漏字符串** — 两处中文硬编码补 tr()：
  - 窗口标题里的 dnd_hint（commit 8925415）
  - train-centroids 进度对话框的 "个 wav" 字串（commit 1d1b27b）
- **build_exe.bat / 启动.bat** — 不再硬编码 `C:\Users\huanc\miniconda3\...`，按
  `VOICEMAP_PYTHON env > miniconda fonadyn > anaconda fonadyn > PATH` 顺序探测，
  任何机器装好依赖后双击都能跑（commit bd528e9 / e9c13b0）。
- **installer.iss** — Inno Setup 6 base 不带 ChineseSimplified.isl，加 `#ifexist`
  守卫；没装翻译包的机器照样能 ISCC 编译（只剩英文）；装了就自动启用中文（commit 0d6783a）。

### 📝 doc

- `DEV_LOG.md`：本条 + 上条
- `ROADMAP.md`：A0-5 状态从 🟡 升 ✅ ("一个能跑的 VoiceMap.exe" + "exe 构建 + 启动验证")。
  剩余两件人工 session 是 Inno Setup 编译（需先装 Inno）+ 截图。

### ⚠️ 还没做的

- v1.0.0 截屏（zh + en × 4-5 状态 = 8-10 张）
- ISCC.exe 编译 → `dist/VoiceMap_v1.0.0_setup.exe`
- `git tag v1.0.0`

---

## 2026-05-07  A0-5 收尾 — 首次 PyInstaller 端到端打通 + Inspector 修复

### ✅ tested

首次完整跑通"双击 build_exe.bat → 双击 VoiceMap.exe → GUI 正常出现"全链路。

**fix 1 — `VoiceMap.spec` collect_all 与新 PyInstaller TOC 不兼容**
症状：`pyinstaller VoiceMap.spec` 报 `ValueError: not enough values to unpack (expected 3, got 2)`。
原因：PyInstaller >= 6.0 在 `Analysis` 构造完成后将 `a.datas` 规范为 3-tuple TOC；旧 spec
在 init 之后做 `a.datas += collect_all(...)`（2-tuple）就崩了。
修复：把 collect_all 结果在 Analysis() 构造时通过 `binaries=` / `datas=` / `hiddenimports=`
传入，不再 post-init 扩展。commit a8b7747.

**fix 2 — exe 启动报 `ImportError: DLL load failed while importing _ctypes`**
症状：第一版 exe 双击瞬间黑窗一闪。打开 console=True 看到 _ctypes 无法导入。
原因：conda 把 `libffi-7.dll` / `ffi-8.dll` 放在 `<env>/Library/bin/`，PyInstaller 不去爬
这个 conda-only 路径，所以 `_ctypes.pyd` 找不到 libffi。
修复：spec 里加 `_conda_runtime_dlls()` helper，把 `<env>/Library/bin/*.dll` 全部拉到
bundle 根（与 `python310.dll` 同级），LoadLibrary 自然找到。commit 3cb8b63.

**fix 3 — 双击 VoiceMap.exe 没反应（无错误也无窗口）**
症状：第二版 exe 双击毫无反应。
原因：双击不带任何参数 → `cli.py` 走 CLI 单文件分支，找默认 `audio/test_Voice_EGG.wav`
（只在源码目录里有），找不到就 `sys.exit(1)`，windowed 模式无 console 所以悄无声息地退。
修复：cli.py 加 no-args → GUI 默认；`voicemap audio.wav` 等显式 CLI 调用照常走 CLI。
commit c48fb38.

**fix 4 — Inspector 顶部 metric 详情区被吞**
症状：默认 1280×800 窗口下，Inspector 只看得到底部"本次值"卡 + 3 个 action 按钮，
metric 名 / 描述 / 单位 / 临床范围全没出来。
原因：Inspector 顶部用了 `tk.Canvas` + `Scrollbar` 的滚动容器，在 sv-ttk 主题下 canvas
没拿到可用高度（fill=both expand=True 失效），scrollable_frame 内容随之高度为 0。
修复：恢复直接 pack —— 默认窗口尺寸足够装下静态卡片，用户拉小到 floor 以下就接受顶部
卡可能裁切；pinned 当前值卡 + actions 始终可见不受影响。commit 8103829.

**最终交付物**
- `dist/VoiceMap/VoiceMap.exe` — 17.0 MB exe，350 MB 整包
- 双击启动正常，全 UI（顶菜单 / Tracks 占位 / Metric Bar / Canvas / Inspector / Status Bar）
  按 option-C 布局渲染
- 15/15 单元测试通过；validate_params.py 仍 48 PASS / 4 WARN / 0 FAIL

---

## 2026-05-07  A0-4 / A0-5 — i18n + option-C layout + 多文件 + 软著文档

### ✅ tested

A0-4 的 5 个 wave + A0-5 的文档/打包配置全部完成（commit ec11ddb → bdce189）。

**A0-4 wave 1-2: i18n 框架**
- `voicemap/i18n.py` 上线：160+ 键 zh/en 对称，`tr(key, **kw)` API
- 持久化到 `~/.voicemap/config.json`，重启恢复
- 帮助 → 语言子菜单一键切换，毫秒级整窗重渲（菜单条重建 + 持久 widget 批量 .configure）
- popup factory 在每次点开时实时读 `tr()`

**A0-4 wave 3a-3f: option-C 布局**
- 旧的 ttk.PanedWindow（左面板 + 右面板）整片拆掉
- 顶部菜单条 / 标题 / Tracks Panel / Metric Bar / 主区(Canvas + Inspector 360px) / Status Bar 5 段式
- Inspector 详情：metric 大字 + 描述 + 单位 + 临床范围（滚动）+ 当前值 pill（pinned）+ 3 action 按钮（pinned）
- **鼠标 hover 探测**：matplotlib motion_notify_event → cell 值实时显示，severity 颜色实时变
- **多文件 Tracks Panel**：TrackEntry dataclass + 行格式（编号/状态/文件名/元数据/Unicode 波形）+ 点击切换 active + 已分析自动缓存
- 日志移出主界面：View → 日志面板独立 Toplevel
- 字体 token 化：FONT_CAPTION/SMALL/UI/UI_B/SUB/DROP/H2/TITLE/DISPLAY/MONO/MONO_B 9 级

**A0-5: 文档 + 打包配置**
- `docs/用户手册.md` ~360 行
- `docs/设计说明书.md` ~360 行
- `VoiceMap.spec` PyInstaller one-folder 打包配置 + `build_exe.bat` 一键构建脚本

**关键 Tk 坑（CLAUDE.md §8 已记）**:
- tk.Menu 在 Win11 上 1px 白边 → 自画 ModernMenubar + ModernPopup（`voicemap/gui/modern_menu.py`）
- overrideredirect Toplevel 多屏定位 → withdraw → set geometry → deiconify
- popup orphan after lang switch → 切语言前先 `_close_open_popup()` 清栈
- BG-coloured outer-pady 显出"黑纹" → 标题行直接 pack 到 self，bg=PANEL 跟菜单条同色

### 待人工验证（next session）
- `dist/VoiceMap.exe` 实际构建 + 干净 Windows 启动测试
- 8-10 张核心截图（初始 / 拖入 wav / 分析中 / 完成 / metric 切换 / Inspector hover / 设置 / 关于）

### Commits 参考
ec11ddb / 4c67f9d (i18n), 8e3bd97 / 1247d7a (header 黑纹), 56172ad / 5da2508 (Inspector wire), 099ef52 / ca7ad8a (多文件 + 波形), 5bcaa2e / 3c5360b (字体 token), ef3002d (文档), 9254fde (PyInstaller spec).

---

## 2026-04-23  M1 — Metric registry + 22 new clinical/学术参数 (待验证)

### 🟡 implemented, untested (待验证)

按 ROADMAP M1 走完第一阶段。**新建注册表** `src/metrics_registry.py` 让所有
metric metadata 集中管理 + 一次性加 22 个常见学术 / 临床声学指标。CSV 列
数 60 → **82**。

**注册表 (M1.a)**：
- `MetricSpec` dataclass + `REGISTRY` 全局字典 + `register()` 函数
- 自动登记 46 个原有 metric（含 P1/P2/P3 + add-on）
- plotter `_merge_registry_into_plotter()` 把注册表内容并入 `METRIC_CFG`
  / `METRIC_CATEGORY` —— 新加 metric 不需要再改 plotter.py，注册即可见
- 后续 M2-M6 都基于这个注册表

**新增 metric（22 项 → 32 列；MFCC 占 13 列）**：

声学：
- **RMS** — 时域均方根
- **F0_Hz** — 原始基频 Hz（=440·2^((MIDI-69)/12)）
- **SpectralCentroid / Bandwidth / Rolloff85 / Flatness / Slope / Skewness / Kurtosis** — 7 项谱矩
- **AlphaRatio** — 50-1000 Hz vs 1-5 kHz 能量比 (dB)
- **HammarbergIndex** — max(0-2 kHz dB) − max(2-5 kHz dB)
- **MFCC 1-13** — 13 列 mel-frequency cepstral coefficients（自实现，无 librosa）
- **GNE-like** — Glottal-to-Noise Excitation 简化代理（待真实 Michaelis 算法替换）

唱歌特异性：
- **B1, B2, B3** — LPC 根法估计的共振峰带宽
- **FormantDispersion** — (F3 − F1) / 2，声道长度代理
- **SPR** — Singing Power Ratio = 10·log10(E[2-4kHz]/E[0-2kHz])
- **VibratoJitter** — vibrato 周期变异系数 (%)，sliding window

整曲级 (broadcast 到每 cell)：
- **MPT** — Maximum Phonation Time，最长连续浊音段 (s)
- **VoicingRatio** — 浊音 cycle 比率
- **DUV** — Degree of Unvoiced (%)

**实现位置**：
- 5 个新 calculator 类追加在 [src/metrics.py](src/metrics.py)
- `analyzer.calculate_all_metrics` 增加 5 个 stage（22 阶段总）
- `analyzer.output_vrp_csv` 加 32 列 + mean 聚合
- `plotter.METRIC_CFG / METRIC_CATEGORY` 自动并入注册表
- `gui._METRIC_SECTIONS` 三个分类（Acoustic/Singing/Density）扩了
- `excel_export._METRIC_COLS` 同步更新

**测试**：[tests/validate_params.py](tests/validate_params.py) 加 18 项范围
检查，全部 PASS。**总 52 项检查：48 PASS / 4 WARN / 0 FAIL**（4 WARN 是
原有的方法学差异，与 M1 无关）。

**待验证清单**（这些都是新加、还没和参考实现对齐的）：
- MFCC 1-13 与 librosa.feature.mfcc 的数值差异
- GNE-like 与原版 Michaelis 1997 的相关性（当前是简化代理）
- Spectral Skewness/Kurtosis 与 Praat 的 spectrum moment 定义对齐
- VibratoJitter 与歌手实际感受到的"颤音不稳"的相关性
- B1/B2/B3 LPC 根法 vs Praat Burg 根法的差异（应在 ±20% 内）

Commits: M1 系列（多个 commit 滚动到 push）

---

## 2026-04-22  Add-on voice-quality metrics + expanded validation

### 🟡 implemented, untested (待验证)

六个 clinically-cited 的声音质量指标加进声学分类，都通过 **代码冒烟 + 数值
范围合理** 但**没有逐一和 Praat/MDVP 数值对齐过**（部分 Praat 没有直接
对应实现，如 PPE 是 Parkinson 文献引用）。留在这里等真实数据评估。

- **ShimmerAPQ3** (%) — 3-point amplitude perturbation quotient
- **ShimmerAPQ5** (%) — 5-point APQ (complements existing APQ11)
- **NHR** — Noise-to-Harmonics Ratio = `1/10^(HNR/10)`. MDVP
  pathological threshold > 0.19. 实现为 HNR 的分析函数（per-cycle
  pointwise consistency 已在 validate 测试中确认 0.0% 误差）
- **CPPS** (dB) — Cepstral Peak Prominence Smoothed (Hillenbrand 1996).
  5-cycle 滑动均值；clinical 文献里比原始 CPP 更稳定
- **PPE** (0-1) — Pitch Period Entropy (Little 2009, Parkinson voice).
  Shannon 熵（40-cycle 窗，10-bin 直方图），归一化到 [0,1]
- **ZCR** — Zero-Crossing Rate per cycle, segment-length-normalised

位置：[src/metrics.py](src/metrics.py) 新增 4 个 calculator 类 + 扩展
PerturbationCalculator.KEYS。
Commit: `f34fa1f`

### ✅ tested (Praat 交叉验证脚本扩展)

`tests/validate_params.py` 从 10 个指标的手写对比，扩展为 34 项系统测试：

- **Praat cross-check**（12 项） — Jitter×3 + Shimmer×5 + HNR + F1/F2/F3
- **Range sanity**（18 项） — 每 metric 的 aggregated 值在文档区间
- **Structural sanity**（2 项） — maxCluster / maxCPhon 标签齐全
- **Internal consistency**（2 项） — NHR 与 HNR 的数学关系、CPPS 近似 CPP

每项自动分级 PASS / WARN / FAIL，汇总写到 `result/validation_report.json`
（CI 可读）。Exit code = FAIL 数量。

**当前结果**：30 PASS / 4 WARN / 0 FAIL
- WARN 全部是已记录的方法学差异（EGG-seg vs voice-autocorr 的 Jitter 3×、
  HNR 静音帧处理差异），或 K-means 空簇救援后的 maxCPhon 主导标签。

Commit: `f34fa1f` (validate script extension)

---

## 2026-04-22  第 N 轮综合整理

### ✅ tested

- **Metric 下拉按类别分组** — 声学 / EGG / 唱歌特异性 / 聚类 / 密度，空节自动隐藏 (`d21a263`)
- **键盘 ← →、◀ ▶ 按钮、鼠标滚轮** 都能切 metric (`97b7cfd`)
- **热图标题右上角类别标签** (Acoustic / EGG / Singing / Cluster / Density) (`97b7cfd`)
- **中文字体** 统一 Microsoft YaHei UI，菜单"幻影"修复 (enabled item + 显式颜色替代 disabled) (`e36b376`, `77d82f7`)
- **Settings 暗色化** — Spinbox / Checkbutton / Radiobutton 全部暗色主题 (`77d82f7`)
- **Clarity 阈值**数字 Spinbox 替换滑条 (`91db070`)
- **16 阶段进度条** "[X/16] <阶段名>"，集中管理在 `_STAGE_LABELS` (`77d82f7`, `91db070`)
- **聚类保证非空** — 三层防线（UI 不过滤 / 聚类救援 / 后过滤救援），k=5 永远 12 项 (`67bb985`)
- **P1：Jitter / Shimmer / HNR** 结果与 Praat 对齐（MDVP 1.3× 周期因子过滤后）(`ab54398`, `0908a2b`)
- **P2a：Vibrato rate / extent**，5-7 Hz 范围 (`6a92951`)
- **P2b：Formants F1/F2/F3 + Singer's Formant Energy**（f1_floor=250 Hz 后 F1 与 Praat 偏差 <10%）(`d85882b`, `0908a2b`)
- **P2c：H1-H2 / H1-H3** 频谱倾斜 (`be30870`)
- **P3：OQ / SPQ / CIQ** 基于 dEGG 事件 (`e9753c8`)
- **Praat 交叉验证脚本** `tests/validate_params.py` (`0908a2b`)

### 🟡 implemented, untested

下面几条 **代码完整、冒烟 OK**，但**没有真实的端到端用户验证**（没真正跑过完整工作流）：

- **多 wav 联合 centroid 训练**
  - GUI：画布工具条 "多 wav 联合训练…" 按钮 → 多选 .wav → 保存 CSV → 自动加载
  - CLI：`python main.py --train-centroids out.csv a.wav b.wav …`
  - 需要验证：真的跨 2+ 录音训练出的 centroid，在另一段录音上能给出一致的 cluster 标签
  - 位置：[gui.py](gui.py) `_train_centroids_from_many`, [analyzer.py](src/analyzer.py) `train_cluster_centroids`
  - Commits: `e5dff32`, `1c0472f`

- **对比 2 段录音 (A | B | A−B)**
  - GUI：左面板 "对比 2 段录音…" → CompareDialog，选两个 VRP CSV、切 metric、导出 PNG
  - CLI：`python main.py --compare a.csv b.csv --compare-metric CPP --compare-out out.png`
  - 需要验证：不同录音的 diff panel 是否合理，导出 PNG 是否质量够用
  - 位置：[gui.py](gui.py) `CompareDialog`, [plotter.py](src/plotter.py) `draw_vrp_comparison` / `save_vrp_comparison`
  - Commit: `ff58326`

- **Excel 导出**
  - GUI："导出 Excel" 按钮（分析完成后可用）
  - CLI：`python main.py audio.wav --excel`
  - 产出 .xlsx：Summary（每 metric 统计） + Grouped（全量 cell 表） + 每 metric 一个 heatmap pivot sheet
  - 需要验证：用 Excel 真的打开一个产物 .xlsx，确认 40+ sheets 可读、数值对齐、中文列名 OK
  - 位置：[src/excel_export.py](src/excel_export.py)
  - Commit: `b0b8165`

- **CLI 批处理**
  - `python main.py --batch corpus_dir/ [--plot-mode none] [--load-centroids cEGG.csv]`
  - 单文件跑过，但多文件目录真实批处理未测
  - 位置：[main.py](main.py)
  - Commit: `bbeb693`

- **Centroid load/save 在分析链里**
  - 保存按钮：分析完成后可用 ✅ tested
  - 加载按钮：点击可选文件、状态条可更新 ✅ tested
  - **未测**：加载完成后下一次拖拽分析 → cluster 标签是否真的按 loaded centroids 分配（而非从头训练）
  - 位置：[gui.py](gui.py) `_load_centroids`, `_save_centroids`
  - Commit: `9a38355`

- **"合并为一张总览" plot_mode=combined**
  - Settings 里的单选按钮可以切，但没真实勾选过然后跑完一次看产物
  - 位置：[plotter.py](src/plotter.py) `plot_vrp_combined`（已有，从 SC 时代继承）

### ⚠️ known issues / methodology notes

- **Jitter 约为 Praat 的 3×** — 不是 bug，是方法学差异：我们基于 EGG 检测周期，Praat 基于语音自相关。EGG 对真实声门脉冲更敏感，更多微周期被算入。文档已注明。
- **HNR 比 Praat 高 ~29%** — 我们排除纯静音帧，Praat 把 -200 dB 静音折入平均。帧级 HNR 差异 ±1 dB。
- **F2 / F3 偏差 20-25%** — LPC spectrum peak-picking vs Praat Burg + root-finding 的方法差。F1 在加了 `f1_floor=250 Hz` 后已 <10%。
- **cPhon 一簇经常为空** — sklearn KMeans 在 9 维 z-score 空间偶尔产空簇；已加三层救援（包括 post-filter 抢 1 个点填入），保证每簇至少 1 个 cell。
- **PNG 导出慢** — 22 个 metric 每个 savefig dpi=150 约 0.4s，全量导出 +8s。GUI 默认关闭，开启需要在 Settings 勾。
- **SC centroid CSV 格式可能不兼容** — 我们写的 CSV 有 `# VoiceMap cluster centroids k=… n_harm=… dim=…` 头（commit 之前是 `# FonaDyn cluster centroids …`，loader 同时兼容两种）+ `cluster;f0;f1;…` 行；SuperCollider 原版的 `cEGG.csv` 字段顺序和分隔符可能不同，导入 SC 到 Python 或反向时需核对。

### 📝 doc / refactor

- **README** 重写，完整 metric schema（40 列）+ 临床参考范围 + CLI 旗标 (`47161bc`)
- **Pipeline 阶段列表**集中到 `VoiceMapAnalyzer._STAGE_LABELS` 作为单一真源 (`77d82f7`)
- **Plotter METRIC_CATEGORY** 映射 — 热图右上角类别标签用 (`97b7cfd`)

---

## 更早的里程碑（倒序摘要）

- `ddd0e91` 绘图区 centroid 工具条 + Settings PNG 导出选项
- `9a38355` centroid load/save 接入 GUI + CLI（单录音版）
- `1d60e8d` 速度优化：DFT 复用 + KMeans n_init 10→3 + GUI 跳过 PNG（7s → 3s 暖机）
- `05be6f5` `feat(gui)`: 初版两栏 drag-drop 界面
- `9aa22b6` `feat(backend)`: analyzer/plotter/main 接入 GUI 的基础设施

---

## 该做但没做的检查清单（短期）

- [ ] 真的跑一轮多 wav 联合训练 → 保存 → 在 CLI 里用 `--load-centroids` → 对比 cluster 标签一致性
- [ ] 对比 2 段录音工作流：用不同说话人的 VRP，看 Δ panel 是否能定位关键差异区
- [ ] Excel 导出物：Excel / WPS 打开，检查 40+ sheets、pivot 格式、数值精度
- [ ] `--batch corpus/` 放 2-3 个 .wav，跑一次完整批处理
- [ ] 所有 GUI 字体，特别是 Menu 滚动切换时是否还有幻影（不同 Windows 版本）
- [ ] 自动 PNG 导出开启 + "合并为一张总览" 模式，看产物
