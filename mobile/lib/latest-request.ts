export interface LatestRequest {
  signal: AbortSignal;
  isCurrent: () => boolean;
}

export class LatestRequestGate {
  private generation = 0;
  private controller: AbortController | null = null;

  start(): LatestRequest {
    const generation = ++this.generation;
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    return {
      signal: controller.signal,
      isCurrent: () => (
        generation === this.generation
        && controller === this.controller
        && !controller.signal.aborted
      ),
    };
  }

  abort(): void {
    this.generation += 1;
    this.controller?.abort();
    this.controller = null;
  }
}