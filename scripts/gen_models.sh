#!/usr/bin/env bash
# Regenerate the Pydantic models in services/contracts from /schemas.
# CI runs this and fails if the result differs from what is committed.
set -euo pipefail
cd "$(dirname "$0")/.."

for name in event tracking overlay world match trigger stats scenario profile agents; do
  uv run --frozen datamodel-codegen \
    --input "schemas/${name}.schema.json" \
    --input-file-type jsonschema \
    --output "services/contracts/${name}.py" \
    --output-model-type pydantic_v2.BaseModel \
    --target-python-version 3.12 \
    --use-standard-collections \
    --use-union-operator \
    --use-annotated \
    --field-constraints \
    --enum-field-as-literal all \
    --use-title-as-name \
    --collapse-root-models \
    --use-type-alias \
    --use-schema-description \
    --use-field-description \
    --use-double-quotes \
    --extra-fields forbid \
    --disable-timestamp \
    --formatters ruff-format ruff-check \
    --custom-file-header "# Generated from schemas/${name}.schema.json by scripts/gen_models.sh. Do not edit."
done
