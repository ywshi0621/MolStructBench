# MolStructBench

Technical report   ·   Version 1.0   ·   October 2026

## Abstract

A model may recognize an amide yet point to the wrong atoms. It may describe a stereocenter correctly yet assign the wrong configuration. MolStructBench measures whether molecular knowledge survives this move from a general description to a specific structure. The benchmark contains 288 fixed questions across three structural domains: Native3D, 3D→2D, and Pure2D. Its 48 dataset–task units cover structure grounding, conformational geometry, molecular properties, and medicinal chemistry. Each unit contains six questions.

The release includes the questions, complete gold answers, an official local scorer, and an optional OpenCode agent harness. Deterministic evaluation handles 180 questions; 108 use a frozen Qwen3.8-Max judge with three independent votes and median aggregation. Five archived model runs are scored by the same procedure. Their MolStructBench Scores range from 87.38 to 98.78 out of 100. All predictions and archived judge votes needed to reproduce these scores are included.

## 1 Benchmark design

MolStructBench asks a practical question: can a language model read a molecular representation, apply the stated chemical rules, and return an answer grounded in the molecule it was given? Answers may be atom indices, bond endpoints, three-dimensional bounding boxes, a molecular identity, or a chemical explanation. The representation and the required output are part of the task contract.

| Domain | Task units | Questions | Input emphasis |
| --- | --- | --- | --- |
| Native3D | 8 | 48 | Atoms, bonds, coordinates |
| 3D→2D | 16 | 96 | Topology derived from 3D sources |
| Pure2D | 24 | 144 | SMILES and indexed graphs |
| Total | 48 | 288 | 153 English and 135 Chinese |

The fixed selection was drawn from a 940-question development pool using molecular and task features, without solver scores, judge outcomes, token usage, or trajectories. In 44 units, the selection contains one easy, two medium, and three hard questions. Four knowledge and identification units instead contain two questions at each of three structural-complexity levels. Label, language, query, and chemical diversity also constrain selection. The released IDs and hashes make this selection explicit.

## 1 Benchmark design continued

### Native3D

The eight Native3D units use explicit atom, bond, and coordinate records. They ask the model to locate functional groups, rotatable bonds, stereocenters, pharmacophore relations, and regions associated with hydrogen-bond contact or torsion changes. Grounding is scored against ordered spatial boxes, with a 0.01 Å tolerance where specified; stereocenter tasks also require the CIP label. A correct chemical label attached to the wrong region does not satisfy the task.

The conformer-energy unit is a stored-energy comparison control. The source energies are supplied in the question, so the task measures correct comparison of those values. It does not require an electronic-structure calculation. This unit remains part of the official score.

### 3D to 2D and Pure2D

The 16 units in 3D→2D work with molecular topology derived from three-dimensional source structures. They combine exact atom-level grounding with scaffold descriptions, functional-group questions, graph comparisons, and property explanations. Pure2D adds eight further units, including bond localization, ring-system grounding, parent standardization, molecular identification, and target or mechanism knowledge. The full catalog appears in the appendix.

These are structured molecular inputs: text records, indexed graphs, SMILES, and coordinates. The three domains distinguish the structural information available to the model. The current release does not require a molecular image encoder. Chemical knowledge questions and structural localization questions therefore remain traceable to the same explicit molecular record.

## 2 The agent harness

The supplied harness retains the OpenCode CLI agent loop and exposes a single scientific_shell tool. A model can write a calculation, receive its result, revise its approach, and produce a final answer. The shell provides Python with RDKit, NumPy, SciPy, pandas, and NetworkX for graph analysis, geometry, descriptors, and numerical work. Profile A gives each solver the same public prompt, tool access, runtime policy, and output schema.

Provider differences are confined to adapters for OpenAI-compatible Chat Completions, the Responses API, and local OpenAI-compatible endpoints such as a configured vLLM service. The model-facing scientific task does not change across adapters. The OpenCode integration requires native tool calling and explicitly rejects an interface that cannot support it. A local endpoint still needs a model and server configuration capable of continuing after tool results.

## 2 The agent harness continued

### Runtime and records

Each question runs in its own session and workspace. Scientific code executes in the Linux bubblewrap sandbox with bounded time, memory, and output. The tool workspace contains the public input and permitted working files. Gold answers and scoring facts are loaded only in the evaluation stage and are excluded from solver system, user, and tool messages.

| Release runtime setting | Value |
| --- | --- |
| Model calls | 24 ordinary calls plus one finalization call |
| Tool calls | 32 maximum |
| API request timeout | 1800 seconds |
| Whole-question timeout | 7200 seconds |
| Scientific tool timeout | 180 seconds |
| API attempts | Up to 3 with finite backoff |

Soft budget reminders occur at 18 model calls and 20 tool calls. Rate limits, server failures, and transport timeouts receive bounded retries. A wrong scientific answer or an error in model-written Python remains part of that attempt rather than becoming a reason to rerun the question. Checkpoints support resume after interruption. Predictions, execution records, tool statistics, and provider usage are written separately. Archived runs retain their original configuration and provenance; the table above describes the published harness settings.

## 3 Official scoring

### Deterministic evaluation

The deterministic scorer checks the public task contract against complete gold and accepted variants. Depending on the task, this means comparing atom sets, sets of atom groups, bond indices or endpoints, canonical structures, class labels, names, or spatial boxes. If the contract permits multiple valid targets, the accepted set records those alternatives. The rules apply to every model through one scorer.

The parser prioritizes the final answer and supports JSON, fenced JSON, tables, and natural-language wrappers. It normalizes equivalent forms and removes duplicate expressions of the same result. Candidate indices, coordinates, or R/S labels in an analysis section must not contaminate a later final conclusion. Contradictions inside the final answer are preserved for scoring. Molecular names accept the documented synonyms, including ordinary bilingual and parenthetical forms.

Molecular identity tasks first use deterministic name and identity matching. An eligible unresolved identity can then use the same frozen three-vote judging procedure. This fallback accepts chemically equivalent naming without turning a single spelling into the only valid answer.

## 3 Official scoring continued

### Semantic evaluation

The semantic judge receives the question, task specification, structured reference facts, frozen public evidence, and the final answer. It receives no solver identity, reasoning trace, or tool history. Qwen3.8-Max is anonymized in exactly the same way when its own solver answers are judged.

The judge evaluates the task contract. A reference answer is non-exhaustive unless the task explicitly defines a closed ontology. Chemically equivalent descriptions and synonyms are accepted, and an additional scientifically correct fact is not penalized merely because it is absent from the reference. A contradiction with a required fact or an omitted required part lowers the grade.

| Judge setting | Frozen value |
| --- | --- |
| Model | qwen3.8-max |
| Thinking and reasoning effort | Enabled and high |
| Temperature | 0.6 |
| Maximum output tokens | 8192 per request |
| Votes | 3 independent requests |
| Grade | 0 incorrect · 1 partial · 2 fully correct |

Each vote is scaled from 0/1/2 to 0/0.5/1, and the median of the three votes is the sample score. Requests and cached results are checked against the judge identity, prompt, parameters, and anonymous-input hashes. Failed requests stay pending and can be resumed; they do not become zero grades. A complete official score requires all necessary votes.

### Aggregation

First, the scorer averages the six sample scores within each dataset–task unit. It then averages the unit scores within each domain. The final MolStructBench Score is 100 times the equal-weight mean of the Native3D, 3D→2D, and Pure2D domain scores. Each domain therefore contributes one third of the headline score, although their question counts differ.

Deterministic, semantic, and micro averages are secondary metrics. They answer different diagnostic questions and do not replace the official aggregation. Partial semantic credit also means that a score expressed out of 100 is not a simple count of fully correct answers.

### Scoring reproducibility

The release pins the data selection, evaluator, accepted variants, judge template, and configuration with file hashes. Historical judge inputs use the archived public-evidence snapshot, preserving the original request identity across local dependency versions. Offline replay validates the original votes and computes scores from predictions and votes. Expected result files serve only as comparison assertions.

## 4 Five model results

Table 1 reports five archived agent runs on the same 288 selected questions, evaluated with the official scorer. The release uses their existing answers and completed judge votes; preparing the release did not call the five solvers again. All 1,440 predictions are present, all 1,665 required votes are complete, and no score is pending. The vote total includes three votes for each of 540 semantic answers and 45 votes for 15 molecular-identity fallbacks.

Table 1   Official scores and domain breakdown on a 0 to 100 scale

| Model | Score | Native3D | 3D→2D | Pure2D |
| --- | --- | --- | --- | --- |
| GPT-6 Astra | 98.78 | 100.00 | 97.40 | 98.96 |
| Kimi K3 | 95.66 | 95.83 | 93.23 | 97.92 |
| DeepSeek V4 Pro 0813 | 93.92 | 91.67 | 91.15 | 98.96 |
| Qwen3.8-Max | 90.28 | 93.75 | 87.50 | 89.58 |
| GLM-5.3-Max | 87.38 | 85.42 | 85.42 | 91.32 |

GPT-6 Astra has the highest aggregate score at 98.78, followed by Kimi K3 at 95.66 and DeepSeek V4 Pro 0813 at 93.92. Qwen3.8-Max scores 90.28, and GLM-5.3-Max scores 87.38. Astra scores 100 on Native3D; Astra and DeepSeek both reach 98.96 on Pure2D. Domain scores separate these aggregate results: Qwen performs better on Native3D than on either topological domain, while Kimi and DeepSeek obtain their strongest results on Pure2D.

Table 2   Secondary metrics on a 0 to 100 scale

| Model | Deterministic | Semantic | Micro |
| --- | --- | --- | --- |
| GPT-6 Astra | 100.00 | 96.30 | 98.61 |
| Kimi K3 | 95.56 | 96.76 | 96.01 |
| DeepSeek V4 Pro 0813 | 96.94 | 92.13 | 95.14 |
| Qwen3.8-Max | 91.11 | 87.04 | 89.58 |
| GLM-5.3-Max | 90.56 | 84.72 | 88.37 |

The secondary metrics help locate the source of a difference. DeepSeek scores 96.94 on deterministic tasks and 92.13 on semantic tasks; Kimi scores 95.56 and 96.76, respectively. The headline score also depends on where those results fall across the three equally weighted domains. The released per-question records and 48-unit breakdown allow readers to examine that structure directly.

## 5 What the task breakdown reveals

### Strict rotatable bonds

The Native3D rotatable-bond grounding unit gives a sharp example of contract-sensitive chemistry. Astra answers all six questions correctly, Kimi four, and the other three models three each. A plausible flexible bond is not necessarily a rotatable bond under the stated strict definition. The model must select the right bond and localize it in space. A broader intuition about molecular flexibility cannot substitute for the requested criterion.

### Scaffold boundaries

The 3D→2D scaffold-core grounding unit separates recognition from exact membership. Astra and DeepSeek score 100, GLM 83.33, Kimi 66.67, and Qwen 33.33. Calling a molecule a member of the right scaffold family does not establish which indexed atoms belong to its core. Exocyclic atoms, fused rings, and substituent attachment points make these boundaries consequential.

### Hydrogen bond explanations

In the 3D→2D hydrogen-bond source explanation unit, scores range from 58.33 to 100. Naming a nitrogen or oxygen atom is only the start: the answer must account for donor or acceptor behavior in its actual chemical environment. Protonation, resonance, and functional-group context can change that role. This unit requires an explanation grounded in the supplied structure, rather than a generic list of heteroatoms.

### Molecular identity

Pure2D molecular identification produces another substantial spread: Astra scores 100 and Qwen 33.33. Two Qwen answers illustrate the difficulty. A glasdegib structure was identified as WAY-267464, and cefixime was identified as ceftibuten. These are different compounds rather than alternative names for the same molecule. Familiar structural motifs can suggest a drug family while still leading to the wrong molecular identity.

### Computing and then using the result

A pairwise property answer from Qwen recognized that both structures had zero rotatable bonds under the strict rule, then used broader counts of three and one to declare A more rotatable. The final comparison no longer followed the task definition. This failure is informative because access to a calculation alone would not fix it: the model also has to carry the correct definition into its conclusion.

These examples show why MolStructBench combines explanation with grounding and exact comparison. Chemical vocabulary, structural membership, and the final decision are separately observable. The aggregate ranking is useful, but the task breakdown reveals what a model actually handled well and where its interpretation changed along the way.

## 6 Open source release and reproduction

MolStructBench uses an open-gold release model. The repository includes all public questions, complete gold, accepted variants, the task catalog, the deterministic evaluator, the judge prompt and configuration, and the official aggregation. The dataset is consequently a public benchmark rather than a hidden test set. Solver execution and scoring remain separate stages even though both sets of assets are distributed together.

| Edition | Included components |
| --- | --- |
| With harness | Data, gold, local scorer, OpenCode agent, scientific_shell |
| Without harness | The same data, gold, and local scorer for an external runner |

Both editions produce the same official score for the same prediction file. The version without a harness lets researchers connect another framework while keeping the task inputs and scoring protocol fixed. Results from different tool or runtime profiles should identify that profile alongside the model and benchmark version.

### Running and scoring locally

On Linux or WSL with Python 3.10, the full edition installs its pinned environment and OpenCode binary. Copy a provider example to a separate configuration file, choose a model that supports tool continuation, and supply API credentials through environment variables. A typical workflow is:

```bash
bash scripts/install_environment.sh
source .runtime/venv/bin/activate
cp configs/chat.json my_model.json
# Configure the model and endpoint in my_model.json
export OPENAI_API_KEY="YOUR_SOLVER_KEY"
molstructbench eval --model MODEL_ID \
  --config my_model.json --output runs/model
export DASHSCOPE_API_KEY="YOUR_JUDGE_KEY"
molstructbench score --predictions runs/model/predictions.jsonl \
  --output scores/model
```

Scoring runs on the user’s machine. Deterministic checks are local, and semantic requests use the user’s DashScope key. No maintainer scoring service or submission token is required. Resume and validated judge caches avoid repeating completed work. The scorer writes final_results.json, per-sample scores, the three-domain and 48-task breakdowns, and judge usage statistics.

### Reproducing the reference leaderboard

```bash
python scripts/verify_release.py
python -m unittest discover -s tests -v
python scripts/gold_selftest.py
python scripts/reproduce_history.py --output results/history
```

The historical replay is fully offline. It uses the packaged predictions and original judge votes, checks their hashes, and reproduces all five model scores without solver or judge API calls. Automated release checks cover the fixed 288 IDs, the 48-unit catalog, 180 deterministic gold self-tests, parsing regressions, and score consistency.

## 7 Scientific scope

MolStructBench focuses on molecular structure understanding and grounding with a bounded scientific tool workflow. Property and medicinal-chemistry questions evaluate the stated structural criteria and supporting explanations. For example, the metabolic-liability contract defines a long alkyl chain as at least five consecutive non-ring sp3 carbon atoms. A path through a saturated ring does not satisfy that condition. This precision keeps the gold, prompt, and evaluator aligned.

The benchmark’s public representations make it possible to inspect an answer against atoms, bonds, and coordinates. They also make the failure cases interpretable: a wrong atom set, a reversed comparison, an unsupported identity, or an explanation that contradicts the molecule. The stored-energy control has a deliberately simpler role within that task set. Every unit keeps its declared scoring contract and official weight.

## 8 Conclusion

MolStructBench brings molecular explanations and structural localization into one reproducible evaluation. The same question can require chemical knowledge, a graph or geometric calculation, and a precise final answer. Its two release editions share one dataset and one local scoring system, so researchers can use the supplied OpenCode agent or integrate their own runner. The archived five-model results provide an immediately reproducible reference, while the task catalog and per-question records show how to interpret new results beyond a single headline score.

## Implementation references

The engineering follows the separation of task data, execution, prediction artifacts, and evaluation used in established benchmark repositories. OpenCode supplies the agent loop. AstaBench, SWE-bench, MLE-bench, and the LM Evaluation Harness offer related reference implementations for scientific agents, executable environments, submission records, and common model interfaces.

- [OpenCode](https://github.com/anomalyco/opencode)

- [AstaBench](https://github.com/allenai/asta-bench)

- [SWE-bench](https://github.com/SWE-bench/SWE-bench)

- [MLE-bench](https://github.com/openai/mle-bench)

- [LM Evaluation Harness](https://github.com/EleutherAI/lm-evaluation-harness)

## Appendix The 48 task units

A unit is a dataset–task combination, with six questions in every unit. The catalog contains 48 units and 33 distinct task-type names. Several task types occur in both topological domains. Display names below replace underscores with spaces; the machine-readable catalog retains the exact identifiers.

### Native3D   8 units

| Task | Scoring target |
| --- | --- |
| conformer energy ranking | Stored energy |
| functional group bbox grounding 3d | 3D boxes |
| hbond contact change grounding 3d | 3D boxes |
| pharmacophore relation grounding 3d | 3D boxes |
| rotatable bond bbox grounding 3d | 3D boxes |
| shared functional group pair grounding 3d | 3D boxes |
| stereocenter grounding 3d | 3D box and CIP |
| torsion change grounding 3d | 3D boxes |

### 3D to 2D   16 units

| Task | Scoring target |
| --- | --- |
| anchor atom grounding | Atom set |
| drug likeness | Semantic |
| functional group grounding | Atom groups |
| functional group qa | Semantic |
| hydrogen bond source explanation | Semantic |
| metabolic liability | Semantic |
| molecule caption | Semantic |
| pairwise analog classification | Class or label |
| pairwise graph diff | Semantic |
| pairwise property comparison | Semantic |
| permeability solubility | Semantic |
| scaffold core grounding | Atom set |
| scaffold fragment caption | Semantic |
| simple ring grounding | Atom set |
| single instance functional group grounding | Atom groups |
| single substituent grounding | Atom groups |

## Appendix Task catalog continued

### Pure2D   24 units

| Task | Scoring target |
| --- | --- |
| anchor atom grounding | Atom set |
| attachment bond endpoint grounding | Bond endpoints |
| bond grounding | Bond target |
| database grounded knowledge caption | Semantic |
| drug likeness | Semantic |
| full form parent standardization | Canonical structure |
| functional group grounding | Atom groups |
| functional group qa | Class or label |
| identity with structural evidence | Semantic |
| known target mechanism | Semantic |
| metabolic liability | Semantic |
| molecule caption | Semantic |
| molecule identification | Molecular identity |
| pairwise analog classification | Class or label |
| pairwise graph diff | Semantic |
| pairwise property comparison | Semantic |
| permeability solubility | Class or label |
| ring system grounding | Atom set |
| scaffold core grounding | Atom set |
| scaffold fragment caption | Semantic |
| scaffold grounding | Core and groups |
| simple ring grounding | Atom set |
| single instance functional group grounding | Atom groups |
| single substituent grounding | Atom groups |

Semantic means three-vote median judging. Molecular identity uses deterministic matching with an eligible identity fallback. All target definitions, output requirements, and accepted alternatives are specified in the released task contracts and scorer assets.
