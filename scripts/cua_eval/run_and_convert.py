#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image


DEFAULT_CUA_BIN = ""
DEFAULT_CUA_CONFIG = "config/cua_eval.json"
AUGMENTED_TOOL_NAMES = {
    "shell_exec",
    "shellexec",
    "shell_sh",
    "shellsh",
    "osascript_exec",
    "osascriptexec",
    "http_request",
    "httprequest",
}


def load_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
        os.environ.setdefault(key, value)
    return values


def env_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_tasks(path: str | Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                task = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_no}: {exc}") from exc
            tasks.append(task)
    return tasks


def split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def filter_tasks(
    tasks: list[dict[str, Any]],
    start: int,
    limit: int | None,
    include_web: set[str],
    exclude_web: set[str],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for task in tasks:
        web_name = str(task.get("web_name", ""))
        if include_web and web_name not in include_web:
            continue
        if exclude_web and web_name in exclude_web:
            continue
        filtered.append(task)

    sliced = filtered[max(0, start):]
    if limit is not None:
        sliced = sliced[:max(0, limit)]
    return sliced


def safe_task_dir_name(task_id: str) -> str:
    return "task" + "".join(ch if ch not in "/\\:" else "_" for ch in task_id)


def build_cua_task_prompt(task: dict[str, Any], profile: str) -> str:
    web = str(task["web"])
    question = str(task["ques"])
    return (
        "You are being evaluated on a WebVoyager web browsing task.\n\n"
        f"Evaluation profile: {profile}\n\n"
        "Open this URL first:\n"
        f"{web}\n\n"
        "Complete this task:\n"
        f"{question}\n\n"
        "Rules:\n"
        "- Use the browser UI to complete the task.\n"
        "- Use Google Chrome as the browser for this benchmark.\n"
        "- Treat this task as independent from any previous task.\n"
        "- At the start of the task, focus Google Chrome and navigate the active tab to the exact URL above using the browser address bar.\n"
        "- Do not rely on pages, forms, answers, or browser state left from previous tasks.\n"
        "- Focus only on the current task instruction; do not continue or reuse goals from any previous task.\n"
        "- Do not use shell, scripts, direct HTTP requests, or filesystem shortcuts to obtain the answer "
        "unless the evaluation profile explicitly allows tool augmentation.\n"
        "- When the task is complete, call done with the final answer in the reason.\n"
        "- The done reason must contain the answer, not just \"task completed\".\n"
    )


def task_init_message(task: dict[str, Any]) -> str:
    return (
        f"Now given a task: {task['ques']}  "
        f"Please interact with {task['web']} and get the answer."
        "Observation: Converted from a CUA trajectory."
    )


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def read_cua_result(run_dir: Path) -> dict[str, Any]:
    steps_json = run_dir / "steps.json"
    if steps_json.exists():
        return read_json(steps_json)

    steps_jsonl = run_dir / "steps.jsonl"
    if steps_jsonl.exists():
        steps: list[dict[str, Any]] = []
        with steps_jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    steps.append(json.loads(line))
        return {
            "runId": run_dir.name,
            "task": "",
            "success": False,
            "reason": "steps.json missing; converted from steps.jsonl",
            "steps": steps,
        }

    raise FileNotFoundError(f"Missing steps.json or steps.jsonl in {run_dir}")


def resolve_screenshot_path(raw_path: str, run_dir: Path, cua_cwd: Path) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(raw_path)
    candidates = []
    if candidate.is_absolute():
        candidates.append(candidate)
    else:
        candidates.extend([
            cua_cwd / candidate,
            run_dir / candidate,
            run_dir / candidate.name,
        ])

    for item in candidates:
        if item.exists() and item.is_file():
            return item.resolve()
    return None


def collect_screenshots(cua_result: dict[str, Any], run_dir: Path, cua_cwd: Path) -> list[Path]:
    screenshots: list[Path] = []
    last_path: Path | None = None
    for step in cua_result.get("steps", []):
        if not isinstance(step, dict):
            continue
        resolved = resolve_screenshot_path(str(step.get("screenshotPath") or ""), run_dir, cua_cwd)
        if resolved and resolved != last_path:
            screenshots.append(resolved)
            last_path = resolved

    if screenshots:
        return screenshots

    fallback = sorted(
        [p for p in run_dir.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    )
    return [p.resolve() for p in fallback]


def copy_as_png(source: Path, dest: Path) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.save(dest, format="PNG")
        return True
    except Exception:
        return False


def json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def extract_final_answer(cua_result: dict[str, Any]) -> str:
    steps = cua_result.get("steps", [])
    if isinstance(steps, list):
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            if step.get("actionName") == "done":
                args = step.get("actionArgs")
                if isinstance(args, dict) and args.get("reason"):
                    return str(args["reason"]).strip()

    reason = str(cua_result.get("reason") or "").strip()
    success = cua_result.get("success")
    if reason:
        return reason
    if success is True:
        return "CUA marked the task as successful but did not provide a final answer."
    return "CUA did not provide a final answer."


def build_interact_messages(task: dict[str, Any], cua_result: dict[str, Any], final_answer: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": "Converted CUA run for WebVoyager evaluation.",
        },
        {
            "role": "user",
            "content": task_init_message(task),
        },
    ]

    for step in cua_result.get("steps", []):
        if not isinstance(step, dict):
            continue
        action_name = str(step.get("actionName") or "unknown")
        action_args = step.get("actionArgs") or {}
        result = step.get("result") or step.get("tool") or step.get("error")
        messages.append({
            "role": "assistant",
            "content": (
                f"Thought: CUA step {step.get('step')} selected {action_name}.\n"
                f"Action: CUA_ACTION; {action_name} {json_compact(action_args)}\n"
                f"Observation: {json_compact(result)}"
            ),
        })

    messages.append({
        "role": "assistant",
        "content": f"Thought: CUA finished or stopped the task.\nAction: ANSWER; {final_answer}",
    })
    return messages


def convert_cua_run(
    task: dict[str, Any],
    run_dir: Path,
    output_root: Path,
    cua_cwd: Path,
) -> dict[str, Any]:
    task_id = str(task["id"])
    output_dir = output_root / safe_task_dir_name(task_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    cua_result = read_cua_result(run_dir)
    screenshots = collect_screenshots(cua_result, run_dir, cua_cwd)
    copied = 0
    for source in screenshots:
        dest = output_dir / f"screenshot{copied + 1}.png"
        if copy_as_png(source, dest):
            copied += 1

    final_answer = extract_final_answer(cua_result)
    messages = build_interact_messages(task, cua_result, final_answer)
    with (output_dir / "interact_messages.json").open("w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

    shutil.copyfile(run_dir / "steps.json", output_dir / "cua_steps.json") if (run_dir / "steps.json").exists() else None

    steps = cua_result.get("steps", [])
    tool_counts: dict[str, int] = {}
    duration_ms = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    failed_tool_steps = 0
    augmented_tools: set[str] = set()
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                name = str(step.get("actionName") or "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1
                normalized_name = name.replace("-", "_").lower()
                if normalized_name in AUGMENTED_TOOL_NAMES:
                    augmented_tools.add(name)

                duration = step.get("durationMs")
                if isinstance(duration, (int, float)):
                    duration_ms += int(duration)

                tool = step.get("tool")
                if isinstance(tool, dict) and tool.get("success") is False:
                    failed_tool_steps += 1

                llm = step.get("llm")
                usage = llm.get("usage") if isinstance(llm, dict) else None
                if isinstance(usage, dict):
                    prompt_tokens += int(usage.get("promptTokens") or 0)
                    completion_tokens += int(usage.get("completionTokens") or 0)
                    total_tokens += int(usage.get("totalTokens") or 0)

    return {
        "task_id": task_id,
        "web_name": task.get("web_name"),
        "web": task.get("web"),
        "cua_run_id": cua_result.get("runId") or run_dir.name,
        "cua_run_dir": str(run_dir),
        "cua_success": cua_result.get("success"),
        "cua_reason": cua_result.get("reason"),
        "steps": len(steps) if isinstance(steps, list) else 0,
        "duration_ms": duration_ms,
        "llm_tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        },
        "screenshots": copied,
        "final_answer": final_answer,
        "tool_counts": tool_counts,
        "failed_tool_steps": failed_tool_steps,
        "augmented_tools": sorted(augmented_tools),
        "converted_dir": str(output_dir),
    }


def child_dirs(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {item.name for item in path.iterdir() if item.is_dir()}


def newest_child_dir(path: Path, candidates: set[str]) -> Path | None:
    dirs = [path / name for name in candidates if (path / name).is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda item: item.stat().st_mtime)


def run_cua(
    task_prompt: str,
    raw_task_dir: Path,
    args: argparse.Namespace,
    env: dict[str, str],
) -> tuple[Path | None, int]:
    raw_task_dir = raw_task_dir.expanduser().resolve()
    raw_task_dir.mkdir(parents=True, exist_ok=True)
    before = child_dirs(raw_task_dir)

    command = [
        args.node_bin,
        args.cua_bin,
        "run",
        task_prompt,
        "--config",
        str(Path(args.cua_config).expanduser().resolve()),
        "--runs-dir",
        str(raw_task_dir),
        "--max-steps",
        str(args.max_steps),
        "--max-images",
        str(args.max_images),
        "--provider",
        args.provider,
        "--base-url",
        args.api_base,
        "--model",
        args.api_model,
        "--no-knowledge",
        "--records-off",
        "--brain-off",
        "--no-prune-after-run",
        "--shell-sh-off",
    ]

    started = int(time.time())
    stdout_path = raw_task_dir / f"cua_stdout_{started}.log"
    stderr_path = raw_task_dir / f"cua_stderr_{started}.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(command, cwd=args.cua_cwd, env=env, stdout=stdout, stderr=stderr, text=True)

    after = child_dirs(raw_task_dir)
    created = after - before
    run_dir = newest_child_dir(raw_task_dir, created) or newest_child_dir(raw_task_dir, after)
    return run_dir, proc.returncode


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def redact(value: str) -> str:
    if not value:
        return ""
    return "<redacted>"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CUA on WebVoyager tasks and convert results.")
    parser.add_argument("--tasks", default="data/tasks_test.jsonl")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-web", default="")
    parser.add_argument("--exclude-web", default="")
    parser.add_argument("--node-bin", default="")
    parser.add_argument("--cua-bin", default="")
    parser.add_argument("--cua-config", default="")
    parser.add_argument("--cua-cwd", default="")
    parser.add_argument("--raw-runs-dir", default="")
    parser.add_argument("--converted-dir", default="")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--max-images", type=int, default=None)
    parser.add_argument("--provider", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--api-model", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--convert-only-run-dir", default="")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--print-config", action="store_true")
    return parser


def finalize_args(args: argparse.Namespace) -> argparse.Namespace:
    load_env_file(args.env_file)

    defaults = {
        "node_bin": env_value("CUA_NODE_BIN", "node"),
        "cua_bin": env_value("CUA_BIN") or env_value("OSWORLD_CUA_BIN") or DEFAULT_CUA_BIN,
        "cua_config": env_value("CUA_CONFIG_PATH") or DEFAULT_CUA_CONFIG,
        "cua_cwd": env_value("CUA_CWD") or env_value("OSWORLD_CUA_REPO_ROOT"),
        "raw_runs_dir": env_value("CUA_RAW_RUNS_DIR") or env_value("OSWORLD_CUA_RUNS_DIR") or "results/cua_raw_runs",
        "converted_dir": env_value("CUA_CONVERTED_DIR", "results/cua_webvoyager"),
        "provider": env_value("CUA_PROVIDER", "openai"),
        "api_key": env_value("DOUBAO_API_KEY") or env_value("OPENAI_API_KEY"),
        "api_base": env_value("DOUBAO_API_URL") or env_value("OPENAI_API_BASE") or env_value("OPENAI_BASE_URL"),
        "api_model": env_value("DOUBAO_API_MODEL") or env_value("OPENAI_API_MODEL"),
        "profile": env_value("CUA_PROFILE", "gui-biased"),
    }
    for key, value in defaults.items():
        if not getattr(args, key):
            setattr(args, key, value)

    args.cua_config = str(Path(args.cua_config).expanduser().resolve())

    if args.max_steps is None:
        args.max_steps = int(env_value("CUA_MAX_STEPS", "15"))
    if args.max_images is None:
        args.max_images = int(env_value("CUA_MAX_IMAGES", "3"))

    if not args.cua_cwd:
        if args.cua_bin:
            cua_bin_path = Path(args.cua_bin).expanduser().resolve()
            args.cua_cwd = str(cua_bin_path.parents[2]) if len(cua_bin_path.parents) >= 3 else str(Path.cwd())
        else:
            args.cua_cwd = str(Path.cwd())

    return args


def validate_args(args: argparse.Namespace, require_api: bool) -> None:
    if require_api:
        if not args.cua_bin or not Path(args.cua_bin).is_file():
            raise FileNotFoundError(f"CUA binary not found: {args.cua_bin}")
        if not Path(args.cua_config).is_file():
            raise FileNotFoundError(f"CUA config not found: {args.cua_config}")
    if args.convert_only_run_dir and not Path(args.convert_only_run_dir).expanduser().exists():
        raise FileNotFoundError(f"CUA run dir not found: {args.convert_only_run_dir}")
    if require_api:
        missing = [name for name in ["api_key", "api_base", "api_model"] if not getattr(args, name)]
        if missing:
            raise ValueError(f"Missing required API settings for CUA run: {', '.join(missing)}")


def main() -> int:
    parser = build_parser()
    args = finalize_args(parser.parse_args())

    convert_only = bool(args.convert_only_run_dir)
    validate_args(args, require_api=not convert_only)

    if args.print_config:
        print(json.dumps({
            "tasks": args.tasks,
            "node_bin": args.node_bin,
            "cua_bin": args.cua_bin,
            "cua_config": args.cua_config,
            "cua_cwd": args.cua_cwd,
            "raw_runs_dir": args.raw_runs_dir,
            "converted_dir": args.converted_dir,
            "max_steps": args.max_steps,
            "max_images": args.max_images,
            "provider": args.provider,
            "api_key": redact(args.api_key),
            "api_base": args.api_base,
            "api_model": args.api_model,
            "profile": args.profile,
            "convert_only_run_dir": args.convert_only_run_dir,
        }, ensure_ascii=False, indent=2))
        if convert_only:
            return 0

    tasks = filter_tasks(
        load_tasks(args.tasks),
        args.start,
        args.limit,
        split_csv(args.include_web),
        split_csv(args.exclude_web),
    )
    if not tasks:
        print("No tasks selected.", file=sys.stderr)
        return 1

    converted_root = Path(args.converted_dir).expanduser().resolve()
    raw_root = Path(args.raw_runs_dir).expanduser().resolve()
    summary_path = converted_root / "summary.jsonl"
    cua_cwd = Path(args.cua_cwd).resolve()
    env = os.environ.copy()
    if args.api_key:
        env["OPENAI_API_KEY"] = args.api_key

    for task in tasks:
        task_id = str(task["id"])
        converted_task_dir = converted_root / safe_task_dir_name(task_id)
        if args.skip_existing and (converted_task_dir / "interact_messages.json").exists():
            continue

        record: dict[str, Any] = {
            "task_id": task_id,
            "web_name": task.get("web_name"),
            "web": task.get("web"),
            "profile": args.profile,
        }

        try:
            if convert_only:
                run_dir = Path(args.convert_only_run_dir).expanduser().resolve()
                returncode = None
            else:
                raw_task_dir = raw_root / safe_task_dir_name(task_id)
                prompt = build_cua_task_prompt(task, args.profile)
                run_dir, returncode = run_cua(prompt, raw_task_dir, args, env)
                record["cua_returncode"] = returncode
                if run_dir is None:
                    raise RuntimeError("CUA did not create a run directory")

            converted = convert_cua_run(task, run_dir, converted_root, cua_cwd)
            record.update(converted)
            record["status"] = "converted"
        except Exception as exc:
            record["status"] = "error"
            record["error"] = str(exc)
            print(f"[ERROR] {task_id}: {exc}", file=sys.stderr)

        append_jsonl(summary_path, record)
        print(json.dumps(record, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
