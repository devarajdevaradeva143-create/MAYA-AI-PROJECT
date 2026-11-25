"""CLI for MAYA INTELLIGENCE — chat | memory | persona | status."""

import sys
import click
from pathlib import Path

from .orchestrator import Orchestrator
from .memory import MemoryStore
from .config import get_db_path, load_persona


def _confirm_prompt(message: str) -> bool:
    """Default confirmation prompt for CLI."""
    try:
        response = input(f"{message} [y/N]: ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _check_session_locked() -> bool:
    """Check if session is locked via security module."""
    try:
        from custom.tools.security import security
        return security.is_session_locked()
    except Exception:
        return False


@click.group()
@click.option("--db", envvar="MAYA_INTEL_DB", help="Memory database path")
@click.pass_context
def cli(ctx, db):
    """MAYA INTELLIGENCE — Offline Intelligence Orchestration."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db
    if _check_session_locked():
        click.echo("Session is locked. Unlock first.", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def chat(ctx):
    """Start interactive chat with Maya."""
    orchestrator = Orchestrator(
        confirm_fn=_confirm_prompt,
        db_path=ctx.obj["db_path"],
    )
    click.echo("Maya: Hello! How can I help you today? (Ctrl+C to exit)")
    try:
        while True:
            try:
                user_input = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                click.echo("\nMaya: Goodbye!")
                break
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye", "/exit", "/quit", "/q"):
                click.echo("Maya: Goodbye!")
                break
            response = orchestrator.chat(user_input)
            click.echo(f"Maya: {response}")
    finally:
        orchestrator.close()


@cli.command()
@click.argument("message")
@click.pass_context
def ask(ctx, message):
    """Ask a single question (non-interactive)."""
    orchestrator = Orchestrator(
        confirm_fn=_confirm_prompt,
        db_path=ctx.obj["db_path"],
    )
    try:
        response = orchestrator.chat(message)
        click.echo(response)
    finally:
        orchestrator.close()


@cli.group()
@click.pass_context
def memory(ctx):
    """Manage persistent memory."""
    ctx.obj["store"] = MemoryStore(Path(ctx.obj["db_path"]) if ctx.obj["db_path"] else get_db_path())


@memory.command("add")
@click.option("--category", type=click.Choice(["personal", "conversation", "project", "knowledge"]), required=True)
@click.option("--key", required=True)
@click.option("--value", required=True)
@click.option("--sensitivity", type=click.Choice(["low", "medium", "high"]), default="low")
@click.option("--allow-secret", is_flag=True, help="Allow storing potential secrets")
@click.pass_context
def memory_add(ctx, category, key, value, sensitivity, allow_secret):
    """Add a memory entry."""
    store = ctx.obj["store"]
    try:
        store.add(category, key, value, sensitivity, allow_secret)
        click.echo(f"Added: [{category}] {key} = {value[:50]}{'...' if len(value) > 50 else ''}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@memory.command("get")
@click.option("--category", type=click.Choice(["personal", "conversation", "project", "knowledge"]), required=True)
@click.option("--key", required=True)
@click.pass_context
def memory_get(ctx, category, key):
    """Get a memory entry."""
    store = ctx.obj["store"]
    entry = store.get(category, key)
    if entry:
        click.echo(f"[{entry.category}] {entry.key}: {entry.value}")
    else:
        click.echo("Not found")


@memory.command("search")
@click.option("--query", required=True)
@click.option("--category", type=click.Choice(["personal", "conversation", "project", "knowledge"]))
@click.option("--limit", default=20)
@click.pass_context
def memory_search(ctx, query, category, limit):
    """Search memories."""
    store = ctx.obj["store"]
    results = store.search(query, category, limit)
    if results:
        for entry in results:
            click.echo(f"[{entry.category}] {entry.key}: {entry.value[:100]}{'...' if len(entry.value) > 100 else ''}")
    else:
        click.echo("No results found")


@memory.command("list")
@click.option("--category", type=click.Choice(["personal", "conversation", "project", "knowledge"]))
@click.option("--limit", default=100)
@click.pass_context
def memory_list(ctx, category, limit):
    """List memories."""
    store = ctx.obj["store"]
    results = store.list(category, limit)
    if results:
        for entry in results:
            click.echo(f"[{entry.category}] {entry.key}: {entry.value[:80]}{'...' if len(entry.value) > 80 else ''}")
    else:
        click.echo("No memories found")


@memory.command("edit")
@click.option("--category", type=click.Choice(["personal", "conversation", "project", "knowledge"]), required=True)
@click.option("--key", required=True)
@click.option("--value")
@click.option("--sensitivity", type=click.Choice(["low", "medium", "high"]))
@click.option("--allow-secret", is_flag=True)
@click.pass_context
def memory_edit(ctx, category, key, value, sensitivity, allow_secret):
    """Edit a memory entry."""
    store = ctx.obj["store"]
    try:
        store.update(category, key, value, sensitivity, allow_secret)
        click.echo(f"Updated: [{category}] {key}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@memory.command("delete")
@click.option("--category", type=click.Choice(["personal", "conversation", "project", "knowledge"]), required=True)
@click.option("--key", required=True)
@click.pass_context
def memory_delete(ctx, category, key):
    """Delete a memory entry."""
    store = ctx.obj["store"]
    if store.delete(category, key):
        click.echo(f"Deleted: [{category}] {key}")
    else:
        click.echo("Not found")


@memory.command("stats")
@click.pass_context
def memory_stats(ctx):
    """Show memory statistics."""
    store = ctx.obj["store"]
    stats = store.stats()
    click.echo(f"Total memories: {stats['total']}")
    click.echo(f"Database: {stats['db_path']}")
    for cat, count in stats["by_category"].items():
        click.echo(f"  {cat}: {count}")


@cli.command()
def persona():
    """Show the current persona prompt."""
    click.echo(load_persona())


@cli.command()
@click.pass_context
def status(ctx):
    """Show system status."""
    orchestrator = Orchestrator(db_path=ctx.obj["db_path"])
    try:
        health = orchestrator.health_check()
        click.echo("MAYA INTELLIGENCE Status")
        click.echo(f"  Engine: {health['engine']}")
        click.echo(f"  Memory: {health['memory']}")
        click.echo(f"  Total memories: {health['memory_stats']['total']}")
        for cat, count in health['memory_stats']['by_category'].items():
            click.echo(f"    {cat}: {count}")
    finally:
        orchestrator.close()


def main():
    cli(obj={})


if __name__ == "__main__":
    main()