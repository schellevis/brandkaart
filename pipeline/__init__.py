"""Brandkaart dataprototype-pipeline.

Handmatig uitvoerbare pipeline die exact dezelfde stappen gebruikt als de
latere uurlijkse GitHub Action: bronnen ophalen, normaliseren via een
veld-allowlist, valideren (versheid, PII, secrets, plausibiliteit) en een
compact statisch artefact plus manifest.json produceren.

Draaien: uv run python -m pipeline.run
"""

SCHEMA_VERSION = "0.1"
PIPELINE_VERSION = "0.1.0"
