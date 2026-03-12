import { useRef, useEffect } from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";

export interface GraphNode {
  id: string;
  name: string;
  type: string;
  mention_count?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  label?: string;
}

interface SimNode extends SimulationNodeDatum, GraphNode {}
interface SimLink extends SimulationLinkDatum<SimNode> {
  label?: string;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

function measureTextWidth(text: string): number {
  return text.length * 11 * 0.6;
}

export default function EntityGraph({ nodes, edges }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || nodes.length === 0) return;

    const width = svg.clientWidth || 900;
    const height = svg.clientHeight || 500;

    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

    // Clear previous contents
    svg.innerHTML = "";

    // Build simulation data
    const simNodes: SimNode[] = nodes.map((n) => ({
      ...n,
      x: Math.random() * width,
      y: Math.random() * height,
    }));

    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

    const simLinks: SimLink[] = edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        label: e.label,
      }));

    // Create SVG elements
    const edgeGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const nodeGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
    svg.appendChild(edgeGroup);
    svg.appendChild(nodeGroup);

    // Create edge lines
    const lineEls: SVGLineElement[] = simLinks.map(() => {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("stroke", "#b8b0a0");
      line.setAttribute("stroke-dasharray", "4 4");
      line.setAttribute("stroke-width", "1");
      edgeGroup.appendChild(line);
      return line;
    });

    // Create node groups
    const PAD_X = 12;
    const RECT_H = 28;

    const nodeEls: SVGGElement[] = simNodes.map((n) => {
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.style.cursor = "grab";

      const textW = measureTextWidth(n.name);
      const rectW = textW + PAD_X * 2;
      const isRisk = n.type === "risk_level";

      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(-rectW / 2));
      rect.setAttribute("y", String(-RECT_H / 2));
      rect.setAttribute("width", String(rectW));
      rect.setAttribute("height", String(RECT_H));
      rect.setAttribute("stroke", "var(--border-strong)");
      rect.setAttribute("stroke-width", "1");
      rect.setAttribute("fill", isRisk ? "var(--accent)" : "transparent");

      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("dominant-baseline", "central");
      text.setAttribute("font-family", "var(--font-mono)");
      text.setAttribute("font-size", "11");
      text.setAttribute("letter-spacing", "0.03em");
      text.setAttribute("fill", isRisk ? "#fff" : "var(--ink-primary)");
      text.textContent = n.name;

      g.appendChild(rect);
      g.appendChild(text);
      nodeGroup.appendChild(g);

      return g;
    });

    // Node radii for collision
    const nodeRadii = simNodes.map((n) => {
      const textW = measureTextWidth(n.name);
      return (textW + PAD_X * 2) / 2 + 8;
    });

    // Simulation
    const simulation = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(140)
      )
      .force("charge", forceManyBody().strength(-300))
      .force("center", forceCenter(width / 2, height / 2))
      .force(
        "collide",
        forceCollide<SimNode>().radius((_, i) => nodeRadii[i])
      );

    simulation.on("tick", () => {
      for (let i = 0; i < simLinks.length; i++) {
        const s = simLinks[i].source as SimNode;
        const t = simLinks[i].target as SimNode;
        lineEls[i].setAttribute("x1", String(s.x ?? 0));
        lineEls[i].setAttribute("y1", String(s.y ?? 0));
        lineEls[i].setAttribute("x2", String(t.x ?? 0));
        lineEls[i].setAttribute("y2", String(t.y ?? 0));
      }

      for (let i = 0; i < simNodes.length; i++) {
        nodeEls[i].setAttribute(
          "transform",
          `translate(${simNodes[i].x ?? 0},${simNodes[i].y ?? 0})`
        );
      }
    });

    // Drag support via mouse events
    let dragNode: SimNode | null = null;

    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Element;
      const g = target.closest("g[style]");
      if (!g) return;
      const idx = nodeEls.indexOf(g as SVGGElement);
      if (idx === -1) return;

      dragNode = simNodes[idx];
      dragNode.fx = dragNode.x;
      dragNode.fy = dragNode.y;
      simulation.alphaTarget(0.3).restart();
      (g as SVGGElement).style.cursor = "grabbing";
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!dragNode) return;
      const rect = svg.getBoundingClientRect();
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;
      dragNode.fx = (e.clientX - rect.left) * scaleX;
      dragNode.fy = (e.clientY - rect.top) * scaleY;
    };

    const onMouseUp = () => {
      if (!dragNode) return;
      simulation.alphaTarget(0);
      dragNode.fx = null;
      dragNode.fy = null;
      dragNode = null;
      nodeEls.forEach((g) => (g.style.cursor = "grab"));
    };

    svg.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      simulation.stop();
      svg.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [nodes, edges]);

  return (
    <svg
      ref={svgRef}
      width="100%"
      height="100%"
      style={{ display: "block" }}
    />
  );
}
