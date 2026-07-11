<template>
  <!-- 工程绘图桌动态插画（动效系统 A1）：漫画墨线风内嵌 SVG，与空态三插画同源
       美学（暖白+ink 线稿+clay 单强调）。极慢 loop（≥20s）明示装饰性（诚实地板：
       常驻 ambient 不暗示活动）。装饰元素：aria-hidden + pointer-events:none。 -->
  <svg
    class="drafting-scene"
    viewBox="0 0 320 200"
    fill="none"
    aria-hidden="true"
    xmlns="http://www.w3.org/2000/svg"
  >
    <defs>
      <clipPath id="drafting-scene-paper-clip">
        <path d="M27 30 276 23Q281 23 282 28L291 153Q292 158 286 159L42 174Q35 175 34 169L24 36Q23 31 27 30Z" />
      </clipPath>
    </defs>

    <g stroke-linecap="round" stroke-linejoin="round">
      <!-- 一张略有翘角的坐标纸：双描边延续空态插画的手绘墨线。 -->
      <path
        class="paper-echo"
        d="M31 34 279 27Q284 27 285 32L294 154Q295 161 288 163L45 178"
      />
      <path
        class="paper-sheet"
        d="M27 30 276 23Q281 23 282 28L291 153Q292 158 286 159L42 174Q35 175 34 169L24 36Q23 31 27 30Z"
      />
      <path class="paper-curl" d="M268 24Q274 29 282 28L283 39Q277 34 269 35Z" />

      <g clip-path="url(#drafting-scene-paper-clip)">
        <!-- 坐标纸网格刻意保留少量线距误差，避免过度机械。 -->
        <path
          class="paper-grid"
          d="M44 28 53 174M65 27 74 173M86 27 95 171M107 26 116 170M128 26 137 169M149 25 158 168M170 25 179 167M191 24 200 165M212 24 221 164M233 23 242 163M254 23 263 162M275 22 284 160M24 49 284 42M25 69 286 61M27 89 287 80M28 109 289 99M30 129 290 118M31 149 292 137M33 169 293 156"
        />
        <path class="axis-line" d="M148 24 158 169M27 109 289 100" />
        <path
          class="axis-ticks"
          d="M144 48 152 48M146 69 154 69M147 89 155 89M149 129 157 129M151 149 159 149M52 105 53 113M74 104 75 112M95 103 96 111M116 103 117 110M178 100 179 108M200 99 201 107M221 98 222 106M243 97 244 105M264 96 265 104"
        />

        <!-- 参考几何与尺寸标注保持静止：它们是图纸内容，不是假活动。 -->
        <circle class="construction-line" cx="93" cy="121" r="46" />
        <path class="construction-line" d="M50 132C74 88 99 68 124 78S151 133 178 132 207 80 244 72" />
        <path class="section-line" d="M187 63 228 62 244 78M185 67 225 66" />

        <g class="dimension-lines">
          <path d="M166 42 240 40M166 37 167 47M239 35 240 45M168 42l6-3M168 42l6 2M238 40l-6-2M238 40l-5 3" />
          <path d="M44 82 48 141M39 82 49 81M43 141 53 140M44 84l-3 6M44 84l4 5M48 139l-4-5M48 139l4-5" />
          <path d="M201 118 232 91M198 115l6 6M229 88l6 6" />
        </g>

        <g class="draft-notes">
          <path d="M188 32h4l-3 6M195 32l-2 3h5M197 32v6M201 37h.1M205 32c-2 0-2 6 0 6s2-6 0-6" />
          <path
            d="M34 108h4M34 108v3h4v3h-4M42 108c-2 0-2 3 0 3s2-3 0-3Zm0 3c-2 0-2 3 0 3s2-3 0-3Z"
            transform="rotate(-86 39 111)"
          />
          <path
            d="M222 84v6M222 84h3q2 0 0 3h-3M224 87l3 3M229 85q2-2 4 0 1 2-4 5h4M237 84l-3 4h5M237 84v6"
            transform="rotate(-39 230 87)"
          />
          <path d="M251 146l2-6 2 6M252 143h2M258 143h4M265 146l2-6 2 6M266 143h2" />
          <path d="M54 154l2-1v6M59 155h.1M59 158h.1M63 154q2-2 4 0 1 2-4 5h4M71 154c-2 0-2 6 0 6s2-6 0-6" />
        </g>

        <!-- 铅笔沿着这条蓝图曲线行进；淡底线像擦不净的石墨草稿。 -->
        <path class="curve-underlay" d="M50 132C74 88 99 68 124 78S151 133 178 132 207 80 244 72" />
        <path
          class="draft-line"
          pathLength="1"
          d="M50 132C74 88 99 68 124 78S151 133 178 132 207 80 244 72"
        />
      </g>

      <!-- 圆规固定针脚，以极慢摆角补完一小段圆弧。 -->
      <path class="compass-guide" d="M124 89A46 46 0 0 1 139 121" />
      <path class="compass-trace" pathLength="1" d="M124 89A46 46 0 0 1 139 121" />
      <g class="compass">
        <path class="tool-surface" d="M96 66 89 117 93 121 101 72Z" />
        <path class="tool-surface" d="M101 69 138 105 135 110 99 76Z" />
        <path class="tool-line" d="M97 65Q95 59 98 55 101 51 105 54 108 58 104 63" />
        <path class="tool-line" d="M93 79Q105 84 114 76M103 80l-4 10M99 85l8 2" />
        <path class="tool-line" d="m91 116-2 8 4-4M136 105l2 8-5-4" />
        <circle class="hinge-outline" cx="100" cy="66" r="5.6" />
        <circle class="clay-mark" cx="100" cy="66" r="3.1" />
      </g>

      <!-- 丁字尺压住图纸下沿；云形尺在右下形成第二个视觉重心。 -->
      <g class="t-square">
        <path class="tool-surface" d="M39 151 269 145 270 157 40 165Z" />
        <path class="tool-line" d="M47 155 259 150M63 153l1 8M83 153l1 7M103 152l1 7M123 151l1 7M143 151l1 6M163 150l1 6M183 150l1 5M203 149l1 6M223 148l1 6M243 148l1 5" />
        <path class="tool-surface" d="M20 140 45 140 47 176 24 179Z" />
        <path class="tool-line" d="M27 145 39 145 41 172 29 173" />
      </g>

      <g class="cloud-ruler">
        <path
          class="tool-surface cloud-body"
          fill-rule="evenodd"
          d="M196 139C201 129 211 126 220 132 224 120 239 116 248 127 258 122 272 127 272 139 272 149 259 153 249 147 240 155 225 153 220 144 211 150 200 148 196 139ZM218 139C227 132 242 130 254 136 246 141 237 145 226 145 222 145 219 143 218 139Z"
        />
        <path class="tool-line" d="M207 135l3 4M216 130l3 4M258 132l-3 4M263 140l-4 1" />
      </g>

      <!-- 笔尖是局部坐标原点；动画只移动整支笔，不触发布局。 -->
      <g class="drawing-pencil">
        <path class="pencil-wood" d="M0 0 7-3.5 7 3.5Z" />
        <path class="pencil-body" d="M7-3.5H31L35 0 31 3.5H7Z" />
        <path class="pencil-detail" d="M7 0H32M27-3.5v7" />
        <path class="clay-mark" d="M28-3.5H31L35 0 31 3.5H28Z" />
        <path class="pencil-lead" d="M0 0 2.6-.7 2.6.7Z" />
      </g>
    </g>
  </svg>
</template>

<script setup>
// 完整制图场景（Codex 5.6 Sol 绘制，主控亲核）：静止的图纸内容（网格/标注/注记）
// 与运动的工具（铅笔描线/圆规补弧）分层——运动 28s 极慢循环，纯 CSS 无 JS。
</script>

<style scoped>
.drafting-scene {
  display: block;
  width: 100%;
  height: auto;
  pointer-events: none;
}

.paper-echo {
  stroke: var(--hairline);
  stroke-width: 2.4;
}

.paper-sheet {
  fill: var(--hairline);
  fill-opacity: 0.16;
  stroke: var(--ink-soft);
  stroke-width: 1.2;
}

.paper-curl,
.tool-surface {
  fill: var(--hairline);
  fill-opacity: 0.58;
  stroke: var(--ink-soft);
  stroke-width: 1.05;
}

.paper-curl {
  fill-opacity: 0.42;
}

.paper-grid {
  stroke: var(--hairline);
  stroke-width: 0.72;
}

.axis-line,
.axis-ticks {
  stroke: var(--ink-faint);
  stroke-width: 0.72;
  opacity: 0.62;
}

.construction-line {
  stroke: var(--hairline);
  stroke-width: 0.9;
  stroke-dasharray: 3 4;
}

.section-line {
  stroke: var(--ink-faint);
  stroke-width: 0.8;
  stroke-dasharray: 6 3 1 3;
  opacity: 0.62;
}

.dimension-lines,
.tool-line,
.pencil-detail {
  fill: none;
  stroke: var(--ink-faint);
  stroke-width: 0.76;
}

.draft-notes {
  fill: none;
  stroke: var(--ink-faint);
  stroke-width: 0.65;
  opacity: 0.82;
}

.curve-underlay {
  stroke: var(--hairline);
  stroke-width: 3.2;
  stroke-dasharray: 2 3;
}

.draft-line,
.compass-trace {
  stroke: var(--ink-soft);
  stroke-width: 1.55;
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
}

.draft-line {
  animation: draft-curve-draw 28s linear infinite;
}

.compass-guide {
  stroke: var(--hairline);
  stroke-width: 1.2;
  stroke-dasharray: 2 3;
}

.compass-trace {
  stroke-width: 1.25;
  animation: compass-arc-draw 28s linear infinite;
}

.compass {
  transform-box: view-box;
  transform-origin: 91px 121px;
  animation: compass-sweep 28s ease-in-out infinite;
}

.hinge-outline {
  fill: var(--hairline);
  stroke: var(--ink-soft);
  stroke-width: 1;
}

.clay-mark {
  fill: var(--clay);
}

.cloud-body {
  fill-opacity: 0.48;
}

.drawing-pencil {
  transform-box: view-box;
  transform-origin: 0 0;
  animation: pencil-follow 28s linear infinite;
}

.pencil-wood,
.pencil-body {
  fill: var(--hairline);
  stroke: var(--ink-soft);
  stroke-width: 0.9;
}

.pencil-body {
  fill-opacity: 0.76;
}

.pencil-lead {
  fill: var(--ink-soft);
}

@keyframes draft-curve-draw {
  0%, 7% { stroke-dashoffset: 1; opacity: 0; }
  11% { opacity: 0.84; }
  82%, 90% { stroke-dashoffset: 0; opacity: 0.9; }
  100% { stroke-dashoffset: 0; opacity: 0; }
}

@keyframes compass-arc-draw {
  0%, 10% { stroke-dashoffset: 1; opacity: 0; }
  16% { opacity: 0.7; }
  56%, 88% { stroke-dashoffset: 0; opacity: 0.72; }
  100% { stroke-dashoffset: 0; opacity: 0; }
}

@keyframes compass-sweep {
  0% { transform: rotate(-4deg); }
  52% { transform: rotate(7deg); }
  100% { transform: rotate(-4deg); }
}

@keyframes pencil-follow {
  0%, 7% { opacity: 0; transform: translate(50px, 132px) rotate(-62deg); }
  11% { opacity: 0.76; transform: translate(56px, 119px) rotate(-60deg); }
  23% { transform: translate(76px, 91px) rotate(-42deg); }
  35% { transform: translate(102px, 73px) rotate(7deg); }
  46% { transform: translate(128px, 81px) rotate(24deg); }
  58% { transform: translate(151px, 124px) rotate(23deg); }
  68% { transform: translate(178px, 132px) rotate(-3deg); }
  75% { transform: translate(203px, 108px) rotate(-48deg); }
  82%, 90% { opacity: 0.76; transform: translate(244px, 72px) rotate(-16deg); }
  94% { opacity: 0; transform: translate(244px, 72px) rotate(-16deg); }
  94.01%, 100% { opacity: 0; transform: translate(50px, 132px) rotate(-62deg); }
}

@media (prefers-reduced-motion: reduce) {
  .draft-line,
  .compass-trace,
  .compass,
  .drawing-pencil {
    animation: none;
  }

  .draft-line,
  .compass-trace {
    stroke-dashoffset: 0;
    opacity: 0.9;
  }

  .compass {
    transform: rotate(0);
  }

  .drawing-pencil {
    opacity: 0.76;
    transform: translate(244px, 72px) rotate(-16deg);
  }
}
</style>
