# MolStructBench editions

Both editions publish exactly the same 288 inputs, gold, accepted variants,
48 task specifications, frozen Judge protocol and historical predictions/votes.
The scientific score is unchanged. Choose one edition per virtual environment.

WITH_HARNESS: standard OpenCode Profile A execution + local scoring.
WITHOUT_HARNESS: data + standalone local scorer; no runner, OpenCode, MCP,
scientific_shell, provider adapters or Agent execution dependencies.

Use an external framework to generate id/prediction JSONL for WITHOUT_HARNESS.
Keep gold out of Solver inputs and disclose the external execution setup; a
different tool/runtime setup is not the same Profile A experiment as the archive.

The display name is MolStructBench. The scibench CLI alias, Python package and
serialized sample/dataset IDs remain for compatibility with immutable historical
records. Renaming IDs or frozen prompts would invalidate historical provenance.
