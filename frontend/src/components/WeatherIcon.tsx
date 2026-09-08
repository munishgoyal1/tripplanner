import { Cloud, CloudFog, CloudLightning, CloudRain, CloudSun, CircleHelp, Snowflake, Sun } from "lucide-react";
import type { WeatherCondition } from "../types";

const ICONS = {
  clear: Sun,
  partly_cloudy: CloudSun,
  cloudy: Cloud,
  fog: CloudFog,
  rain: CloudRain,
  storm: CloudLightning,
  snow: Snowflake,
  unknown: CircleHelp,
};

export default function WeatherIcon({ condition, size = 18 }: { condition: WeatherCondition; size?: number }) {
  const Icon = ICONS[condition] || CircleHelp;
  return <Icon size={size} aria-hidden />;
}