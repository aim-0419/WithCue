import { useNavigate } from "react-router-dom";
import { BodyPartSelection } from "../components/BodyPartSelection";

export default function CheckSelectPage() {
  const navigate = useNavigate();

  return (
    <BodyPartSelection
      onClose={() => navigate("/main")}
      onSelect={(partId) => {
        const nextUrl = `/check?part=${encodeURIComponent(partId)}`; // 단일
        navigate(nextUrl);
      }}
      onSelectAll={() => navigate("/check")}
    />
  );
}
