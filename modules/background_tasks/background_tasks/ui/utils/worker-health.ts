/**
 * The one "is the fleet healthy" decision, shared by every place on this page
 * that needs to explain a stalled queue.
 *
 * `TasksEmptyRow` and `WorkerHealthBanner` used to each re-derive this from
 * their own projection of the worker snapshot (a server-rendered
 * `{broker_reachable, worker_count}` prop vs. a client-fetched
 * `WorkerSnapshot`), with the same two-branch logic and independently
 * drifting wording. Both branches always meant the same thing — broker down,
 * or broker up but nobody consuming the queue — so the decision now lives in
 * one place; only the copy for each surface is left to the caller.
 */
export type WorkerHealthState = 'broker_unreachable' | 'no_workers_online' | 'healthy';

export function diagnoseWorkerHealth(input: {
  brokerReachable: boolean;
  onlineWorkerCount: number;
}): WorkerHealthState {
  if (!input.brokerReachable) return 'broker_unreachable';
  if (input.onlineWorkerCount === 0) return 'no_workers_online';
  return 'healthy';
}
