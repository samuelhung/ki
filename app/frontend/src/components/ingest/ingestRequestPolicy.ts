export function isLatestRequest(sequence: number, latestSequence: number) {
  return sequence === latestSequence;
}
