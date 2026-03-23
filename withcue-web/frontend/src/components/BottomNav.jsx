// /WithCue/withcue-web/frontend/src/components/BottomNav.jsx
// 하단바 (홈/분석/자세분석버튼/기록/내 정보)
// 분석 : 운동자세 통계
// 기록 : 날짜 기록

import React from "react";
import { Home, BarChart2, CalendarDays, User, ScanLine } from 'lucide-react';
import { clsx } from 'clsx';
import { useNavigate } from "react-router-dom"

export default function BottomNav({ activeTab }) {
    const navigate = useNavigate();

    const items = [
      { id: 'home', icon: Home, label: '홈', path: '/main'},
      { id: 'analysis', icon: BarChart2, label: '분석', path: '/analysis' },
      { id: 'spacer' },
      { id: 'record', icon: CalendarDays, label: '기록', path: '/record' },
      { id: 'profile', icon: User, label: '내 정보', path: '/mypage' },
    ];

    return (
      <div className="fixed bottom-0 left-0 w-full z-50 pointer-events-none">
        <div className="relative w-full pointer-events-auto">

          {/* 중앙 가동범위측정 시작 버튼  */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-50">
          <button
            onClick={() => navigate('/check/select')}
            className="w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center text-white
                       shadow-[0_0_15px_rgba(37,99,235,0.5)]
                       border-4 border-slate-950
                       active:scale-95 transition"
          >
            <ScanLine size={24} />
          </button>
        </div>

        {/* 하단 바 */}
        <div className="h-20 bg-slate-900 border-t border-slate-800 flex justify-center">
          <div className="flex justify-between items-center w-full max-w-lg px-6 h-full pb-2">
            {items.map(item => {
              if (item.id === 'spacer') {
                return <div key="spacer" className="w-16" />;
              }

              return (
                <button
                  key={item.id}
                  onClick={() => navigate(item.path)}
                  className={clsx(
                    'flex flex-col items-center gap-1 w-16',
                    activeTab === item.id
                      ? 'text-blue-500'
                      : 'text-slate-500'
                  )}
                >
                  <item.icon size={22} />
                  <span className="text-[11px]">{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}