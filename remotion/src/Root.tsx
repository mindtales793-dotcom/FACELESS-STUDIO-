import React from "react";
import { Composition } from "remotion";
import { FacelessScene, type FacelessSceneProps } from "./compositions/FacelessScene";

const defaultProps: FacelessSceneProps = {
  text: "Sua próxima história começa aqui.",
  duration: 5,
  width: 1280,
  height: 720,
  cor_primaria: "#2F6FED",
  estilo: "documentario",
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="FacelessScene"
    component={FacelessScene}
    durationInFrames={120}
    fps={24}
    width={1280}
    height={720}
    defaultProps={defaultProps}
    calculateMetadata={({ props }) => {
      const sceneProps = props as unknown as FacelessSceneProps;
      return {
        durationInFrames: Math.max(1, Math.ceil(sceneProps.duration * 24)),
        width: sceneProps.width,
        height: sceneProps.height,
      };
    }}
  />
);
