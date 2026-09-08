# 校准文献（已核实，2026-08-31 定稿）

## 最终榜单

**顶级 3（报告主引）**
1. Masi et al. 2011, PSPR —— 干预效应量总标尺（四分类 d 值）
2. Wei et al. 2022, BMC Geriatrics —— 独居 vs 非独居孤独率 + 三年新发率（CLHLS）
3. Lu et al. 2024, Innovation in Aging —— 时间银行唯一准实验主报告

**非常适合 2（补充主引）**
4. Yang & Gu 2021, Soc Sci Med —— 丧偶→孤独动态（OR 2.34 / 3.09 / 0.47）
5. Hoang et al. 2022, JAMA Network Open —— 按干预亚型拆分的 RCT 荟萃
   （技术类单列 → platform 参数依据）
   DOI: 10.1001/jamanetworkopen.2022.36676 | PMID: 36251294
   ✅ 全文已核实（2026-09-02，literature/hoang2022_jama_netw_open.pdf）：
   技术 SMD -0.19 (-0.51, 0.14)；CBT -0.52 (-1.21, 0.17)；多组件 -0.67 (-1.13, -0.21)
   注意：技术类 CI 跨 0 —— platform 干预效应应设为最弱，与我们冒烟结果
   （platform 效果最差）方向一致，可写成"模拟再现了荟萃证据的排序"
   ⚠️ 全文核对新发现：**CBT 的 CI 也跨 0**，仅多组件在社区场景显著——
   casework 参数（0.4–0.6）应主引 Masi 社会认知类 -0.598，Hoang 只作方向佐证

**C 的补充引用（不占席）**
- Lu, Chui & Lum 2025, The Gerontologist, gnaf200：项目内时数 T1 β=0.56 /
  T2 β=0.36，项目外 β=1.02(p=.078) 无挤出【Grok 与 GPT 独立给出相同 β，
  交叉一致，仍待全文抽查】
- Lu et al. 2025, Applied Research in Quality of Life, 20:2141–2160,
  10.1007/s11482-025-10503-4（链式中介 → 生活质量）【存在性已核实】

核实方式：题录经搜索引擎与官方数据库交叉验证；标注【待全文核对】的数字需下载 PDF 后抽查。
检索由外部学术 agent（Grok / Gemini）完成，本文件只收录通过核实的条目。

教训存档：Gemini 返回的 2 条独有题录中，1 条完全编造（"Loneliness Dynamics…"
J Aging & Health 一文不存在），1 条真实论文配编造数字（Hayashi 2012 并无
48.5%/51% 延续率，题目与 DOI 也给错）。共同特征：**给出的数字与我们的校准
靶标"完美吻合"**（15%、27pp、50% 全部精准命中）——这是迎合式幻觉的标志，
凡此类结果必须原文核对后才能采信。

## A. 干预效果量 → 三种干预强度参数

Masi, C. M., Chen, H.-Y., Hawkley, L. C., & Cacioppo, J. T. (2011).
A meta-analysis of interventions to reduce loneliness.
*Personality and Social Psychology Review*, 15(3), 219–266.
DOI: 10.1177/1088868310377394 | PMID: 20716644 | 开放全文: PMC3865701

- RCT 总体效应 d = -0.198；社会认知类干预 -0.598；增强社会支持类 ≈ -0.162；
  单组前后测上限 -0.367（负号 = 孤独感下降）【-0.598 与总体结论已多源核实】
- 用法：casework（含认知重构成分）目标效应取 0.4–0.6；
  timebank / platform（支持/接触类）取 0.15–0.25
- 候补（需要更贴老年样本时再核实）：Hoang et al. 2022, JAMA Network Open,
  10.1001/jamanetworkopen.2022.36676
- 候补 2【题录已核实，效应量待全文核对】：Sun, Y., et al. (2025).
  Interventions to Reduce Loneliness among Community-dwelling Older Adults:
  A Network Meta-analysis and Systematic Review. *JAMDA*, 26(3), 105441.
  DOI: 10.1016/j.jamda.2024.105441 | PMID: 39799979
  （港中文团队网络 meta；Claude-agent 称总体 SMD -0.95，摘要未证实，
  且与 Grok 引的另一篇 JAMDA 2024 "Geriatric Giant" d=-0.47 差距大，
  两篇是不同论文，引用前必须下载原文分辨）

## B. 中国老人丧偶–孤独实证 → 校准靶标三角验证

Yang, F., & Gu, D. (2021). Widowhood, widowhood duration, and loneliness
among older adults in China. *Social Science & Medicine*, 283, 114179.
DOI: 10.1016/j.socscimed.2021.114179 | PMID: 34225038
（注意：文章号是 114179，Grok 给的 114187 有误；作者含 Gu, Danan，Grok 漏了）

- CLHLS 2002–2014 五轮；丧偶 vs 在婚孤独 OR = 2.34；丧偶头几年 OR = 3.09；
  丧偶 40 年后仍 OR = 1.96；丧偶后再婚 OR = 0.47【摘要级已核实】
- 患病率（加权"有时孤独"19.3%、"常常/总是"6.3%）出自 Grok 转述【待全文核对】
- 用法：与我们 Harmonized CHARLS 丧偶冲击（+27pp 风险差）方向互证。
  写报告注意：**OR ≠ 百分点差，不可互换**；我们 CLHLS 2021 独居样本 ≈15% vs
  该文全体老人 6–9% 的差异要写明"独居子样本 vs 全体 + 年份不同"
- 候补：Luo & Waite 2014, J Gerontol B, 10.1093/geronb/gbu007；
  Lin et al. 2024, J Gerontol B, gbae187

### B-2（并列采用）：独居 vs 非独居直接对比

Wei, K., Liu, Y., Yang, J., Gu, N., Cao, X., Zhao, X., Jiang, L., & Li, C.
(2022). Living arrangement modifies the associations of loneliness with
adverse health outcomes in older adults: evidence from the CLHLS.
*BMC Geriatrics*, 22, 59.
DOI: 10.1186/s12877-021-02742-5 | PMID: 35038986 | 开放全文: PMC8764854

- 【摘要级已核实】CLHLS 2008/09 波，n=13,738（65+ 社区居住）；
  独居"感到孤独"（总是/常常/有时）52% vs 非独居 29.5%，
  OR = 1.90 (95%CI 1.67–2.16)
- 用法：与我们 CLHLS 2021 独居"有时及以上"40.3% 同口径互证
  （差异来源：波次 2008/09 vs 2021 + 高龄样本构成）；
  独居/非独居差值也支持模型的"独居暴露"设定
- 该文另证明"同住但孤独"人群健康结局更差——报告讨论部分可引，
  说明独居不是唯一风险路径
- ✅ Table 2 已核实（2026-09-02，literature/wei2022_bmc_geriatrics.pdf）：三年新发孤独率
  独居 217 (34.0%) vs 非独居 1052 (22.3%)，差 11.7pp——
  与我们 Harmonized CHARLS 的 27.2% vs 15.8%（差 11.4pp）几乎完全互证
  ⚠️ 全文核对新发现：该差异**调整协变量后不显著**（未调整 OR 1.73 [1.46–2.05]，
  模型2 OR 1.27 [1.00–1.62] p=.051，全调整 OR 1.09 [0.84–1.43] p=.518）——
  稿中只能作**描述性发生率**互证，不可写成"独居显著增加新发孤独"
- 口径警告：该文"孤独"含"有时"，不能与我们"经常+总是"≈15% 并列使用

## C. 时间银行准实验 → post_persist 参数依据

Lu, S., Chui, C., Lum, T., Liu, T., Wong, G., & Chan, W. (2024).
Promoting late-life volunteering with timebanking: A quasi-experimental
mixed-methods study in Hong Kong. *Innovation in Aging*, 8(7), igae056.
DOI: 10.1093/geroni/igae056 | 开放全文: PMC11275466

- 设计与样本已核实：香港 2021–2022，时间银行组 n=116 vs 对照 n=114，
  测量点 T0 / T1(6个月) / T2(12个月)
- ✅ β 值已核实（2026-09-02，literature/lu2024_innovation_aging.pdf）：
  T2 周志愿时数 1.37 (0.2, 2.54) p=.021；意向 T1 0.54 / T2 0.51；
  积分留自用者 T2 2.09 (0.43, 3.76) p=.014——Grok 转述全部准确
- ⚠ 关键口径修正：干预期约 1 年，**T2 ≈ 项目终点而非撤出后随访**——
  该文只能支持"效应维持到项目结束不衰减"，不能直接支持撤出后延续概率
- 用法：post_persist=0.5 表述为"敏感性扫描中点（区间 0.3–0.7）"；
  报告措辞："准实验显示时间银行效应在 12 个月观察期内保持，
  撤出后关系延续概率无直接点估计，故做参数扫描"
- 同团队后续（已核实存在）：Lu, Chui & Lum 2025, *The Gerontologist*,
  gnaf200 —— 时间银行无挤出效应，可作补充引用

## 已否决条目（勿引用）

1. "Yang, F., & Gu, D. (2021). Loneliness Dynamics Among Older Adults in
   China. *Journal of Aging and Health*" —— **不存在**，Gemini 拼接编造
   （作者组合真实、期刊真实、题目与数字均为编造）
2. Hayashi (2012) 的"48.5–53.2% 转化为非正式关系 / 51% 一年后维持" ——
   论文本身真实，正确题录为：Hayashi, M. (2012). Japan's Fureai Kippu
   Time-banking in Elderly Care: Origins, Development, Challenges and
   Impact. *IJCCR*, 16(A), 30–44. DOI: 10.15133/j.ijccr.2012.003
   （Gemini 给的题目变体与 .004 均错）。该文是历史制度分析，上述数字
   无出处。可作时间银行定性背景引用，**禁止引用上述数字**。

---

# 第二轮检索（D / E，2026-08-31 定稿）

检索由 Claude-agent 与 GPT-agent 独立完成，本节只收录**两者交叉一致**或**单源但题录可核**
的条目，并明确标注置信等级。

## 本轮最重要结论（写进方法论限制）

**两个 agent 独立得出同一个否定结论：不存在支持 `decay_rate=0.06` 或 `caseload=8`
的权威文献。** 二者都拒绝了迎合式凑数（对比第一轮 Gemini 编造"完美吻合"数字的教训），
这个收敛的否定本身就是可报告的发现：这两个参数属于**建模选择**，不是文献标定，
必须以敏感性扫描而非单点引用的方式处理。

## D. 关系衰减 → decay_rate 参数

### ⚠️ 口径纠正（本项目自查；两 agent 与本项目初次分析均有误，已用原文 + 实测更正）

**第一层错误（两个 agent）**：都把 `0.94^12 ≈ 47.6%` 当作"一年后关系存活率"去对标
Burt 的 24.7%。`custom/envs/elder_support_env.py:389` 中 6% 衰减的是**关系强度**
（`strength *= 0.94`，且**仅在当月无联系时**触发），关系只有跌破 `strength < 0.05`
才被删除。47.6% 是强度残留，不是存活率。

**第二层错误（本项目 2026-08-31 初次分析）**：曾据此推出"单条无联系纽带寿命
2.8–3.7 年，落在 Burt 家庭 3.42 年与一般关系 2.63 年之间"。**此结论作废**：
（a）"单条纽带死亡时点"与 Burt 的"群体半衰期"仍非同一个量；
（b）Burt 的 2.63 本身是原文算术错误（见 D-2）。

**正确做法：以 Burt 的口径实测模型输出。** 脚本 `tests/measure_tie_survival.py`
（纯规则层，不耗 LLM，50 人 × 48 月，seed=7）记录 T0 时全部 203 条关系，
逐年统计仍存在的比例，与 Burt Figure 1A 幂函数直接比较：

| | 1 年 | 2 年 | 3 年 | 4 年 | 半衰期 |
| --- | --- | --- | --- | --- | --- |
| 模型（decay=0.06） | 94.1% | 90.1% | 84.7% | 78.8% | > 4 年 |
| Burt 同口径（KIN=47.8%） | 66.1% | 51.9% | 43.7% | 38.3% | 2.20 年 |

**模型关系流失显著慢于文献，4 年差距约 2 倍。**

### ⛔ 结构性发现：存活率地板 ≈ 46%，非参数可解

对 `decay_rate` 做 0.06→0.40 扫描（同脚本）：

| decay | 1 年 | 2 年 | 3 年 | 4 年 | 半衰期 |
| --- | --- | --- | --- | --- | --- |
| 0.06 | 94.1% | 90.1% | 84.7% | 78.8% | >4 年 |
| 0.10 | 94.1% | 85.2% | 68.0% | 57.1% | >4 年 |
| 0.15 | 91.6% | 58.1% | 51.7% | 48.3% | 3.33 年 |
| 0.20 | 78.8% | 49.3% | 47.8% | 47.3% | 2.00 年 |
| 0.30 | 51.2% | 47.3% | 46.8% | 46.8% | 1.17 年 |
| 0.40 | 47.8% | 46.3% | 46.3% | 46.3% | 0.83 年 |

1. **存在约 46% 的存活率地板**：`decay_rate` 再大也降不下去——约 46% 的关系
   （`contact_per_month > 0` 的子女 + 高频邻里）每月都被 `_touch_tie` 刷新
   `last_contact_month`，永不进入衰减分支。Burt 4 年预测 38.3% **低于此地板**，
   故**不存在任何 `decay_rate` 能匹配文献的长期流失**。
2. **曲线形状不同**：Burt 是持续下降的幂函数，模型是快速触底后进入平台。
   对齐 1 年存活率需 decay ≈ 0.25，对齐半衰期需 ≈ 0.18，两者不相容。

这是**机制层面的限制，不是参数标定问题**，须写入方法论限制，
不应靠调 `decay_rate` 掩盖。

### D-1（主引）：老年人关系终止率 —— ✅ 已核实（2026-08-31）

Klein Ikkink, C. E., & van Tilburg, T. G. (1999). Broken ties: Reciprocity and
other factors affecting the termination of older adults' relationships.
*Social Networks*, 21(2), 131–146.
DOI: 10.1016/S0378-8733(99)00005-2
核实来源：LASA（Longitudinal Aging Study Amsterdam）官方出版物页
lasa-vu.nl/publications/broken-ties-... 的正式摘要，与 VU 研究记录一致。

**✅ 核实通过**（GPT-agent 转述准确，Claude-agent 未检出此文）

- 题录、期刊、卷期页码、DOI 全部确认；作者隶属 Vrije Universiteit Amsterdam
- **n = 2,057 名老人**，T1 识别出 **18,915 段关系** ✅
- 关系在第二**和**第三次测量均未被提及即判定中断；T1 关系中 **4,042 段中断** ✅
- 终止率 21.37%（= 4042/18915）与延续 14,873 段均为**由上述两数推算**，
  非原文直述，但算术自洽
- 理论框架：交换理论——支持交换失衡且预期不改善时关系被终止

**用法与限制**

- 这是本轮唯一**直接测量老年人关系终止**的一手研究，作为 D 主引
- ⚠️ 口径：测的是"是否再被提名"（离散存活），非连续强度；且判定需跨两个后续
  波次（LASA 波次间隔约 3 年，故 21.37% 覆盖约 6 年窗口），**不能换算为月率**
- ⚠️ 独立于 Burt：已核对 Burt (2000) preprint 全文，其 Table 1 的 7 个研究
  **不含**本文（Burt preprint 成稿于 1999 年 8 月，与本文同年），故二者为
  相互独立的证据来源，可并列引用


### D-2（主引）：衰减函数形状 —— ✅ 全文已核实（2026-08-31）

Burt, R. S. (2000). Decay functions. *Social Networks*, 22(1), 1–28.
DOI: 10.1016/S0378-8733(99)00015-5
核实所用全文：作者官网 preprint（ronaldsburt.com/research/files/DF.pdf，
39 页，标注 "Forthcoming in Social Networks, August 1999"），已下载并逐行核对。

**✅ 核实通过的数字**

- 银行家 12,655 条关系，T1/T2/T3 存活率 **24.7% / 10.1% / 8.0%**
  （正文 §3，preprint p.9；Table 1 study A 首三行）——两 agent 交叉一致，原文确认
- 同事关系半衰期 **0.46 年**（正文 §6，preprint p.23："half disappear within
  six months (.46 years)"）
- **Morgan, Neal & Carder (1997) 丧偶者 54%** ✅ 原文 §2（preprint p.5）逐字确认：
  "Morgan, Neal, and Carder (1997) describe change in the people cited by 234
  recent widows for having the most effect on their lives. Of 4,955 people cited
  in the first interview, 54% were cited again a year later in the seventh
  interview."（Claude-agent 转述准确，未编造）
- 家庭关系半衰期 **3.42 年** ✅ 原文 §6（preprint p.23）确认

**❌ 发现原文算术错误：家庭外一般社会关系半衰期不是 2.63 年，应为 1.63 年**

Burt §4.1（preprint p.11）给出跨研究拟合方程与 OLS 系数：

    Y = (T+1)^(γ + κ·KIN + λ·WORK)
    γ = −0.716（时间）  κ = 0.250（亲属更慢）  λ = −1.126（同事更快）

令 Y=0.5 解 T：

| 关系类型 | 指数 | T+1 | **正确 T** | Burt 原文 |
| --- | --- | --- | --- | --- |
| 家庭（KIN=1） | −0.466 | 4.426 | **3.43 年** | 3.42 ✅ |
| 家庭以外（KIN=0） | −0.716 | 2.633 | **1.63 年** | 2.63 ❌ |
| 同事（WORK=1） | −1.842 | 1.457 | **0.46 年** | .46 ✅ |

三处中家庭与同事都正确地由 T+1 减 1 得到 T，唯独"家庭以外"直接报了 T+1=2.633
而漏减 1。这是 preprint 原文即存在的错误，两个 agent 均照抄未察。
**引用时须用 1.63 年，或注明"依原文方程重算"。** 复算见
`tests/measure_tie_survival.py` 中 `burt_survival()`。

**⚠️ 重要限定：3.42 / 1.63 不是实测值**

二者由跨 **7 个独立研究、Table 1 共 19 行**存活率拟合的 OLS 幂函数外推而来
（R² = 95%，preprint p.11），不是任一样本的直接观测。Burt 本人只有银行家样本
是一手数据；家庭/非家庭的分野来自 KIN 这一**行级比例变量**，非个体层面分类。
报告引用时须写明"基于 Burt (2000) 跨研究拟合方程外推"，不可写成"实证测得"。

- 用法：主要引用其**"衰减率非常数、呈幂函数、关系越老越稳"**的核心结论
  （"liability of newness"，§6，preprint p.23），作为我们固定月衰减率的**明示限制**
- ⛔ 禁止写法：不得写成"所有关系约 90% 会消失"——24.7%→8.0% 是银行家专业关系的
  三年轨迹，不是全部关系的结论（GPT-agent 明确警告此点，核实无误）
- ⚠️ 丧偶者 54% 的样本是"recent widows"，Burt 未标注年龄分布；
  Morgan et al. (1997) 原研究为老年寡妇样本，但**引用为"老年人"前应核对原研究**

### D-3（佐证，不可代入模型）

两 agent 各给一篇 NSHAP 美国老年样本，均为 **person-level**（"有多少比例的人经历了
任一关系变动"）而非 per-tie 存活率，单位与模型不同，只能作讨论部分佐证：

- Cornwell, B., et al. (2014). Assessment of Social Network Change in a National
  Longitudinal Survey. *J Gerontol B*, 69(Suppl 2), S75–S82.
  DOI: 10.1093/geronb/gbu037 | 开放全文 PMC4303098
  【GPT-agent】5 年追踪：联系频率 6.85→6.76；49.5% 的关系联系频率下降；
  93.1% 受访者报告网络组成变化
- Goldman, A. W., Cornwell, E. Y., & Cornwell, B. (2023). Neighborhood conditions
  and social network turnover among older adults. *Social Networks*, 73, 114–129.
  DOI: 10.1016/j.socnet.2023.01.003
  【Claude-agent】约 5 年间隔内 81% 受访者流失至少一位非亲属联络人、54% 新增

### D 的参数结论（依实测更新）

`decay_rate` **不做单点标定，做敏感性扫描**。建议扫描 `0.06 / 0.15 / 0.25`
——依实测存活曲线选点，而非 GPT-agent 建议的 0.02–0.12（该区间全部落在
"4 年存活率 > 57%" 的平坦段，对结局几乎无区分度，属无效扫描）：

| 取值 | 依据 |
| --- | --- |
| 0.06（基准） | 现行值，保守端；4 年存活 78.8% |
| 0.15 | 中点；半衰期 3.33 年 ≈ Burt 家庭关系 3.43 年 |
| 0.25 | 上端；1 年存活 ≈ 66% ≈ Burt 同口径一年期预测 |

报告措辞（须同时交代三点）：
"Burt (2000) 的跨研究拟合显示关系半衰期随类型跨度达 7 倍（家庭 3.43 年、
家庭以外 1.63 年、弱专业联系 0.46 年；后者由原文方程重算，原文 2.63 为
漏减常数项之误），且证明衰减率非常数而呈幂函数。本模型采用固定月衰减率为
简化假设，故对该参数做敏感性扫描。需明确承认的机制限制是：本模型中衰减仅在
当月完全无联系时触发，而约 46% 的关系（有固定联系频率的子女与高频邻里）
每月均被刷新，因此群体存活率存在约 46% 的下界，无论衰减率取值多大都无法
复现 Burt 幂函数在 4 年处 38.3% 的持续下降。本研究因此不将关系流失速率
作为标定目标，仅将其作为敏感性维度。"


## E. 社工个案管理 → casework 干预参数

### E-1（主引）：独居老人个案管理 RCT —— ✅ 全文已核实（2026-08-31）

Ristolainen, H., Kannasoja, S., Tiilikainen, E., Hakala, M., Närhi, K., &
Rissanen, S. (2020). Effects of 'participatory group-based care management' on
wellbeing of older people living alone: a randomized controlled trial.
*Archives of Gerontology and Geriatrics*, 89, 104095.
DOI: 10.1016/j.archger.2020.104095 | PMID: 32446172
核实所用全文：JYX 机构库开放自存档版（jyx.jyu.fi，11 页），已下载逐行核对。

**✅ 核实通过的数字**（GPT-agent 转述全部准确）

- 干预组 **n = 185** / 对照组 **n = 207** ✅（Abstract + Fig.1 流程图）
- 按方案（per-protocol）分析实际纳入 345 人（干预 159 / 对照 186）
- poor QoL 亚组 **n = 150** ✅（Table 3 行首标注）；44.4% 的参与者按
  WHOQOL-Bref < 60 判为 QoL 差
- 该亚组 UCLA 孤独感：干预 2.5→2.4、对照 2.2→2.2，
  组间×时间 **p = .034，ES = .35** ✅（Table 3 + 正文 §结果）
- **ITT 分析对 QoL 与孤独感均无显著效应** ✅（摘要原文："The intention-to-treat
  analysis did not result in any significant effects on QoL or loneliness"）

**⛔ 两 agent 均漏报的关键限制（作者自陈，直接削弱 ES=.35）**

原文结果段明确写道：poor QoL 亚组的干预组与对照组**基线孤独感不可比**——
"the intervention and control groups of participants with poor QoL were not
fully comparable in terms of loneliness, because baseline values differed
between the intervention and control groups (Table 3)"。基线 2.5 vs 2.2，
干预组起点本就更孤独，故 ES=.35 有向均值回归的成分。

作者自己的结论也很保守："Based on some evidence of small positive effects,
the intervention **may be** beneficial … Because of the **contradictory results**,
more research is needed."

**用法**

- 样本口径最贴合本研究（独居 + 老年 + RCT），作为 casework 效应方向的主引
- ⛔ 禁止将 ES=.35 当作普遍效应：它同时受限于（a）仅 per-protocol、
  （b）仅 poor QoL 亚组、（c）该亚组基线不可比。报告须写成
  "在基线生活质量较差的亚组中观察到方向一致的小效应，但基线不可比且 ITT 为零结果"


### E-2（主引）—— ✅ 全文已核实（2026-09-02，literature/taube2018_sjcs.pdf）

Taube, E., Kristensson, J., Midlöv, P., & Jakobsson, U. (2018). The use of case
management for community-dwelling older people: the effects on loneliness,
symptoms of depression and life satisfaction in a randomised controlled trial.
*Scandinavian Journal of Caring Sciences*, 32(2), 889–901.
DOI: 10.1111/scs.12520 | PMID: 28895175

- 【两 agent 独立给出完全相同的 DOI / PMID / 全部效应量 → 交叉核实通过】
  n=153，12 个月、每月至少一次家庭访问，对象为有功能依赖、与医疗系统反复接触的
  社区失能老人
- 完整病例分析：6 个月孤独感 **RR=0.49, p=.028**；生活满意度 **ES=0.41, p=.028**（6 个月）；
  抑郁症状 **ES=0.47, p=.035**（12 个月）
- ⚠ 【两 agent 均独立指出】总体 ITT 结论保守，作者原文自陈"did not result in clear
  favourable effects for the primary outcomes … however this study indicates that
  case management may be beneficial"
- ⚠ 【GPT-agent 补充】个案管理者主要是**护士 / 物理治疗师**，非社工；样本亦非独居专属
- 用法：报告如实写"方向一致但证据强度中等"，**禁止写成"显著有效"**
- 候补题录（未核实）：You, Dunt & Doyle (2013) 个案管理照护成本证据综述；
  Kristensson et al. (2010) 体弱老人个案管理 RCT 先导研究

### E-3（标准）：中国官方人力配置标准

《老年社会工作服务指南》MZ/T 064—2016，民政部第 396 号公告发布，
全国社会工作标准化技术委员会（SAC/TC 534）归口，推荐性行业标准。
发布 / 实施日期 2016-01-08，备案号 53802-2016。

- 【两 agent 交叉一致，条文高置信】§9.1.3：**城镇养老机构每 200 名老年人配备
  1 名老年社会工作者；城市社区每 1,000 名老年人配备 1 名以上**（不足 1,000 人
  可多社区共用）
- 【GPT-agent 补充条文】§6.2.6 照顾管理含综合评估、计划、协调、监督、再评估与改进，
  适用于长期 / 多重 / 复杂需求；§7.6 服务结束后应跟踪
- ⛔ **该标准不含任何"每社工 N 个活跃个案"的条款**（两 agent 独立确认）
- ✅ **效力状态已核实：现行**（用户于 2026-08-31 在全国标准信息公共服务平台
  std.samr.gov.cn 亲自查证：MZ/T 064-2016 老年社会工作服务指南，民政，**现行**，
  发布 2016-01-08 / 实施 2016-01-08）。Claude-agent 所称"废止"为误读，已否决。

### ⚠️ E 的口径纠正（本项目自查）

两个 agent 都正确指出 1:200 / 1:1000 是"人力配置比"而非"活跃个案量"，单位不同。
但更关键的是模型内 `caseload` 的**实际作用**：

`elder_support_env.py:462-467` 中 `capacity = n_workers × caseload = 2 × 8 = 16`，
而 N=20 → **覆盖率 16/20 = 80%**，且按 `_risk_rank()` 取风险最高者。
所以 `caseload=8` 在本模型里实际扮演的是**覆盖率上限**，不是现实世界的社工负荷。

反过来看，MZ/T 064 的社区比 1:1000 意味着 2 名社工可覆盖 2,000 人——对一个
20 人的模拟村落而言等价于 100% 覆盖。因此该标准**不构成对 80% 覆盖率的否定**，
只是无法用来标定这个数字。

- NASW《Standards for Social Work Case Management》—— ✅ 版本已核实（2026-08-31）
  **两个版本都真实存在，应引用 2013 现行版**：
  - **2013 版（现行，应引）**：共 12 项标准，**Standard 11 "Workload
    Sustainability"** —— 要求个案管理者为自己争取"能够允许高质量地规划、提供和
    评估个案管理服务的案量（caseload）与工作范围（scope of work）"。
    官方 PDF：socialworkers.org（NASW_s-CaseManagementStandards2013.pdf）
  - 1992 版（已被取代）：共 10 项标准，对应条款为 Standard 9 "reasonable
    caseload"。全文见 ERIC ED365909。
  - 判定：GPT-agent 引用现行版，正确；Claude-agent 引用 1992 旧版，**过时但非错误**
  【两 agent 实质结论一致，核实无误】NASW **刻意不给任何具体数字**，2013 版更把
  1992 的 "reasonable caseload" 重构为更宽泛的 "workload sustainability"，
  强调"倡导"而非规定，合理工作量取决于服务模式、风险与复杂度、联系频率、
  服务时长、资源与行政支持。
  → 可直接引用为"业界共识：个案量无统一数字标准"的立场依据
- 实务参考区间（**产业资讯彙整，非法规 / 学术来源，仅供讨论**）：
  密集型个案管理约 12–15 人/社工（上限 20–25）；美国明尼苏达州重度精神疾病成人
  个案管理法定上限 30:1；一般老年个案管理常见范围 60–75 人

### E 的参数结论

`caseload` **不做单点标定，做敏感性扫描**：建议 `4 / 8 / 12`
（对应 N=20 下覆盖率 40% / 80% / 100%，比 GPT 建议的 8/15/25 更贴合本模型量级——
15 和 25 在 N=20 下都已饱和为 100% 覆盖，无区分度）。
报告措辞："中国 MZ/T 064—2016 仅规定人力配置比（机构 1:200 / 社区 1:1000），
NASW 明确拒绝设定统一个案量标准；本研究中该参数实际控制的是高风险老人的
干预覆盖率，故按覆盖率维度做扫描而非引用外部个案量标准。"

## 规则层扫描结果（2026-09-01，`tests/scan_decay_outcomes.py`）

D/E 两个扫描已在规则层跑通（20 老人全规则层、24 月、干预窗 7–18、10 种子，
不耗 LLM；绝对水平与 LLM 批次不可比，只看条件间对比方向）。
完整数字见 `tests/scan_decay_outcomes_result.json`。要点：

1. **干预排序对 decay 稳健**：三个 decay 取值下，干预期平均孤独感均为
   casework < timebank < platform < none（与 Hoang 2022 荟萃排序一致）。
2. **撤出后可持续性分化**：casework 撤出后孤立率回弹至接近 none
   （decay=0.15 时 0.030→0.146），timebank 因结对关系存续回弹最小
   （0.069→0.080）——H4 机制在规则层已可见。
3. **decay 抬高整体孤独水平但不改变干预排序**：none 期末孤独感
   0.384 / 0.459 / 0.478（decay 0.06/0.15/0.25）。
4. **caseload 干预期内单调**（4/8/12 → 0.277/0.237/0.217），
   撤出后三者收敛（≈0.29–0.31）——覆盖率只影响在场效应，不影响可持续性。

## 本轮待办（引用前必须完成）

1. ~~下载 Burt (2000) PDF 核对三个数字~~ ✅ **已完成 2026-08-31**：
   丧偶者 54% ✅、家庭半衰期 3.42 ✅ 均逐字核实通过（Claude-agent 未编造）；
   **家庭外 2.63 为原文算术错误，正确值 1.63**，已按原文方程复算更正。
   附带发现：3.42/1.63 系跨 7 研究 19 行 OLS 外推，非实测值。
2. ~~核实 Klein Ikkink & van Tilburg (1999)~~ ✅ **已完成**：题录、n=2,057、
   18,915 条关系、4,042 条中断均经 LASA 官方摘要确认；21.37% 为推算值（自洽）
3. ~~核实 Ristolainen et al. (2020)~~ ✅ **已完成**：下载 JYX 开放全文，
   n=185/207、亚组 n=150、ES=.35/p=.034、ITT 零结果全部通过；
   **新增发现**：作者自陈该亚组基线孤独感不可比（2.5 vs 2.2），两 agent 均漏报
4. ~~去 std.samr.gov.cn 查 MZ/T 064—2016 当前效力状态~~ ✅ 已完成：**现行**
5. ~~确认 NASW 个案管理标准版本年份~~ ✅ **已完成**：两版均存在，
   2013 版（12 项，Standard 11 Workload Sustainability）为现行版，应引用之

## ✅ 本轮核实全部完成（2026-08-31）

5 项待办已全部结清。核实产出的**新发现**（非 agent 提供，均由本项目自查得出）：

1. Burt (2000) 家庭外关系半衰期 2.63 年为**原文算术错误**，正确值 1.63 年
2. Burt 的 3.42 / 1.63 **不是实测值**，是跨 7 研究 19 行的 OLS 外推
3. 本模型关系流失显著慢于文献（4 年 78.8% vs 38.3%），且存在
   **~46% 的存活率地板**，属机制限制而非参数问题
4. Ristolainen (2020) 的 ES=.35 所在亚组**基线不可比**（作者自陈）
5. Klein Ikkink (1999) 与 Burt (2000) 互为**独立证据**（Burt Table 1 不含该文）

两个 agent 本轮**均未编造文献或数字**——所有可核实项都通过了。
与第一轮 Gemini 编造 "Loneliness Dynamics…" 一文形成对照，
差别在于本轮两 agent 都主动声明"找不到支持 6%/月 与个案量 8 的文献"，
而非凑出吻合数字。**主动报告空缺是可信度的正向信号。**

## 第三轮检索（2026-09-07，多源聚合 MCP 接口：RAGFlow/arXiv/CrossRef/OpenAlex）

- **δ=0.06（月度衰减率）**：两组查询（tie decay / network turnover longitudinal）均无直接文献，
  与前两轮结论一致。三轮独立检索均为阴性，"无权威文献支持"声明进一步坐实。
- **caseload=8**：新命中 Pardasani (2018) Educational Gerontology 44(11):712-723,
  doi:10.1080/03601277.2018.1555205（NYC DFTA 居家老人个案管理个案量研究）。
  实测平均登记个案量 ~75 人/社工、40% 超过 85 人、且被认为已超载（配套 2014 DFTA 报告）。
  **不支持 caseload=8 为登记个案量**——但确认了"现实登记个案量与本模型月度高强度覆盖参数
  单位不同"的论证，已作为实证锚点补入论文 §建模选择（中英两版）+ refs.bib（pardasani2018caseload）。
- **platform 条件**：检索有候选（JMIR 数字人、电话主动干预等）但均与"志愿匹配平台"机制不完全对口，
  现有 hoang2022（技术类干预 CI 跨零荟萃）仍是最贴切依据，不更换。
