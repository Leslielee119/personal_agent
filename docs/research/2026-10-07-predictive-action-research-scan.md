# Milestone C 相关工作调研：个人下一动作预测

日期：2026-10-07

目标：确认 Personal Predictive AI 的下一动作预测阶段应如何设计，避免重复已有工作、避免因标签塌缩或数据泄漏得到虚高结果，并明确哪些思想可借鉴、哪些问题仍属于我们自己的工程/研究问题。

## 1. 结论先行

Milestone C 不应直接训练 GRU/Transformer，也不应把普通 accuracy 当作主结论。

更合适的路线是：

```text
C0 Validity Audit
  -> C1 Strong Non-neural Baselines
  -> C2 Structured Retrieval
  -> C3 B2 Memory Ablation
  -> only then learned sequence model
```

核心原因：我们当前真实资格数据中 182/182 个 B1 action 都是 `chrome.exe / key_input`。这种数据上任何 majority predictor 都能得到接近完美的 accuracy，但不存在有意义的“下一动作理解”。

## 2. Predictive Process Monitoring：最重要的警告

Pfeiffer et al., 2025, *Learning from the Data to Predict the Process: Generalization Capabilities of Next Activity Prediction Algorithms*, Business & Information Systems Engineering。

DOI 页面：
https://link.springer.com/article/10.1007/s12599-025-00936-4

与本项目最相关的结论：

1. Next-activity prediction 本质上可写成 trace-prefix -> next activity 的多分类问题。
2. 常见 event log 的 train/test 中会出现大量重复 prefix，论文在多个真实日志中报告 prefix example leakage 接近或超过 80%，部分接近 100%。
3. 普通 top-1 accuracy 还受到“同一 prefix 本来就可能有多个合法后继”的 accuracy limit / Bayes error 影响。
4. 论文使用 trigram + Kneser-Ney smoothing 作为 naive baseline；在不少日志上，这个简单 baseline 与更复杂的 MPPN 神经模型非常接近。
5. 因此，复杂模型优于弱 baseline 并不能自动证明有效预测能力；必须显式检查 leakage、可预测性和 generalization。

对我们的直接影响：

- C0 必须计算 prefix leakage，而不是只做 random train/test。
- 数据切分必须 chronological / session-forward。
- C1 的序列 baseline 至少应包含 trigram + backoff/smoothing，而不是只放一个弱的一阶 Markov。
- 需要报告 majority/global-frequency baseline 与近似 accuracy ceiling / conditional ambiguity。

## 3. UI-Vision：桌面行为不能压成单一 accuracy

Nayak et al., ICML 2025, *UI-Vision: A Desktop-centric GUI Benchmark for Visual Perception and Interaction*。

论文：
https://proceedings.mlr.press/v267/nayak25a.html

代码：
https://github.com/uivision/UI-Vision

UI-Vision 覆盖 83 个桌面软件，包含真实 human demonstrations，并把 GUI Action Prediction 明确拆成不同动作类型评估：click/move、drag、typing、hotkey 等分别使用距离、Recall@d、typing/hotkey correctness、SSR 等指标。

对我们的直接影响：

- “Action”不是一个天然同质标签。
- Milestone C V1 应先预测较稳定的层级：`Application`、`Operation`、`Application x Operation`。
- `concrete/fine`、鼠标坐标、具体文本等以后应使用动作类型专属指标，而不是硬塞进 joint-class accuracy。
- 当前 coarse B1 `key_input` 塌缩应被 benchmark 诊断出来，而不是通过人为细分标签提前掩盖。

## 4. Session-Based Recommendation：把预测看成排序而非仅分类

Session-based recommendation 的任务与我们的局部问题有高度结构相似性：给定当前 session 的行为 prefix，预测下一 item/action。

相关经验研究与近期模型通常使用：

- HitRate / Recall@K；
- MRR@K；
- NDCG@K；
- sliding / chronological evaluation。

代表性参考：

- Ludewig et al., *Empirical analysis of session-based recommendation algorithms*：
  https://link.springer.com/article/10.1007/s11257-020-09277-1
- 2024-2025 多篇 SBR 工作仍使用 Recall@K / MRR@K / NDCG@K。

对我们的直接影响：

- Policy 最终本来就需要输出 action distribution / candidate ranking，因此 C 不应只保存 argmax。
- V1 固定报告 Top-1、HitRate@3、MRR、NLL；如 label 数量允许，再报告 NDCG@3。
- ranking metrics 对未来“给用户三个候选动作”比单一 accuracy 更自然。

## 5. Retrieval-Augmented Next Activity Prediction：值得做，但不要先上 LLM

Casciani et al., Information Systems 2026, *Enhancing next activity prediction in process mining with Retrieval-Augmented Generation*。

文章页面：
https://www.sciencedirect.com/science/article/pii/S0306437925001280

论文说明 retrieval + sequence/context 可以对 next-activity prediction 有竞争力，同时也明确报告了 interleaving sensitivity 和 concept drift 等限制。

对我们的直接影响：

- Structured Retrieval 是合理强 baseline，而不是“为了我们项目临时发明”的实验。
- 但没有必要一开始引入 LLM；我们可以先用可解释的 structured similarity，隔离 retrieval 本身的贡献。
- concept drift 必须作为后续纵向评估的一部分；Personal AI 的用户习惯天然非平稳。

## 6. Personalized sequential recommendation：长期用户特征是有价值的，但必须单独消融

2025 年 Personalized Dual Transformer Network 等 sequential recommendation 工作强调：当前 session context 与长期 personalized characteristics 是不同信息源。

参考：
https://www.sciencedirect.com/science/article/pii/S0925231224020150

对我们的对应关系：

```text
short-term context   <-> B1 recent states/actions
long-term profile    <-> B2 active FACT/HABIT Memory
```

因此 C2/C3 应明确做：

```text
Retrieval without B2
vs
Retrieval + B2 active Memory
```

不能把长期 Memory 和短期 context 一起加入后只报告最终模型结果，否则无法回答 B2 是否真的有预测价值。

## 7. 当前项目与已有工作的区别

我们不把“next activity prediction”本身当创新点。这个任务在 process mining、recommendation、GUI agent 里都已有大量研究。

我们的独特问题组合在于：

1. 单用户、跨应用、连续桌面行为，而不是固定业务流程或单站点 clickstream；
2. 输入来自本地 event-sourced computer state，而不是预定义 item/event log；
3. actor/provenance 是一等语义，AI 自己执行的动作不能被重新学习成用户偏好；
4. Memory 有 temporal validity、supersession、dependency/invalidation，而不是简单 user embedding；
5. 预测数据本身随着 Agent 介入会发生 policy-induced distribution shift；
6. 完全本地、长期持续学习，同时要求可审计和隐私边界。

因此 C 的研究价值不在“再做一个 next-action model”，而在建立一个可信的 personal predictive evaluation protocol，并验证：

```text
short context 是否真的可预测未来行为？
structured state 是否比 action-only sequence 有增益？
long-term provenance-aware Memory 是否有独立增益？
这些增益在时间推进 / 行为漂移后是否仍成立？
```

## 8. 对 Milestone C 的最终建议

采用：

```text
C0 Validity Audit
  - target diversity
  - dominant-class ratio
  - entropy
  - independent sessions
  - prefix leakage
  - unseen-prefix rate
  - conditional ambiguity / empirical accuracy ceiling

C1 Strong baselines
  - global frequency
  - contextual frequency
  - unigram/bigram
  - trigram + deterministic backoff/smoothing

C2 Structured retrieval
  - pre-action state + recent action sequence
  - no embedding / no LLM in V1

C3 Memory ablation
  - Retrieval
  - Retrieval + B2 gated ACTIVE Memory
```

只有当 C0 数据资格通过，而且 C1/C2 显示稳定的 out-of-time 增益时，才进入 learned GRU/SSM。

## 9. 明确不做的重复实验

Milestone C V1 不把以下内容作为主要研究贡献：

- “Transformer 比 Markov 强不强”——已有大量 next-activity / recommendation 工作；
- “RAG 能不能预测 next activity”——2026 已有直接工作；
- “LSTM 能不能处理 event sequence”——是成熟基线；
- “GUI agent 能不能预测 click/type”——UI-Vision 等已有专门 benchmark。

这些方法以后可以作为外部 baseline 或升级模型，而不是当前最先投入资源的实验。
