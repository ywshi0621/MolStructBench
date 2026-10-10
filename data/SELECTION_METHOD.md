# MolStructBench fixed Core selection v1

- 288 samples = 48 task units × 6.
- 44 task units: **1 easy + 2 medium + 3 hard**, difficulty defined only by model-independent intrinsic chemistry/task features.
- 4 knowledge/identification task units: **2 low + 2 medium + 2 high structural-complexity** samples; no solver-derived “hardness”.
- Label balance, language balance, query/property diversity, and chemical diversity are enforced before preferring marginally harder samples.
- No Qwen3.8 pilot correctness, judge score, trajectory, latency, or token usage was used for selection.

Counts:
- Native 3D: 48
- 3D→2D: 96
- Pure2D: 144
- Deterministic: 180
- Semantic judge: 108
- English / Chinese: 153 / 135

Classification constraints include:
- conformer A/B: 3/3
- binary functional-group QA: 3/3 where applicable
- drug-likeness alert/none: 3/3 where applicable
- metabolic-liability flag/none: 3/3 where applicable
- analog close/related/not-close: 2/2/2

Important:
`scibench_000687` remains in the selected set. Run Core288 only after the known `metabolic_liability` long-sp3-chain contract is repaired/frozen in r2. If r2 merely clarifies “acyclic/non-ring long sp3 chain”, IDs can remain unchanged; if its gold semantic class changes, rerun selection.

The previous Qwen3.8 48-task pilot overlaps 19 selected IDs. This overlap was checked only after selection and was not used to choose them.
