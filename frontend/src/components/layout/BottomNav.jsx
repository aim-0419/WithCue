// /WithCue/withcue-web/frontend/src/components/BottomNav.jsx
// 하단바 (홈/분석/검사결과/기록/내 정보)
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
      { id: 'analysis', icon: BarChart2, label: '자세 분석', path: '/analysis' },
      { id: 'check-history', icon: ScanLine, label: '검사 결과', path: '/check/history' },
      { id: 'record', icon: CalendarDays, label: '운동 기록', path: '/record' },
      { id: 'profile', icon: User, label: '내 정보', path: '/mypage' },
    ];

    return (
      <div className="fixed bottom-0 left-0 w-full z-50">
        <div className="h-20 bg-slate-900 border-t border-slate-800 flex justify-center">
          <div className="flex justify-between items-center w-full max-w-lg px-6 h-full pb-2">
            {items.map(item => (
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
            ))}
          </div>
        </div>
      </div>
  );
}
