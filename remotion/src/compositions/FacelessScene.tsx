import { AbsoluteFill, addEffect, IFrame, Video, useCurrentFrame, useVideoConfig } from "remotion";
import React from "react";

export interface FacelessSceneProps {
  text: string;
  duration: number; // segundos
  width: number;
  height: number;
  cor_primaria?: string;
  estilo?: string; // id do estilo (documentario, noir, etc.)
}

export const FacelessScene = React.memo(
  ({ text, duration, width, height, cor_primaria = "#2F6FED", estilo = "documentario" }: FacelessSceneProps) => {
    const { duration: videoDuration, width: videoWidth, height: videoHeight, fps } = useVideoConfig();
    const frame = useCurrentFrame();
    const seconds = frame / fps;
    const progress = Math.min(1, seconds / duration);

    // Cores por estilo
    const styleColors: Record<string, { bg: string; text: string; accent: string }> = {
      documentario: { bg: "#0B0F19", text: "#EAF2FF", accent: "#2F6FED" },
      historia_sepia: { bg: "#2B1A0B", text: "#F6EAD0", accent: "#B8860B" },
      noir: { bg: "#000000", text: "#FFFFFF", accent: "#FF4D5E" },
      misterio: { bg: "#1A1A2E", text: "#A9CCDE", accent: "#FF4D5E" },
      default: { bg: "#0B0F19", text: "#EAF2FF", accent: cor_primaria },
    };

    const colors = styleColors[estilo] || styleColors.default;

    // Efeito de fade-in baseado no progresso
    const opacity = Math.min(1, progress * 3);

    return (
      <IFrame
        style={{
          width: videoWidth,
          height: videoHeight,
          backgroundColor: colors.bg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: colors.text,
          fontFamily: "Arial, sans-serif",
        }}
      >
        <div
          style={{
            textAlign: "center",
            padding: 40,
            opacity,
            transition: "opacity 1s ease-in-out",
            transform: `scale(${1 - progress * 0.1})`,
          }}
        >
          <h1 style={{ margin: 0, fontSize: 48, color: colors.accent, fontWeight: 700 }}>
            {text.split(".")[0]}
          </h1>
          <p style={{ marginTop: 20, fontSize: 24, opacity: 0.8 }}>
            {text.split(".").slice(1).join(".").trim()}
          </p>
          <div
            style={{
              marginTop: 40,
              width: 300,
              height: 4,
              background: "#333",
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${progress * 100}%`,
                height: "100%",
                background: colors.accent,
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <div style={{ marginTop: 20, fontSize: 16, color: colors.accent, opacity: 0.6 }}>
            {Math.floor(seconds)}s / {duration}s
          </div>
        </div>
      </IFrame>
    );
  },
);

FacelessScene.displayName = "FacelessScene";
