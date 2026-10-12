"""Command-line interface: `penwise setup`, `penwise check`, `penwise model`, and friends."""

from __future__ import annotations

import argparse
import dataclasses
import json
import platform
import sys
import time

from penwise import __version__, config, engine, history, presets, render, setup_mac, wizard
from penwise.config import ConfigError
from penwise.lessons import LABELS
from penwise.llm import ChatClient, LLMError

FORMATS = ("pretty", "text", "json", "jsonl")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    if not argv and not sys.stdin.isatty():
        argv = ["check"]  # `pbpaste | penwise` just works
    args = parser.parse_args(argv)
    if not args.command:
        if not config.config_path().exists():
            print("Welcome to Penwise! Run `penwise setup` to get started.\n")
        parser.print_help()
        return 0
    try:
        return args.run(args)
    except (ConfigError, LLMError) as exc:
        if getattr(args, "format", None) == "jsonl":
            print(json.dumps({"type": "error", "message": str(exc)}), flush=True)
        print(f"penwise: {exc}", file=sys.stderr)
        return 1
    except EOFError:
        print("\npenwise: this command asks questions, so run it in a terminal.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="penwise",
        description="English writing fixes you can learn from.",
        epilog="Run `penwise <command> --help` for details.",
    )
    parser.add_argument("--version", action="version", version=f"penwise {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("setup", help="guided setup: choose a model, save your key, install the hotkey")
    p.set_defaults(run=cmd_setup)

    p = sub.add_parser("check", help="check a text (argument or stdin) and show each change")
    p.add_argument("text", nargs="*", help="text to check; read from stdin if omitted")
    p.add_argument("-m", "--mode", choices=config.MODES, help="fix: only errors; improve: also clarity and flow")
    p.add_argument(
        "-f", "--format", choices=FORMATS, help="output format (default: pretty in a terminal, text when piped)"
    )
    p.add_argument(
        "--explain", action=argparse.BooleanOptionalAction, default=None, help="ask the model why for each change"
    )
    p.add_argument("--model", help="override the model from the config")
    p.add_argument("--base-url", help="override the API base URL from the config")
    p.set_defaults(run=cmd_check)

    p = sub.add_parser("model", help="show the model in use, or switch to another one")
    p.add_argument("id", nargs="?", help="model to switch to, e.g. mistralai/mistral-small-2603")
    p.add_argument("--no-test", action="store_true", help="switch without testing the model first")
    p.set_defaults(run=cmd_model)

    p = sub.add_parser("config", help="show settings, or change one")
    p.add_argument("action", nargs="?", choices=("show", "set", "unset"), default="show")
    p.add_argument("name", nargs="?", help=f"one of: {', '.join(config.SETTINGS)}")
    p.add_argument("value", nargs="?")
    p.set_defaults(run=cmd_config)

    p = sub.add_parser("insights", help="show the fixes you make most often")
    p.add_argument("-n", "--limit", type=int, default=8, help="how many items to show (default: 8)")
    p.set_defaults(run=cmd_insights)

    p = sub.add_parser("history", help="show where your history is kept, or clear it")
    p.add_argument("--clear", action="store_true", help="delete the history file")
    p.set_defaults(run=cmd_history)

    p = sub.add_parser("doctor", help="check your setup and test the model")
    p.set_defaults(run=cmd_doctor)

    p = sub.add_parser("init", help="write a config file with every setting explained")
    p.add_argument("--force", action="store_true", help="overwrite an existing config file")
    p.set_defaults(run=cmd_init)

    p = sub.add_parser("setup-mac", help="install or update only the hotkey (part of `penwise setup`)")
    p.set_defaults(run=cmd_setup_mac)

    p = sub.add_parser("record", help="save accepted changes (JSON on stdin); used by the Mac panel")
    p.set_defaults(run=cmd_record)
    return parser


def cmd_setup(args: argparse.Namespace) -> int:
    return wizard.run()


def cmd_check(args: argparse.Namespace) -> int:
    cfg = config.load()
    if args.model:
        cfg.model = args.model
    if args.base_url:
        cfg.base_url = args.base_url
    mode = args.mode or cfg.mode
    explain = cfg.explain if args.explain is None else args.explain
    fmt = args.format or ("pretty" if sys.stdout.isatty() else "text")

    text = " ".join(args.text) if args.text else sys.stdin.read()
    if not text.strip():
        raise ConfigError("Nothing to check: pass some text or pipe it in.")

    def emit(event: dict) -> None:
        if fmt == "jsonl":
            print(json.dumps(event), flush=True)

    emit({"type": "start", "mode": mode, "model": cfg.model, "explain": explain})
    client = ChatClient.from_config(cfg)
    result = engine.check(
        text,
        client.chat,
        mode=mode,
        model=cfg.model,
        explain=explain,
        max_chunk_chars=cfg.max_chunk_chars,
        on_event=emit,
        annotate_seen=history.mark_seen if cfg.history else None,
    )
    emit({"type": "done"})

    if fmt == "text":
        sys.stdout.write(result.edited)
    elif fmt == "json":
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    elif fmt == "pretty":
        render.write_pretty(result)
    return 0


def cmd_model(args: argparse.Namespace) -> int:
    cfg = config.load()
    if not args.id:
        print(f"Model: {cfg.model}  ({cfg.base_url})")
        provider = presets.provider_for(cfg.base_url)
        if provider and provider.models:
            print("\nSuggestions:")
            for model in provider.models:
                print(f"  {model.id:<30} {model.blurb}")
        print("\nSwitch with: penwise model <id>")
        return 0

    effort = presets.reasoning_effort_for(args.id)
    if not args.no_test:
        print(f"Testing {args.id}… ", end="", flush=True)
        trial = dataclasses.replace(cfg, model=args.id, reasoning_effort=effort)
        try:
            started = time.monotonic()
            result = engine.check(wizard.TEST_SENTENCE, ChatClient.from_config(trial).chat)
        except LLMError as exc:
            print(f"✗\n{exc}\nStill using {cfg.model}.")
            return 1
        print(f'✓ "{result.edited}" ({time.monotonic() - started:.1f}s)')
    config.set_values({"model": args.id, "reasoning_effort": effort or None})
    print(f"Now using {args.id}.")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    path = config.config_path()
    if args.action == "show":
        cfg = config.load()
        print(f"{path}{'' if path.exists() else ' (not created yet: run `penwise setup`)'}\n")
        for name in config.SETTINGS:
            if name.startswith("api_key"):
                continue
            value = getattr(cfg, name)
            shown = str(value).lower() if isinstance(value, bool) else (value if value != "" else "(default)")
            print(f"  {name:<17} {shown}")
        print(f"  {'api key':<17} {cfg.describe_key()}")
        print("\nChange one with: penwise config set <name> <value>")
        return 0
    if not args.name or (args.action == "set" and args.value is None):
        raise ConfigError(f"Usage: penwise config {args.action} <name>{' <value>' if args.action == 'set' else ''}")
    value = None if args.action == "unset" else config.parse_value(args.name, args.value)
    config.set_values({args.name: value})
    print(f"{args.name} {'reset to default' if value is None else f'= {args.value}'}")
    return 0


def cmd_insights(args: argparse.Namespace) -> int:
    data = history.insights(limit=args.limit)
    if not data["total"]:
        print("No history yet. Accept some changes in the panel, and your patterns will show up here.")
        return 0
    print(f"{data['total']} accepted changes since {data['first'][:10]}\n")
    print("What you fix most:")
    for category, n in data["categories"]:
        print(f"  {n:>4}  {LABELS.get(category, category)}")
    if data["repeated"]:
        print("\nFixes you've made more than once:")
        for pair, n, example in data["repeated"]:
            print(f"  {n:>4}× {pair}")
            if example:
                print(f"         e.g. …{example}…")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    path = history.history_path()
    if args.clear:
        print("History deleted." if history.clear() else "There was no history to delete.")
        return 0
    entries = history.load()
    print(f"{path} ({len(entries)} entries)")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = config.write_template(force=args.force)
    print(f"Created {path}\nEdit it to choose your model, then run `penwise doctor`.")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    cfg = config.load()
    if not cfg.history:
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        raise ConfigError(f"record expects JSON on stdin: {exc}") from exc
    history.record(payload.get("changes", []))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True

    def line(label: str, status: str, good: bool = True) -> None:
        print(f"{'✓' if good else '✗'} {label:<11} {status}")

    path = config.config_path()
    line("Config", f"{path}" if path.exists() else f"{path} (not found, using defaults; run `penwise setup`)")
    try:
        cfg = config.load()
    except ConfigError as exc:
        line("Config", str(exc), good=False)
        return 1
    line("Model", f"{cfg.model} at {cfg.base_url}")
    line("API key", cfg.describe_key())
    line("History", f"{'on' if cfg.history else 'off'} ({history.history_path()})")

    sample = "This sentence have a error."
    try:
        client = ChatClient.from_config(cfg)
        started = time.monotonic()
        result = engine.check(sample, client.chat, mode="fix", model=cfg.model, explain=False)
        seconds = time.monotonic() - started
        line("Test", f'"{sample}" → "{result.edited}" ({seconds:.1f}s)')
    except (ConfigError, LLMError) as exc:
        line("Test", f"{exc}\n              To change settings, run `penwise setup`.", good=False)
        ok = False

    if platform.system() == "Darwin":
        has_app = setup_mac.hammerspoon_installed()
        spoon = (setup_mac.hammerspoon_dir() / "Spoons" / setup_mac.SPOON_NAME).exists()
        line("Hotkey", "installed" if has_app and spoon else "not installed (run `penwise setup`)", has_app and spoon)
        ok = ok and has_app and spoon
    return 0 if ok else 1


def cmd_setup_mac(args: argparse.Namespace) -> int:
    if platform.system() != "Darwin":
        print("The hotkey is for macOS. On other systems, use `penwise check` in the terminal.")
        return 1
    return 0 if wizard.setup_hotkey() else 1


if __name__ == "__main__":
    raise SystemExit(main())
