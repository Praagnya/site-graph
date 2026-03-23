import hashlib
import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class InteractiveElement(BaseModel):
    id: str  # e.g., "elem-1"
    tag: str
    text: str
    role: Optional[str] = None
    href: Optional[str] = None

class Action(BaseModel):
    type: str  # e.g., "click", "fill", "finish"
    target: Optional[str] = None  # the element id
    value: Optional[str] = None # text to fill
    description: str

class Node(BaseModel):
    id: str
    url: str
    title: str
    dom_fingerprint: str
    interactive_elements: List[Dict[str, Any]]
    screenshot: str

class Edge(BaseModel):
    from_node: str
    to_node: str
    action: Action

class StateGraph(BaseModel):
    nodes: List[Node] = []
    edges: List[Edge] = []

def compute_fingerprint(elements: List[Dict[str, Any]]) -> str:
    """
    Compute a consistent structural fingerprint of the page based on interactive elements.
    We just map over the elements and keep tag, text, role, href.
    """
    # Create a simplified list to hash
    simplified = []
    for el in elements:
        simplified.append({
            "tag": el.get("tag", "").upper(),
            "text": str(el.get("text", "")).strip(),
            "role": el.get("role", ""),
            "href": el.get("href", ""),
        })
    
    # Sort or directly serialize depending on application logic.
    # In SPAs, element order matters. We won't sort, we keep DOM order.
    schema_str = json.dumps(simplified, sort_keys=True)
    return hashlib.sha256(schema_str.encode('utf-8')).hexdigest()

class GraphTracker:
    def __init__(self):
        self.graph = StateGraph()
        self.node_counter = 0

    def add_node(self, url: str, title: str, elements: List[Dict[str, Any]], screenshot_path: str) -> bool:
        """
        Adds a new node if it does not exist based on fingerprint. 
        Returns True if node was newly added, False if it already existed.
        """
        fingerprint = compute_fingerprint(elements)
        # Check if exists
        for node in self.graph.nodes:
            if node.dom_fingerprint == fingerprint and node.url == url:
                return False, node.id
        
        self.node_counter += 1
        node_id = f"state_{self.node_counter:03d}"
        
        new_node = Node(
            id=node_id,
            url=url,
            title=title,
            dom_fingerprint=fingerprint,
            interactive_elements=elements,
            screenshot=screenshot_path
        )
        self.graph.nodes.append(new_node)
        return True, node_id

    def add_edge(self, from_id: str, to_id: str, action: Action):
        # Prevent duplicate edges conceptually if wanted, but simpler to just append
        new_edge = Edge(from_node=from_id, to_node=to_id, action=action)
        self.graph.edges.append(new_edge)

    def to_json(self):
        return self.graph.model_dump_json(indent=2)
