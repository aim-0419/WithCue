// /WithCue/withcue-web/frontend/src/components/WsCamera.jsx
// CheckPage.jsx, ExercisePage.jsx 실시간 카메라 Backend 연결

//  - msg.type
// "frame" → 항상 들어오는 실시간 스트림
//  - msg.data.status
// "preparing" → 준비 중
// "measuring" → 측정 중
// "stage_finished" → 한 자세 끝
// "finished" → 전체 끝

import { useEffect, useRef, useState } from "react";

export default function WsCamera({
  wsUrl,
  onState,
  onResult,
  showSkeleton = true,
  enabled = true,
}) {
  const wsRef = useRef(null);
  const onStateRef = useRef(onState);
  const onResultRef = useRef(onResult);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const enabledRef = useRef(enabled);
  const instanceIdRef = useRef(Math.random().toString(36).slice(2, 8));

  const imgRef = useRef(null);
  const canvasRef = useRef(null);

  const [imgSrc, setImgSrc] = useState("");
  const [statusText, setStatusText] = useState("connecting...");

  useEffect(() => {
    onStateRef.current = onState;
    onResultRef.current = onResult;
  }, [onState, onResult]);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (wsRef.current) {
        const ws = wsRef.current;
        wsRef.current = null;
        try {
          console.log("[WS] force close (disabled)", instanceIdRef.current);
          ws.close(1000, "disabled");
        } catch {}
      }
      return;
    }
    if (!wsUrl) return;

    // 이전 소켓 정리
    if (wsRef.current) {
      const prev = wsRef.current;
      wsRef.current = null;
      try {
        prev.onopen = prev.onclose = prev.onerror = prev.onmessage = null;
        // CONNECTING이어도 닫되, “내가 만든 것”만 닫게 분리
        prev.close(1000, "reconnect");
      } catch { }
    }

    const connect = () => {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      setStatusText("connecting...");

      ws.onopen = () => {
        console.log("[WS] open", wsUrl);
        setStatusText("connected");
        reconnectAttemptRef.current = 0;
      };
      ws.onerror = (e) => {
        console.error("[WS] error", wsUrl, e);
        setStatusText("ws error");
      };
      ws.onclose = (e) => {
        console.warn("[WS] close", wsUrl, {
          code: e.code,
          reason: e.reason,
          wasClean: e.wasClean,
          enabled: enabledRef.current,
          instance: instanceIdRef.current,
        });
        setStatusText(`closed (${e.code})`);
        if (!enabledRef.current) {
          return;
        }
        if (reconnectTimerRef.current) return;
        reconnectAttemptRef.current += 1;
        const delay = Math.min(8000, 1000 * reconnectAttemptRef.current);
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          if (wsRef.current === null) return;
          connect();
        }, delay);
      };

      ws.onmessage = (evt) => {
      
        let msg;
        try { msg = JSON.parse(evt.data); } catch { return; }

        if (msg.type === "frame") {
          if (!enabledRef.current) {
            if (wsRef.current) {
              console.log("[WS] close on message while disabled", instanceIdRef.current);
              try { wsRef.current.close(1000, "disabled"); } catch {}
              wsRef.current = null;
            }
            return;
          }
          if (msg.jpeg_b64) setImgSrc(`data:image/jpeg;base64,${msg.jpeg_b64}`);

          const data = msg.data || {};

          // ref로 호출
          onStateRef.current?.(data);

          if (data.status === "stage_finished" || data.status === "finished") {
            onResultRef.current?.(data);
          }

          if (data.message) setStatusText(data.message);
          else if (data.status) setStatusText(data.status);

          if (showSkeleton) drawOverlay(canvasRef.current, imgRef.current, data);
          else clearCanvas(canvasRef.current);
        }
      };
    };

    connect();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      // “내가 만든 ws”만 닫기 (경합 방지)
      if (wsRef.current) {
        console.log("[WS] cleanup close", instanceIdRef.current);
        try { wsRef.current.close(1000, "cleanup"); } catch {}
        wsRef.current = null;
      }
    };
  }, [wsUrl, showSkeleton, enabled]);


  return (
    <>
      <div className="ws-wrap">
        <img
          ref={imgRef}
          className="ws-img"
          src={imgSrc || null}
          alt="live"
        />
        <canvas ref={canvasRef} className="ws-canvas" />
        {!imgSrc && <div className="ws-ph">{statusText}</div>}
      </div>

      <style>{`
        .ws-wrap{
          position:relative;
          width:100%;
          height:100%;
          background:#000;
          overflow:hidden;
        }
        .ws-img{
          position:absolute;
          inset:0;
          width:100%;
          height:100%;
          object-fit:cover;
          display:block;
        }
        .ws-canvas{
          position:absolute;
          inset:0;
          width:100%;
          height:100%;
          pointer-events:none;
        }
        .ws-ph{
          position:absolute;
          inset:0;
          display:flex;
          align-items:center;
          justify-content:center;
          color:#fff;
          font-weight:800;
          opacity:0.75;
          padding:12px;
          text-align:center;
        }
      `}</style>
    </>
  );
}

//coco17 keypoint
const EDGES = [
  [5, 7], [7, 9],
  [6, 8], [8, 10],
  [5, 6],
  [11, 12],
  [5, 11], [6, 12],
  [11, 13], [13, 15],
  [12, 14], [14, 16],
  [0, 1], [0, 2], [1, 3], [2, 4],
  [3, 5], [4, 6],
];

function clearCanvas(canvas) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function drawOverlay(canvas, img, data) {
  if (!canvas || !img || !img.complete) return;

  const kpts = data?.keypoints;
  if (!kpts || Object.keys(kpts).length === 0) {
    clearCanvas(canvas);
    return;
  }

  // 캔버스 화면 크기
  const rect = canvas.getBoundingClientRect();
  const dstW = Math.max(1, Math.round(rect.width));
  const dstH = Math.max(1, Math.round(rect.height));

  // DPR 반영
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(dstW * dpr);
  canvas.height = Math.round(dstH * dpr);

  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, dstW, dstH);

  // 백엔드가 알려주면 그걸 우선 사용(추천)
  const srcW = data?.frame_w || img.naturalWidth || 1280;
  const srcH = data?.frame_h || img.naturalHeight || 720;

  // object-fit: cover 보정
  const scale = Math.max(dstW / srcW, dstH / srcH);
  const drawW = srcW * scale;
  const drawH = srcH * scale;
  const padX = (dstW - drawW) / 2;
  const padY = (dstH - drawH) / 2;

  const getP = (i) => {
    const p = kpts[i] || kpts[String(i)];
    if (!p) return null;
    return { x: p.x, y: p.y };
  };

  const toScreen = (p) => {
    const isPixel = p.x > 1.5 || p.y > 1.5;

    if (isPixel) {
      return {
        x: padX + p.x * scale,
        y: padY + p.y * scale,
      };
    }

    return {
      x: padX + p.x * drawW,
      y: padY + p.y * drawH,
    };
  };

  // 선
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(59,130,246,0.95)";
  ctx.shadowBlur = 8;
  ctx.shadowColor = "rgba(59,130,246,0.35)";
  ctx.beginPath();
  for (const [a, b] of EDGES) {
    const pa = getP(a);
    const pb = getP(b);
    if (!pa || !pb) continue;
    const A = toScreen(pa);
    const B = toScreen(pb);
    ctx.moveTo(A.x, A.y);
    ctx.lineTo(B.x, B.y);
  }
  ctx.stroke();
  ctx.shadowBlur = 0;

  // 점
  ctx.fillStyle = "rgba(255,255,255,0.95)";
  ctx.strokeStyle = "rgba(0,0,0,0.35)";
  ctx.lineWidth = 2;
  for (let i = 0; i < 17; i++) {
    const p = getP(i);
    if (!p) continue;
    const S = toScreen(p);
    ctx.beginPath();
    ctx.arc(S.x, S.y, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
}
