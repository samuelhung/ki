export interface QueuePollItem {
  status?: string;
}

export function shouldPollQueue(modalOpen: boolean, items: QueuePollItem[], pollId: string | null) {
  return modalOpen
    || Boolean(pollId)
    || items.some((item) => item.status === 'pending' || item.status === 'running' || item.status === 'processing');
}

export function isLatestRequest(sequence: number, latestSequence: number) {
  return sequence === latestSequence;
}
