# Roadmap

按优先级 / 依赖关系组织。完成一个在 `DEV_LOG.md` 标 ✅ 并打勾这里对应条目。

## Milestone 1 — 回填未测试功能验证（本轮迭代的 P0）

目标：`DEV_LOG.md` 里 🟡 untested 一栏**清零**。每条都是 code 已有、只需人工跑一遍。

- [ ] 多 wav 联合 centroid 训练端到端：2 段不同录音 → 联合训练 → 用产物 CSV 去跑第三段录音，肉眼核对 `maxCluster` / `maxCPhon` 的分布是否一致
- [ ] `CompareDialog` 工作流：拿 2 个不同性别 / 不同唱法的 VRP CSV，逐 metric 看 Δ 合理性
- [ ] 真的导出一个 `.xlsx` → Excel/WPS 打开 → 40+ sheets 正常渲染，中文列名无乱码
- [ ] 批处理：放 `audio/{a,b,c}.wav` 目录 → `python main.py --batch audio/` → 3 个 CSV + 汇总日志
- [ ] `--plot-mode combined` 单独走一次，检查单张总览图的布局、分辨率
- [ ] Centroid 加载后**不训练只分类**的路径：明确从日志看到 "Classified against N preloaded centroids" 而不是"fitting K-means"

## Milestone 2 — 方法学提升 / 数据质量

减少前面列的 ⚠️ 方法差异，让输出更接近教科书 / Praat 标准。

- [ ] **Formant 方法切换** — 加一个 Settings 开关：LPC spectrum peak-picking (当前) vs LPC root-finding (Praat 方式)。对 F2/F3 偏差大的情形让研究者自己选
- [ ] **OQ 阈值法**作为 derivative 法的对照 — 现在只有 dEGG 峰值法，加一个 3/7 或 25% 阈值法并列输出 `OQ_threshold` 列
- [ ] **cPhon 特征权重** — 现在 9 个 quality 指标等权 z-score，可选让用户勾选哪些维度参与 / 给某些维度加权
- [ ] **空簇救援**目前是"抢最差点"，换成"用 K-means++ 的距离采样"挑一个点重新初始化该簇，可能更合理
- [ ] **Vibrato 规则性 / 抖动** — 除了 rate / extent，加 vibrato jitter（相邻周期 rate 变化量）
- [ ] **Singer's formant band**可配 — 不同学派用 2.5-3.5 kHz vs 2.8-3.4 kHz，在 Settings 里放

## Milestone 3 — 研究工作流增强

让论文写作、数据整理更顺滑。

- [ ] **Cluster 命名持久化** — 分析完成后让用户给 maxCluster=1 标注一个 label（"breathy" / "pressed" / "modal" …），存到 centroid CSV 的 header 里一起走
- [ ] **多录音统计视图** — 在 CompareDialog 之外，加"批量导入 N 个 CSV → 每 metric 的箱线图 / 散点"
- [ ] **人口分层 VRP** — 按标签（年龄组、性别、行当）叠加多个 VRP，算平均 VRP 和标准差 VRP
- [ ] **临床报告自动导出** — 一键从最新分析产出一页 PDF：VRP 缩略图 + 核心指标值 + 参考范围标红
- [ ] **Segment / 片段选择** — 拖入一段长录音后，先在波形上框选有效片段再分析（裁掉前后静音、咳嗽）
- [ ] **实时分析** — 唱歌时实时看 VRP 长出来（麦克风 + EGG 流式读取，每 1s 更新一次图）
- [ ] **SC centroid 互通** — 写一个 SC `cEGG.csv` ↔ 我们格式的转换脚本，跨工具复用聚类中心

## Milestone 4 — 工程化 / 部署

让别人能方便地用这个工具。

- [ ] **PyInstaller 单文件打包**（`FonaDyn.py` 前身已有，但被 revert，需要重建以适配新依赖：scikit-learn / numba / openpyxl / tkinterdnd2）
- [ ] **Windows 安装器** — Inno Setup 脚本
- [ ] **macOS / Linux 验证** — 主要验证 tkinterdnd2、numba、字体回退
- [ ] **配置持久化** — 用户改的 Clarity 阈值 / k / n_harm / PNG 导出选项，存到 `~/.config/fonadyn/gui.json`，下次启动自动恢复
- [ ] **最近文件** — drop zone 旁加 "最近分析过的 wav"，点击即再次分析
- [ ] **CI** — GitHub Actions 跑 `tests/validate_params.py` + 基础 import 冒烟

## Milestone 5 — 数据科学方向

长期，可能需要外部协作者。

- [ ] **Cluster 个数自动选择** — 跑 k=2..10 的 silhouette / BIC 曲线，推荐最优 k
- [ ] **跨受试者标准化** — 每个录音的 VRP 做 per-subject z-score 后再比较（消除绝对响度 / 录音设备差异）
- [ ] **深度学习 phonation classifier** — 用已有的 cPhon 标签训一个 1D-CNN，替代 K-means，得到更稳定的跨录音标签
- [ ] **Web demo** — PyScript / streamlit 版本，上传 WAV 即可在浏览器看 voice map
- [ ] **大规模数据集 benchmark** — 和公开数据集（Saarbruecken Voice Database、AVSpoof）对比数值范围

## 不做（明确拒绝）

- ❌ **修改 FonaDyn 特有的 Qcontact / Icontact / HRFegg / Entropy 公式** — 这些保持和 SuperCollider 原版完全一致，是这套工具的身份标识。需要"Praat 版本"的用户应该直接用 Praat
- ❌ **替换 tkinter 为 PyQt / Tauri** — 当前 GUI 够用，切换引擎不带来可写论文的价值
- ❌ **EGG 周期检测改成语音自相关** — 那就变成 Praat 了，也失去了 EGG 的独特性
