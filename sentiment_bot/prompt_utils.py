"""
TTY-aware prompt utilities for non-interactive safety.
Implements Phase 4 of the performance optimization plan.
"""

import sys
import os
from typing import Optional, List, Any
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.console import Console

console = Console()


def is_interactive() -> bool:
    """
    Check if we're in an interactive TTY session.
    
    Returns False if:
    - stdin is not a TTY (piped input)
    - Running in CI/CD environment
    - NO_INTERACTIVE env var is set
    """
    # Check environment override
    if os.environ.get('NO_INTERACTIVE', '').lower() in ('1', 'true', 'yes'):
        return False
    
    # Check CI environment variables
    ci_vars = ['CI', 'CONTINUOUS_INTEGRATION', 'GITHUB_ACTIONS', 'JENKINS', 'TRAVIS']
    if any(os.environ.get(var) for var in ci_vars):
        return False
    
    # Check if stdin is a TTY
    try:
        return sys.stdin.isatty()
    except:
        return False


def safe_prompt(
    message: str,
    default: str = "",
    choices: Optional[List[str]] = None,
    password: bool = False
) -> str:
    """
    TTY-safe text prompt that returns default in non-interactive mode.
    
    Args:
        message: Prompt message
        default: Default value (returned in non-interactive mode)
        choices: Optional list of valid choices
        password: Whether to mask input
    
    Returns:
        User input or default value
    """
    if not is_interactive():
        console.print(f"{message} [dim](non-interactive, using: {default})[/dim]")
        return default
    
    try:
        return Prompt.ask(
            message,
            default=default,
            choices=choices,
            password=password
        )
    except (EOFError, KeyboardInterrupt):
        console.print(f"\n[yellow]Input interrupted, using default: {default}[/yellow]")
        return default


def safe_confirm(
    message: str,
    default: bool = True
) -> bool:
    """
    TTY-safe confirmation prompt that returns default in non-interactive mode.
    
    Args:
        message: Confirmation message
        default: Default value (returned in non-interactive mode)
    
    Returns:
        User confirmation or default value
    """
    if not is_interactive():
        console.print(f"{message} [dim](non-interactive, using: {default})[/dim]")
        return default
    
    try:
        return Confirm.ask(message, default=default)
    except (EOFError, KeyboardInterrupt):
        console.print(f"\n[yellow]Input interrupted, using default: {default}[/yellow]")
        return default


def safe_int_prompt(
    message: str,
    default: int = 0,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None
) -> int:
    """
    TTY-safe integer prompt that returns default in non-interactive mode.
    
    Args:
        message: Prompt message
        default: Default value (returned in non-interactive mode)
        min_value: Minimum allowed value
        max_value: Maximum allowed value
    
    Returns:
        User input or default value
    """
    if not is_interactive():
        console.print(f"{message} [dim](non-interactive, using: {default})[/dim]")
        return default
    
    try:
        # Rich's IntPrompt doesn't support min/max directly
        while True:
            value = IntPrompt.ask(message, default=default)
            
            if min_value is not None and value < min_value:
                console.print(f"[red]Value must be at least {min_value}[/red]")
                continue
            
            if max_value is not None and value > max_value:
                console.print(f"[red]Value must be at most {max_value}[/red]")
                continue
            
            return value
            
    except (EOFError, KeyboardInterrupt):
        console.print(f"\n[yellow]Input interrupted, using default: {default}[/yellow]")
        return default


def safe_choice(
    message: str,
    choices: List[str],
    default: Optional[str] = None
) -> str:
    """
    TTY-safe choice prompt that returns default in non-interactive mode.
    
    Args:
        message: Prompt message
        choices: List of valid choices
        default: Default choice (if None, uses first choice)
    
    Returns:
        Selected choice or default
    """
    if default is None:
        default = choices[0] if choices else ""
    
    if not is_interactive():
        console.print(f"{message} [dim](non-interactive, using: {default})[/dim]")
        return default
    
    # Display choices
    console.print(message)
    for i, choice in enumerate(choices, 1):
        console.print(f"  {i}. {choice}")
    
    try:
        # Get numeric selection
        while True:
            selection = safe_prompt(
                "Select option",
                default=str(choices.index(default) + 1) if default in choices else "1"
            )
            
            try:
                index = int(selection) - 1
                if 0 <= index < len(choices):
                    return choices[index]
                else:
                    console.print(f"[red]Please select 1-{len(choices)}[/red]")
            except ValueError:
                # Try matching by name
                if selection in choices:
                    return selection
                console.print(f"[red]Invalid selection: {selection}[/red]")
                
    except (EOFError, KeyboardInterrupt):
        console.print(f"\n[yellow]Input interrupted, using default: {default}[/yellow]")
        return default


def safe_multi_select(
    message: str,
    choices: List[str],
    defaults: Optional[List[str]] = None
) -> List[str]:
    """
    TTY-safe multi-select prompt that returns defaults in non-interactive mode.
    
    Args:
        message: Prompt message
        choices: List of available choices
        defaults: Default selections (if None, selects none)
    
    Returns:
        List of selected choices
    """
    if defaults is None:
        defaults = []
    
    if not is_interactive():
        console.print(
            f"{message} [dim](non-interactive, using: {', '.join(defaults)})[/dim]"
        )
        return defaults
    
    # Display choices
    console.print(message)
    console.print("[dim]Enter numbers separated by commas, or 'all' for all[/dim]")
    
    for i, choice in enumerate(choices, 1):
        marker = "✓" if choice in defaults else " "
        console.print(f"  [{marker}] {i}. {choice}")
    
    try:
        selection = safe_prompt(
            "Select options",
            default=",".join(str(choices.index(d) + 1) for d in defaults if d in choices)
        )
        
        if selection.lower() == 'all':
            return choices.copy()
        
        selected = []
        for part in selection.split(','):
            part = part.strip()
            if not part:
                continue
            
            try:
                index = int(part) - 1
                if 0 <= index < len(choices):
                    selected.append(choices[index])
            except ValueError:
                # Try matching by name
                if part in choices:
                    selected.append(part)
        
        return selected if selected else defaults
        
    except (EOFError, KeyboardInterrupt):
        console.print(f"\n[yellow]Input interrupted, using defaults[/yellow]")
        return defaults


def get_view_preference(default: str = "Summary") -> str:
    """
    Get the view preference (Summary/Articles/Analysis).
    Returns default in non-interactive mode.
    """
    return safe_choice(
        "What would you like to view?",
        choices=["Summary", "Articles", "Analysis", "Exit"],
        default=default
    )


def handle_interactive_menu(
    stats: dict,
    results: dict, 
    articles: list,
    default_view: str = "Summary"
) -> None:
    """
    Handle the post-analysis interactive menu.
    In non-interactive mode, shows the default view and exits.
    """
    from .analyzer import display_ingestion_summary, display_analysis_results
    
    if not is_interactive():
        # Non-interactive: show default view and exit
        console.print(f"[dim]Non-interactive mode, showing {default_view}[/dim]")
        
        if default_view == "Summary":
            display_ingestion_summary(stats)
        elif default_view == "Articles":
            console.rule("Fetched Articles")
            for art in articles[:20]:  # Limit output
                console.print(f"- {art.title}")
        elif default_view == "Analysis":
            display_analysis_results(results)
        
        return
    
    # Interactive mode: show menu
    while True:
        choice = get_view_preference(default_view)
        
        if choice == "Exit":
            break
        elif choice == "Summary":
            display_ingestion_summary(stats)
        elif choice == "Articles":
            console.rule("Fetched Articles")
            for art in articles:
                console.print(f"- {art.title}")
        elif choice == "Analysis":
            display_analysis_results(results)
        else:
            break