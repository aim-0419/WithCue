// /WithCue/withcue-web/frontend/src/components/Main.jsx
// main화면 

import React from "react";
import { Play, ScanLine } from 'lucide-react';
import { motion } from "framer-motion";
import { getUserId, getUserName } from "../../../utils/authStorage";

export default function Main({ onStartWorkout, onStartCheck }) {
    const userName = getUserName();
    const userId = getUserId();
    const userLabel = userName || userId;

    return (
    <div className="p-6 pb-24 h-full overflow-y-auto bg-slate-950 text-white">
      <div className="max-w-4xl mx-auto w-full">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-1">
            {userLabel ? `안녕하세요 ${userLabel}님 👋` : "안녕하세요 👋"}
          </h1>
          <p className="text-slate-400 text-sm">오늘도 바른 자세로 운동을 시작해보세요.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-cyan-500 to-blue-700 p-6 shadow-2xl shadow-cyan-950/20 flex flex-col justify-center min-h-[520px]"
          >
            <div className="relative z-10 flex flex-col items-center text-center py-4">
              <div className="text-cyan-50 font-medium mb-2 uppercase tracking-wide text-sm">
                AI Posture Check
              </div>
              <h2 className="text-4xl font-black mb-4">부위별 검사</h2>
              <p className="text-cyan-50/85 text-sm leading-relaxed max-w-xs mb-6">
                어깨, 허리, 무릎 등 원하는 부위를 선택해 자세 불균형과 가동범위를 확인해보세요.
              </p>

              <button
                onClick={onStartCheck}
                className="group relative flex items-center justify-center w-20 h-20 rounded-full bg-white shadow-lg hover:scale-105 transition-all duration-300 cursor-pointer"
              >
                <ScanLine className="w-8 h-8 text-cyan-600" />
                <div className="absolute inset-0 rounded-full border-4 border-white/30 animate-ping" />
              </button>

              <p className="mt-6 text-cyan-50 font-medium text-lg">검사 시작하기</p>
            </div>

            <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl -mr-16 -mt-16 pointer-events-none" />
            <div className="absolute bottom-0 left-0 w-48 h-48 bg-black/10 rounded-full blur-2xl -ml-10 -mb-10 pointer-events-none" />
          </motion.div>

          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-600 to-blue-800 p-6 shadow-2xl shadow-blue-900/20 flex flex-col justify-center min-h-[520px]"
          >
            <div className="relative z-10 flex flex-col items-center text-center py-4">
              <div className="text-blue-100 font-medium mb-2 uppercase tracking-wide text-sm">
                Today&apos;s Workout
              </div>
              <h2 className="text-4xl font-black mb-4">AI 코칭 재활</h2>
              <p className="text-blue-100/85 text-sm leading-relaxed max-w-xs mb-6">
                추천 운동을 바로 시작하고, 실시간 코칭과 함께 정확한 자세를 익혀보세요.
              </p>

              <button
                onClick={onStartWorkout}
                className="group relative flex items-center justify-center w-20 h-20 rounded-full bg-white shadow-lg hover:scale-105 transition-all duration-300 cursor-pointer"
              >
                <Play className="w-8 h-8 text-blue-600 ml-1 fill-blue-600" />
                <div className="absolute inset-0 rounded-full border-4 border-white/30 animate-ping" />
              </button>

              <p className="mt-6 text-blue-100 font-medium text-lg">운동 시작하기</p>
            </div>

            <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl -mr-16 -mt-16 pointer-events-none" />
            <div className="absolute bottom-0 left-0 w-48 h-48 bg-black/10 rounded-full blur-2xl -ml-10 -mb-10 pointer-events-none" />
          </motion.div>
        </div>
      </div>
    </div>
  );
}
