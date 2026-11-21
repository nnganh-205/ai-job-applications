import React from "react";

export function PaperSkeleton({ className = "" }) {
  return (
    <div className={`zen-paper-skeleton ${className}`} aria-hidden="true">
      <div className="zen-paper-person" />
      <div className="zen-paper-name">
        <i />
        <i />
      </div>
      <hr />
      {Array.from({ length: 4 }, (_, i) => (
        <div className="zen-paper-section" key={i}>
          <b />
          {[0, 1, 2].map((n) => (
            <i key={n} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function HeroRail() {
  return (
    <div className="zen-hero-rail" aria-hidden="true">
      <div className="zen-rail-papers">
        <PaperSkeleton />
        <div className="zen-hero-document">
          <img
            src="/templates/previews/classic.png"
            alt=""
            fetchPriority="high"
            width="600"
            height="849"
          />
          <span>Harvard · Một cách kể chuyện rõ ràng hơn</span>
        </div>
        <PaperSkeleton />
      </div>
      <div className="zen-rail-strip">
        <span>Thông tin của bạn</span>

        <span>Câu chuyện của bạn</span>

        <span>Cơ hội tiếp theo</span>

      </div>
    </div>
  );
}

export { default as DocumentStage } from "./LaptopStage.jsx";
