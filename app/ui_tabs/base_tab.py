"""
Base Tab class for PXE Boot Station UI
Provides common functionality and patterns for all tabs
"""

import gradio as gr
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Callable, Tuple

from .helpers import (
    create_status_textbox,
    create_action_buttons,
    create_section_header,
    create_info_box,
    refresh_dropdown_choices
)


class BaseTab(ABC):
    """
    Base class for all UI tabs.

    Provides common functionality and enforces consistent patterns
    across all tabs in the application.
    """

    def __init__(self, ui_controller):
        """
        Initialize base tab.

        Args:
            ui_controller: Main UI controller instance (PXEBootStationUI)
        """
        self.ui_controller = ui_controller
        self._components = {}  # Store tab components for reference

    @abstractmethod
    def create_tab(self) -> gr.Tab:
        """
        Create and return the tab component.

        Must be implemented by child classes.

        Returns:
            gr.Tab: The created tab component
        """
        raise NotImplementedError("Child classes must implement create_tab()")

    @property
    @abstractmethod
    def tab_name(self) -> str:
        """Tab display name with icon."""
        raise NotImplementedError("Child classes must define tab_name")

    @property
    @abstractmethod
    def tab_id(self) -> str:
        """Tab HTML element ID."""
        raise NotImplementedError("Child classes must define tab_id")

    # =========================
    # COMMON UI CREATION METHODS
    # =========================

    def _create_status_textbox(self,
                               label: str = "Status",
                               lines: int = 10,
                               initial_value: str = "",
                               component_key: Optional[str] = None) -> gr.Textbox:
        """
        Create a standardized status textbox.

        Args:
            label: Textbox label
            lines: Number of lines
            initial_value: Initial content
            component_key: Key to store component reference

        Returns:
            gr.Textbox: Created textbox
        """
        textbox = create_status_textbox(
            label=label,
            lines=lines,
            initial_value=initial_value
        )

        if component_key:
            self._components[component_key] = textbox

        return textbox

    def _create_action_buttons(self, *button_configs, component_keys: Optional[List[str]] = None):
        """
        Create action buttons and optionally store references.

        Args:
            *button_configs: Button configurations
            component_keys: Keys to store button references

        Returns:
            Tuple of buttons or single button
        """
        buttons = create_action_buttons(*button_configs)

        if component_keys:
            if isinstance(buttons, tuple):
                for i, key in enumerate(component_keys):
                    if i < len(buttons):
                        self._components[key] = buttons[i]
            else:
                # Single button
                if component_keys:
                    self._components[component_keys[0]] = buttons

        return buttons

    def _create_section_header(self, title: str, icon: str = "", description: str = "") -> gr.HTML:
        """Create a section header."""
        return create_section_header(title, icon, description)

    def _create_info_box(self, message: str, box_type: str = "info") -> gr.HTML:
        """Create an information box."""
        return create_info_box(message, box_type)

    # =========================
    # COMMON EVENT HANDLING
    # =========================

    def _setup_refresh_dropdown(self,
                                dropdown: gr.Dropdown,
                                refresh_btn: gr.Button,
                                get_choices_fn: Callable,
                                empty_msg: str = "No items found"):
        """
        Setup dropdown refresh functionality.

        Args:
            dropdown: Dropdown component
            refresh_btn: Refresh button
            get_choices_fn: Function to get new choices
            empty_msg: Message when no items found
        """
        refresh_btn.click(
            fn=lambda: refresh_dropdown_choices(get_choices_fn, empty_msg),
            outputs=dropdown
        )

    def _chain_events(self,
                      trigger_component: gr.Component,
                      event_chain: List[Dict[str, Any]]):
        """
        Chain multiple events from a single trigger.

        Args:
            trigger_component: Component that triggers the chain
            event_chain: List of event dictionaries with 'fn', 'inputs', 'outputs'

        Usage:
            self._chain_events(
                delete_btn,
                [
                    {'fn': self.delete_item, 'inputs': [item_name], 'outputs': [status]},
                    {'fn': self.refresh_list, 'outputs': [dropdown]},
                    {'fn': self.update_summary, 'outputs': [summary]}
                ]
            )
        """
        event = trigger_component.click(
            fn=event_chain[0]['fn'],
            inputs=event_chain[0].get('inputs', []),
            outputs=event_chain[0].get('outputs', [])
        )

        for next_event in event_chain[1:]:
            event = event.then(
                fn=next_event['fn'],
                inputs=next_event.get('inputs', []),
                outputs=next_event.get('outputs', [])
            )

    # =========================
    # COMPONENT ACCESS
    # =========================

    def get_component(self, key: str) -> Optional[gr.Component]:
        """
        Get stored component by key.

        Args:
            key: Component key

        Returns:
            Component or None if not found
        """
        return self._components.get(key)

    def store_component(self, key: str, component: gr.Component):
        """
        Store component reference.

        Args:
            key: Component key
            component: Component to store
        """
        self._components[key] = component

    # =========================
    # VALIDATION HELPERS
    # =========================

    def _validate_required_modules(self, modules: List[str]) -> Optional[str]:
        """
        Validate that required modules are available.

        Args:
            modules: List of module attribute names to check

        Returns:
            Error message if any module is missing, None if all are available
        """
        missing_modules = []

        for module_attr in modules:
            if not getattr(self.ui_controller, module_attr, None):
                missing_modules.append(module_attr)

        if missing_modules:
            return f"❌ Required modules not available: {', '.join(missing_modules)}"

        return None

    # =========================
    # COMMON PATTERNS
    # =========================

    # def _create_summary_ui_section(self,
    #                             get_summary_fn: Callable,
    #                             title: str = "Summary",
    #                             icon: str = "📊") -> Tuple[gr.HTML, gr.Textbox, gr.Button]:
    #     """
    #     Create a common summary section pattern.
    #
    #     Args:
    #         get_summary_fn: Function to get summary data
    #         title: Section title
    #         icon: Section icon
    #
    #     Returns:
    #         Tuple of (header, summary_textbox, refresh_button)
    #     """
    #     with gr.Row():
    #         with gr.Column():
    #             summary_textbox = self._create_status_textbox(
    #                 label=f"{title}",
    #                 initial_value=get_summary_fn(),
    #                 lines=4,
    #                 component_key="summary"
    #             )
    #             refresh_btn = gr.Button(f"🔄 Refresh {title}", variant="secondary", size="sm")
    #
    #     # Setup refresh functionality
    #     refresh_btn.click(
    #         fn=get_summary_fn,
    #         outputs=summary_textbox
    #     )
    #
    #     return summary_textbox, refresh_btn

    def _create_summary_ui_section(self,
                                   get_summary_fn: Callable,
                                   title: str = "Summary",
                                   icon: str = "📊") -> Tuple[gr.Textbox, gr.Button]:
        """
        Create a common summary UI section pattern.

        Args:
            get_summary_fn: Function to get summary data
            title: Section title
            icon: Section icon

        Returns:
            Tuple of (summary_textbox, refresh_button)
        """
        with gr.Row():
            with gr.Column():
                summary_textbox = self._create_status_textbox(
                    label=f"{title}",
                    initial_value=get_summary_fn(),
                    lines=4,
                    component_key="summary"
                )
                refresh_btn = gr.Button(f"🔄 Refresh {title}", variant="secondary", size="sm")

        # Setup refresh functionality
        refresh_btn.click(
            fn=get_summary_fn,
            outputs=summary_textbox
        )

        return summary_textbox, refresh_btn

    def _create_management_section(self,
                                   items_dropdown: gr.Dropdown,
                                   management_actions: List[Tuple[str, str, str]],  # (text, variant, icon)
                                   status_textbox: gr.Textbox) -> List[gr.Button]:
        """
        Create a common management section pattern.

        Args:
            items_dropdown: Dropdown with items to manage
            management_actions: List of button configurations
            status_textbox: Status output textbox

        Returns:
            List of created buttons
        """
        buttons = []

        with gr.Row():
            for text, variant, icon in management_actions:
                btn = gr.Button(f"{icon} {text}", variant=variant)
                buttons.append(btn)

        return buttons

    # =========================
    # DEBUGGING AND LOGGING
    # =========================

    def _log_component_creation(self, component_type: str, component_key: str = ""):
        """
        Log component creation for debugging.

        Args:
            component_type: Type of component created
            component_key: Optional component key
        """
        tab_name = getattr(self, 'tab_name', 'Unknown Tab')
        key_info = f" (key: {component_key})" if component_key else ""
        print(f"[DEBUG] {tab_name}: Created {component_type}{key_info}")

    def get_component_summary(self) -> Dict[str, Any]:
        """
        Get summary of all components in this tab.

        Returns:
            Dictionary with component information
        """
        return {
            'tab_name': getattr(self, 'tab_name', 'Unknown'),
            'tab_id': getattr(self, 'tab_id', 'unknown'),
            'component_count': len(self._components),
            'component_keys': list(self._components.keys())
        }