import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";

export interface FacelessSceneProps {
  text: string;
  duration: number;
  width: number;
  height: number;
  cor_primaria?: string;
  estilo?: string;
}

const STYLE_COLORS: Record<string, { bg: string; text: string; accent: string }> = {
  documentario: { bg: "#0B0F19", text: "#EAF2FF", accent: "#2F6FED" },
  historia_sepia: { bg: "#2B1A0B", text: "#F6EAD0", accent: "#B8860B" },
  noir: { bg: "#000000", text: "#FFFFFF", accent: "#FF4D5E" },
  misterio: { bg: "#1A1A2E", text: "#A9CCDE", accent: "#FF4D5E" },
};

export const FacelessScene: React.FC<FacelessSceneProps> = ({
  text,
  duration,
  cor_primaria = "#2F6FED",
  estilo = "documentario",
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const safeDuration = Math.max(1, duration);
  const progress = Math.min(1, frame / (safeDuration * fps));
  const colors = STYLE_COLORS[estilo] || {
    bg: "#0B0F19",
    text: "#EAF2FF",
    accent: cor_primaria,
  };
  const title = text.trim().split(/(?<=[.!?])\s+/)[0] || text.trim();
  const remainder = text.trim().slice(title.length).trim();
  const titleSize = Math.max(32, Math.min(76, width * 0.055));
  const opacity = Math.min(1, progress * 4 + 0.12);
  const scale = 1.035 - progress * 0.035;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.bg,
        color: colors.text,
        alignItems: "center",
        justifyContent: "center",
        padding: "8%",
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 1500,
          textAlign: "center",
          opacity,
          transform: `scale(${scale})`,
        }}
      >
        <div
          style={{
            width: 72,
            height: 6,
            margin: "0 auto 34px",
            borderRadius: 6,
            backgroundColor: colors.accent,
          }}
        />
        <h1
          style={{
            margin: 0,
            fontSize: titleSize,
            lineHeight: 1.12,
            fontWeight: 800,
            color: colors.text,
          }}
        >
          {title}
        </h1>
        {remainder ? (
          <p
            style={{
              margin: "28px auto 0",
              maxWidth: 1100,
              fontSize: Math.max(22, titleSize * 0.42),
              lineHeight: 1.35,
              color: colors.text,
              opacity: 0.78,
            }}
          >
            {remainder}
          </p>
        ) : null}
        <div
          style={{
            height: 5,
            width: "100%",
            marginTop: 54,
            backgroundColor: "rgba(255,255,255,0.16)",
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${progress * 100}%`,
              backgroundColor: colors.accent,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

FacelessScene.displayName = "FacelessScene";
