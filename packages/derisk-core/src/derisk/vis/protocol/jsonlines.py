"""
VIS Protocol V2 - JSON Lines Protocol Converter

Converts VIS components to/from JSON Lines format for streaming.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union

logger = logging.getLogger(__name__)


class VisMessageType(str, Enum):
    """Message types for JSON Lines protocol."""
    
    COMPONENT = "component"
    PATCH = "patch"
    COMPLETE = "complete"
    ERROR = "error"
    BATCH = "batch"


@dataclass
class VisJsonLine:
    """Single line in JSON Lines format."""
    
    type: VisMessageType
    tag: Optional[str] = None
    uid: Optional[str] = None
    props: Optional[Dict[str, Any]] = None
    ops: Optional[List[Dict[str, Any]]] = None
    slots: Optional[Dict[str, List[str]]] = None
    events: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    items: Optional[List["VisJsonLine"]] = None
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        data = {"type": self.type.value}
        
        if self.tag:
            data["tag"] = self.tag
        if self.uid:
            data["uid"] = self.uid
        if self.props:
            data["props"] = self.props
        if self.ops:
            data["ops"] = self.ops
        if self.slots:
            data["slots"] = self.slots
        if self.events:
            data["events"] = self.events
        if self.message:
            data["message"] = self.message
        if self.items:
            data["items"] = [item.to_dict() for item in self.items]
        
        return json.dumps(data, ensure_ascii=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = {"type": self.type.value}
        
        if self.tag:
            data["tag"] = self.tag
        if self.uid:
            data["uid"] = self.uid
        if self.props:
            data["props"] = self.props
        if self.ops:
            data["ops"] = self.ops
        if self.slots:
            data["slots"] = self.slots
        if self.events:
            data["events"] = self.events
        if self.message:
            data["message"] = self.message
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisJsonLine":
        """Create from dictionary."""
        return cls(
            type=VisMessageType(data.get("type", "component")),
            tag=data.get("tag"),
            uid=data.get("uid"),
            props=data.get("props"),
            ops=data.get("ops"),
            slots=data.get("slots"),
            events=data.get("events"),
            message=data.get("message"),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "VisJsonLine":
        """Parse from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class JsonPatchOperation:
    """JSON Patch operation (RFC 6902)."""
    
    @staticmethod
    def add(path: str, value: Any) -> Dict[str, Any]:
        """Add operation."""
        return {"op": "add", "path": path, "value": value}
    
    @staticmethod
    def remove(path: str) -> Dict[str, Any]:
        """Remove operation."""
        return {"op": "remove", "path": path}
    
    @staticmethod
    def replace(path: str, value: Any) -> Dict[str, Any]:
        """Replace operation."""
        return {"op": "replace", "path": path, "value": value}
    
    @staticmethod
    def move(path: str, from_path: str) -> Dict[str, Any]:
        """Move operation."""
        return {"op": "move", "path": path, "from": from_path}
    
    @staticmethod
    def copy(path: str, from_path: str) -> Dict[str, Any]:
        """Copy operation."""
        return {"op": "copy", "path": path, "from": from_path}
    
    @staticmethod
    def test(path: str, value: Any) -> Dict[str, Any]:
        """Test operation."""
        return {"op": "test", "path": path, "value": value}


class VisJsonLinesConverter:
    """
    Converter for VIS JSON Lines protocol.
    
    Key advantages over markdown format:
    - Single line = complete message (streaming friendly)
    - Native JSON Patch support
    - Strict schema validation possible
    - 50%+ parsing performance improvement
    """
    
    def __init__(self):
        self._buffer: List[VisJsonLine] = []
    
    def create_component(
        self,
        tag: str,
        uid: str,
        props: Optional[Dict[str, Any]] = None,
        slots: Optional[Dict[str, List[str]]] = None,
    ) -> VisJsonLine:
        """Create a component message."""
        return VisJsonLine(
            type=VisMessageType.COMPONENT,
            tag=tag,
            uid=uid,
            props=props or {},
            slots=slots,
        )
    
    def create_patch(
        self,
        uid: str,
        ops: List[Dict[str, Any]],
    ) -> VisJsonLine:
        """Create a patch message for incremental updates."""
        return VisJsonLine(
            type=VisMessageType.PATCH,
            uid=uid,
            ops=ops,
        )
    
    def create_append_patch(
        self,
        uid: str,
        path: str,
        value: Any,
    ) -> VisJsonLine:
        """Create a patch that appends to a property."""
        return self.create_patch(uid, [
            JsonPatchOperation.add(f"{path}/-", value)
        ])
    
    def create_incremental_text(
        self,
        uid: str,
        text: str,
        path: str = "/props/markdown",
    ) -> VisJsonLine:
        """Create incremental text update."""
        return self.create_patch(uid, [
            JsonPatchOperation.add(path, text)
        ])
    
    def create_complete(self, uid: str) -> VisJsonLine:
        """Create a complete message."""
        return VisJsonLine(
            type=VisMessageType.COMPLETE,
            uid=uid,
        )
    
    def create_error(
        self,
        uid: Optional[str],
        message: str,
    ) -> VisJsonLine:
        """Create an error message."""
        return VisJsonLine(
            type=VisMessageType.ERROR,
            uid=uid,
            message=message,
        )
    
    def create_batch(
        self,
        items: List[VisJsonLine],
    ) -> VisJsonLine:
        """Create a batch message containing multiple items."""
        return VisJsonLine(
            type=VisMessageType.BATCH,
            items=items,
        )
    
    def to_jsonl(self, lines: List[VisJsonLine]) -> str:
        """Convert multiple lines to JSON Lines format."""
        return "\n".join(line.to_json() for line in lines)
    
    def from_jsonl(self, jsonl: str) -> List[VisJsonLine]:
        """Parse JSON Lines format to list of lines."""
        lines = []
        for line_str in jsonl.strip().split("\n"):
            if line_str.strip():
                lines.append(VisJsonLine.from_json(line_str))
        return lines
    
    def to_markdown_compat(self, line: VisJsonLine) -> str:
        """
        Convert JSON Line to legacy markdown format for backward compatibility.
        
        Format: ```tag\n{json}\n```
        """
        if line.type == VisMessageType.COMPONENT:
            props = line.props or {}
            props["uid"] = line.uid
            props["type"] = "all"
            
            return f"```{line.tag}\n{json.dumps(props, ensure_ascii=False)}\n```"
        
        elif line.type == VisMessageType.PATCH:
            props = {
                "uid": line.uid,
                "type": "incr",
                **{op["path"].split("/")[-1]: op.get("value") for op in (line.ops or [])}
            }
            
            return f"```vis-patch\n{json.dumps(props, ensure_ascii=False)}\n```"
        
        elif line.type == VisMessageType.COMPLETE:
            return f"[DONE:{line.uid}]"
        
        elif line.type == VisMessageType.ERROR:
            return f"[ERROR]{line.message}[/ERROR]"
        
        return ""
    
    def from_markdown_compat(self, markdown: str) -> List[VisJsonLine]:
        """
        Parse legacy markdown format to JSON Lines.
        
        Handles backward compatibility with existing markdown-based VIS.
        """
        import re
        
        lines = []
        
        pattern = r'```(\S+)\n(.*?)\n```'
        matches = re.findall(pattern, markdown, re.DOTALL)
        
        for tag, content in matches:
            try:
                props = json.loads(content)
                uid = props.pop("uid", None)
                msg_type = props.pop("type", "all")
                
                if msg_type == "incr":
                    ops = []
                    for key, value in props.items():
                        if value is not None:
                            ops.append(JsonPatchOperation.replace(f"/props/{key}", value))
                    
                    lines.append(self.create_patch(uid, ops))
                else:
                    lines.append(self.create_component(tag, uid, props))
            
            except json.JSONDecodeError:
                lines.append(self.create_error(None, f"Invalid JSON in block: {tag}"))
        
        return lines
    
    async def stream_to_jsonl(
        self,
        stream: AsyncIterator[VisJsonLine]
    ) -> AsyncIterator[str]:
        """Convert a stream of lines to JSON Lines strings."""
        async for line in stream:
            yield line.to_json() + "\n"
    
    async def stream_from_jsonl(
        self,
        stream: AsyncIterator[str]
    ) -> AsyncIterator[VisJsonLine]:
        """Parse a stream of JSON Lines strings."""
        buffer = ""
        
        async for chunk in stream:
            buffer += chunk
            
            while "\n" in buffer:
                line_str, buffer = buffer.split("\n", 1)
                if line_str.strip():
                    try:
                        yield VisJsonLine.from_json(line_str)
                    except json.JSONDecodeError as e:
                        yield self.create_error(None, f"JSON parse error: {e}")


class VisJsonLinesBuilder:
    """
    Builder for creating VIS JSON Lines sequences.
    
    Fluent API for constructing streaming VIS output.
    """
    
    def __init__(self):
        self._lines: List[VisJsonLine] = []
        self._converter = VisJsonLinesConverter()
    
    def component(
        self,
        tag: str,
        uid: str,
        props: Optional[Dict[str, Any]] = None,
        slots: Optional[Dict[str, List[str]]] = None,
    ) -> "VisJsonLinesBuilder":
        """Add a component message."""
        self._lines.append(self._converter.create_component(tag, uid, props, slots))
        return self
    
    def thinking(
        self,
        uid: str,
        markdown: str,
        is_incremental: bool = False,
    ) -> "VisJsonLinesBuilder":
        """Add a thinking component."""
        if is_incremental:
            self._lines.append(self._converter.create_incremental_text(
                uid, markdown, "/props/markdown"
            ))
        else:
            self._lines.append(self._converter.create_component(
                "vis-thinking", uid, {"markdown": markdown}
            ))
        return self
    
    def message(
        self,
        uid: str,
        markdown: str,
        role: Optional[str] = None,
        name: Optional[str] = None,
        avatar: Optional[str] = None,
        is_incremental: bool = False,
    ) -> "VisJsonLinesBuilder":
        """Add a message component."""
        props = {"markdown": markdown}
        if role:
            props["role"] = role
        if name:
            props["name"] = name
        if avatar:
            props["avatar"] = avatar
        
        if is_incremental:
            self._lines.append(self._converter.create_incremental_text(
                uid, markdown, "/props/markdown"
            ))
        else:
            self._lines.append(self._converter.create_component(
                "drsk-msg", uid, props
            ))
        return self
    
    def tool(
        self,
        uid: str,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        status: str = "running",
        output: Optional[str] = None,
    ) -> "VisJsonLinesBuilder":
        """Add a tool execution component."""
        props = {"name": name, "status": status}
        if args:
            props["args"] = args
        if output:
            props["output"] = output
        
        self._lines.append(self._converter.create_component("vis-tool", uid, props))
        return self
    
    def tool_complete(
        self,
        uid: str,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> "VisJsonLinesBuilder":
        """Mark tool as complete."""
        ops = [JsonPatchOperation.replace("/props/status", "completed")]
        if output:
            ops.append(JsonPatchOperation.replace("/props/output", output))
        if error:
            ops.append(JsonPatchOperation.replace("/props/error", error))
        
        self._lines.append(self._converter.create_patch(uid, ops))
        return self
    
    def complete(self, uid: str) -> "VisJsonLinesBuilder":
        """Add a complete marker."""
        self._lines.append(self._converter.create_complete(uid))
        return self
    
    def error(self, message: str, uid: Optional[str] = None) -> "VisJsonLinesBuilder":
        """Add an error message."""
        self._lines.append(self._converter.create_error(uid, message))
        return self
    
    def build(self) -> List[VisJsonLine]:
        """Build and return all lines."""
        return self._lines
    
    def to_jsonl(self) -> str:
        """Convert to JSON Lines string."""
        return self._converter.to_jsonl(self._lines)
    
    def to_markdown_compat(self) -> str:
        """Convert to legacy markdown format."""
        return "\n".join(
            self._converter.to_markdown_compat(line)
            for line in self._lines
        )
    
    def clear(self) -> "VisJsonLinesBuilder":
        """Clear all lines."""
        self._lines.clear()
        return self


def vis_builder() -> VisJsonLinesBuilder:
    """Create a new VIS JSON Lines builder."""
    return VisJsonLinesBuilder()