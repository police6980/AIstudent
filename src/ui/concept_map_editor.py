"""Visual, click-based concept map editor embedded in Gradio via SVG + JS.

Interaction model:
    - Double-click empty canvas → prompt for concept name → new node
    - Click node A, then click node B → prompt for linking phrase → new edge
    - Drag a node to reposition
    - Select a node/edge + press Delete → remove
    - Right-click a node/edge → context menu (rename / delete)

State is serialized to JSON and written to a hidden Gradio Textbox so the
Python layer can parse it as a ConceptMap. The resulting dict mirrors
the ParseResult from concept_map_ui: {concepts, propositions, cross_links,
examples}.
"""

from __future__ import annotations

import json
from typing import Any

import gradio as gr

from src.models.concept_map import (
    Concept,
    ConceptMap,
    CrossLink,
    Example,
    Proposition,
)


def build_visual_concept_map_editor(
    prefix: str,
    height_px: int = 520,
) -> dict[str, Any]:
    """Return Gradio components for a visual concept map editor.

    prefix: unique string used in DOM ids (e.g. 'pre_map', 'post_map').

    Returned dict keys the caller wires:
        'state_in'  — hidden gr.Textbox holding JSON state (consumed by Python)
        'html'      — gr.HTML with the SVG canvas + toolbar
    """

    # The hidden state textbox — JS writes JSON here; Python reads it.
    state_in = gr.Textbox(
        value="{}",
        visible=False,
        elem_id=f"cm-{prefix}-state",
    )

    html = gr.HTML(f"""
<div class="cm-wrapper" id="cm-{prefix}-wrapper">
  <div class="cm-toolbar">
    <button type="button" class="cm-btn" onclick="window.cmEditors['{prefix}'].addConceptPrompt()">
      ➕ 개념 추가
    </button>
    <button type="button" class="cm-btn" onclick="window.cmEditors['{prefix}'].addExamplePrompt()">
      🧪 예시 추가
    </button>
    <button type="button" class="cm-btn cm-btn-muted"
            onclick="window.cmEditors['{prefix}'].clearAll()">
      🗑️ 전체 지우기
    </button>
    <span class="cm-hint">
      💡 <b>사용법</b>: <b>개념 추가</b> → 캔버스에서 드래그로 이동 → 한 개념을 클릭한 뒤 다른 개념을 클릭하면 <b>연결선</b> 생성(연결어 입력) · 우클릭으로 삭제·이름변경
    </span>
  </div>
  <div class="cm-canvas-wrap">
    <svg id="cm-{prefix}-svg" class="cm-svg" width="100%" height="{height_px}"
         preserveAspectRatio="xMidYMid meet">
      <defs>
        <marker id="cm-{prefix}-arrow" viewBox="0 0 10 10" refX="10" refY="5"
                markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569"></path>
        </marker>
        <marker id="cm-{prefix}-arrow-cross" viewBox="0 0 10 10" refX="10" refY="5"
                markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#dc2626"></path>
        </marker>
      </defs>
      <g class="cm-edges"></g>
      <g class="cm-nodes"></g>
    </svg>
  </div>
  <div class="cm-stats" id="cm-{prefix}-stats">개념 0 · 연결 0 · 예시 0</div>
</div>

<script>
(function() {{
  if (typeof window.cmEditors === 'undefined') window.cmEditors = {{}};
  const PREFIX = '{prefix}';
  const HEIGHT = {height_px};
  const svg = document.getElementById('cm-' + PREFIX + '-svg');
  const edgesLayer = svg.querySelector('.cm-edges');
  const nodesLayer = svg.querySelector('.cm-nodes');
  const stateEl = document.querySelector('#cm-' + PREFIX + '-state textarea');
  const statsEl = document.getElementById('cm-' + PREFIX + '-stats');

  const state = {{
    nextId: 1,
    concepts: [], // {{id, label, x, y}}
    edges: [],    // {{id, from, to, linking, isCross}}
    examples: [], // {{concept_id, text}}
    pendingFromId: null,
  }};

  function saveToHidden() {{
    const serial = {{
      concepts: state.concepts.map(c => ({{id: c.id, label: c.label}})),
      propositions: state.edges.filter(e => !e.isCross).map(e => ({{
        from_id: e.from, to_id: e.to, linking_phrase: e.linking
      }})),
      cross_links: state.edges.filter(e => e.isCross).map(e => ({{
        from_id: e.from, to_id: e.to, linking_phrase: e.linking
      }})),
      examples: state.examples.map(ex => ({{
        concept_id: ex.concept_id, text: ex.text
      }})),
      _layout: state.concepts.map(c => ({{id: c.id, x: c.x, y: c.y}})),
    }};
    if (stateEl) {{
      stateEl.value = JSON.stringify(serial);
      stateEl.dispatchEvent(new Event('input', {{bubbles: true}}));
    }}
    const propCount = state.edges.filter(e => !e.isCross).length;
    const crossCount = state.edges.filter(e => e.isCross).length;
    statsEl.textContent = `개념 ${{state.concepts.length}} · 연결 ${{propCount}}`
      + (crossCount ? ` · 교차연결 ${{crossCount}}` : '')
      + ` · 예시 ${{state.examples.length}}`;
  }}

  function makeSvgEl(name, attrs, text) {{
    const el = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (text !== undefined) el.textContent = text;
    return el;
  }}

  function render() {{
    nodesLayer.innerHTML = '';
    edgesLayer.innerHTML = '';

    // Edges
    state.edges.forEach(edge => {{
      const a = state.concepts.find(c => c.id === edge.from);
      const b = state.concepts.find(c => c.id === edge.to);
      if (!a || !b) return;
      const color = edge.isCross ? '#dc2626' : '#475569';
      const dash = edge.isCross ? '6,4' : '';
      const marker = edge.isCross
        ? `url(#cm-${{PREFIX}}-arrow-cross)` : `url(#cm-${{PREFIX}}-arrow)`;
      // Line
      const line = makeSvgEl('line', {{
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        stroke: color, 'stroke-width': 2,
        'stroke-dasharray': dash,
        'marker-end': marker,
        'data-edge-id': edge.id,
        class: 'cm-edge',
      }});
      line.addEventListener('contextmenu', ev => {{
        ev.preventDefault();
        showEdgeMenu(ev, edge);
      }});
      edgesLayer.appendChild(line);
      // Label
      const midX = (a.x + b.x) / 2;
      const midY = (a.y + b.y) / 2;
      const labelBg = makeSvgEl('rect', {{
        x: midX - (edge.linking.length * 4 + 6),
        y: midY - 10,
        width: edge.linking.length * 8 + 12,
        height: 20,
        rx: 6, ry: 6,
        fill: 'white',
        stroke: color,
        'stroke-width': 1,
        class: 'cm-edge-bg',
      }});
      const label = makeSvgEl('text', {{
        x: midX, y: midY + 4,
        'text-anchor': 'middle',
        'font-size': 12,
        fill: color,
        class: 'cm-edge-label',
      }}, edge.linking);
      edgesLayer.appendChild(labelBg);
      edgesLayer.appendChild(label);
    }});

    // Nodes
    state.concepts.forEach(c => {{
      const g = makeSvgEl('g', {{
        class: 'cm-node',
        transform: `translate(${{c.x}},${{c.y}})`,
        'data-id': c.id,
      }});
      const isPending = state.pendingFromId === c.id;
      const r = Math.max(32, c.label.length * 6 + 12);
      const rect = makeSvgEl('rect', {{
        x: -r, y: -20, width: r * 2, height: 40,
        rx: 12, ry: 12,
        fill: isPending ? '#fde68a' : '#eef2ff',
        stroke: isPending ? '#d97706' : '#4f46e5',
        'stroke-width': isPending ? 3 : 1.5,
      }});
      const txt = makeSvgEl('text', {{
        x: 0, y: 5,
        'text-anchor': 'middle',
        'font-size': 13,
        'font-weight': 600,
        fill: '#1e293b',
      }}, c.label);
      g.appendChild(rect);
      g.appendChild(txt);

      // Examples attached to this concept
      const exs = state.examples.filter(ex => ex.concept_id === c.id);
      exs.forEach((ex, i) => {{
        const exBg = makeSvgEl('rect', {{
          x: r + 10, y: 5 + i * 22 - 10,
          width: ex.text.length * 7 + 16,
          height: 18,
          rx: 9, ry: 9,
          fill: '#fef9c3',
          stroke: '#ca8a04',
          'stroke-width': 1,
        }});
        const exTxt = makeSvgEl('text', {{
          x: r + 18, y: 5 + i * 22 + 3,
          'font-size': 11,
          fill: '#713f12',
        }}, ex.text);
        g.appendChild(exBg);
        g.appendChild(exTxt);
      }});

      // Click: start-or-finish edge
      g.addEventListener('click', ev => {{
        if (draggedId) return; // suppressed after drag
        ev.stopPropagation();
        onNodeClick(c.id);
      }});
      // Drag
      g.addEventListener('mousedown', ev => {{
        if (ev.button !== 0) return;
        startDrag(c.id, ev);
      }});
      // Right-click
      g.addEventListener('contextmenu', ev => {{
        ev.preventDefault();
        showNodeMenu(ev, c);
      }});
      nodesLayer.appendChild(g);
    }});
  }}

  function onNodeClick(id) {{
    if (state.pendingFromId && state.pendingFromId !== id) {{
      const linking = (prompt('두 개념 사이의 연결어를 입력하세요 (예: \"의 조건은\", \"이 일어나는 곳은\")') || '').trim();
      if (linking) {{
        const isCross = confirm('이 연결이 "교차연결" 인가요? (서로 다른 가지를 잇는 특별한 연결)\\n확인 = 예(교차연결) / 취소 = 아니오(일반 명제)');
        state.edges.push({{
          id: state.nextId++,
          from: state.pendingFromId,
          to: id,
          linking: linking,
          isCross: isCross,
        }});
      }}
      state.pendingFromId = null;
    }} else if (state.pendingFromId === id) {{
      state.pendingFromId = null;
    }} else {{
      state.pendingFromId = id;
    }}
    render();
    saveToHidden();
  }}

  let draggedId = null;
  let dragOffset = {{x: 0, y: 0}};
  let dragStartPos = {{x: 0, y: 0}};

  function startDrag(id, ev) {{
    const c = state.concepts.find(cc => cc.id === id);
    if (!c) return;
    const pt = getSvgPoint(ev);
    dragOffset = {{x: pt.x - c.x, y: pt.y - c.y}};
    dragStartPos = {{x: c.x, y: c.y}};
    draggedId = id;
    function onMove(mv) {{
      if (!draggedId) return;
      const p = getSvgPoint(mv);
      const node = state.concepts.find(cc => cc.id === draggedId);
      if (node) {{
        node.x = p.x - dragOffset.x;
        node.y = p.y - dragOffset.y;
        render();
      }}
    }}
    function onUp(up) {{
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      const node = state.concepts.find(cc => cc.id === draggedId);
      const moved = node &&
        (Math.abs(node.x - dragStartPos.x) + Math.abs(node.y - dragStartPos.y) > 4);
      // If it wasn't really a drag, treat as a click (handled by click listener).
      setTimeout(() => {{ draggedId = null; }}, moved ? 100 : 0);
      saveToHidden();
    }}
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }}

  function getSvgPoint(ev) {{
    const rect = svg.getBoundingClientRect();
    const w = rect.width || 800;
    const h = rect.height || HEIGHT;
    return {{x: ev.clientX - rect.left, y: ev.clientY - rect.top}};
  }}

  function showNodeMenu(ev, concept) {{
    const action = prompt(
      `'${{concept.label}}'\\n1 = 이름 바꾸기 / 2 = 삭제 / 빈값 = 취소`,
      ''
    );
    if (action === '1') {{
      const newLabel = (prompt('새 이름', concept.label) || '').trim();
      if (newLabel) {{
        concept.label = newLabel;
        render();
        saveToHidden();
      }}
    }} else if (action === '2') {{
      deleteConcept(concept.id);
    }}
  }}

  function showEdgeMenu(ev, edge) {{
    const action = prompt(
      `연결 "${{edge.linking}}"\\n1 = 연결어 바꾸기 / 2 = 일반↔교차연결 토글 / 3 = 삭제 / 빈값 = 취소`,
      ''
    );
    if (action === '1') {{
      const newLink = (prompt('새 연결어', edge.linking) || '').trim();
      if (newLink) {{
        edge.linking = newLink;
        render();
        saveToHidden();
      }}
    }} else if (action === '2') {{
      edge.isCross = !edge.isCross;
      render();
      saveToHidden();
    }} else if (action === '3') {{
      state.edges = state.edges.filter(e => e.id !== edge.id);
      render();
      saveToHidden();
    }}
  }}

  function deleteConcept(id) {{
    if (!confirm('이 개념과 관련된 모든 연결·예시도 같이 삭제됩니다. 계속?')) return;
    state.concepts = state.concepts.filter(c => c.id !== id);
    state.edges = state.edges.filter(e => e.from !== id && e.to !== id);
    state.examples = state.examples.filter(ex => ex.concept_id !== id);
    if (state.pendingFromId === id) state.pendingFromId = null;
    render();
    saveToHidden();
  }}

  // Background double-click → add concept at that position
  svg.addEventListener('dblclick', ev => {{
    if (ev.target !== svg && ev.target.tagName !== 'g') {{
      // ignore double-clicks directly on shapes
      return;
    }}
    const pt = getSvgPoint(ev);
    const name = (prompt('새 개념 이름 (예: 용해, 용액, 용질)') || '').trim();
    if (!name) return;
    state.concepts.push({{
      id: state.nextId++,
      label: name,
      x: pt.x,
      y: pt.y,
    }});
    render();
    saveToHidden();
  }});

  const editor = {{
    addConceptPrompt() {{
      const name = (prompt('새 개념 이름 (예: 용해, 용액, 용질)') || '').trim();
      if (!name) return;
      const rect = svg.getBoundingClientRect();
      state.concepts.push({{
        id: state.nextId++,
        label: name,
        x: 80 + Math.random() * (rect.width - 160),
        y: 80 + Math.random() * (HEIGHT - 160),
      }});
      render();
      saveToHidden();
    }},
    addExamplePrompt() {{
      if (state.concepts.length === 0) {{
        alert('먼저 개념을 하나 이상 추가해주세요.');
        return;
      }}
      const labels = state.concepts.map((c, i) => `${{i+1}}. ${{c.label}}`).join('\\n');
      const pick = prompt(
        `어느 개념에 예시를 추가할까요? 번호 입력:\\n${{labels}}`, '1'
      );
      const idx = parseInt(pick, 10) - 1;
      if (isNaN(idx) || idx < 0 || idx >= state.concepts.length) return;
      const text = (prompt('예시 내용 (예: "설탕은 포도당의 변형")') || '').trim();
      if (!text) return;
      state.examples.push({{
        concept_id: state.concepts[idx].id,
        text: text,
      }});
      render();
      saveToHidden();
    }},
    clearAll() {{
      if (!confirm('모든 개념·연결·예시를 지울까요?')) return;
      state.concepts = [];
      state.edges = [];
      state.examples = [];
      state.pendingFromId = null;
      state.nextId = 1;
      render();
      saveToHidden();
    }},
    getState() {{ return state; }},
  }};
  window.cmEditors[PREFIX] = editor;
  render();
  saveToHidden();
}})();
</script>
""")

    return {
        "state_in": state_in,
        "html": html,
    }


def parse_visual_concept_map(json_text: str) -> ConceptMap:
    """Parse the JSON produced by the visual editor into a ConceptMap."""

    if not json_text or not json_text.strip():
        raise ValueError("개념도가 비어있어요. 최소한 몇 개의 개념을 추가해주세요.")
    try:
        raw = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"개념도 데이터 파싱 실패: {exc}") from exc

    concepts_raw = raw.get("concepts") or []
    if not concepts_raw:
        raise ValueError("개념이 하나도 없어요. 캔버스에서 '+ 개념 추가' 버튼으로 추가해주세요.")

    # JS-assigned integer ids → string ids that match pydantic constraints
    id_map: dict = {}
    concepts: list[Concept] = []
    for c in concepts_raw:
        jid = c.get("id")
        label = (c.get("label") or "").strip()
        if not label:
            continue
        sid = f"c{jid}"
        id_map[jid] = sid
        concepts.append(Concept(id=sid, label=label))

    def _translate(edge_raw):
        fid = id_map.get(edge_raw.get("from_id"))
        tid = id_map.get(edge_raw.get("to_id"))
        linking = (edge_raw.get("linking_phrase") or "").strip()
        if not fid or not tid or not linking:
            return None
        return fid, tid, linking

    propositions: list[Proposition] = []
    for p in raw.get("propositions") or []:
        translated = _translate(p)
        if translated:
            fid, tid, linking = translated
            propositions.append(
                Proposition(from_id=fid, to_id=tid, linking_phrase=linking)
            )

    cross_links: list[CrossLink] = []
    for p in raw.get("cross_links") or []:
        translated = _translate(p)
        if translated:
            fid, tid, linking = translated
            cross_links.append(
                CrossLink(from_id=fid, to_id=tid, linking_phrase=linking)
            )

    examples: list[Example] = []
    for ex in raw.get("examples") or []:
        cid = id_map.get(ex.get("concept_id"))
        text = (ex.get("text") or "").strip()
        if cid and text:
            examples.append(Example(concept_id=cid, text=text))

    return ConceptMap(
        concepts=concepts,
        propositions=propositions,
        cross_links=cross_links,
        examples=examples,
    )
