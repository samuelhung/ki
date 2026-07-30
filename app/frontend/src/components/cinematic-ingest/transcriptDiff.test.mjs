import assert from 'node:assert/strict';
import test from 'node:test';

import { alignTranscriptGaps } from './transcriptDiff.ts';

test('aligns punctuation and paragraph changes around stable body anchors', () => {
  const result = alignTranscriptGaps('你好世界第二段', '你好，世界。\n\n第二段！');

  assert.deepEqual(result.body, [...'你好世界第二段']);
  assert.deepEqual(
    result.changes.map(({ index, before, after }) => ({ index, before, after })),
    [
      { index: 2, before: '', after: '，' },
      { index: 4, before: '', after: '。\n\n' },
      { index: 7, before: '', after: '！' },
    ],
  );
});

test('tracks punctuation removal replacement whitespace and trailing gaps', () => {
  const result = alignTranscriptGaps('A，B。 C！', 'A;B\nC？\n');

  assert.deepEqual(result.body, ['A', 'B', 'C']);
  assert.deepEqual(result.changes, [
    { index: 1, before: '，', after: ';' },
    { index: 2, before: '。 ', after: '\n' },
    { index: 3, before: '！', after: '？\n' },
  ]);
});

test('keeps emoji as body anchors and rejects any body mutation', () => {
  assert.deepEqual(alignTranscriptGaps('你好🙂世界', '你好，🙂\n世界').body, [
    '你', '好', '🙂', '世', '界',
  ]);
  assert.throws(
    () => alignTranscriptGaps('ABC123', 'abc123'),
    /正文字符不一致/,
  );
});
