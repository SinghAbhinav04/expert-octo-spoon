"""
Tool Registry — Central registry for agent-executable tools

Each tool is a self-describing, executable unit that the LLM planner
can discover and the executor can invoke.
"""
from typing import Dict, Any, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
import time
import traceback


class ToolCategory(str, Enum):
    """Categories for tool classification"""
    LLM = "llm"
    VISION = "vision"
    COMMUNICATION = "communication"
    FILE_SYSTEM = "file_system"
    BROWSER = "browser"
    SYSTEM = "system"
    CUSTOM = "custom"


@dataclass
class ToolResult:
    """Result returned by a tool execution"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    latency_ms: int = 0
    tokens_used: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolParameter:
    """Describes a single tool parameter"""
    name: str
    type: str  # "string", "integer", "boolean", "object", "array"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


class Tool:
    """
    Base class for all agent tools.
    
    Subclass this and implement `execute()` to create a new tool.
    The LLM planner uses `name`, `description`, and `parameters`
    to decide when and how to invoke the tool.
    """

    def __init__(
        self,
        name: str,
        description: str,
        category: ToolCategory = ToolCategory.CUSTOM,
        parameters: Optional[List[ToolParameter]] = None,
        requires_confirmation: bool = False,
    ):
        self.name = name
        self.description = description
        self.category = category
        self.parameters = parameters or []
        self.requires_confirmation = requires_confirmation

    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with given arguments.
        Must be overridden by subclasses.
        """
        raise NotImplementedError(f"Tool '{self.name}' must implement execute()")

    def to_schema(self) -> Dict[str, Any]:
        """
        Export tool as a JSON-serializable schema for LLM consumption.
        The planner prompt includes this so the LLM knows what tools exist.
        """
        params = {}
        required = []
        for p in self.parameters:
            param_schema = {
                "type": p.type,
                "description": p.description,
            }
            if p.enum:
                param_schema["enum"] = p.enum
            if p.default is not None:
                param_schema["default"] = p.default
            params[p.name] = param_schema
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "requires_confirmation": self.requires_confirmation,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required,
            },
        }


class ToolRegistry:
    """
    Central registry for all agent tools.
    
    Usage:
        registry = ToolRegistry()
        registry.register(MyTool())
        result = await registry.execute("my_tool", arg1="value")
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool in the registry"""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        print(f"🔧 Registered tool: {tool.name} [{tool.category.value}]")

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry"""
        if name in self._tools:
            del self._tools[name]

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all tools as schemas (for LLM consumption)"""
        return [tool.to_schema() for tool in self._tools.values()]

    def list_names(self) -> List[str]:
        """List all registered tool names"""
        return list(self._tools.keys())

    def count(self) -> int:
        """Number of registered tools"""
        return len(self._tools)

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name with given arguments.
        Handles timing, error catching, and result normalization.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found. Available: {self.list_names()}"
            )

        start_time = time.time()
        try:
            result = await tool.execute(**kwargs)
            if not isinstance(result, ToolResult):
                result = ToolResult(success=True, output=result)
            result.latency_ms = int((time.time() - start_time) * 1000)
            return result
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                latency_ms=latency_ms,
                metadata={"traceback": traceback.format_exc()},
            )


# ─── Singleton ───────────────────────────────────────────────────────────────

_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_builtin_tools(_registry)
    return _registry


def _register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools"""
    from app.agent.tools.llm_tool import LLMGenerateTool
    from app.agent.tools.image_tool import ImageAnalysisTool
    from app.agent.tools.email_tool import EmailTool

    registry.register(LLMGenerateTool())
    registry.register(ImageAnalysisTool())
    registry.register(EmailTool())

    print(f"✅ {registry.count()} built-in tools registered")
