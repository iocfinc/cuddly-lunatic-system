import "./index.css";
import {Composition} from "remotion";
import {SectorUniverseExplainer} from "./SectorUniverseExplainer";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="SectorUniverseExplainer"
      component={SectorUniverseExplainer}
      durationInFrames={300}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
