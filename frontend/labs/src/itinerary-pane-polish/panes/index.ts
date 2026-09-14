import type { ComponentType } from "react";
import type { OptionId } from "../options";
import type { PlannerState } from "../state";
import { AgendaPane } from "./AgendaPane";
import { CardsPane } from "./CardsPane";
import { CrispPane } from "./CrispPane";
import { TimelinePane } from "./TimelinePane";
import { WarmPane } from "./WarmPane";

export const PANES: Record<OptionId, ComponentType<{ state: PlannerState }>> = {
  crisp: CrispPane,
  timeline: TimelinePane,
  warm: WarmPane,
  agenda: AgendaPane,
  cards: CardsPane,
};
