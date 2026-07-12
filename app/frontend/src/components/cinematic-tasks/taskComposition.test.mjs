import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicTasks.tsx', import.meta.url), 'utf8');
const taskRoutes = readFileSync(new URL('../../../../../src/zhiji_backend/routes/task_routes.py', import.meta.url), 'utf8');

test('task center composes the shared cinematic shell and laser workspace', () => {
  assert.match(page, /CinematicTemplatePage/);
  assert.match(page, /CinematicLaserWorkspace/);
  assert.match(page, /LaserFlow/);
  assert.match(page, /task-detail-reader/);
  assert.match(page, /task-core-box/);
});

test('task center preserves an explicit legacy route', () => {
  assert.match(app, /path="tasks" element={<CinematicTasks/);
  assert.match(app, /path="tasks-old" element={<Tasks/);
});

test('AI judgment endpoint returns both the task and visible analysis result', () => {
  assert.match(taskRoutes, /return \{"task": get_task\(task_id\), "judgment": judgment\}/);
});
