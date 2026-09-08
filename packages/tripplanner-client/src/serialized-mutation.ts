export type SerializedMutation<T> = () => Promise<T>;

export class SerializedMutationQueue {
  private pending: Promise<void> = Promise.resolve();

  run<T>(mutation: SerializedMutation<T>): Promise<T> {
    const result = this.pending.then(mutation);
    this.pending = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }
}