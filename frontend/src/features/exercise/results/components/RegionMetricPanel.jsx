import React from "react";

export default function RegionMetricPanel({
  selectedRegionData,
  description,
  className = "",
}) {
  return (
    <div
      className={`bg-slate-950/40 border border-slate-800 rounded-2xl p-4 overflow-hidden ${className}`}
    >
      <div className="mb-4">
        <p className="text-xs text-slate-500 font-bold mb-1">선택 부위</p>
        <h4 className="text-xl font-black text-blue-400">
          {selectedRegionData.label}
        </h4>
        <p className="text-xs text-slate-400 mt-2">
          관련 관절: {selectedRegionData.joints.join(", ")}
        </p>
        {description ? (
          <p className="text-xs leading-relaxed text-slate-400 mt-3">
            {description}
          </p>
        ) : null}
      </div>

      <div className="space-y-3">
        {selectedRegionData.metrics.map((metric) => (
          <div
            key={metric.label}
            className="bg-slate-900/80 border border-slate-800 rounded-xl p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-slate-400">{metric.label}</span>
              <span className="text-sm font-bold text-white">
                {metric.value}
              </span>
            </div>

            <div className="flex items-center justify-between mt-2">
              <span className="text-[11px] text-slate-500">
                {metric.target}
              </span>
              <span
                className={`text-[11px] px-2 py-1 rounded-full font-bold ${
                  metric.status === "양호"
                    ? "bg-green-500/15 text-green-300"
                    : metric.status === "주의"
                    ? "bg-amber-500/15 text-amber-300"
                    : "bg-red-500/15 text-red-300"
                }`}
              >
                {metric.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
