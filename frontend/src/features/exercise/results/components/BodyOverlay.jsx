import React, { useMemo } from "react";
import humanBodyHitAreasSvgRaw from "../../../../assets/body/overlays/human_body_hitareas.svg?raw";

export default function BodyOverlay({
  selectedRegion,
  enabledRegions,
  onSelectRegion,
  onHoverRegion,
  onLeaveRegion,
  hoverGroups = null, // { region_id: "group_name" } — 같은 그룹은 <g>로 묶어 CSS hover 동시 처리
}) {
  const enabledRegionSet = enabledRegions ? new Set(enabledRegions) : null;

  const { viewBox, paths } = useMemo(() => {
    if (typeof window === "undefined") {
      return { viewBox: "0 0 1024 1536", paths: [] };
    }
    const parser = new DOMParser();
    const doc = parser.parseFromString(humanBodyHitAreasSvgRaw, "image/svg+xml");
    const svgElement = doc.querySelector("svg");
    const viewBox = svgElement?.getAttribute("viewBox") || "0 0 1024 1536";
    const paths = Array.from(svgElement?.querySelectorAll("path") || []).map((path) => ({
      id: path.getAttribute("id"),
      d: path.getAttribute("d"),
    }));
    return { viewBox, paths };
  }, []);

  // hoverGroups가 있으면 그룹별로 분류, 없으면 flat 렌더
  const { groupMap, singles } = useMemo(() => {
    if (!hoverGroups) return { groupMap: null, singles: paths };
    const groupMap = {};
    const singles = [];
    for (const p of paths) {
      const g = hoverGroups[p.id];
      if (g) {
        if (!groupMap[g]) groupMap[g] = [];
        groupMap[g].push(p);
      } else {
        singles.push(p);
      }
    }
    return { groupMap, singles };
  }, [paths, hoverGroups]);

  const renderPath = ({ id, d }) => {
    const enabled = enabledRegionSet ? enabledRegionSet.has(id) : true;
    return (
      <path
        key={id}
        id={id}
        d={d}
        className={`body-overlay__path ${enabled ? "enabled" : "disabled"}`}
        style={{ pointerEvents: enabled ? "all" : "none" }}
        onMouseEnter={() => { if (!enabled) return; onHoverRegion?.(id); }}
        onMouseLeave={() => { if (!enabled) return; onLeaveRegion?.(); }}
        onClick={() => { if (!enabled) return; onSelectRegion?.(id); }}
      />
    );
  };

  return (
    <div className="absolute inset-0" aria-hidden="true">
      <svg
        viewBox={viewBox}
        className="h-full w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <radialGradient id="bodyOverlayGlow" cx="50%" cy="50%" r="50%" fx="50%" fy="50%" gradientUnits="objectBoundingBox">
            <stop offset="0%" stopColor="rgba(34,211,238,0.85)" />
            <stop offset="35%" stopColor="rgba(34,211,238,0.38)" />
            <stop offset="100%" stopColor="rgba(34,211,238,0)" />
          </radialGradient>
        </defs>
        <style>{`
          .body-overlay__path {
            fill: transparent;
            stroke: transparent;
            stroke-width: 0;
            filter: none;
            cursor: default;
          }

          .body-overlay__path.enabled {
            fill: url(#bodyOverlayGlow);
            fill-opacity: 0.18;
            animation: bodyGlowPulse 2.5s ease-in-out infinite;
            cursor: pointer;
          }

          .body-overlay__path.enabled:hover {
            animation: none;
            fill-opacity: 0.45;
          }

          /* 그룹 <g>가 hover되면 (= 그룹 내 어느 path든 hover되면) 그룹 전체 동시 점등 */
          .body-overlay__group:hover .body-overlay__path.enabled {
            animation: none;
            fill-opacity: 0.45;
          }

          .body-overlay__path.disabled {
            opacity: 0;
            pointer-events: none;
          }

          @keyframes bodyGlowPulse {
            0% {
              fill-opacity: 0.12;
              filter: drop-shadow(0 0 2px rgba(34,211,238,0.2));
            }
            50% {
              fill-opacity: 0.38;
              filter: drop-shadow(0 0 12px rgba(34,211,238,0.55));
            }
            100% {
              fill-opacity: 0.12;
              filter: drop-shadow(0 0 2px rgba(34,211,238,0.2));
            }
          }
        `}</style>

        {/* 그룹 path: 같은 그룹을 <g class="body-overlay__group">으로 묶음 */}
        {groupMap && Object.entries(groupMap).map(([groupName, groupPaths]) => (
          <g key={groupName} className="body-overlay__group">
            {groupPaths.map(renderPath)}
          </g>
        ))}

        {/* 단독 path (그룹 없음) */}
        {singles.map(renderPath)}
      </svg>
    </div>
  );
}
