import hashlib
import json
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field


class Action(BaseModel):
    type: str                       # "click" | "fill" | "press" | "finish"
    target: Optional[str] = None
    value: Optional[str] = None     # text for "fill"
    key: Optional[str] = None       # key for "press" e.g. "Enter"
    description: str


class Node(BaseModel):
    id: str
    url: str
    title: str
    dom_fingerprint: str
    interactive_elements: List[str]  # list of element IDs e.g. ["el_0", "el_1"]
    screenshot: str


class Edge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    action: Action

    model_config = {"populate_by_name": True}


class StateGraph(BaseModel):
    nodes: List[Node] = []
    edges: List[Edge] = []


def compute_fingerprint(url: str, elements: List[Dict[str, Any]]) -> str:
    """
    Hash of (url + visible element tags/texts) — unique per visual state.
    Same URL with a modal open will produce a different fingerprint.
    """
    simplified = [
        {"tag": el.get("tag", "").lower(), "text": el.get("text", "").strip()}
        for el in elements
    ]
    raw = json.dumps({"url": url, "elements": simplified}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class GraphTracker:
    def __init__(self):
        self.graph = StateGraph()
        self._counter = 0
        self._seen: Dict[str, str] = {}  # fingerprint -> node_id

    def add_node(self, url: str, title: str, elements: list, screenshot: str) -> Tuple[bool, str]:
        """
        Returns (is_new, node_id).
        If the fingerprint already exists, returns the existing node_id.
        """
        fp = compute_fingerprint(url, elements)
        if fp in self._seen:
            return False, self._seen[fp]

        self._counter += 1
        node_id = f"state_{self._counter:03d}"
        self._seen[fp] = node_id

        self.graph.nodes.append(Node(
            id=node_id,
            url=url,
            title=title,
            dom_fingerprint=fp,
            interactive_elements=[el["id"] for el in elements],
            screenshot=screenshot,
        ))
        return True, node_id

    def add_edge(self, from_id: str, to_id: str, action: Action):
        # Skip duplicate edges (same transition already recorded)
        for e in self.graph.edges:
            if e.from_ == from_id and e.to == to_id and e.action.target == action.target:
                return
        self.graph.edges.append(Edge(**{"from": from_id, "to": to_id, "action": action}))

    def to_json(self) -> str:
        return self.graph.model_dump_json(indent=2, by_alias=True)
