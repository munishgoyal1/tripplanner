"""Interactive CLI for the personal assistant."""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.markdown import Markdown

from tripplanner.observability import setup_logging

setup_logging()
console = Console()


def main() -> None:
    console.print("[bold green]Personal Assistant[/bold green] — type 'quit' to exit\n")

    # Lazy import to avoid startup cost if just checking CLI help
    from tripplanner.graph import app_graph

    messages: list = []

    while True:
        try:
            user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        messages.append(HumanMessage(content=user_input))

        result = app_graph.invoke({"messages": messages, "current_agent": ""})
        messages = result["messages"]

        # Print the last AI message
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content and msg.type == "ai":
                console.print(f"\n[bold yellow]Assistant:[/bold yellow] {msg.content}\n")
                break


if __name__ == "__main__":
    main()

