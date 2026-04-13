import TopBar from "../../../components/layout/TopBar";
import BottomNav from "../../../components/layout/BottomNav";

export default function SettingsPage() {
    return (
        <div className="settings-root">
          <TopBar></TopBar>
          
          <div className="settings-body">
            <h1>설정</h1>
            <p>음성 안내, 디바이스, 계정 설정</p>
          </div>

          <BottomNav active="settings"></BottomNav>

          <style>{`
            .settings-root {
              min-height: 100nh;
              background: #f6f0ff;
              display: flex;
              flex-direction: column;
            }

            .settings-body {
              flex: 1;
              padding:24px 16px 96px;
              text-align:center;
            }

            h1 {
              font-size:22px;
              font-weight:900;
              margin-bottom:12px;
            }
          `}</style>
        </div>
    )
}
