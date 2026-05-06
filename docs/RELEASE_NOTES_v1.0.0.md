# VoiceMap v1.0.0 · Release Notes

发布日期：待定（A0-5 截屏完成 + Inno Setup 构建验证后）

**软件名**：嗓音声学品质多维分析图谱（VoiceMap）
**作者**：蔡寰宸 (Huanchen Cai)
**许可**：MIT

---

## v1.0.0 — 软著首发版本

经过 A0-1 ~ A0-5 五个迭代波，VoiceMap 从一个单文件 `gui.py` 原型成长
为有完整双语 UI + 多文件管理 + 临床范围参考 + 现代视觉的桌面分析软件，
准备申请软件著作权（中国版权保护中心）。

### 核心能力

- **40+ 嗓音质量指标**计算（声学 + EGG + 唱歌特异性 + 聚类 + 密度）
- **VRP 热图**实时渲染 + 鼠标 hover 实时显示当前 cell 数值
- **多文件 Tracks Panel**（可同时拖入多个 wav，点击切换 active）
- **临床范围参考**（基于 MDVP / KayPENTAX / 文献阈值，4 档严重度色）
- **中英文双语**一键切换（菜单 帮助 → 语言）
- **多格式导出**（CSV 82 列 / Excel 多 sheet / .md 报告 / PNG/PDF/SVG/EMF 图片）
- **跨录音聚类一致**（联合训练 cEGG.csv，加载后跳过 K-means）

### 架构

```
voicemap/                10 个模块 + gui/ 子包 5 个模块
├── analyzer.py          主分析编排
├── metrics.py           20+ calculator
├── csv_writer.py        VRP CSV 写盘 + plot 分发
├── plotter.py           heatmap 渲染（11 种 cmap）
├── plot_overlay.py      拟合曲线 + 标注 + 多格式保存
├── excel_export.py      Excel 多 sheet
├── report.py            临床叙述 .md（_THRESHOLDS 查询表）
├── i18n.py              160+ 键 zh/en + 持久化
├── config.py            VoiceMapConfig dataclass
├── logger.py            setup / get
└── gui/
    ├── app.py           VoiceMapApp 主类
    ├── theme.py         颜色/字体/METRIC_SECTIONS 单一来源
    ├── modern_menu.py   ModernMenubar + ModernPopup（自画 popup，圆角，无 Win32 白边）
    ├── widgets.py       MetricPopup（旧）+ QueueHandler
    └── dialogs.py       Settings/Compare/Progress/About/LogWindow
```

详见 `docs/设计说明书.md`。

### 软件著作权适配

- 软件名按中国版权中心推荐格式：中文全称 "嗓音声学品质多维分析图谱"
- 桌面应用形态（tkinter，非 Web），单一可执行 .exe（PyInstaller one-folder
  + Inno Setup setup.exe）
- 全 UI 中文本地化 + 英文备份；专业术语保留括号英文（"聚类中心 (Centroid)"）
- 用户手册.md + 设计说明书.md 各 ~360 行（PDF 化后 10-30 页）
- 上游 KTH FonaDyn 算法在 LICENSE 与 README 显式致谢

### A0-1 ~ A0-5 关键交付（按 commit）

| 阶段 | 内容 | 关键 commit |
|------|------|-------------|
| A0-1 | 架构重排 + rename FonaDyn → VoiceMap | 10e921e |
| A0-2 | god 类拆分（gui.py 5 文件 + analyzer.csv_writer 拆分） | 56172ad |
| A0-3 | pyproject.toml + LICENSE + 调色板切到 option-C amber | 4f1188e |
| A0-4 wave 1 | i18n 框架 + 顶部菜单中英切换 | 8e3bd97 |
| A0-4 wave 2 | 对话框 / 状态 / 日志 / 拖放区 i18n 全覆盖 | 4c67f9d |
| A0-4 wave 3 | option-C layout（Tracks/Inspector/Status Bar）+ Inspector 内容接入 + 多文件 Tracks Panel + 字体 token + 鼠标 hover 探测 | 42bd9da → 3c5360b |
| A0-5 | 用户手册.md + 设计说明书.md + VoiceMap.spec + installer.iss | ef3002d → 4ee54f3 |

### 已知方法学差异（vs Praat）

`tests/validate_params.py` 当前基准：48 PASS / 4 WARN / 0 FAIL

- **Jitter / JitterRAP / JitterPPQ5 偏高 ~3-4×**：本软件用 EGG 周期切分，
  Praat 用 voice autocorr 切分，方法学差距是已知的。文献结果一致。
- **maxCPhon 偶尔缺标签 4**：sklearn KMeans 有时让某簇为空，三层救援
  保证最终标签都出现，但聚类标签的语义没绝对稳定。

### 性能

| 操作 | 耗时（60s 立体声 wav，i7-12700） |
|------|----------------------------------|
| 全 metric 分析（GUI / CLI）| ~12.5 s（5.6× 实时） |
| GUI 启动到可交互 | ~1.5 s（首次 numba 编译 +1-2 s） |

### 系统要求

- Windows 10 / 11（64 位）
- 内存 ≥ 4 GB（峰值 ~800 MB）
- 磁盘 ≥ 200 MB

### 安装

下载 `VoiceMap_v1.0.0_setup.exe` 双击安装，按提示选择安装目录。

或从源码运行：
```bash
git clone https://github.com/HuanchenCai/VoiceMapping
cd VoiceMapping
pip install -e .
voicemap --gui
```

### 联系

- GitHub: https://github.com/HuanchenCai/VoiceMapping
- Email: huanchen.se@gmail.com
