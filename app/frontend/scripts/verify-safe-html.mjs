import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Script } from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../src/safeHtml.ts', import.meta.url), 'utf8');
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;

const sandbox = { exports: {} };
new Script(transpiled).runInNewContext(sandbox);

const { escapeHtml, sanitizeHtml } = sandbox.exports;

assert.equal(
  escapeHtml('<img src=x onerror=alert(1)> "quote" & \'apostrophe\''),
  '&lt;img src=x onerror=alert(1)&gt; &quot;quote&quot; &amp; &#39;apostrophe&#39;'
);

const payload = [
  '<script>alert(1)</script>',
  '<iframe src="https://evil.example"></iframe>',
  '<a href="javascript:alert(1)" onclick="alert(2)">quoted</a>',
  '<a href=javascript:alert(1) onmouseover=alert(2)>unquoted</a>',
  '<img src="data:text/html,<script>alert(1)</script>" onerror="alert(2)">',
].join('\n');

const cleaned = sanitizeHtml(payload);

assert.equal(/<\/?(?:script|iframe)\b/i.test(cleaned), false, cleaned);
assert.equal(/\son\w+\s*=/i.test(cleaned), false, cleaned);
assert.equal(/(?:href|src)\s*=\s*["']?\s*(?:javascript:|data:text\/html|vbscript:)/i.test(cleaned), false, cleaned);

console.log('safeHtml XSS smoke ok');
