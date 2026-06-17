import type {CSSProperties, ReactNode} from "react";
import {
  AbsoluteFill,
  Easing,
  Sequence,
  interpolate,
  useCurrentFrame,
} from "remotion";

const palette = {
  bg: "#1a1a1a",
  panel: "#22211f",
  panelSoft: "rgba(255,255,255,0.045)",
  neutral: "#f4f1eb",
  muted: "#aaa39a",
  dim: "#756f67",
  line: "rgba(255,255,255,0.15)",
  strongLine: "rgba(255,255,255,0.25)",
  accent: "#ff4632",
  amber: "#fedc2a",
};

const ease = Easing.bezier(0.16, 1, 0.3, 1);
const sceneLength = 75;

const clamp = (
  frame: number,
  input: [number, number],
  output: [number, number],
) =>
  interpolate(frame, input, output, {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });

const sceneFade = (frame: number) =>
  Math.min(
    clamp(frame, [0, 16], [0, 1]),
    clamp(frame, [sceneLength - 16, sceneLength], [1, 0]),
  );

const translateY = (frame: number, offset = 34) =>
  interpolate(frame, [0, 22], [offset, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: ease,
  });

const styles = {
  stage: {
    background:
      "radial-gradient(circle at 16% 32%, rgba(255,70,50,0.2), transparent 430px), linear-gradient(180deg, rgba(255,255,255,0.035), transparent 56%), #1a1a1a",
    color: palette.neutral,
    fontFamily:
      'Geist, Satoshi, "Avenir Next", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    overflow: "hidden",
  } satisfies CSSProperties,
  grid: {
    position: "absolute",
    inset: 0,
    backgroundImage:
      "linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
    backgroundSize: "74px 74px",
    opacity: 0.24,
  } satisfies CSSProperties,
  safe: {
    position: "absolute",
    inset: "72px 92px",
  } satisfies CSSProperties,
  label: {
    color: palette.accent,
    fontFamily: '"JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace',
    fontSize: 22,
    textTransform: "uppercase",
  } satisfies CSSProperties,
  title: {
    fontSize: 104,
    lineHeight: 0.92,
    letterSpacing: -5,
    fontWeight: 760,
    margin: 0,
    maxWidth: 1060,
  } satisfies CSSProperties,
  body: {
    color: palette.muted,
    fontSize: 34,
    lineHeight: 1.35,
    maxWidth: 790,
  } satisfies CSSProperties,
  mono: {
    fontFamily: '"JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace',
  } satisfies CSSProperties,
};

const SceneShell = ({
  children,
  label,
  frame,
}: {
  children: ReactNode;
  label: string;
  frame: number;
}) => {
  const opacity = sceneFade(frame);
  return (
    <AbsoluteFill
      style={{
        ...styles.stage,
        opacity,
      }}
    >
      <div style={styles.grid} />
      <div style={styles.safe}>
        <div style={{...styles.label, transform: `translateY(${translateY(frame, 18)}px)`}}>
          {label}
        </div>
        {children}
      </div>
    </AbsoluteFill>
  );
};

const Metric = ({
  value,
  label,
  delay,
  frame,
}: {
  value: string;
  label: string;
  delay: number;
  frame: number;
}) => {
  const local = Math.max(0, frame - delay);
  const opacity = clamp(local, [0, 16], [0, 1]);
  return (
    <div
      style={{
        borderTop: `1px solid ${palette.line}`,
        paddingTop: 22,
        opacity,
        transform: `translateY(${translateY(local, 24)}px)`,
      }}
    >
      <div style={{...styles.mono, fontSize: 62, lineHeight: 1}}>{value}</div>
      <div
        style={{
          ...styles.mono,
          color: palette.dim,
          fontSize: 18,
          marginTop: 16,
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
    </div>
  );
};

const Pill = ({
  children,
  active,
  delay,
  frame,
}: {
  children: ReactNode;
  active?: boolean;
  delay: number;
  frame: number;
}) => {
  const local = Math.max(0, frame - delay);
  return (
    <div
      style={{
        border: `1px solid ${active ? "rgba(255,70,50,0.82)" : palette.line}`,
        background: active ? "rgba(255,70,50,0.18)" : palette.panelSoft,
        padding: "20px 24px",
        color: active ? palette.neutral : palette.muted,
        fontSize: 26,
        opacity: clamp(local, [0, 14], [0, 1]),
        transform: `translateY(${translateY(local, 22)}px)`,
      }}
    >
      {children}
    </div>
  );
};

const IntroScene = ({frame}: {frame: number}) => (
  <SceneShell label="Quant Researcher Desk" frame={frame}>
    <div style={{display: "grid", gridTemplateColumns: "1.1fr 0.9fr", gap: 70}}>
      <div>
        <h1
          style={{
            ...styles.title,
            marginTop: 56,
            transform: `translateY(${translateY(frame)}px)`,
          }}
        >
          Map markets as supply chains.
        </h1>
        <p
          style={{
            ...styles.body,
            marginTop: 42,
            opacity: clamp(frame, [16, 34], [0, 1]),
          }}
        >
          Moomoo sector plates become a working research graph: industries, adjacent
          layers, and report-ready evidence queues.
        </p>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 28,
          alignContent: "center",
          paddingTop: 96,
        }}
      >
        <Metric value="643" label="HK/US plates" delay={16} frame={frame} />
        <Metric value="256" label="industry plates" delay={22} frame={frame} />
        <Metric value="53" label="starter edges" delay={28} frame={frame} />
        <Metric value="3h" label="sector cadence" delay={34} frame={frame} />
      </div>
    </div>
  </SceneShell>
);

const ExploreScene = ({frame}: {frame: number}) => (
  <SceneShell label="Interactive universe browser" frame={frame}>
    <div style={{display: "grid", gridTemplateColumns: "420px 1fr", gap: 54, marginTop: 76}}>
      <div style={{borderTop: `1px solid ${palette.strongLine}`, paddingTop: 28}}>
        <div style={{...styles.mono, color: palette.dim, fontSize: 18, textTransform: "uppercase"}}>
          Market
        </div>
        <Pill frame={frame} delay={10} active>
          HK
        </Pill>
        <div
          style={{
            ...styles.mono,
            color: palette.dim,
            fontSize: 18,
            marginTop: 34,
            textTransform: "uppercase",
          }}
        >
          Industry
        </div>
        <Pill frame={frame} delay={18} active>
          Hotels & Resorts
        </Pill>
        <Pill frame={frame} delay={26}>Heavy Machinery</Pill>
        <Pill frame={frame} delay={34}>Semiconductors</Pill>
      </div>
      <div style={{borderTop: `1px solid ${palette.strongLine}`, paddingTop: 28}}>
        <h2 style={{...styles.title, fontSize: 78, maxWidth: 940}}>One dropdown, one research slice.</h2>
        <p style={{...styles.body, fontSize: 30, maxWidth: 870}}>
          The app narrows a crowded market taxonomy into a readable field view:
          role mix, plate counts, and a graph surface for upstream and downstream
          investigation.
        </p>
        <div style={{display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 44}}>
          <Metric value="HK" label="selected market" delay={36} frame={frame} />
          <Metric value="9" label="plates in view" delay={42} frame={frame} />
        </div>
      </div>
    </div>
  </SceneShell>
);

const GraphScene = ({frame}: {frame: number}) => {
  const progress = clamp(frame, [18, 58], [0, 1]);
  const nodes = [
    {x: 210, y: 260, label: "Input layer"},
    {x: 660, y: 185, label: "Operating layer"},
    {x: 1110, y: 260, label: "Demand layer"},
    {x: 660, y: 500, label: "Evidence queue"},
  ];
  return (
    <SceneShell label="Supply-chain graph" frame={frame}>
      <h2 style={{...styles.title, fontSize: 84, marginTop: 56}}>Edges start as questions.</h2>
      <svg width="1500" height="660" viewBox="0 0 1500 660" style={{marginTop: 38}}>
        <path
          d="M300 292 C460 210, 500 212, 570 220"
          stroke={palette.amber}
          strokeWidth="3"
          strokeOpacity={0.42 * progress}
          fill="none"
        />
        <path
          d="M750 220 C930 214, 980 222, 1020 292"
          stroke={palette.amber}
          strokeWidth="3"
          strokeOpacity={0.42 * progress}
          fill="none"
        />
        <path
          d="M660 250 C650 350, 650 390, 660 450"
          stroke={palette.accent}
          strokeWidth="3"
          strokeOpacity={0.52 * progress}
          fill="none"
        />
        {nodes.map((node, index) => {
          const local = Math.max(0, frame - 12 - index * 8);
          return (
            <g
              key={node.label}
              opacity={clamp(local, [0, 16], [0, 1])}
              transform={`translate(0 ${translateY(local, 24)})`}
            >
              <rect
                x={node.x}
                y={node.y}
                width="250"
                height="82"
                fill={index === 1 ? "rgba(255,70,50,0.18)" : "rgba(255,255,255,0.045)"}
                stroke={index === 1 ? "rgba(255,70,50,0.82)" : "rgba(255,255,255,0.18)"}
              />
              <text x={node.x + 22} y={node.y + 38} fill={palette.neutral} fontSize="28" fontWeight="700">
                {node.label}
              </text>
              <text x={node.x + 22} y={node.y + 63} fill={palette.dim} fontSize="15" fontFamily="JetBrains Mono">
                validate with filings
              </text>
            </g>
          );
        })}
      </svg>
    </SceneShell>
  );
};

const OutputScene = ({frame}: {frame: number}) => (
  <SceneShell label="Output surface" frame={frame}>
    <div style={{display: "grid", gridTemplateColumns: "0.95fr 1.05fr", gap: 70, marginTop: 76}}>
      <div>
        <h2 style={{...styles.title, fontSize: 92}}>From taxonomy to publishable research.</h2>
        <p style={{...styles.body, fontSize: 31, marginTop: 34}}>
          The same source powers the browser, Telegram one-pagers, slide PDFs,
          A4 prospectuses, and scheduled sector rotation.
        </p>
      </div>
      <div style={{display: "grid", gap: 22, paddingTop: 16}}>
        <Pill frame={frame} delay={12} active>Interactive sector browser</Pill>
        <Pill frame={frame} delay={20}>Telegram 4x5 one-pager</Pill>
        <Pill frame={frame} delay={28}>16:9 slide PDF</Pill>
        <Pill frame={frame} delay={36}>A4 magazine prospectus</Pill>
      </div>
    </div>
  </SceneShell>
);

export const SectorUniverseExplainer: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={styles.stage}>
      <Sequence durationInFrames={75}>
        <IntroScene frame={frame} />
      </Sequence>
      <Sequence from={75} durationInFrames={75}>
        <ExploreScene frame={frame - 75} />
      </Sequence>
      <Sequence from={150} durationInFrames={75}>
        <GraphScene frame={frame - 150} />
      </Sequence>
      <Sequence from={225} durationInFrames={75}>
        <OutputScene frame={frame - 225} />
      </Sequence>
    </AbsoluteFill>
  );
};
