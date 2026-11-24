"""Maya AI CLI — command-only interface.

Usage:
    python -m custom.cli chat         — Start interactive chat
    python -m custom.cli config       — Show current settings
    python -m custom.cli wake         — Print wake response
    python -m custom.cli version      — Print version
    python -m custom.cli todo add     — Add a to-do item
    python -m custom.cli reminder set — Set a reminder

Or, with the package installed (``uv run maya ...``):
    uv run maya todo add "Task description"
"""

from importlib import metadata
from pathlib import Path
import time

import click

from .config import load_settings
from .engine.bridge import bridge as engine_bridge
from .persona.loader import list_personas, load_persona
from .tools.assistant import (
    add_todo,
    complete_todo,
    list_reminders,
    list_todos,
    set_reminder,
)
from .tools.chat_history import ChatHistory
from .tools.knowledge import (
    index_documents,
    knowledge_search,
    load_index,
    save_index,
)
from .tools.monitor import (
    get_full_report,
    check_thresholds,
    load_thresholds,
    MonitorAlert,
    monitor_loop,
)
from .tools.security import security as security_manager
from .tools.voice import (
    speak,
    listen,
    listen_mic,
    check_wake,
    wake_reply,
    voice_status,
)
from .tools import voice_clap
from .tools import rag
from .tools import biometrics
from .tools import voice_stt


CONTEXT_SETTINGS = dict(help_option_names=["--help", "-h"])

#: ASCII stand-ins used when the console cannot encode emoji (Windows cp1252).
_ASCII_FALLBACKS = {
    "✅": "[x]",
    "❌": "[ ]",
    "🔔": "*",
    "❤️": "<3",
    "❤": "<3",
    "👋": "!",
}


def _echo(message: object = "", **kwargs: object) -> None:
    """click.echo() that never crashes on non-UTF-8 consoles.

    Windows pipes/terminals often use cp1252, so emoji (✅ ❌ 🔔) raise
    UnicodeEncodeError. Fall back to ASCII replacements instead of crashing.
    """
    text = str(message)
    try:
        click.echo(text, **kwargs)
    except UnicodeEncodeError:
        for symbol, replacement in _ASCII_FALLBACKS.items():
            text = text.replace(symbol, replacement)
        click.echo(text.encode("ascii", "replace").decode("ascii"), **kwargs)


LOCKED_MESSAGE = (
    "Maya is locked.\n"
    "Unlock with one of:\n"
    "  maya security unlock <pin>\n"
    "  maya security unlock --face\n"
    "  maya security unlock --voice"
)


def _asks_for_help(args: list[str]) -> bool:
    """True when -h/--help is used before any literal ``--`` separator."""
    before_separator = args[: args.index("--")] if "--" in args else args
    return any(arg in ("-h", "--help") for arg in before_separator)


class LockedGroup(click.Group):
    """Click group that refuses commands while the Maya session is locked.

    ``locked_allow`` lists the direct subcommands that remain available.
    Nested groups get their own instance, so an allowed group is checked
    again at its own level. Help always works and shows the command list.
    """

    def __init__(self, *args, locked_allow: tuple[str, ...] = (), **kwargs):
        super().__init__(*args, **kwargs)
        self.locked_allow = frozenset(locked_allow)

    def invoke(self, ctx: click.Context):
        args = [*ctx._protected_args, *ctx.args]
        if args and not _asks_for_help(args):
            security_manager.reload()
            if security_manager.is_session_locked() and args[0] not in self.locked_allow:
                raise click.ClickException(LOCKED_MESSAGE)
        return super().invoke(ctx)


@click.group(cls=LockedGroup, locked_allow=("security", "biometrics", "lock", "version"),
             context_settings=CONTEXT_SETTINGS)
def main() -> None:
    """Maya AI — your local personal assistant."""
    pass


@main.command()
def config() -> None:
    """Show current Maya settings from settings.yaml."""
    settings = load_settings()
    _echo("Maya AI Settings:")
    _echo("=" * 40)
    for key, value in settings.items():
        _echo(f"  {key}: {value}")
    _echo("=" * 40)


@main.command()
def wake() -> None:
    """Print Maya's wake response."""
    _echo("Sollu da, enna venum?")


@main.command()
def version() -> None:
    """Print Maya version."""
    try:
        ver = metadata.version("maya-custom")
    except Exception:
        ver = "0.1.0"
    _echo(f"Maya AI version {ver}")


@main.command()
@click.argument("persona", required=False)
@click.option("--classic", is_flag=True, help="Use the raw engine chat (no intelligence layer).")
def chat(persona: str | None = None, classic: bool = False) -> None:
    """Start interactive chat with Maya.

    Usage: maya chat [persona] [--classic]
    Personas: girlfriend, english_teacher
    """
    security_manager.reload()
    if security_manager.is_session_locked():
        raise click.ClickException(LOCKED_MESSAGE)

    history = ChatHistory()

    # Optional CLI argument to start with a specific persona
    if persona:
        available = list_personas()
        if persona not in available:
            _echo(f"Unknown persona: {persona}")
            _echo(f"Available: {', '.join(available)}")
            return
        history.set_persona(persona)
        _echo(f"Persona switched to: {persona}")

    persona_name = history.persona
    persona_prompt = load_persona(persona_name) or ""
    available = list_personas()

    # Intelligence layer (MAYA INTELLIGENCE). Falls back to classic chat.
    bridge = None
    if not classic:
        from .intelligence_bridge import IntelligenceBridge

        candidate = IntelligenceBridge()
        if candidate.available:
            bridge = candidate
            bridge.set_persona(persona_prompt)
        else:
            _echo("Intelligence layer unavailable - using classic chat.")
            if candidate.init_error:
                _echo(f"  ({candidate.init_error})")
            candidate.close()

    if bridge is None:
        # Classic path: inject persona as system message
        if persona_prompt:
            history.set_system(persona_prompt)

    _echo("\n--- Maya AI Chat ---")
    _echo(f"Persona: {persona_name}")
    _echo(f"Available: {', '.join(available)}")
    _echo(f"Mode: {'classic' if bridge is None else 'intelligent'}")
    _echo("Commands: /quit, /clear, /persona <name>")
    _echo()

    try:
        while True:
            try:
                user_input = input("You> ").strip()
            except (EOFError, KeyboardInterrupt):
                _echo("\nGoodbye!")
                break

            if not user_input:
                continue

            cmd = user_input.lower()

            # Handle commands
            if cmd in ("/quit", "/exit", "/q"):
                _echo("Goodbye!")
                break
            elif cmd == "/clear":
                if bridge is not None:
                    bridge.clear()
                history.messages = []
                if persona_prompt:
                    history.set_system(persona_prompt)
                _echo("History cleared.")
                continue
            elif cmd.startswith("/persona"):
                parts = cmd.split(None, 1)
                if len(parts) == 2:
                    new_persona = parts[1].strip()
                    if new_persona in available:
                        new_prompt = load_persona(new_persona) or ""
                        history.set_persona(new_persona)
                        if new_prompt:
                            history.set_system(new_prompt)
                        if bridge is not None:
                            bridge.set_persona(new_prompt)
                        persona_name = new_persona
                        persona_prompt = new_prompt
                        _echo(f"Persona switched to: {persona_name}")
                    else:
                        _echo(f"Unknown persona: {new_persona}")
                        _echo(f"Available: {', '.join(available)}")
                else:
                    _echo(f"Current persona: {persona_name}")
                    _echo(f"Available: {', '.join(available)}")
                continue

            if bridge is not None:
                reply = bridge.chat(user_input)
                _echo(f"\nMaya: {reply}\n")
                continue

            # Classic path
            history.add_user(user_input)
            messages = history.get_messages()
            reply = engine_bridge.chat(messages)

            # Add assistant message (skip saving error replies)
            if not reply.startswith("[engine error]"):
                history.add_assistant(reply)

            _echo(f"\nMaya: {reply}\n")

            # Keep history manageable
            history.trim(keep=19)
    finally:
        if bridge is not None:
            bridge.close()


@main.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option("--persona", "persona_name", default=None, help="Persona to use for this reply.")
@click.option("--classic", is_flag=True, help="Use the raw engine chat (no intelligence layer).")
def ask(
    prompt: tuple[str, ...],
    persona_name: str | None = None,
    classic: bool = False,
) -> None:
    """Ask Maya one question and print the answer.

    Usage: maya ask "What is 17 * 24?"
    """
    security_manager.reload()
    if security_manager.is_session_locked():
        raise click.ClickException(LOCKED_MESSAGE)

    text = " ".join(prompt).strip()
    if not text:
        _echo('Usage: maya ask "your question"')
        return

    history = ChatHistory()
    selected = persona_name or history.persona
    persona_prompt = load_persona(selected) or ""

    def classic_reply() -> str:
        messages = []
        if persona_prompt:
            messages.append({"role": "system", "content": persona_prompt})
        messages.append({"role": "user", "content": text})
        return engine_bridge.chat(messages)

    if classic:
        _echo(classic_reply())
        return

    from .intelligence_bridge import IntelligenceBridge

    bridge = IntelligenceBridge()
    try:
        if not bridge.available:
            _echo(f"Intelligence layer unavailable ({bridge.init_error}). Using classic chat.")
            _echo(classic_reply())
            return
        if persona_prompt:
            bridge.set_persona(persona_prompt)
        _echo(bridge.chat(text))
    finally:
        bridge.close()


@main.group()
def todo() -> None:
    """To-do list management."""


@todo.command()
@click.argument("task", required=False)
def add(task: str | None = None) -> None:
    """Add a to-do item.

    Usage: maya todo add "Task description"
    """
    if not task:
        _echo('Usage: maya todo add "Task description"')
        return
    _echo(add_todo(task))


@todo.command(name="list")
def todo_list() -> None:
    """List all to-do items."""
    for i, t in enumerate(list_todos(), 1):
        status = "✅" if t["done"] else "❌"
        _echo(f"  {i}. {status} {t['task']}")


@todo.command()
@click.argument("index", type=int)
def complete(index: int) -> None:
    """Complete a to-do item by index (1-based)."""
    _echo(complete_todo(index))


@main.group()
def reminder() -> None:
    """Reminder management."""


@reminder.command(name="set")
@click.argument("time")
@click.argument("text")
def set_reminder_cmd(time: str, text: str) -> None:
    """Set a reminder.

    Usage: maya reminder set "09:00" "Drink water"
    """
    _echo(set_reminder(text, time))


@reminder.command(name="list")
def reminder_list() -> None:
    """List all reminders."""
    for r in list_reminders():
        _echo(f"  🔔 {r['time']}: {r['text']}")


@main.group()
def devices() -> None:
    """Multi-device connection management."""


@devices.command()
def status() -> None:
    """List connected and discoverable devices."""
    from .tools.devices import get_device_status_summary

    _echo(f"Device Status: {get_device_status_summary()}")


@devices.command(name="pair")
@click.argument("name")
@click.option(
    "--code", default=None,
    help="Shared code (16+ chars). Exposes the code in shell history; prefer --ask-code.",
)
@click.option("--ask-code", is_flag=True, help="Prompt for the code with hidden input.")
def devices_pair(name: str, code: str | None, ask_code: bool) -> None:
    """Pair a trusted device (stores only a salted code hash)."""
    from .tools.devices import pair_device

    if ask_code and code is not None:
        raise click.UsageError("Use either --code or --ask-code, not both.")
    if ask_code:
        code = click.prompt("Pairing code", hide_input=True, confirmation_prompt=True)
    result = pair_device(name, code)
    if not result["ok"]:
        raise click.ClickException(result["error"])
    _echo(f"Paired device: {result['name']} (id {result['id']})")
    if result.get("generated"):
        _echo(f"Pairing code (shown once, not stored): {result['code']}")
        _echo("Use the same code on the other device to import its bundles.")


@devices.command(name="list")
def devices_list() -> None:
    """List paired devices (never shows codes)."""
    from .tools.devices import list_paired_devices

    paired = list_paired_devices()
    if not paired:
        _echo("No paired devices. Use: maya devices pair <name>")
        return
    _echo("Paired devices:")
    for device in paired:
        last = (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(device["last_sync"]))
            if device.get("last_sync")
            else "never"
        )
        _echo(f"  {device['name']}  id={device['id']}  last sync: {last}")


@devices.command(name="revoke")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Skip the confirmation.")
def devices_revoke(name: str, yes: bool) -> None:
    """Remove a paired device; old bundles stop importing."""
    from .tools.devices import revoke_device

    if not yes:
        click.confirm(f"Revoke paired device '{name}'?", abort=True)
    result = revoke_device(name)
    if not result["ok"]:
        raise click.ClickException(result["error"])
    _echo(f"Revoked device: {result['name']}")


@devices.command(name="export")
@click.argument("name")
@click.option(
    "--source", "sources", multiple=True, required=True,
    type=click.Path(exists=True), help="File or folder to include (repeatable).",
)
@click.option("--out", "out_path", required=True, type=click.Path(), help="Bundle file to write.")
@click.option("--code", default=None, help="Pairing code (prompted when omitted).")
@click.option(
    "--allow-sensitive", is_flag=True,
    help="Allow .env / security stores / DEVARAJ (dangerous).",
)
def devices_export(
    name: str, sources, out_path: str, code: str | None, allow_sensitive: bool
) -> None:
    """Write an HMAC-signed bundle for a paired device."""
    from .tools.devices import export_bundle

    if code is None:
        code = click.prompt("Pairing code", hide_input=True)
    result = export_bundle(
        name, code, list(sources), out_path, allow_sensitive=allow_sensitive
    )
    if not result["ok"]:
        raise click.ClickException(result["error"])
    size = result["bytes"] / 1024
    _echo(f"Bundle written: {result['out']}")
    _echo(f"  device: {result['device']}  files: {result['files']}  size: {size:.1f} KB")
    _echo("  Note: signed, not encrypted. Transfer it over a trusted path.")


@devices.command(name="import")
@click.argument("bundle_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--dest", "dest_dir", required=True, type=click.Path(), help="Folder to extract into.")
@click.option("--code", default=None, help="Pairing code (prompted when omitted).")
@click.option("--overwrite", is_flag=True, help="Replace files that already exist.")
def devices_import(
    bundle_path: str, dest_dir: str, code: str | None, overwrite: bool
) -> None:
    """Verify a signed bundle and extract it (explicit destination only)."""
    from .tools.devices import import_bundle

    if code is None:
        code = click.prompt("Pairing code", hide_input=True)
    result = import_bundle(bundle_path, dest_dir, code, overwrite=overwrite)
    if not result["ok"]:
        raise click.ClickException(result["error"])
    size = result["bytes"] / 1024
    _echo(f"Imported {result['files']} file(s) into {result['dest']} ({size:.1f} KB)")
    _echo(f"  from paired device: {result['device']}")


@devices.command(name="send")
@click.argument("bundle_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--host", required=True, help="Receiver IP address.")
@click.option("--port", default=8765, show_default=True, type=int, help="Receiver port.")
@click.option("--timeout", default=60.0, show_default=True, type=float, help="Network timeout (s).")
def devices_send(bundle_path: str, host: str, port: int, timeout: float) -> None:
    """Send a signed bundle over the LAN (Wi-Fi/USB-tether/BT-PAN)."""
    from .tools.transport import send_bundle

    result = send_bundle(bundle_path, host, port=port, timeout=timeout)
    if not result.get("ok"):
        raise click.ClickException(result.get("error", "send failed"))
    _echo(f"Sent {result.get('bytes', 0)} bytes to {host}:{port}")


@devices.command(name="receive")
@click.option("--out", "dest_dir", required=True, type=click.Path(), help="Folder to extract into.")
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind address.")
@click.option("--port", default=8765, show_default=True, type=int, help="Listen port.")
@click.option("--timeout", default=120.0, show_default=True, type=float, help="Wait timeout (s).")
@click.option("--allow-public", is_flag=True, help="Accept non-private (public) clients.")
def devices_receive(
    dest_dir: str, host: str, port: int, timeout: float, allow_public: bool
) -> None:
    """Receive one signed bundle over the LAN and import it."""
    from .tools.transport import receive_once

    code = click.prompt("Pairing code", hide_input=True)
    _echo(f"Listening on {host}:{port} for up to {int(timeout)}s...")
    result = receive_once(
        code, dest_dir, host=host, port=port, timeout=timeout, allow_public=allow_public
    )
    if not result.get("ok"):
        raise click.ClickException(result.get("error", "receive failed"))
    size = int(result.get("bytes", 0)) / 1024
    _echo(f"Imported {result.get('files', 0)} file(s) into {result.get('dest')} ({size:.1f} KB)")
    _echo(f"  from paired device: {result.get('device')}")


@devices.command()
def android() -> None:
    """Check Android device connection status."""
    from .tools.devices import check_adb_available, get_connected_androids

    adb_available = check_adb_available()
    androids = get_connected_androids()

    _echo(f"ADB Available: {'Yes' if adb_available else 'No'}")

    if androids:
        for device in androids:
            if isinstance(device, dict):
                serial = device.get("serial", "unknown")
                device_status = device.get("status", "unknown")
                _echo(f"Android [{serial}]: {device_status}")
            else:
                _echo(device)
    else:
        _echo("No Android devices connected.")


@devices.command()
@click.argument("ssid", required=False, default="")
@click.argument("password", required=False, default="")
def wifi(ssid: str, password: str) -> None:
    """Test Wi-Fi connection.

    Usage: maya devices wifi "MyNetwork" "password123"
    """
    from .tools.devices import test_wifi_connection, validate_wifi_credentials

    if not ssid or not password:
        _echo('Usage: maya devices wifi "SSID" "PASSWORD"')
        _echo("Or run without args to see available networks (limited).")
        return

    # Validate credentials
    validated = validate_wifi_credentials(ssid, password)
    _echo(f"SSID: {validated['ssid']}")
    masked = "*" * len(validated["password"]) if validated["password"] else "(none)"
    _echo(f"Password: {masked}")
    _echo(f"Credentials valid: {validated['valid']}")

    # Test connection
    if validated["valid"]:
        result = test_wifi_connection(ssid, password)
        if result["success"]:
            _echo(f"✅ Wi-Fi connected: {ssid}")
        else:
            error = result.get("error", "unknown error")
            _echo(f"❌ Wi-Fi connection failed: {error}")
    else:
        _echo("❌ Please provide both SSID and password.")


@devices.command()
@click.argument("source")
@click.argument("dest")
@click.argument("remote", required=False, default="")
def sync(source: str, dest: str, remote: str) -> None:
    """Sync files between devices.

    Usage: maya devices sync "local_file.txt" "remote_file.txt" [remote_host]
    """
    from .tools.devices import sync_file_between_devices

    # Remote host provided -> remote sync; otherwise local copy.
    result = sync_file_between_devices(source, dest, remote)

    _echo(f"Sync type: {result.get('sync_type', 'unknown')}")
    _echo(f"Status: {result.get('status', 'unknown')}")
    if "note" in result:
        _echo(f"Note: {result['note']}")
    if "error" in result:
        _echo(f"Error: {result['error']}")


@devices.command()
def remote() -> None:
    """Check remote access status."""
    from .tools.devices import check_remote_access_allowed

    remote_status = check_remote_access_allowed()
    if remote_status["remote_access"]:
        _echo(f"Remote access enabled: {remote_status['note']}")
    else:
        _echo(f"❌ Remote access disabled: {remote_status['note']}")
        _echo("   Configure SSH or OpenJarvis settings to enable.")


@main.group()
def monitor() -> None:
    """System monitoring: status, thresholds, background loop."""


@monitor.command(name="status")
def monitor_status() -> None:
    """Show full system status report."""
    _echo(get_full_report())


@monitor.command(name="alerts")
def monitor_alerts() -> None:
    """Check current threshold breaches and show alerts."""
    thresholds = load_thresholds()
    alerts = check_thresholds(thresholds)
    if not alerts:
        _echo("All systems normal. No alerts.")
        return
    _echo(f"Threshold Alerts ({len(alerts)}):")
    for a in alerts:
        _echo(f"  {a}")


@monitor.command(name="thresholds")
def monitor_thresholds() -> None:
    """Show current monitor thresholds."""
    thresholds = load_thresholds()
    _echo("Monitor Thresholds:")
    for key, value in thresholds.items():
        _echo(f"  {key}: {value}")


@monitor.command(name="start")
def monitor_start() -> None:
    """Start the background monitor loop (prints alerts as they fire)."""

    def _on_alert(alert: MonitorAlert) -> None:
        _echo(str(alert))

    monitor_loop.on_alert = _on_alert
    monitor_loop.start()
    _echo(f"Monitor loop started (interval: {monitor_loop.interval}s).")
    _echo("Press Ctrl+C to stop.")
    try:
        while monitor_loop.running:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor_loop.stop()
        _echo("Monitor loop stopped.")


@monitor.command(name="stop")
def monitor_stop() -> None:
    """Stop the background monitor loop."""
    monitor_loop.stop()
    _echo("Monitor loop stopped.")


@main.group(cls=LockedGroup, locked_allow=("unlock", "status"))
def security() -> None:
    """Security: PIN lock/unlock, status, backup code."""


@security.command(name="set-pin")
@click.argument("pin")
@click.option("--old-pin", default=None, help="Current PIN, needed to change it.")
def security_set_pin(pin: str, old_pin: str | None = None) -> None:
    """Set the Maya PIN lock.

    Usage: maya security set-pin 1234
    Change: maya security set-pin 5678 --old-pin 1234
    """
    _echo(security_manager.set_pin(pin, old_pin))


@security.command(name="unlock")
@click.argument("pin", required=False)
@click.option("--face", "use_face", is_flag=True, help="Unlock with Windows Hello face.")
@click.option("--voice", "use_voice", is_flag=True, help="Unlock with your spoken phrase + voiceprint.")
@click.option("--wav", "wav_file", default=None, help="Voice: verify a WAV file instead of the mic.")
@click.option("--seconds", default=5, show_default=True, help="Voice: microphone seconds.")
@click.option("--timeout", default=60, show_default=True, help="Face: prompt timeout.")
def security_unlock(
    pin: str | None,
    use_face: bool,
    use_voice: bool,
    wav_file: str | None,
    seconds: int,
    timeout: int,
) -> None:
    """Unlock Maya with PIN, Windows Hello face or voice.

    Usage:
      maya security unlock 1234
      maya security unlock --face
      maya security unlock --voice
    """
    security_manager.reload()
    if not security_manager.is_locked():
        _echo("No PIN set. Use 'maya security set-pin <pin>' first.")
        raise SystemExit(1)
    if use_face and use_voice:
        raise click.ClickException("Choose one method: --face or --voice.")
    if pin is not None and (use_face or use_voice):
        raise click.ClickException("Give a PIN or a biometric option, not both.")
    if wav_file and not use_voice:
        raise click.ClickException("--wav is only valid with --voice.")

    if not security_manager.is_session_locked():
        _echo("Maya is already unlocked.")
        return

    if use_face:
        _echo("Windows Hello prompt is open - look at the camera.")
        result = biometrics.face_verify(timeout)
        if not result["ok"]:
            security_manager.record_unauthorized("Face unlock failed")
            raise click.ClickException(f"Face not verified: {result['error']}")
        security_manager.reload()
        _echo(security_manager.unlock("face"))
        return

    if use_voice:
        if wav_file and not Path(wav_file).is_file():
            raise click.ClickException(f"File not found: {wav_file}")
        result = _voice_attempt(wav_file=wav_file, seconds=seconds)
        if not result["ok"]:
            security_manager.record_unauthorized("Voice unlock failed")
            raise click.ClickException(f"Voice not verified: {result['error']}")
        security_manager.reload()
        _echo(security_manager.unlock("voice"))
        return

    if pin is None:
        raise click.ClickException("Give a PIN, or use --face / --voice.")

    _echo(security_manager.verify_pin(pin))


@security.command(name="status")
def security_status() -> None:
    """Show security status (no secrets exposed)."""
    security_manager.reload()
    st = security_manager.status()
    _echo("Security Status:")
    _echo(f"  PIN set: {st['pin_set']}")
    _echo(f"  Session locked: {st['session_locked']}")
    last = st.get("last_unlock")
    if last:
        when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last["time"]))
        _echo(f"  Last unlock: {last['method']} at {when}")
    else:
        _echo("  Last unlock: never")
    _echo(f"  Failed attempts: {st['failed_attempts']}")
    _echo(f"  Locked out: {st['locked_out']}")
    _echo(f"  Backup code set: {st['backup_code_set']}")
    _echo(f"  Unauthorized alerts: {st['unauthorized_alerts']}")


@security.command(name="alerts")
def security_alerts() -> None:
    """Show unauthorized access alerts."""
    alerts = security_manager.get_unauthorized_alerts()
    if not alerts:
        _echo("No unauthorized access alerts.")
        return
    _echo(f"Unauthorized Access Alerts ({len(alerts)}):")
    for a in alerts:
        _echo(f"  {a['timestamp']} — {a['detail']}")


@security.command(name="watchdog")
@click.option(
    "--idle-minutes", type=float, default=None,
    help="Lock after N minutes without input (0 disables).",
)
@click.option(
    "--max-session-minutes", type=float, default=None,
    help="Lock N minutes after the last unlock (0 disables).",
)
@click.option(
    "--voice-every", type=float, default=None,
    help="Ask for the voice phrase every N minutes (0 disables).",
)
@click.option(
    "--check-seconds", type=float, default=None,
    help="Seconds between checks (default: settings.yaml).",
)
@click.option("--voice-seconds", type=int, default=None, help="Mic seconds per voice check.")
@click.option("--once", is_flag=True, help="Run one check and exit.")
def security_watchdog(
    idle_minutes: float | None,
    max_session_minutes: float | None,
    voice_every: float | None,
    check_seconds: float | None,
    voice_seconds: int | None,
    once: bool,
) -> None:
    """Lock Maya when the session is idle, expired or re-check fails.

    Everything is local and command-driven: Maya never starts this by itself.
    """
    from .tools.watchdog import SessionWatchdog, watchdog_config

    cfg = watchdog_config(
        {
            "idle_lock_minutes": idle_minutes,
            "max_session_minutes": max_session_minutes,
            "voice_check_minutes": voice_every,
            "check_seconds": check_seconds,
            "voice_seconds": voice_seconds,
        }
    )
    dog = SessionWatchdog(manager=security_manager, cfg=cfg)

    def _show(result: dict) -> None:
        stamp = time.strftime("%H:%M:%S")
        if result["action"] == "locked":
            _echo(f"[{stamp}] {result['message']}")
        elif result["action"] == "skipped":
            _echo(f"[{stamp}] Voice check skipped: {result['error']}")
        elif result["action"] == "voice_ok":
            _echo(f"[{stamp}] Voice re-check passed.")

    if once:
        result = dog.tick()
        if result["action"] == "locked":
            _echo(result["message"])
            _echo("Watchdog stopped. Unlock Maya, then start it again.")
        elif result["action"] == "idle":
            _echo(result["message"])
        elif result["action"] == "skipped":
            _echo(f"Voice check skipped: {result['error']}")
        elif result["action"] == "voice_ok":
            _echo("Voice re-check passed.")
        else:
            _echo("No action needed.")
        return

    _echo(f"Watchdog: {dog.summary()}")
    if not dog.idle_available():
        _echo("  Warning: idle detection is unavailable here; idle lock is inactive.")
    _echo("Press Ctrl+C to stop. Maya never starts this by itself.")
    try:
        while True:
            result = dog.tick()
            if result["action"] == "locked":
                _show(result)
                _echo("Watchdog stopped. Unlock Maya, then start it again.")
                break
            if result["action"] == "idle":
                _echo(result["message"])
                _echo("Watchdog stopped.")
                break
            _show(result)
            time.sleep(cfg["check_seconds"])
    except KeyboardInterrupt:
        _echo("\nWatchdog stopped.")


@security.command(name="backup-code")
@click.argument("code")
def security_backup_code(code: str) -> None:
    """Set a backup unlock code (emergency access).

    Usage: maya security backup-code <code>
    """
    _echo(security_manager.set_backup_unlock_code(code))


@main.command()
def lock() -> None:
    """Lock Maya (requires PIN to unlock)."""
    security_manager.reload()
    _echo(security_manager.lock())


def _unlock_session(method: str) -> None:
    """Open the Maya session after a factor has already been verified."""
    security_manager.reload()
    if not security_manager.is_locked():
        _echo("No PIN set - nothing to unlock.")
        return
    _echo(security_manager.unlock(method))


def _voice_attempt(
    wav_file: str | None = None,
    text: str | None = None,
    seconds: int = 5,
) -> dict:
    """Run one local voice check (mic, WAV, or phrase-only diagnostic)."""
    if text is not None and not wav_file:
        _echo("[diagnostic] phrase-only check - the voiceprint is not used.")
        return biometrics.voice_verify(text, enforce_speaker=False)
    if wav_file:
        if not Path(wav_file).is_file():
            raise click.ClickException(f"File not found: {wav_file}")
        transcript = biometrics.transcribe_wav(wav_file)
        try:
            vector = biometrics.speaker_vector(wav_file)
        except RuntimeError as exc:
            raise click.ClickException(str(exc))
        return biometrics.voice_verify(transcript, vector)

    _echo(f"Speak now ({seconds}s) ...")
    try:
        wav, peak = voice_stt.record(seconds)
    except Exception as exc:
        raise click.ClickException(f"Microphone error: {exc}")
    try:
        if peak < voice_stt.SILENCE_PEAK:
            raise click.ClickException(f"No mic signal (peak {peak}).")
        transcript = biometrics.transcribe_wav(wav)
        try:
            vector = biometrics.speaker_vector(wav)
        except RuntimeError:
            vector = None
    finally:
        Path(wav).unlink(missing_ok=True)
    return biometrics.voice_verify(transcript, vector)


@main.group(
    name="biometrics",
    cls=LockedGroup,
    locked_allow=("status", "face-check", "face-verify", "face-settings", "voice-verify"),
)
def biometrics_group() -> None:
    """Biometrics: Windows Hello face + local voice verification."""


@biometrics_group.command(name="status")
@click.option("--no-face", is_flag=True, help="Skip the Windows Hello probe.")
def biometrics_status(no_face: bool) -> None:
    """Show face + voice biometric status (no secrets)."""
    st = biometrics.status(face=not no_face)
    face = st["face"]
    _echo("Biometrics Status:")
    if no_face:
        _echo("  face: (skipped)")
    elif face.get("available"):
        _echo("  face: available (Windows Hello)")
    else:
        _echo(f"  face: {face.get('code')} - {face.get('error')}")
    voice = st["voice"]
    _echo(f"  voice enrolled: {voice['enrolled']} ({voice['variants']} phrase variant(s))")
    _echo(f"  voiceprint: {'yes' if voice['speaker'] else 'no'} (threshold {voice['threshold']})")
    _echo(f"  require speaker: {st['require_speaker']}")
    _echo(f"  speaker model: {'found' if st['speaker_model'] else 'missing'}")
    if voice["locked"]:
        _echo(f"  locked: yes ({voice['remaining']}s)")
    _echo(f"  store: {st['store']}")


@biometrics_group.command(name="face-check")
@click.option("--force", is_flag=True, help="Ignore the 30 s cache.")
def biometrics_face_check(force: bool) -> None:
    """Check whether Windows Hello face is available (no prompt)."""
    st = biometrics.face_status(force=force)
    if st["available"]:
        _echo("Windows Hello face: available")
    else:
        _echo(f"Windows Hello face: {st['code']} - {st['error']}")


@biometrics_group.command(name="face-verify")
@click.option("--timeout", default=60, show_default=True, help="Seconds to wait.")
@click.option("--unlock", "do_unlock", is_flag=True, help="Unlock the Maya session on success.")
def biometrics_face_verify(timeout: int, do_unlock: bool) -> None:
    """Show the Windows Hello prompt and verify your face."""
    _echo("Windows Hello prompt is open - look at the camera.")
    st = biometrics.face_verify(timeout)
    if st["ok"]:
        _echo("Face verified.")
        if do_unlock:
            _unlock_session("face")
    else:
        _echo(f"Face not verified: {st['error']}")
        if do_unlock:
            security_manager.reload()
            if security_manager.is_session_locked():
                security_manager.record_unauthorized("Face unlock failed")


@biometrics_group.command(name="face-settings")
def biometrics_face_settings() -> None:
    """Open Windows Sign-in options to enroll/improve face sign-in."""
    st = biometrics.open_face_settings()
    if st["ok"]:
        _echo("Opened Windows Sign-in options.")
    else:
        _echo(f"Could not open Settings: {st['error']}")


@biometrics_group.command(name="voice-enroll")
@click.option("--samples", default=None, type=int, help="Samples to record (default: settings).")
@click.option("--seconds", default=5, show_default=True, help="Seconds per sample.")
@click.option("--wav", "wavs", multiple=True, help="WAV file(s) instead of the mic.")
def biometrics_voice_enroll(samples: int | None, seconds: int, wavs) -> None:
    """Enroll a spoken phrase + voiceprint (stored locally as hash/vector)."""
    samples = samples or biometrics.default_samples()
    transcripts: list[str] = []
    vectors: list[list[float]] = []

    if wavs:
        if len(wavs) < 2:
            raise click.ClickException("Give at least two --wav samples.")
        for path in wavs:
            if not Path(path).is_file():
                raise click.ClickException(f"File not found: {path}")
            _echo(f"Reading {Path(path).name} ...")
            transcripts.append(biometrics.transcribe_wav(path))
            try:
                vectors.append(biometrics.speaker_vector(path))
            except RuntimeError as exc:
                raise click.ClickException(str(exc))
    else:
        _echo(f"Say the SAME short phrase {samples} times (2-14 words).")
        _echo("Example: 'maya open the door'.")
        for index in range(1, samples + 1):
            click.prompt(
                f"Sample {index}/{samples} - press Enter, then speak",
                default="",
                show_default=False,
            )
            try:
                wav, peak = voice_stt.record(seconds)
            except Exception as exc:
                raise click.ClickException(f"Microphone error: {exc}")
            try:
                if peak < voice_stt.SILENCE_PEAK:
                    raise click.ClickException(f"No mic signal (peak {peak}).")
                transcript = biometrics.transcribe_wav(wav)
                vector = biometrics.speaker_vector(wav)
            except RuntimeError as exc:
                raise click.ClickException(str(exc))
            finally:
                Path(wav).unlink(missing_ok=True)
            _echo(f"  heard {len(transcript.split())} word(s)")
            transcripts.append(transcript)
            vectors.append(vector)

    result = biometrics.voice_enroll(transcripts, vectors)
    if not result["ok"]:
        raise click.ClickException(result["error"])
    _echo(
        f"Voice enrolled: {result['variants']} phrase variant(s); "
        f"voiceprint: {'yes' if result['speaker'] else 'no'} "
        f"({result.get('dim', 0)}-dim)"
    )


@biometrics_group.command(name="voice-verify")
@click.option("--wav", "wav_file", default=None, help="Verify a WAV file instead of the mic.")
@click.option("--text", "text", default=None, help="Diagnostic: phrase only, no audio.")
@click.option("--seconds", default=5, show_default=True, help="Mic seconds.")
@click.option("--explain", is_flag=True, help="Show which factor failed.")
@click.option("--unlock", "do_unlock", is_flag=True, help="Unlock the Maya session on success.")
def biometrics_voice_verify(wav_file, text, seconds: int, explain: bool, do_unlock: bool) -> None:
    """Verify your spoken phrase and voiceprint."""
    if do_unlock and text is not None and not wav_file:
        raise click.ClickException(
            "--text is a diagnostic phrase check and cannot unlock Maya."
        )

    result = _voice_attempt(wav_file=wav_file, text=text, seconds=seconds)

    if result["ok"]:
        _echo("Voice verified.")
        if result.get("speaker_score") is not None:
            _echo(f"  speaker similarity: {result['speaker_score']:.3f}")
        if do_unlock:
            _unlock_session("voice")
        return

    _echo(f"Voice not verified: {result['error']}")
    if explain:
        _echo(f"  phrase match: {result.get('passphrase_ok')}")
        score = result.get("speaker_score")
        _echo(f"  speaker similarity: {'n/a' if score is None else f'{score:.3f}'}")
    if do_unlock:
        security_manager.reload()
        if security_manager.is_session_locked():
            security_manager.record_unauthorized("Voice unlock failed")


@biometrics_group.command(name="voice-reset")
@click.option("--yes", is_flag=True, help="Skip the confirmation.")
def biometrics_voice_reset(yes: bool) -> None:
    """Delete the enrolled voice phrase and voiceprint."""
    if not yes:
        click.confirm("Delete the voice phrase and voiceprint?", abort=True)
    result = biometrics.voice_reset()
    if result["ok"]:
        _echo("Voice biometric data deleted.")
    else:
        _echo(f"Error: {result['error']}")


@main.group()
def knowledge() -> None:
    """Knowledge base: index a folder, search its content (local only)."""


@knowledge.command(name="index")
@click.argument("folder", default=".")
def knowledge_index(folder: str) -> None:
    """Index .pdf / .txt / .md files under FOLDER and save the index."""
    index = index_documents(folder)
    if "error" in index:
        _echo(f"Error: {index['error']}")
        return
    if not save_index(index):
        _echo("Error: could not save the knowledge index.")
        return
    _echo(f"Indexed {index['total']} file(s) from {folder}")
    _echo(f"  pdf: {len(index['pdf'])} | txt: {len(index['txt'])} | md: {len(index['md'])}")


@knowledge.command(name="search")
@click.argument("query")
def knowledge_search_cmd(query: str) -> None:
    """Search the saved index for QUERY (content match)."""
    index = load_index()
    if not index:
        _echo("No index yet. Run: maya knowledge index <folder>")
        return
    results = knowledge_search(query, index)
    if not results:
        _echo(f"No matches for '{query}'.")
        return
    _echo(f"Matches for '{query}' ({len(results)}):")
    for r in results:
        _echo(f"  {r['file']}  [{r['match_type']}]")
        preview = r.get("preview", "").replace("\n", " ")
        _echo(f"    {preview[:120]}")


@knowledge.command(name="status")
def knowledge_status() -> None:
    """Show the saved index summary."""
    index = load_index()
    if not index:
        _echo("No index yet. Run: maya knowledge index <folder>")
        return
    _echo("Knowledge Index:")
    _echo(f"  base: {index.get('base', '(not recorded)')}")
    _echo(f"  total: {index.get('total', 0)} file(s)")
    for kind in ("pdf", "txt", "md", "other"):
        _echo(f"  {kind}: {len(index.get(kind, []))}")


MODE_OPTION = click.option(
    "--mode",
    type=click.Choice(["hybrid", "bm25", "semantic"], case_sensitive=False),
    default="hybrid",
    show_default=True,
    help="Retriever: hybrid = BM25 + semantic, or one alone.",
)


@knowledge.command(name="rag-index")
@click.argument("folder")
@click.option("--reset", is_flag=True, help="Rebuild from scratch.")
@click.option("--no-semantic", is_flag=True, help="Skip embeddings (BM25 only).")
def knowledge_rag_index(folder: str, reset: bool, no_semantic: bool) -> None:
    """Chunk + rank-index a folder for retrieval (offline)."""
    summary = rag.index_files(folder, reset=reset, use_embeddings=not no_semantic)
    if "error" in summary:
        _echo(f"Error: {summary['error']}")
        return
    _echo(f"RAG index built from {summary['base']}")
    _echo(f"  files: {summary['files']} (new/changed: {summary['added']}, reused: {summary['reused']})")
    _echo(f"  chunks: {summary['chunks']}")
    if summary.get("embedder"):
        _echo(f"  vectors: {summary['vectors']}/{summary['chunks']} ({summary['embedder']})")
    elif no_semantic:
        _echo("  vectors: skipped (--no-semantic)")
    else:
        _echo("  vectors: none — semantic model not available, BM25 only")
    _echo(f"  saved: {summary['saved']}")


@knowledge.command(name="rag-search")
@click.argument("query")
@click.option("-k", "top_k", default=5, show_default=True, help="Number of chunks.")
@MODE_OPTION
def knowledge_rag_search(query: str, top_k: int, mode: str) -> None:
    """Search the RAG index and show ranked chunks."""
    hits = rag.search(query, k=top_k, mode=mode)
    if not hits:
        _echo(f"No matches ({mode}). Run: maya knowledge rag-index <folder>")
        return
    _echo(f"Top {len(hits)} chunk(s) for '{query}' [{mode}]:")
    for hit in hits:
        preview = " ".join(hit["text"].split())[:140]
        signals = hit.get("signals") or {}
        detail = ""
        if signals:
            parts = []
            if "bm25" in signals:
                parts.append(f"bm25 {signals['bm25']:.2f}")
            if "semantic" in signals:
                parts.append(f"cos {signals['semantic']:.3f}")
            detail = "  (" + ", ".join(parts) + ")"
        _echo(f"  [{hit['score']:.3f}] {hit['path']} #{hit['position']}{detail}")
        _echo(f"      {preview}")


@knowledge.command(name="rag-ask")
@click.argument("query")
@click.option("-k", "top_k", default=4, show_default=True, help="Chunks given to the model.")
@MODE_OPTION
def knowledge_rag_ask(query: str, top_k: int, mode: str) -> None:
    """Answer a question from your documents using the local model (RAG)."""
    prompt, used = rag.build_prompt(query, k=top_k, mode=mode)
    if not prompt:
        _echo(f"Nothing indexed ({mode}). Run: maya knowledge rag-index <folder>")
        return
    _echo(f"Sources [{mode}]: " + ", ".join(f"{h['path']}#{h['position']}" for h in used))
    reply = engine_bridge.chat(
        [
            {"role": "system", "content": "You answer strictly from the provided context."},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    _echo("")
    _echo(reply)


@knowledge.command(name="rag-status")
def knowledge_rag_status() -> None:
    """Show the RAG index summary."""
    summary = rag.RagIndex.load().summary()
    _echo("RAG Index:")
    _echo(f"  base: {summary['base'] or '(empty)'}")
    _echo(f"  files: {summary['files']}  chunks: {summary['chunks']}")
    _echo(f"  vectors: {summary['vectors']} (dim {summary['dim']})")
    _echo(f"  retriever: {summary['retriever']}")
    _echo(f"  path: {summary['index_path']}")


@main.group()
def voice() -> None:
    """Voice: TTS, STT, wake word."""


@voice.command(name="speak")
@click.argument("text")
@click.option("--lang", default="english", help="Language: english or tamil")
def voice_speak(text: str, lang: str) -> None:
    """Speak text using local TTS.

    Usage: maya voice speak "Hello" --lang english
    """
    _echo(speak(text, lang))


@voice.command(name="listen")
@click.argument("audio_path")
@click.option("--lang", default="en", show_default=True, help="en | en-in")
def voice_listen(audio_path: str, lang: str) -> None:
    """Transcribe an audio file using local STT.

    Usage: maya voice listen recording.wav
    """
    _echo(listen(audio_path, lang))


@voice.command(name="mic")
@click.option("--seconds", default=6, show_default=True, help="Recording length (1-15).")
@click.option("--lang", default="en", show_default=True, help="en | en-in")
def voice_mic(seconds: int, lang: str) -> None:
    """Record from the microphone and print the transcript (offline Vosk)."""
    _echo(f"Listening for {seconds}s... (speak now)")
    _echo(listen_mic(seconds, lang))


@voice.group(name="clap")
def voice_clap_group() -> None:
    """3-clap wake detection (offline, does not launch anything by default)."""


@voice_clap_group.command(name="status")
def voice_clap_status() -> None:
    """Show clap-listener settings and verify the detection logic."""
    st = voice_clap.status()
    _echo("Clap Wake Status:")
    _echo(f"  microphone: {'available' if st['windows_mic'] else 'not available'}")
    _echo(f"  threshold: {st['threshold']}  count: {st['count']}")
    _echo(f"  gap: {st['min_gap']}s-{st['max_gap']}s  window: {st['window']}s")
    _echo(f"  cooldown: {st['cooldown']}s")
    _echo(f"  logic self-test: {'ok' if st['logic_ok'] else 'FAILED'}")


@voice_clap_group.command(name="test")
def voice_clap_test() -> None:
    """Verify the detector with synthetic claps (no microphone needed)."""
    ok = voice_clap.simulate()
    _echo("Clap logic: ok" if ok else "Clap logic: FAILED")


@voice_clap_group.command(name="listen")
@click.option("--once", is_flag=True, help="Exit after the first detection.")
@click.option("--seconds", default=30, show_default=True, help="Safety time limit.")
def voice_clap_listen(once: bool, seconds: int) -> None:
    """Listen for the clap pattern (prints when detected, launches nothing)."""
    _echo(f"Listening for claps ({seconds}s limit)...")
    result = voice_clap.listen(once=once, verbose=True, max_seconds=seconds)
    _echo(f"Done. triggers={result['triggers']} device={result['device']}")
    if result["reason"]:
        _echo(f"  stopped: {result['reason']}")


@voice.command(name="wake")
def voice_wake() -> None:
    """Print Maya's wake response."""
    _echo(wake_reply())


@voice.command(name="check-wake")
@click.argument("text")
def voice_check_wake(text: str) -> None:
    """Check if text contains a wake phrase.

    Usage: maya voice check-wake "Maya, Maya, Maya"
    """
    if check_wake(text):
        _echo("Wake phrase detected!")
    else:
        _echo("No wake phrase.")


@voice.command(name="status")
def voice_status_cmd() -> None:
    """Show voice subsystem status."""
    st = voice_status()
    _echo("Voice Status:")
    _echo(f"  Piper available: {st['piper_available']}")
    _echo(f"  TTS English ready: {st['tts_english_ready']}")
    _echo(f"  TTS Tamil ready: {st['tts_tamil_ready']}")
    _echo(f"  Whisper available: {st['whisper_available']}")
    _echo(f"  Vosk installed: {st['vosk_installed']}")
    models = ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in st["stt_models"].items())
    _echo(f"  STT models: {models}")
    _echo(f"  STT ready: {st['stt_ready']}")
    if st.get("input_devices"):
        _echo(f"  Mic: {st['input_devices'][0]}")
    _echo(f"  Voice dir: {st['voice_dir']}")


if __name__ == "__main__":
    main()
