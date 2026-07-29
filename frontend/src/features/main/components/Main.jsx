// /WithCue/withcue-web/frontend/src/components/Main.jsx
// main화면

import React from "react";
import { Play, ScanLine } from 'lucide-react';
import { getUserId, getUserName } from "../../../utils/authStorage";

export default function Main({ onStartWorkout, onStartCheck }) {
  const userName = getUserName();
  const userId = getUserId();
  const userLabel = userName || userId;

  return (
    <div className="p-6 pb-24 h-full flex flex-col bg-slate-950 text-white">
      <style>{`
        @keyframes mc-fadein {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        .mc-card {
          animation: mc-fadein 0.35s ease both;
        }
        .mc-card:nth-child(2) {
          animation-delay: 0.1s;
        }
        .mc-btn {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 80px;
          height: 80px;
          border-radius: 999px;
          background: #fff;
          box-shadow: 0 0 0 6px rgba(255,255,255,0.18), 0 0 0 12px rgba(255,255,255,0.07);
          cursor: pointer;
          border: none;
          transition: opacity 0.12s;
        }
        .mc-btn:active {
          opacity: 0.75;
        }
      `}</style>

      <div className="max-w-4xl mx-auto w-full flex flex-col flex-1 min-h-0">
        <div className="mb-8 shrink-0">
          <h1 className="text-2xl font-bold mb-1">
            {userLabel ? `안녕하세요 ${userLabel}님 👋` : "안녕하세요 👋"}
          </h1>
          <p className="text-slate-400 text-sm">오늘도 바른 자세로 운동을 시작해보세요.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 부위별 검사 카드 */}
          <div className="mc-card relative overflow-hidden rounded-3xl bg-gradient-to-br from-cyan-500 to-blue-700 p-6 shadow-2xl flex flex-col justify-center aspect-square">
            <div className="relative z-10 flex flex-col items-center text-center py-4">
              <div className="text-cyan-50 font-medium mb-2 uppercase tracking-wide text-sm">
                AI Posture Check
              </div>
              <h2 className="text-4xl font-black mb-4">부위별 검사</h2>
              <p className="text-cyan-50/85 text-sm leading-relaxed max-w-xs mb-6">
                어깨, 허리, 무릎 등 원하는 부위를 선택해 자세 불균형과 가동범위를 확인해보세요.
              </p>
              <button className="mc-btn" onClick={onStartCheck}>
                <ScanLine className="w-8 h-8 text-cyan-600" />
              </button>
              <p className="mt-6 text-cyan-50 font-medium text-lg">검사 시작하기</p>
            </div>
          </div>

          {/* AI 코칭 재활 카드 */}
          <div className="mc-card relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-600 to-blue-800 p-6 shadow-2xl flex flex-col justify-center aspect-square">
            <div className="relative z-10 flex flex-col items-center text-center py-4">
              <div className="text-blue-100 font-medium mb-2 uppercase tracking-wide text-sm">
                Today&apos;s Workout
              </div>
              <h2 className="text-4xl font-black mb-4">AI 코칭 재활</h2>
              <p className="text-blue-100/85 text-sm leading-relaxed max-w-xs mb-6">
                추천 운동을 바로 시작하고, 실시간 코칭과 함께 정확한 자세를 익혀보세요.
              </p>
              <button className="mc-btn" onClick={onStartWorkout}>
                <Play className="w-8 h-8 text-blue-600 ml-1 fill-blue-600" />
              </button>
              <p className="mt-6 text-blue-100 font-medium text-lg">운동 시작하기</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
