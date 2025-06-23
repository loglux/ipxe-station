"""
UI Helpers - Common UI utilities for PXE Boot Station
Shared components and patterns used across all tabs
"""

import gradio as gr
from typing import Callable, Optional, List, Tuple, Any
import functools


def safe_method(module_attr: Optional[str] = None, error_prefix: str = "Operation"):
    """
    Decorator for safe method calls with unified error handling.

    Args:
        module_attr: Name of the module attribute to check (e.g., 'ubuntu_downloader')
        error_prefix: Prefix for error messages (e.g., 'Ubuntu download')

    Usage:
        @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu download')
        def download_ubuntu_files(self, version: str):
            return self.ubuntu_downloader.download_all_files(version)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                # Check if required module is available
                if module_attr and not getattr(self, module_attr, None):
                    return f"❌ {error_prefix} module not available"

                # Execute the actual method
                return func(self, *args, **kwargs)

            except Exception as e:
                return f"❌ {error_prefix} failed: {str(e)}"

        return wrapper

    return decorator


def create_status_textbox(label: str = "Status",
                          lines: int = 10,
                          initial_value: str = "",
                          max_lines: Optional[int] = None,
                          show_label: bool = True,
                          **kwargs) -> gr.Textbox:
    """
    Create standardized status textbox component.

    Args:
        label: Textbox label
        lines: Number of visible lines
        initial_value: Initial text content
        max_lines: Maximum expandable lines
        show_label: Whether to show the label
        **kwargs: Additional Gradio textbox parameters

    Returns:
        gr.Textbox: Configured textbox component
    """
    return gr.Textbox(
        label=label,
        value=initial_value,
        lines=lines,
        max_lines=max_lines,
        interactive=False,
        show_label=show_label,
        **kwargs
    )


def create_action_buttons(*button_configs) -> Tuple[gr.Button, ...]:
    """
    Create a row of action buttons with consistent styling.

    Args:
        *button_configs: Tuples of (text, variant, icon) for each button

    Usage:
        download_btn, check_btn = create_action_buttons(
            ("Download", "primary", "⬇️"),
            ("Check All", "secondary", "🔍")
        )

    Returns:
        tuple: Button components
    """
    buttons = []
    for config in button_configs:
        if len(config) == 3:
            text, variant, icon = config
            button_text = f"{icon} {text}" if icon else text
        elif len(config) == 2:
            text, variant = config
            button_text = text
        else:
            text = config[0]
            variant = "secondary"
            button_text = text

        btn = gr.Button(button_text, variant=variant)
        buttons.append(btn)

    return tuple(buttons) if len(buttons) > 1 else buttons[0]


def create_section_header(title: str, icon: str = "", description: str = "") -> gr.HTML:
    """
    Create a standardized section header.

    Args:
        title: Section title
        icon: Optional icon (emoji)
        description: Optional description

    Returns:
        gr.HTML: Section header component
    """
    header_text = f"{icon} {title}" if icon else title

    if description:
        content = f"""
        <div style="margin: 20px 0 10px 0;">
            <h3 style="margin: 0; color: #374151;">{header_text}</h3>
            <p style="margin: 5px 0 0 0; color: #6B7280; font-size: 0.9em;">{description}</p>
        </div>
        """
    else:
        content = f"""
        <div style="margin: 20px 0 10px 0;">
            <h3 style="margin: 0; color: #374151;">{header_text}</h3>
        </div>
        """

    return gr.HTML(content)


def create_info_box(message: str, box_type: str = "info") -> gr.HTML:
    """
    Create an information box with different styles.

    Args:
        message: Message to display
        box_type: Type of box ('info', 'warning', 'error', 'success')

    Returns:
        gr.HTML: Information box component
    """
    colors = {
        'info': {'bg': '#EFF6FF', 'border': '#3B82F6', 'text': '#1E40AF'},
        'warning': {'bg': '#FFFBEB', 'border': '#F59E0B', 'text': '#92400E'},
        'error': {'bg': '#FEF2F2', 'border': '#EF4444', 'text': '#DC2626'},
        'success': {'bg': '#F0FDF4', 'border': '#10B981', 'text': '#047857'}
    }

    color = colors.get(box_type, colors['info'])

    content = f"""
    <div style="
        background-color: {color['bg']};
        border-left: 4px solid {color['border']};
        padding: 12px 16px;
        margin: 10px 0;
        border-radius: 4px;
        color: {color['text']};
        font-size: 14px;
    ">
        {message}
    </div>
    """

    return gr.HTML(content)


def create_dropdown_with_refresh(choices: List[str],
                                 value: Optional[str] = None,
                                 label: str = "Select option",
                                 refresh_fn: Optional[Callable] = None) -> Tuple[gr.Dropdown, Optional[gr.Button]]:
    """
    Create dropdown with optional refresh button.

    Args:
        choices: List of dropdown choices
        value: Default value
        label: Dropdown label
        refresh_fn: Function to call for refresh (if None, no refresh button)

    Returns:
        tuple: (dropdown, refresh_button or None)
    """
    if not value and choices:
        value = choices[0]

    dropdown = gr.Dropdown(
        choices=choices,
        value=value,
        label=label,
        allow_custom_value=False
    )

    if refresh_fn:
        refresh_btn = gr.Button("🔄", variant="secondary", size="sm")
        return dropdown, refresh_btn

    return dropdown, None


def create_accordion_section(title: str,
                             content_fn: Callable,
                             open_by_default: bool = False,
                             icon: str = "") -> gr.Accordion:
    """
    Create an accordion section with standardized styling.

    Args:
        title: Accordion title
        content_fn: Function that creates content inside accordion
        open_by_default: Whether accordion is open by default
        icon: Optional icon

    Returns:
        gr.Accordion: Accordion component with content
    """
    accordion_title = f"{icon} {title}" if icon else title

    with gr.Accordion(accordion_title, open=open_by_default) as accordion:
        content_fn()

    return accordion


def refresh_dropdown_choices(get_choices_fn: Callable,
                             empty_msg: str = "No items found",
                             error_msg: str = "Error loading items") -> dict:
    """
    Universal dropdown refresh function.

    Args:
        get_choices_fn: Function to get new choices
        empty_msg: Message when no items found
        error_msg: Message on error

    Returns:
        dict: Gradio update dictionary
    """
    try:
        items = get_choices_fn()
        if not items:
            items = [empty_msg]
            value = empty_msg
        else:
            value = items[0]

        return gr.update(choices=items, value=value)
    except Exception:
        return gr.update(choices=[error_msg], value=error_msg)


def create_progress_display(message: str = "Processing...") -> gr.HTML:
    """
    Create a progress display component.

    Args:
        message: Progress message

    Returns:
        gr.HTML: Progress display component
    """
    content = f"""
    <div style="
        text-align: center;
        padding: 20px;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 8px;
        margin: 10px 0;
    ">
        <div style="font-size: 16px; margin-bottom: 10px;">🔄 {message}</div>
        <div style="font-size: 12px; opacity: 0.8;">Please wait...</div>
    </div>
    """

    return gr.HTML(content)


# Common CSS styles
COMMON_CSS = """
.gradio-container {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.tab-nav {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
}
.status-good { color: #28a745; }
.status-warning { color: #ffc107; }
.status-error { color: #dc3545; }
.section-header {
    border-bottom: 2px solid #e5e7eb;
    padding-bottom: 8px;
    margin-bottom: 16px;
}
"""


def create_main_header() -> gr.HTML:
    """Create the main application header."""
    return gr.HTML("""
    <div style="text-align: center; padding: 20px; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px; margin-bottom: 20px;">
        <h1>🚀 PXE Boot Station Control Panel</h1>
        <p>Complete PXE network boot management solution</p>
    </div>
    """)


def create_main_footer() -> gr.HTML:
    """Create the main application footer."""
    return gr.HTML("""
    <div style="text-align: center; padding: 20px; margin-top: 30px; border-top: 1px solid #ddd;">
        <p>🚀 <strong>PXE Boot Station</strong> - Network Boot Management Made Easy</p>
        <p style="color: #666;">Refactored Architecture • Clean Code • Enterprise Ready • Multi-Version Support</p>
    </div>
    """)


# Export commonly used functions
__all__ = [
    'safe_method',
    'create_status_textbox',
    'create_action_buttons',
    'create_section_header',
    'create_info_box',
    'create_dropdown_with_refresh',
    'create_accordion_section',
    'refresh_dropdown_choices',
    'create_progress_display',
    'create_main_header',
    'create_main_footer',
    'COMMON_CSS'
]