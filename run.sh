#!/bin/bash
set -a
if [ -f ".env" ]; then
    source ".env"
fi
set +a

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
API_KEY="${OPENAI_API_KEY:-${DOUBAO_API_KEY:-}}"
API_MODEL="${OPENAI_API_MODEL:-${DOUBAO_API_MODEL:-gpt-4-vision-preview}}"
API_BASE="${OPENAI_API_BASE:-${OPENAI_BASE_URL:-${DOUBAO_API_URL:-}}}"

API_BASE_ARGS=()
if [ -n "$API_BASE" ]; then
    API_BASE_ARGS=(--api_base "$API_BASE")
fi

nohup "$PYTHON_BIN" -u run.py \
    --test_file ./data/tasks_test.jsonl \
    --api_key "$API_KEY" \
    --api_model "$API_MODEL" \
    "${API_BASE_ARGS[@]}" \
    --headless \
    --max_iter 15 \
    --max_attached_imgs 3 \
    --temperature 1 \
    --fix_box_color \
    --seed 42 > test_tasks.log &
