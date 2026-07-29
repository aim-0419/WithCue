// 자세 검사 부위 선택 페이지. 선택된 부위를 parts 쿼리로 변환해 CheckPage로 이동한다.
import { useNavigate } from "react-router-dom";
import { BodyPartSelection } from "../components/BodyPartSelection";

const PARTS_MAP = {
  shoulder: "shoulder",
  neck: "neck",
  knee: "knee",
};

export default function CheckSelectPage() {
  const navigate = useNavigate();

  return (
    <BodyPartSelection
      onClose={() => navigate("/main")}
      onSelect={(partId) => {
        const parts = PARTS_MAP[partId] ?? partId;
        navigate(`/check?part=${encodeURIComponent(parts)}`);
      }}
      onSelectAll={() => navigate("/check")}
    />
  );
}
