import React, { useState } from "react";
import BODY_IMAGES from "../config/bodyImages";
import BodyOverlay from "./BodyOverlay";

const REGION_LABELS = {
  neck: "목",
  right_arm: "오른팔",
  left_arm: "왼팔",
  torso: "몸통",
  pelvis: "골반",
  right_leg: "오른쪽 다리",
  left_leg: "왼쪽 다리",
  right_thigh: "오른쪽 허벅지",
  left_thigh: "왼쪽 허벅지",
  right_calf: "오른쪽 종아리",
  left_calf: "왼쪽 종아리",
};

export default function BodyFigure({
  gender = "male",
  selectedRegion,
  enabledRegions,
  onSelectRegion,
  hoverGroups = null,
}) {
  const [hoverRegion, setHoverRegion] = useState(null);
  const figureGender = gender === "female" ? "female" : "male";
  const activeBodyImage =
    (selectedRegion && BODY_IMAGES[selectedRegion]) ||
    (hoverRegion && BODY_IMAGES[hoverRegion]) ||
    BODY_IMAGES.default;
  const activeImageOpacity = selectedRegion ? 0.96 : hoverRegion ? 0.75 : 0.96;

  return (
    <div className="flex h-full w-full flex-col" data-gender={figureGender}>
      <div className="mb-2">
        <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-slate-500">
          신체 부위 선택
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">
          파란색으로 표시된 부위를 선택해 관절 분석 결과를 확인하세요.
        </p>
      </div>

      <div className="relative flex min-height-0 flex-1 items-center justify-center">
        <div className="relative flex h-full max-h-[620px] w-full items-center justify-center">
          <div className="relative mx-auto h-full max-h-[620px] aspect-[1024/1536] w-full max-w-[420px] overflow-hidden">
            <img
              src={activeBodyImage}
              alt={
                figureGender === "female"
                  ? "Female body silhouette"
                  : "Male body silhouette"
              }
              className="absolute inset-0 h-full w-full object-contain"
              style={{ opacity: activeImageOpacity }}
            />
            <BodyOverlay
              selectedRegion={selectedRegion}
              enabledRegions={enabledRegions}
              onSelectRegion={onSelectRegion}
              onHoverRegion={setHoverRegion}
              onLeaveRegion={() => setHoverRegion(null)}
              hoverGroups={hoverGroups}
            />
          </div>
        </div>
      </div>

      
    </div>
  );
}
