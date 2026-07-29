// /WithCue/withcue-web/frontend/src/components/SideBySideStage.jsx 
// CheckPage.jsx, ExercisePage.jsx 에 들어가는 영상 영역 

import TopBar from "./TopBar";

export default function SideBySideStage({
    topSlot,
    bottomRightSlot,
    leftTitle,
    leftSub,
    leftContent,
    rightTitle,
    rightSub,
    rightContent,
    single = false, //1컬럼
}) {
    return (
    <div className="stage-root">
      <TopBar />

      {topSlot ? <div className="stage-top">{topSlot}</div> : null}

      <div className="stage-split">
        {!single && (
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">{leftTitle}</div>
            <div className="panel-sub">{leftSub}</div>
          </div>
          <div className="media-wrap">{leftContent}</div>
        </div>
        )}

        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">{rightTitle}</div>
            <div className="panel-sub">{rightSub}</div>
          </div>
          <div className="media-wrap">{rightContent}</div>
        </div>
      </div>

        {bottomRightSlot && (
            <div className="stage-bottom-right">
            {bottomRightSlot}
            </div>
        )}

      <style>{`
        .stage-root{
          height:100%;
          position:relative;
          background:#0b1220;
          display:flex;
          flex-direction:column;
          overflow:hidden;
          }
          .stage-top{
              padding: 1px 0;
              display:flex;
              justify-content:center;  
              align-items:center;
              }
        .stage-split{
          flex:1;
          display:flex;
          gap:12px;
          padding:12px;
          min-height:0;
        }
        .panel{
          flex:1;
          border-radius:18px;
          background:rgba(255,255,255,0.06);
          border:1px solid rgba(255,255,255,0.1);
          display:flex;
          flex-direction:column;
          overflow:hidden;
          min-height:0;
        }
        .panel-head{
          padding:10px 12px;
          border-bottom:1px solid rgba(255,255,255,0.1);
          display:flex;
          justify-content:space-between;
        }
        .panel-title{
          font-weight:900;
          font-size:14px;
          color:#fff;
        }
        .panel-sub{
          font-size:12px;
          color:rgba(255,255,255,0.6);
          font-weight:700;
        }
        .media-wrap{
          flex:1;
          width:100%;
          display:flex;
          align-items:center;
          justify-content:center;
          
          background:#000;
          height:100%;
          max-height:100%;
          aspect-ratio:auto;
        }
        .progress-pill{
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.12);
            color:#fff;
            font-weight: 900;
            font-size: 13px;
            }
        .stage-bottom-right{
          position: absolute;
          right: 20px;
          bottom: 20px;
          z-index: 50;
        }
        @media (max-width: 900px){
          .stage-split{
            flex-direction:column;
          }
        }
      `}</style>
    </div>
  );
}
