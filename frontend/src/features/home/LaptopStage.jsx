import React from "react";
import Icon from "../../components/ui/Icon.jsx";
import "./laptop-stage.css";

const keyRows = [
  [
    ["esc", 1.5],
    "☀",
    "☼",
    "▣",
    "⌕",
    "◉",
    "☾",
    "◀",
    "▷",
    "▶",
    "◀◀",
    "♩",
    "♫",
    "◉",
  ],
  [
    "~\n`",
    "!\n1",
    "@\n2",
    "#\n3",
    "$\n4",
    "%\n5",
    "^\n6",
    "&\n7",
    "*\n8",
    "(\n9",
    ")\n0",
    "_\n−",
    "+\n=",
    ["delete", 1.5],
  ],
  [
    ["tab", 1.5],
    "Q",
    "W",
    "E",
    "R",
    "T",
    "Y",
    "U",
    "I",
    "O",
    "P",
    "{\n[",
    "}\n]",
    "|\n\\",
  ],
  [
    ["caps lock", 1.8],
    "A",
    "S",
    "D",
    "F",
    "G",
    "H",
    "J",
    "K",
    "L",
    ":\n;",
    "\"\n'",
    ["return", 1.8],
  ],
  [
    ["shift", 2.3],
    "Z",
    "X",
    "C",
    "V",
    "B",
    "N",
    "M",
    "<\n,",
    ">\n.",
    "?\n/",
    ["shift", 2.3],
  ],
  ["fn", "⌃", "⌥", ["⌘", 1.3], ["", 6], ["⌘", 1.3], "⌥", "◀", "▲\n▼", "▶"],
];

function Keyboard() {
  return (
    <div className="zen-laptop-deck" aria-hidden="true">
      <div className="zen-laptop-hinge" />
      <div className="zen-laptop-key-area">
        <div className="zen-laptop-speaker" />
        <div className="zen-laptop-keys">
          {keyRows.map((row, r) => (
            <div className="zen-laptop-key-row" key={r}>
              {row.map((value, k) => {
                const [label, width] = Array.isArray(value)
                  ? value
                  : [value, 1];
                return (
                  <span
                    key={k}
                    style={{ flex: width }}
                    className={label === "" ? "zen-laptop-spacebar" : ""}
                  >
                    {label.split("\n").map((line, n) => (
                      <i key={n}>{line}</i>
                    ))}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
        <div className="zen-laptop-speaker" />
      </div>
      <div className="zen-laptop-trackpad" />
      <div className="zen-laptop-notch" />
    </div>
  );
}

export default function LaptopStage() {
  return (
    <div className="zen-laptop-stage">
      <div className="zen-laptop-scroll-track" aria-hidden="true" />
      <div
        className="zen-laptop"
        role="img"
        aria-label="Laptop với tờ CV phóng lớn và trượt khỏi màn hình theo vị trí cuộn"
      >
        <div className="zen-laptop-lid">
          <div className="zen-laptop-screen">
            <span className="zen-laptop-camera" />
            <div className="zen-laptop-app" aria-hidden="true">
              <div className="zen-laptop-app-bar">
                <strong>
                  <Icon name="file" size={12} /> CV của bạn
                </strong>
                <span className="zen-laptop-avatar">A</span>
              </div>
              <div className="zen-laptop-app-tools">
                <span>↶</span>
                <span>↷</span>
                <small>Bản nháp · Minh họa</small>
                <span className="zen-laptop-export">
                  <Icon name="download" size={10} /> Xuất PDF
                </span>
              </div>
              <div className="zen-laptop-editor">
                <div className="zen-laptop-preview" />
                <div className="zen-laptop-fields">
                  <div className="zen-laptop-editor-tabs">
                    <b>Chỉnh sửa</b>
                    <span>Thiết kế</span>
                    <Icon name="chat" size={11} />
                  </div>
                  {[
                    "Thông tin cá nhân",
                    "Kinh nghiệm làm việc",
                    "Học vấn",
                    "Dự án",
                    "Kỹ năng",
                  ].map((label, i) => (
                    <div className="zen-laptop-field" key={label}>
                      <span>
                        {label}
                        <small>{i === 0 ? "⌄" : "+"}</small>
                      </span>
                      {i === 0 && (
                        <>
                          <i />
                          <i />
                          <i />
                        </>
                      )}
                    </div>
                  ))}
                  <div className="zen-laptop-source-note">
                    <Icon name="shield" size={10} /> Nội dung từ hồ sơ của bạn
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="zen-laptop-flying-cv">
            <img
              className="zen-laptop-paper-cv"
              src="/templates/previews/classic.png"
              width="600"
              height="849"
              alt="Mẫu CV Harvard phóng lớn từ màn hình laptop khi cuộn"
            />
          </div>
        </div>
        <Keyboard />
        <div className="zen-laptop-edge" />
      </div>
      <div className="zen-laptop-paper-scene">
        <img
          className="zen-laptop-cloud"
          src="/images/home/laptop-cloud.svg"
          loading="lazy"
          alt=""
          aria-hidden="true"
        />
        <div className="zen-laptop-paper-caption">
          <span>CHUẨN BỊ CHỈN CHU. GỬI ĐI TỰ TIN.</span>
          <h3>
            Để câu chuyện của bạn
            <br />
            tự cất lời.
          </h3>
        </div>
        <div className="zen-laptop-hands" aria-hidden="true">
          <img
            width="164"
            height="440"
            className="zen-laptop-hand zen-laptop-hand-left"
            src="/images/home/laptop-hand-left.png"
            loading="lazy"
            alt=""
            aria-hidden="true"
          />
          <img
            width="164"
            height="440"
            className="zen-laptop-hand zen-laptop-hand-right"
            src="/images/home/laptop-hand-right.png"
            loading="lazy"
            alt=""
            aria-hidden="true"
          />
        </div>
      </div>
    </div>
  );
}
