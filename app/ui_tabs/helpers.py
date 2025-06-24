import gradio as gr

def safe_method(module_attr=None, error_prefix="Operation"):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            try:
                if module_attr and not getattr(self, module_attr, None):
                    return f"❌ {error_prefix} module not available"
                return func(self, *args, **kwargs)
            except Exception as e:
                return f"❌ {error_prefix} failed: {str(e)}"
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator

def _create_status_textbox(label="Status", lines=10, initial_value="", max_lines=None, show_label=True, **kwargs):
    return gr.Textbox(
        label=label,
        value=initial_value,
        lines=lines,
        max_lines=max_lines,
        interactive=False,
        show_label=show_label,
        **kwargs
    )

# def _create_action_buttons(*button_configs):
#     buttons = []
#     for config in button_configs:
#         if len(config) == 3:
#             text, variant, icon = config
#             button_text = f"{icon} {text}" if icon else text
#         elif len(config) == 2:
#             text, variant = config
#             button_text = text
#         else:
#             text = config[0]
#             variant = "secondary"
#             button_text = text
#         btn = gr.Button(button_text, variant=variant)
#         buttons.append(btn)
#     return tuple(buttons) if len(buttons) > 1 else buttons[0]


def _create_action_buttons(*button_configs):
    """
    Create a row of action buttons with consistent styling.

    Args:
        *button_configs: Tuples of (text, variant, icon) for each button

    Usage:
        download_btn, check_btn = _create_action_buttons(
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