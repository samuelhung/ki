export interface TranscriptGapChange {
  index: number;
  before: string;
  after: string;
}

export interface TranscriptGapAlignment {
  body: string[];
  beforeGaps: string[];
  afterGaps: string[];
  changes: TranscriptGapChange[];
}

const punctuation = /\p{P}/u;

function splitBodyAndGaps(value: string) {
  const body: string[] = [];
  const gaps: string[] = [''];
  for (const char of value) {
    if (/\s/u.test(char) || punctuation.test(char)) {
      gaps[gaps.length - 1] += char;
    } else {
      body.push(char);
      gaps.push('');
    }
  }
  return { body, gaps };
}

export function alignTranscriptGaps(
  before: string,
  after: string,
): TranscriptGapAlignment {
  const source = splitBodyAndGaps(before);
  const candidate = splitBodyAndGaps(after);
  if (
    source.body.length !== candidate.body.length
    || source.body.some((char, index) => char !== candidate.body[index])
  ) {
    throw new Error('正文字符不一致');
  }
  const changes = source.gaps.flatMap((gap, index) => (
    gap === candidate.gaps[index]
      ? []
      : [{ index, before: gap, after: candidate.gaps[index] }]
  ));
  return {
    body: source.body,
    beforeGaps: source.gaps,
    afterGaps: candidate.gaps,
    changes,
  };
}
