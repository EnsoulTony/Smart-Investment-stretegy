"""Strategy Engine: Pluggable decision engine core.

Responsibilities:
- Load and validate plugins
- Validate Input/Output schemas
- Execute plugin logic
- Generate canonical JSON hash for reproducibility
"""

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Dict, Type, Any, Optional

from .schemas import InputSchema, OutputSchema, MissingDataError


def canonical_json_hash(data: dict) -> str:
    """Generate SHA256 hash of canonical JSON (sorted keys, no whitespace).

    This ensures reproducibility: same input always produces same hash.

    Args:
        data: Dictionary to hash

    Returns:
        SHA256 hex digest
    """
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StrategyPlugin(ABC):
    """Abstract base class for strategy plugins.

    All plugins must:
    - Accept InputSchema
    - Return OutputSchema
    - Handle missing data gracefully (return MissingDataError)
    """

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Plugin identifier (e.g., 'v1.4')."""
        pass

    @property
    @abstractmethod
    def plugin_version(self) -> str:
        """Plugin version (e.g., '1.4.0')."""
        pass

    @abstractmethod
    def execute(self, input_data: InputSchema) -> OutputSchema:
        """Execute strategy logic.

        Args:
            input_data: Validated InputSchema

        Returns:
            OutputSchema with decision, actions, and evidence

        Raises:
            MissingDataException: When required data is missing
        """
        pass

    def validate_input(self, input_data: InputSchema) -> Optional[MissingDataError]:
        """Validate input data completeness.

        Override in subclass to add plugin-specific validation.

        Args:
            input_data: InputSchema to validate

        Returns:
            MissingDataError if validation fails, None if OK
        """
        return None


class MissingDataException(Exception):
    """Exception raised when required data is missing."""

    def __init__(self, missing_fields: list[str], message: str = ""):
        self.missing_fields = missing_fields
        self.message = message or f"Missing required fields: {', '.join(missing_fields)}"
        super().__init__(self.message)

    def to_error(self) -> MissingDataError:
        """Convert to MissingDataError response."""
        return MissingDataError(
            status="missing_data",
            missing_fields=self.missing_fields,
            message=self.message,
        )


class StrategyEngine:
    """Main strategy engine: loads plugins and executes decisions.

    Usage:
        engine = StrategyEngine()
        engine.register_plugin("v1.4", V1_4Plugin)

        input_data = InputSchema(...)
        result = engine.execute("v1.4", input_data)
    """

    def __init__(self):
        self._plugins: Dict[str, Type[StrategyPlugin]] = {}

    def register_plugin(self, name: str, plugin_class: Type[StrategyPlugin]) -> None:
        """Register a strategy plugin.

        Args:
            name: Plugin name (e.g., 'v1.4')
            plugin_class: Plugin class (not instance)
        """
        self._plugins[name] = plugin_class

    def get_plugin(self, name: str) -> Optional[StrategyPlugin]:
        """Get plugin instance by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        plugin_class = self._plugins.get(name)
        if plugin_class:
            return plugin_class()
        return None

    def list_plugins(self) -> list[str]:
        """List registered plugin names."""
        return list(self._plugins.keys())

    def execute(
        self, plugin_name: str, input_data: InputSchema
    ) -> OutputSchema:
        """Execute a strategy plugin.

        Args:
            plugin_name: Plugin to execute (e.g., 'v1.4')
            input_data: Validated InputSchema

        Returns:
            OutputSchema with decision and evidence

        Raises:
            ValueError: If plugin not found
            MissingDataException: If required data is missing
        """
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_name}' not found. Available: {self.list_plugins()}")

        # Validate input (plugin-specific validation)
        validation_error = plugin.validate_input(input_data)
        if validation_error:
            raise MissingDataException(
                missing_fields=validation_error.missing_fields,
                message=validation_error.message,
            )

        # Execute plugin logic
        return plugin.execute(input_data)

    def compute_inputs_hash(self, input_data: InputSchema) -> str:
        """Compute canonical hash of input data.

        Args:
            input_data: InputSchema to hash

        Returns:
            SHA256 hex digest
        """
        return canonical_json_hash(input_data.model_dump())


# =============================================================================
# Singleton engine instance with auto-registration
# =============================================================================

_default_engine: Optional[StrategyEngine] = None


def get_default_engine() -> StrategyEngine:
    """Get or create the default strategy engine with all plugins registered.

    Returns:
        StrategyEngine instance with plugins loaded
    """
    global _default_engine

    if _default_engine is None:
        _default_engine = StrategyEngine()

        # Register v1.4 plugin
        try:
            from .plugins.v1_4.plugin import V1_4Plugin
            _default_engine.register_plugin("v1.4", V1_4Plugin)
        except ImportError:
            pass  # Plugin not available

    return _default_engine
