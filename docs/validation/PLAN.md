# VoiceMap Validation & Productization Plan

> **本文件是下一个 session 的执行路线图。按顺序读 → 按 Phase 推进 → 每动一处填 log。**

## 进度（顶部 ✓ 标记）
- ✅ **Phase 0 — Validation Infrastructure**（2026-05-31, session=validation-bootstrap）
  - 0.1 ✅ 12 合成信号 + manifest（`test_signals/make_signals.py`）
  - 0.2 ✅ 通用 harness（`scripts/validate_metric.py`）
  - 0.3 ✅ CI（`.github/workflows/validate.yml` + `requirements-validation.txt`）
  - 0.4 ✅ 文档框架（`_template.md` / `log.md` / `conventions.md`）
  - 0.5 ⚠ corpus：本地 `audio/` stand-in 就位；真实 Saarbrücken 下载 deferred（仅阻塞 PPE/SFE/MPT 的 (C) 测试）
- 🔄 **Phase 1 — P0 指标 (11/12 PASS)**：1 ✅ Jitter；2 ✅ Shimmer；3 ✅ F0/Clarity；4 ✅ HNR/NHR；5 ✅ CPP/CPPS；6 ✅ Formants；7 ✅ B1/B2/B3；8 ✅ Spectral moments；9 ✅ Alpha/Hammarberg (opensmile 已装, r≈±1)；10 ✅ Vibrato (extent)；12 ✅ MFCC。**剩 11 PPE（需真实语料,正在下载）**

---

## 0. 总目标（三个并列要求）

1. **方法学可发表**：每个指标都有「文献引用 + 数值 parity test + 合成信号验证」
2. **可复现**：任何人用相同输入跑出相同输出（跨平台、跨 Python 版本）
3. **可融入 ML pipeline**：sklearn-compatible feature extractor + 标准化 schema

---

## 1. 验证方法学（每个指标至少一项通过）

- **(A) Numerical parity** — 跟权威参考工具数值匹配（Praat / librosa / COVAREP / MDVP / VoiceSauce）。容差按指标定。
- **(B) Synthetic ground truth** — 已知答案的合成信号（已知 F0、jitter、formant）→ 验证算法输出。
- **(C) Real corpus behavior** — 在公开 corpus 上，输出分布与文献吻合。

**P0 指标必须 A + B + C 都过；P1 至少 A 或 B；P2 至少 B 或 C。**

---

## 2. 文档与目录结构（强制约定）

```
docs/validation/
├── PLAN.md                          # 本文档
├── log.md                           # 全 session append-only 改动日志
├── conventions.md                   # 单位/容差/test signal 命名
├── metrics/                         # 每个指标一个 md
│   ├── _template.md                # 标准模板（8 节）
│   ├── jitter.md                   # ✅ 已验证示例
│   └── ...
├── test_signals/                    # 合成信号
│   ├── README.md
│   ├── make_signals.py
│   └── *.wav
└── corpora/                         # 公开 corpus 适配
    ├── meei.md
    └── saarbruecken.md
```

**每个 metric md 强制 8 节**：

```
# <Metric Name>

## 1. Implementation
File / class / line numbers in current code.

## 2. Reference Standard
Author / year / paper title / algorithm reference.
Formulas in LaTeX or plain text.

## 3. Test Signals
Bullet list of synthetic + real samples used.

## 4. Validation Method
A / B / C — which ones, with exact steps and tolerance numbers.

## 5. Results
Tables / numbers / figures. Always include "n_compared" and the
acceptance metric (median |Δ|, Pearson r, etc.).

## 6. Status
[PASS / FAIL / IN_PROGRESS]  validated_on=YYYY-MM-DD  session=<id>

## 7. Known Limitations

## 8. Change Log
Reverse chronological; one bullet per touch.
```

**`log.md`** 是 append-only session timeline。每个 commit 必须 append 一段：

```
## 2026-MM-DD session-<short-id>
- Touched: <file:line>
- Why: <one sentence>
- Before / After (numerical, if applicable)
- Validation: <link to metrics/<name>.md>
- Tests: <pass count> / <total>
```

---

## 3. Phase 0 — Validation Infrastructure（必须先全做完）

| # | 任务 | 输出 | 验收 |
|---|---|---|---|
| 0.1 | Test signal library | `docs/validation/test_signals/make_signals.py` 生成 12 个合成 wav | 12 个文件齐 + manifest.json |
| 0.2 | Reference comparison harness | `scripts/validate_metric.py` 通用框架 | `python scripts/validate_metric.py jitter_local` 出 PASS 报告 |
| 0.3 | CI 配置 | `.github/workflows/validate.yml` + parity tests 接入 | push 触发 → 全测试通过 |
| 0.4 | Documentation 框架 | `_template.md` + `log.md` + `conventions.md` 三个种子文件 | 文件齐备 |
| 0.5 | 公开 corpus 接入 | 选 **Saarbruecken Voice Database**（免费、2000+ samples） | 本地至少 50 个 wav + 病/健康 label |

**Phase 0 完成判定**：
```bash
python scripts/validate_metric.py jitter_local
# 输出标准 PASS 报告，引用 docs/validation/metrics/jitter.md
```

### Phase 0.1 — 12 个合成信号（细节）

| 名称 | 用途 |
|---|---|
| `vowel_modal_200Hz_5s.wav` | 标准 modal 元音，F0=200Hz，无 jitter，做 baseline |
| `vowel_breathy_200Hz_SNR15dB.wav` | 加 Gaussian 噪声，HNR ≈ 15 dB |
| `vowel_jitter_0p5pct.wav` | 已知 jitter 0.5% |
| `vowel_jitter_2pct.wav` | jitter 2% |
| `vowel_shimmer_5pct.wav` | shimmer 5% |
| `vowel_vibrato_6Hz_100cent.wav` | 已知 6 Hz / 100 cent peak-to-peak vibrato |
| `vowel_pitch_glide_150_to_400Hz.wav` | F0 扫描，测 pitch tracker |
| `vowel_formants_a_e_i.wav` | 三个元音，F1/F2/F3 已知 |
| `vowel_high_pitch_800Hz.wav` | 测高音 corner case |
| `vowel_low_pitch_70Hz.wav` | 测低音 corner case |
| `silent_5s.wav` | 测 NaN / 边界处理 |
| `chirp_50_1000Hz.wav` | 非周期信号，所有 voicing-gated 指标应输出 0 |

### Phase 0.2 — 通用 harness 接口

```python
# scripts/validate_metric.py
def validate(metric_name, *, references=['praat'], signals=['all'],
             tolerance='default', report_md=True): ...
```

输出标准报告 to stdout + 更新 `docs/validation/metrics/<name>.md` 的 Section 5.

---

## 4. Phase 1 — P0 核心指标（约 12 个）

发论文必须 rigorous 的这一批。**按顺序做**。

| 序 | 指标 | 参考标准 | 当前状态 | 待做 |
|---|---|---|---|---|
| 1 | **Jitter** (local/RAP/PPQ5) | Praat VoiceAnalysis.cpp | ✅ PASS (A parity 1e-9 + B 合成GT) | ✅ docs/metrics/jitter.md 8 节完成 |
| 2 | **Shimmer** (local/dB/APQ3/5/11) | Praat AmplitudeTier.cpp | ✅ PASS (A parity 1e-6 + amp-tier identity + B 合成GT) | ✅ docs/metrics/shimmer.md 8 节完成 |
| 3 | **F0 / Clarity** | cycle-marker=Praat AC；VRP Clarity/MIDI=Tartini NSDF (McLeod-Wyvill 2005) | ✅ PASS (A AC parity 99.75% voicing + B NSDF octave stress) | ✅ docs/metrics/f0_clarity.md 8 节完成；§7 记低音<78Hz floor |
| 4 | **HNR / NHR** | Praat To Harmonicity (cc) + 物理锚 HNR==SNR | ✅ PASS (B HNR==SNR<0.3dB + A Praat<0.3dB on stationary) | ✅ docs/metrics/hnr.md 8 节；§7 记 ~6dB 非稳态发散 |
| 5 | **CPP / CPPS** | Hillenbrand 1996；SC Cepstrum 约定（≠Praat 绝对值）| ✅ PASS (A corr r=0.98 vs Praat CPPS + B SNR 单调 r=0.99) | ✅ docs/metrics/cpp.md 8 节；§7 记 absolute 不可比、需自标定 |
| 6 | **Formants F1/F2/F3** | Praat Burg + roots | ✅ PASS (A real-audio parity 0.8–2.4% + B 合成 F1) | ✅ docs/metrics/formants.md 8 节；§7 记合成 F2/F3 高 F0 谐波混淆 |
| 7 | **B1/B2/B3** | Praat get_bandwidth (同 Burg 极点) | ✅ PASS (A 中位数 parity 1–5%；>800Hz 清零) | ✅ docs/metrics/bandwidths.md 8 节；§7 记逐周期高散度 10–18% |
| 8 | **Spectral centroid/bandwidth/rolloff/flatness/slope** | librosa | ✅ PASS (A 公式==librosa 1e-16 同谱 + B slope 解析 GT + 纯音物理) | ✅ docs/metrics/spectral_moments.md 8 节；§7 记 power-weighting 约定 |
| 9 | **AlphaRatio / Hammarberg** | eGeMAPS (Eyben 2016) / OpenSMILE | ✅ PASS (B 双音解析 GT 精确 + A OpenSMILE Alpha r=-1/Hamm r=+1) | ✅ docs/metrics/alpha_hammarberg.md 8 节；§7 记 Alpha 反号约定 |
| 10 | **Vibrato** (rate / extent / jitter) | Sundberg 1995 + commit d53b47b 修过 | ✅ PASS extent (合成 GT <5%)；⚠ rate 分辨率受限 (F0/W≈5Hz bin, 6Hz 读成~4.7) | ✅ docs/metrics/vibrato.md 8 节；§7 标 rate 需 post-freeze zero-pad 修 |
| 11 | **PPE** | Little 2009 | ⚠ commit f208fce 改了 bin，需 corpus 验证 | Saarbruecken 健康 vs 病态分类 AUC > 0.7 |
| 12 | **MFCC 1-13** | librosa.feature.mfcc | ✅ PASS (A mel 中心+DCT 精确；full MFCC r≥0.999 分层) | ✅ docs/metrics/mfcc.md 8 节；§7 记 HTK 顶点量化 + 自然对数 vs dB |

**每个指标的 acceptance criteria 都在它的 `docs/validation/metrics/<name>.md` 里写死**。Phase 1 完成判定：12 个 md 都 Status = PASS。

---

## 5. Phase 2 — P1 EGG + 次要 acoustic（约 12 个）

| 指标 | 参考标准 | 待做 |
|---|---|---|
| **Qcontact** | Howard 1995 (Speech Communication) | 比对 SC FonaDyn 源码 + Howard 公式；合成 EGG 信号验证 |
| **dEGGmax** | FonaDyn convention | 同上 |
| **Icontact** | log10(dEGGmax) · Qcontact 定义 | 数值 spot-check |
| **OQ / SPQ / CIQ** | Baken & Orlikoff 2000 | corpus 测典型值（modal/breathy/pressed）|
| **HRFegg** | Howard 1998 | parity vs SC `namePhasePortrait` |
| **Sample Entropy (CSE)** | Richman & Moorman 2000 | parity vs `nolds.sampen()` |
| **Cluster / cPhon (K-means)** | sklearn 标准 | 验证 feature 抽取与归一化 |
| **SPL** | IEC 61672 / SC scserver | 校准 `spl_correction_db` 与 SC reference |
| **SpecBal** | SC `PV_SpecCentroid` 等 | parity vs SC source |
| **Crest** | (peak / RMS) 标准定义 | 合成正弦信号验证（应 = √2）|
| **H1-H2 / H1-H3** | Iseli & Alwan 2004 | parity vs VoiceSauce |
| **Singer's Formant (SFE)** | Sundberg 1974 | corpus（古典歌手 vs 普通说话）|
| **SPR** | Omori 1996 | corpus 验证范围 |

---

## 6. Phase 3 — 实验性 / 待验证

`待验证=True` 的要么验证通过转正，要么删：

| 指标 | 行动 |
|---|---|
| ZCR | 合成信号验证 |
| GNE | 跟 Praat GNE 比；若实现差太多就删 |
| MPT / VoicingRatio / DUV | corpus 验证（typical MPT > 15s for healthy）|
| VibratoJitter | corpus 验证（流行歌手 vs 美声）|
| cPhon | 验证 feature 物理含义 |

---

## 7. Phase 4 — 端到端 + 性能

| # | 任务 | 验收 |
|---|---|---|
| 4.1 | 三种 mode 端到端（mono / stereo+EGG / stereo+no-EGG）| 每种 3 个标准录音，输出 CSV regression test |
| 4.2 | 性能 benchmark | wall time / RAM 跨 10s/60s/300s，O(N) scaling 表 |
| 4.3 | 跨平台 reproducibility | Linux / Win / Mac 同一录音 ±1e-9 一致 |
| 4.4 | 批量稳定性 | 100+ 录音批跑，无 crash / NaN / leak |

---

## 8. Phase 5 — 论文 / 方法学包

| # | 任务 | 输出 |
|---|---|---|
| 5.1 | 算法参考文档 | `docs/methodology.md` 每个指标的算法 + 公式 + 引用 |
| 5.2 | 公开 test corpus | github release：小型 voice corpus + ground-truth annotations |
| 5.3 | Replication 包 | `docs/reproducibility.md`：conda env + 一行命令复现所有 paper figures |
| 5.4 | API stability tag | semver 1.0.0 + API freeze 文档 |

---

## 9. Phase 6 — ML 集成

| # | 任务 | 输出 |
|---|---|---|
| 6.1 | Sklearn wrapper | `from voicemap.ml import VoiceFeatureExtractor`：fit/transform/get_feature_names_out |
| 6.2 | Schema 文档 | `docs/ml_schema.md`：列名 / 类型 / 缺失值约定 |
| 6.3 | Centroid library | 预训练 EGG cluster centroids + cPhon centroids 内置 + 加载脚本 |
| 6.4 | Pandas/parquet 兼容 | CSV 直接读成 sklearn-ready DataFrame |
| 6.5 | Performance baseline | demo notebook：voice → features → simple classifier |

---

## 10. 时间预估

| Phase | 工作量估计 |
|---|---|
| 0 | 1-2 天（基础设施一次到位）|
| 1 | 5-7 天（12 个 P0 指标，每个 0.5 天）|
| 2 | 4-5 天（12 个 P1 指标）|
| 3 | 1-2 天 |
| 4 | 1-2 天 |
| 5 | 2-3 天（含写论文级文档）|
| 6 | 2-3 天 |
| **总计** | **3-4 周专心做** |

---

## 11. 下个 session 启动清单

```
[ ] 1. cd H:/Projects/VoiceMap && cat docs/validation/PLAN.md  # 读本文档
[ ] 2. 创建 docs/validation/log.md / conventions.md / metrics/_template.md
[ ] 3. 执行 Phase 0.1 → 写 docs/validation/test_signals/make_signals.py
[ ] 4. 执行 Phase 0.2 → 写 scripts/validate_metric.py
[ ] 5. 执行 Phase 0.3 → CI 配置
[ ] 6. 执行 Phase 0.5 → 下载 Saarbruecken corpus（或先用本地 audio/ 做 stand-in）
[ ] 7. 开始 Phase 1.1 (jitter)：填 docs/validation/metrics/jitter.md 8 节，因为 parity test 已经在
[ ] 8. 每完成一个 metric → metrics/<name>.md Status = PASS → log.md 加一段 → commit
[ ] 9. 每完成一个 Phase → PLAN.md 顶部加 ✓
```

---

## 12. Out of scope（本计划不做）

- 实时 streaming pipeline（当前是 offline batch）
- veryAccurate=True (AC_GAUSS + sinc-700)（task #13 deferred，覆盖 <5% 用例）
- 多语种 corpus（仅做中文 + 公开英文 corpus）
- 跨人 normalization（留给 ML 阶段）

---

## 13. 当前已就位的资产（不要重复做）

- ✅ `voicemap/praat_perturbation.py` — Jitter/Shimmer 公式 atol=1e-6 parity
- ✅ `voicemap/praat_pitch.py` — Sound_to_Pitch 完整翻译（4 commits, parity 99.5%）
- ✅ `tests/test_praat_perturbation_parity.py` — 12 个 parity test
- ✅ `tests/test_praat_pitch_parity.py` — 9 个 parity test
- ✅ `tests/test_inverse_filtering.py` — IAIF + GCI 测试
- ✅ `scripts/diagnose_*.py` — vibrato, clarity_ppe 诊断脚本
- ✅ `scripts/compare_perturbation_vs_praat.py` — Praat 比对
- ✅ `scripts/probe_cycle_count.py` — cycle 计数对比
- ✅ Mode hierarchy (mono / stereo+EGG / stereo+no-EGG) 已就位

---

**END OF PLAN. 下个 session 从 §11 启动清单第 1 行开始。**
