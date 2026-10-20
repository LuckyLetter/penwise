"""Command-line interface: `penwise setup`, `penwise check`, `penwise model`, and friends."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import os
import platform
import sys
import time

from penwise import (
    __version__,
    config,
    engine,
    history,
    i18n,
    ollama,
    presets,
    render,
    settings,
    setup_mac,
    uninstall,
    updater,
    wizard,
)
from penwise.config import ConfigError
from penwise.i18n import tr
from penwise.llm import ChatClient, LLMError

FORMATS = ("pretty", "text", "json", "jsonl")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    if not argv and not sys.stdin.isatty():
        argv = ["check"]  # `pbpaste | penwise` just works
    args = parser.parse_args(argv)
    with contextlib.suppress(Exception):  # the language chosen in the settings; English till they're read
        i18n.use(config.load().language)
    if not args.command:
        if not config.config_path().exists():
            print("Welcome to Penwise! Run `penwise setup` to get started.\n")
        parser.print_help()
        return 0
    try:
        return args.run(args)
    except (ConfigError, LLMError) as exc:
        link = getattr(exc, "link", None)
        # Whether the settings can fix it (a key, a model, the address); a setting itself always can.
        in_settings = getattr(exc, "in_settings", True)
        if getattr(args, "format", None) == "jsonl":
            event = {"type": "error", "message": str(exc), "in_settings": in_settings}
            print(json.dumps({**event, "link": link} if link else event), flush=True)
        print(f"penwise: {exc}", file=sys.stderr)
        if link:
            print(f"{link['label']}: {link['url']}", file=sys.stderr)
        if isinstance(exc, LLMError) and in_settings:  # the panel has a link to them; here, the command
            print("To change the settings, run `penwise setup`.", file=sys.stderr)
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
    p.add_argument("--style", choices=presets.STYLES, help="tone for improve mode (default: guessed from --app)")
    p.add_argument("--app", default="", help="bundle id of the app the text comes from (set by the Mac panel)")
    p.add_argument("--window", default="", help="title of the window the text comes from (set by the Mac panel)")
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

    p = sub.add_parser("keep", help="words Penwise should never change (names, jargon); list, add or remove")
    p.add_argument("words", nargs="*", help="words to add (or remove, with --remove)")
    p.add_argument("--remove", action="store_true", help="remove the words instead of adding them")
    p.set_defaults(run=cmd_keep)

    p = sub.add_parser("insights", help="show the fixes you make most often")
    p.add_argument("-n", "--limit", type=int, default=8, help="how many items to show (default: 8)")
    p.add_argument("--json", action="store_true", help="answer in JSON (used by the menu bar icon)")
    p.set_defaults(run=cmd_insights)

    p = sub.add_parser("history", help="show where your history is kept, or clear it")
    p.add_argument("--clear", action="store_true", help="delete the history file")
    p.set_defaults(run=cmd_history)

    p = sub.add_parser("settings", help="the settings as JSON, or save them (used by the Mac settings window)")
    p.add_argument("--save", action="store_true", help="save settings given as JSON in $PENWISE_SETTINGS or on stdin")
    p.add_argument("--models", action="store_true", help="the models a service offers (address and key as for --save)")
    p.set_defaults(run=cmd_settings)

    p = sub.add_parser("try", help="open a practice note to try the hotkey on (macOS)")
    p.add_argument("--hotkey", default="", help="the hotkey to name in it, if not ⌃⌥P (e.g. ⌃⌥E)")
    p.set_defaults(run=cmd_try)

    p = sub.add_parser("uninstall", help="remove Penwise: the hotkey, your settings and history, and Penwise itself")
    p.add_argument("--yes", action="store_true", help="don't ask first")
    p.add_argument("--hammerspoon", action="store_true", help="also move Hammerspoon to the Trash")
    p.add_argument("--json", action="store_true", help="say what was removed as JSON")
    p.set_defaults(run=cmd_uninstall)

    p = sub.add_parser("doctor", help="check your setup and test the model")
    p.set_defaults(run=cmd_doctor)

    p = sub.add_parser("update", help="update Penwise to the latest version, hotkey included")
    p.add_argument("--check", action="store_true", help="only say whether an update is available")
    p.add_argument("--json", action="store_true", help="with --check: answer in JSON (used by the menu bar icon)")
    p.set_defaults(run=cmd_update)

    p = sub.add_parser("init", help="write a config file with every setting explained")
    p.add_argument("--force", action="store_true", help="overwrite an existing config file")
    p.set_defaults(run=cmd_init)

    p = sub.add_parser("setup-mac", help="install or update only the hotkey (part of `penwise setup`)")
    p.add_argument("--refresh", action="store_true", help="only update an installed hotkey; ask nothing")
    p.add_argument(
        "--background", action="store_true", help="install without questions, Hammerspoon out of sight (installer)"
    )
    p.set_defaults(run=cmd_setup_mac)

    p = sub.add_parser("record", help="save accepted changes; used by the Mac panel")
    p.add_argument("changes", nargs="?", help="the changes as JSON (default: read from stdin)")
    p.set_defaults(run=cmd_record)
    return parser


def cmd_setup(args: argparse.Namespace) -> int:
    return wizard.run()


def cmd_check(args: argparse.Namespace) -> int:
    cfg = config.load()
    if sys.stderr.isatty():  # in the Terminal, where someone may have just edited the file
        for _, problem in cfg.problems:
            print(f"penwise: {cfg.path}: {problem}; the default is used.", file=sys.stderr)
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

    style = args.style or presets.style_for(args.app, args.window)
    new_here = cfg.history and len(history.load()) < 3  # show the panel's first-time tips
    emit({"type": "start", "mode": mode, "model": cfg.model, "explain": explain, "style": style, "tips": new_here})
    # A model on this Mac, but Ollama was quit, or the Mac just started: start it, then check.
    if ollama.serves(cfg.base_url) and not ollama.running() and ollama.app():
        emit({"type": "status", "text": tr("Starting Ollama…")})
        ollama.start()
        emit({"type": "status", "text": ""})
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
        keep=cfg.keep,
        style=style,
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

    # As Save in the settings window does: what makes the model think less, tried, and kept if it works.
    found = settings.less_thinking_setting(cfg.base_url, args.id)
    if not args.no_test:
        print(f"Testing {args.id}… ", end="", flush=True)
        client = ChatClient.from_config(dataclasses.replace(cfg, model=args.id, less_thinking=found))
        try:
            started = time.monotonic()
            result = engine.check(wizard.TEST_SENTENCE, client.chat)
        except LLMError as exc:
            print(f"✗\n{exc}\nStill using {cfg.model}.")
            return 1
        if client.refused_quicker:
            found["send"] = {}
        print(f'✓ "{result.edited}" ({time.monotonic() - started:.1f}s)')
    config.set_values({"model": args.id, "less_thinking": found})
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
            if isinstance(value, bool):
                shown = str(value).lower()
            elif isinstance(value, dict):  # less_thinking, as Save found it
                shown = json.dumps(value, ensure_ascii=False)
            else:
                shown = value if value != "" else "(default)"
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


def cmd_keep(args: argparse.Namespace) -> int:
    kept = config.load().keep
    if not args.words:
        if kept:
            print("Penwise never changes these words:\n  " + "\n  ".join(kept))
        else:
            print("No words kept yet. Add some with: penwise keep PyTorch ResNet")
        return 0
    if args.remove:
        kept = [word for word in kept if word not in args.words]
    else:
        kept = kept + [word for word in args.words if word not in kept]
    config.set_values({"keep": kept or None})
    action = "No longer keeping" if args.remove else "Keeping"
    print(f"{action}: {', '.join(args.words)}")
    return 0


def cmd_insights(args: argparse.Namespace) -> int:
    data = history.insights(limit=args.limit)
    if args.json:
        print(
            json.dumps(
                {
                    "total": data["total"],
                    "since": (data["first"] or "")[:10],
                    "categories": [
                        {"label": tr(title), "count": n, "note": tr(note), "example": example}
                        for title, note, n, example in data["lessons"]
                    ],
                    "repeated": [{"pair": pair, "count": n, "example": ex} for pair, n, ex in data["repeated"]],
                },
                ensure_ascii=False,
            )
        )
        return 0
    if not data["total"]:
        print("No history yet. Accept some changes in the panel, and your patterns will show up here.")
        return 0
    print(f"{data['total']} accepted changes since {data['first'][:10]}\n")
    print("What you fix most:")
    for title, _, n, example in data["lessons"]:
        print(f"  {n:>4}  {title}" + (f"   e.g. …{example}…" if example else ""))
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


def cmd_settings(args: argparse.Namespace) -> int:
    if not (args.save or args.models):
        print(json.dumps(settings.describe()))
        return 0
    # From the Mac app the settings come in an environment variable: unlike arguments,
    # other users' programs can't see those (the API key is among them).
    raw = os.environ.get("PENWISE_SETTINGS") or sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"settings --save expects JSON: {exc}") from exc
    if args.models:
        print(json.dumps(settings.list_models(request)))
        return 0
    # A line for each step that takes a while (starting Ollama, downloading a model), then the result.
    result = settings.save(request, lambda text: print(json.dumps({"type": "progress", "text": text}), flush=True))
    print(json.dumps(result))
    return 0 if result["ok"] else 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    what = "the hotkey, your settings, API key and history, and Penwise itself"
    if not args.yes and not wizard.confirm(f"Remove {what}?", default=False):
        print("Nothing was removed.")
        return 1
    own_hammerspoon = uninstall.runs_own_hammerspoon()  # Penwise.app's: it goes with it
    removed = uninstall.run(remove_hammerspoon=args.hammerspoon)
    if args.json:
        print(json.dumps({"removed": removed}), flush=True)
    else:
        print(f"✓ Removed {', '.join(removed)}." if removed else "Penwise wasn't installed here.")
        if args.hammerspoon and not any(item.startswith("Hammerspoon") for item in removed):
            print("Hammerspoon is still in Applications: drag it to the Trash if you don't need it.")
    if args.hammerspoon or own_hammerspoon:
        # Last: it may be what started this command. Its own files go once it has quit.
        uninstall.forget_hammerspoon()
        uninstall.quit_hammerspoon()
    else:
        uninstall.forget_penwise_in_hammerspoon()
    return 0


def cmd_try(args: argparse.Namespace) -> int:
    if platform.system() != "Darwin":
        print('The practice note is for the Mac hotkey. Here, try: penwise check "This sentence have a error."')
        return 0
    path = setup_mac.open_practice_note(config.config_path().parent, args.hotkey)
    print(f"Opened {path} in TextEdit. Click in it and press {args.hotkey or 'Control+Option+P'}.")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    cfg = config.load()
    if not cfg.history:
        return 0
    try:
        payload = json.loads((sys.stdin.read() if args.changes is None else args.changes) or "{}")
    except json.JSONDecodeError as exc:
        raise ConfigError(f"record expects JSON: {exc}") from exc
    history.record(payload.get("changes", []))
    return 0


def _settings_hint() -> str:
    """Where to change the settings: Penwise's menu once the hotkey is installed, else the guided setup."""
    if platform.system() == "Darwin" and setup_mac.spoon_installed():
        return tr("open Settings from Penwise in the menu bar")
    return tr("run `penwise setup`")


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True

    def line(label: str, status: str, good: bool = True) -> None:
        print(f"{'✓' if good else '✗'} {label:<11} {status}")

    # Versions first: what someone helping you needs to know.
    mac = platform.mac_ver()[0]
    system = f"macOS {mac}" if mac else platform.platform(terse=True)
    line("Penwise", tr("{version} on {system}", version=__version__, system=system))
    path = config.config_path()
    missing = tr("not found, using defaults; {hint}", hint=_settings_hint())
    line(tr("Config"), f"{path}" if path.exists() else f"{path} ({missing})")
    try:
        cfg = config.load()
    except ConfigError as exc:
        line(tr("Config"), str(exc), good=False)
        return 1
    for _, problem in cfg.problems:
        line(tr("Config"), tr("{problem}: ignored, the default is used", problem=problem), good=False)
    line(tr("Model"), tr("{model} at {address}", model=cfg.model, address=cfg.base_url))
    line(tr("API key"), cfg.describe_key())
    line(tr("History"), f"{tr('on') if cfg.history else tr('off')} ({history.history_path()})")

    sample = "This sentence have a error."
    try:
        client = ChatClient.from_config(cfg)
        started = time.monotonic()
        result = engine.check(sample, client.chat, mode="fix", model=cfg.model, explain=False)
        seconds = time.monotonic() - started
        line(tr("Test"), f'"{sample}" → "{result.edited}" ({seconds:.1f}s)')
    except (ConfigError, LLMError) as exc:
        hint = tr("To change the settings, {hint}.", hint=_settings_hint())
        line(tr("Test"), f"{exc}\n              {hint}", good=False)
        ok = False

    if platform.system() == "Darwin":
        has_app = setup_mac.hammerspoon_installed()
        spoon = setup_mac.spoon_installed()
        version = setup_mac.hammerspoon_version()
        installed = tr("installed (Hammerspoon {version})", version=version) if version else tr("installed")
        state = installed if has_app and spoon else tr("not installed (run `penwise setup`)")
        line(tr("Hotkey"), state, has_app and spoon)
        ok = ok and has_app and spoon
        steps = setup_mac.hotkey_log()
        if steps:
            print("\n" + tr("What the hotkey did lately ({log}; never your text):", log=setup_mac.HOTKEY_LOG))
            print("\n".join(f"  {step}" for step in steps))
    return 0 if ok else 1


def cmd_update(args: argparse.Namespace) -> int:
    if not args.check:
        return updater.run()
    available = updater.check()
    if args.json:
        # in_place: the update needs no Terminal (Penwise.app).
        in_place = updater.install_source()[0] == "app"
        print(json.dumps({"available": bool(available), "detail": available or "", "in_place": in_place}))
    elif available:
        print(f"An update is available ({available}). Get it with: penwise update")
    else:
        print("Penwise is up to date.")
    return 0


def cmd_setup_mac(args: argparse.Namespace) -> int:
    if platform.system() != "Darwin":
        print("The hotkey is for macOS. On other systems, use `penwise check` in the terminal.")
        return 1
    if args.refresh:
        if setup_mac.refresh():
            print("✓ Hotkey updated, and Hammerspoon restarted to load it.")
        return 0
    if args.background:
        try:
            setup_mac.install_quietly()
        except setup_mac.SetupError as exc:
            print(exc, file=sys.stderr)
            return 1
        print("✓ Hotkey installed, and Hammerspoon restarted to load it.")
        return 0
    return 0 if wizard.setup_hotkey() else 1


if __name__ == "__main__":
    raise SystemExit(main())
