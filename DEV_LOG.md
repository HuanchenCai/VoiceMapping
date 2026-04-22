# 开发日志 Development Log

Purpose: 记录每一轮做了什么、测过没，未测试的功能单独标出来方便回头补验证。
新改动请**按时间倒序**追加到顶部。每条标注状态：

- ✅ **tested** — 用户在 GUI / CLI 里真实走过一遍，确认符合预期
- 🟡 **implemented, untested** — 代码写完、单元冒烟通过，但没有端到端人工验证
- ⚠️ **known issue** — 已知问题 / 方法学差异 / 需要下轮改
- 📝 **doc** — 仅文档 / 重构，无功能变化

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
- **SC centroid CSV 格式可能不兼容** — 我们写的 CSV 有 `# FonaDyn cluster centroids k=… n_harm=… dim=…` 头 + `cluster;f0;f1;…` 行；SuperCollider 原版的 `cEGG.csv` 字段顺序和分隔符可能不同，导入 SC 到 Python 或反向时需核对。

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
