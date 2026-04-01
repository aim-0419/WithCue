// /WithCue/withcue-web/frontend/src/components/Main.jsx
// main화면 

import React from "react";
import { Play, ChevronRight, Activity, TrendingUp, AlertCircle, CheckCircle2 } from 'lucide-react';
import { motion } from "framer-motion";
import { AreaChart, Area, Tooltip, ResponsiveContainer } from 'recharts';

export default function Main({ onStartWorkout, onViewAnalysis, finalAccuracy = 0, weeklyAccuracyData = [] }) {
    // [조현석] 메인 우측 카드에는 마지막 운동의 최종 정확도만 표시합니다.
    const displayAccuracy = Math.max(0, Math.min(100, Math.round(finalAccuracy)));

    const userName = localStorage.getItem("user_name");

    return (
    <div className="p-6 pb-24 h-full overflow-y-auto bg-slate-950 text-white">
      <div className="max-w-4xl mx-auto w-full">
        <div className="mb-8">
          <h1 className="text-2xl font-bold mb-1">
            {userName ? `${userName}님 안녕하세요 👋` : "안녕하세요 👋"}
          </h1>
          <p className="text-slate-400 text-sm">오늘도 바른 자세로 운동을 시작해보세요.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-blue-600 to-blue-800 p-6 shadow-2xl shadow-blue-900/20 flex flex-col justify-center min-h-[300px]"
          >
            <div className="relative z-10 flex flex-col items-center text-center py-4">
              <div className="text-blue-100 font-medium mb-2 uppercase tracking-wide text-sm">
                오늘의 추천 운동
              </div>
              <h2 className="text-4xl font-black italic mb-6">Cat–Cow</h2>

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

           <div className="flex flex-col gap-6">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold flex items-center gap-2">
                  <Activity className="text-green-500" size={20} />
                  최근 자세 분석
                </h3>
                <button
                  onClick={onViewAnalysis}
                  className="text-xs text-slate-500 flex items-center hover:text-white transition-colors"
                >
                  전체보기 <ChevronRight size={14} />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4 h-[calc(100%-40px)]">
                <div className="bg-slate-900/50 border border-slate-800 p-4 rounded-2xl flex flex-col justify-center">
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-slate-400 text-xs">정확도</span>
                    <CheckCircle2 size={16} className="text-green-500" />
                  </div>
                  <div className="text-3xl font-bold mb-2">
                    {displayAccuracy}<span className="text-sm font-normal text-slate-500">%</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-green-500 transition-all duration-300" style={{ width: `${displayAccuracy}%` }} />
                  </div>
                </div>

                <div className="bg-slate-900/50 border border-slate-800 p-4 rounded-2xl flex flex-col justify-center">
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-slate-400 text-xs">주의 구간</span>
                    <AlertCircle size={16} className="text-amber-500" />
                  </div>
                  <div className="text-xl font-medium text-slate-200">허리 굽힘</div>
                  <div className="text-xs text-slate-500 mt-1">하강 시 주의 필요</div>
                </div>
              </div>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 p-5 rounded-2xl flex-1">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp className="text-blue-500" size={20} />
                <h3 className="font-bold">주간 자세 점수</h3>
              </div>

              <div className="h-32 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  {/* [조현석] 주간 자세 점수는 월요일 시작 7일 고정 데이터이며, 하루에는 마지막 운동 점수만 표시됩니다. */}
                  <AreaChart data={weeklyAccuracyData}>
                    <defs>
                      <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1e293b',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#fff',
                      }}
                      itemStyle={{ color: '#60a5fa' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="score"
                      stroke="#3b82f6"
                      strokeWidth={3}
                      fillOpacity={1}
                      fill="url(#colorScore)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
