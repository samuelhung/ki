import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import ts from 'typescript';
import { isLatestRequest } from './ingest/ingestRequestPolicy.ts';
import { RequestLifecycle } from './ingest/requestLifecycle.ts';

export function readSourceModules(urls) {
  return urls.filter(existsSync).map((url) => {
    const source = readFileSync(url, 'utf8');
    const name = url.pathname.split('/').at(-1) || 'source.tsx';
    return {
      name,
      source,
      sourceFile: ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX),
    };
  });
}

export function combinedSource(modules) {
  return modules.map((module) => module.source).join('\n');
}

export function declarationText(modules, name) {
  for (const module of modules) {
    const statement = module.sourceFile.statements.find((candidate) => {
      if (ts.isFunctionDeclaration(candidate)) return candidate.name?.text === name;
      if (!ts.isVariableStatement(candidate)) return false;
      return candidate.declarationList.declarations.some((declaration) => (
        ts.isIdentifier(declaration.name) && declaration.name.text === name
      ));
    });
    if (statement) return statement.getText(module.sourceFile).replace(/^export\s+(?:default\s+)?/, '');
  }
  assert.fail(`Expected ${name} in ${modules.map((module) => module.name).join(', ')}`);
}

export function loadPureDeclarations(modules, names, dependencies = {}) {
  const compiled = ts.transpileModule(names.map((name) => declarationText(modules, name)).join('\n'), {
    compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return Function(...Object.keys(dependencies), `${compiled}\nreturn { ${names.join(', ')} };`)(...Object.values(dependencies));
}

function exportedObjectMembers(module, typeName) {
  for (const statement of module.sourceFile.statements) {
    const exported = statement.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword);
    if (!exported || statement.name?.text !== typeName) continue;
    if (ts.isInterfaceDeclaration(statement)) return statement.members;
    if (ts.isTypeAliasDeclaration(statement) && ts.isTypeLiteralNode(statement.type)) return statement.type.members;
  }
  return null;
}

export function assertExportedObjectType(modules, typeName, expectedShape) {
  let members = null;
  let owner = null;
  for (const module of modules) {
    members = exportedObjectMembers(module, typeName);
    if (members) {
      owner = module;
      break;
    }
  }
  assert.ok(members && owner, `Expected exported ${typeName} object type`);

  const actual = {};
  for (const member of members) {
    assert.ok(ts.isPropertySignature(member) && member.type, `${typeName} must contain only typed properties`);
    const name = member.name.getText(owner.sourceFile).replace(/^['"]|['"]$/g, '');
    actual[name] = {
      type: member.type.getText(owner.sourceFile).replace(/\s+/g, ''),
      optional: Boolean(member.questionToken),
    };
  }
  assert.deepEqual(actual, expectedShape);
}

export function assertNamedImports(module, moduleSpecifier, expectedNames) {
  const declaration = module.sourceFile.statements.find((statement) => (
    ts.isImportDeclaration(statement)
    && ts.isStringLiteral(statement.moduleSpecifier)
    && statement.moduleSpecifier.text === moduleSpecifier
  ));
  assert.ok(declaration, `${module.name} must import ${moduleSpecifier}`);
  const bindings = declaration.importClause?.namedBindings;
  assert.ok(bindings && ts.isNamedImports(bindings), `${module.name} must use named imports from ${moduleSpecifier}`);
  const actualNames = new Map(bindings.elements.map((element) => [
    element.propertyName?.text || element.name.text,
    element.name.text,
  ]));
  for (const expectedName of expectedNames) {
    assert.equal(
      actualNames.get(expectedName),
      expectedName,
      `${module.name} must import ${expectedName} without aliasing from ${moduleSpecifier}`,
    );
  }
}

export function variableArrayInitializer(modules, name) {
  for (const module of modules) {
    for (const statement of module.sourceFile.statements) {
      if (!ts.isVariableStatement(statement)) continue;
      const declaration = statement.declarationList.declarations.find((candidate) => (
        ts.isIdentifier(candidate.name) && candidate.name.text === name
      ));
      if (declaration?.initializer && ts.isArrayLiteralExpression(declaration.initializer)) {
        return { initializer: declaration.initializer, sourceFile: module.sourceFile };
      }
    }
  }
  assert.fail(`Expected array ${name}`);
}

export function objectArrayValues(modules, name) {
  const { initializer, sourceFile } = variableArrayInitializer(modules, name);
  return initializer.elements.map((element) => {
    assert.ok(ts.isObjectLiteralExpression(element), `${name} entries must be object literals`);
    return Object.fromEntries(element.properties.map((property) => {
      assert.ok(ts.isPropertyAssignment(property), `${name} entries must use property assignments`);
      const key = property.name.getText(sourceFile).replace(/^['"]|['"]$/g, '');
      const value = property.initializer.getText(sourceFile).replace(/^['"]|['"]$/g, '');
      return [key, value];
    }));
  });
}

export function jsxExpressionProps(module, componentName) {
  let attributes = null;
  function visit(node) {
    if (attributes) return;
    if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && node.tagName.getText(module.sourceFile) === componentName) {
      attributes = node.attributes.properties;
      return;
    }
    ts.forEachChild(node, visit);
  }
  visit(module.sourceFile);
  assert.ok(attributes, `Expected <${componentName}> in ${module.name}`);

  return Object.fromEntries(attributes.filter(ts.isJsxAttribute).map((attribute) => {
    const name = attribute.name.getText(module.sourceFile);
    const expression = attribute.initializer && ts.isJsxExpression(attribute.initializer)
      ? attribute.initializer.expression?.getText(module.sourceFile) || ''
      : '';
    return [name, expression];
  }));
}

export function assertForwardedCallbacks(module, componentName, expectedCallbacks) {
  const props = jsxExpressionProps(module, componentName);
  for (const [callbackName, expectedHandler] of Object.entries(expectedCallbacks)) {
    assert.ok(Object.hasOwn(props, callbackName), `<${componentName}> must receive ${callbackName}`);
    assert.equal(
      props[callbackName],
      expectedHandler,
      `<${componentName}>.${callbackName} must forward ${expectedHandler}`,
    );
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

export function loadRequestCoordinatorFactory(module) {
  const statement = module.sourceFile.statements.find((candidate) => {
    if (ts.isFunctionDeclaration(candidate)) return candidate.name?.text === 'createRequestCoordinator';
    if (!ts.isVariableStatement(candidate)) return false;
    return candidate.declarationList.declarations.some((declaration) => (
      ts.isIdentifier(declaration.name) && declaration.name.text === 'createRequestCoordinator'
    ));
  });
  assert.ok(statement, `${module.name} must declare createRequestCoordinator`);
  assert.ok(
    statement.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword),
    `${module.name} must export createRequestCoordinator`,
  );
  const source = statement.getText(module.sourceFile).replace(/^export\s+(?:default\s+)?/, '');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return Function(
    'RequestLifecycle',
    'isLatestRequest',
    `${compiled}\nreturn createRequestCoordinator;`,
  )(RequestLifecycle, isLatestRequest);
}

export async function assertRequestCoordinatorBehavior(createRequestCoordinator) {
  assert.equal(typeof createRequestCoordinator, 'function', 'hook must export createRequestCoordinator');
  const commits = [];
  const errors = [];
  const coordinator = createRequestCoordinator({
    onCommit: (value) => commits.push(value),
    onError: (reason) => errors.push(reason),
  });
  for (const method of ['start', 'run', 'mutateAndRefresh', 'abort']) {
    assert.equal(typeof coordinator?.[method], 'function', `request coordinator must expose ${method}()`);
  }

  const stale = deferred();
  const firstOwner = coordinator.start('item-a');
  const staleRun = coordinator.run({
    owner: firstOwner,
    selectedId: 'item-a',
    request: () => stale.promise,
  });
  const secondOwner = coordinator.start('item-b');
  assert.equal(firstOwner.signal.aborted, true, 'starting a new request must cancel the previous owner');

  await coordinator.run({
    owner: secondOwner,
    selectedId: 'different-item',
    request: async () => ({ id: 'wrong-owner' }),
  });
  assert.deepEqual(commits, [], 'a response must not commit for a different selected id');

  await coordinator.run({
    owner: secondOwner,
    selectedId: 'item-b',
    request: async () => ({ id: 'item-b' }),
  });
  stale.resolve({ id: 'item-a' });
  await staleRun;
  assert.deepEqual(commits, [{ id: 'item-b' }], 'stale responses must not overwrite the latest result');

  const mutationCalls = [];
  const mutationOwner = coordinator.start('item-c');
  await coordinator.mutateAndRefresh({
    owner: mutationOwner,
    selectedId: 'item-c',
    mutate: async () => { mutationCalls.push('mutation'); },
    refresh: async () => { mutationCalls.push('refresh'); return { id: 'item-c', refreshed: true }; },
  });
  assert.deepEqual(mutationCalls, ['mutation', 'refresh']);
  assert.deepEqual(commits.at(-1), { id: 'item-c', refreshed: true });

  const failure = new Error('request failed');
  const errorOwner = coordinator.start('item-d');
  await coordinator.run({
    owner: errorOwner,
    selectedId: 'item-d',
    request: async () => { throw failure; },
  });
  assert.deepEqual(errors, [failure], 'the current request error must commit exactly once');

  const errorCountBeforeAbort = errors.length;
  const running = deferred();
  const abortedOwner = coordinator.start('item-e');
  const abortedRun = coordinator.run({
    owner: abortedOwner,
    selectedId: 'item-e',
    request: () => running.promise,
  });
  coordinator.abort();
  assert.equal(abortedOwner.signal.aborted, true, 'abort() must cancel the current owner');
  running.reject(new DOMException('Aborted', 'AbortError'));
  await abortedRun;
  assert.equal(errors.length, errorCountBeforeAbort, 'an in-flight abort must not commit an error');

  const staleFailure = new Error('stale request failed');
  const staleRejection = deferred();
  const staleOwner = coordinator.start('item-f');
  const staleRejectedRun = coordinator.run({
    owner: staleOwner,
    selectedId: 'item-f',
    request: () => staleRejection.promise,
  });
  coordinator.start('item-g');
  staleRejection.reject(staleFailure);
  await staleRejectedRun;
  assert.equal(errors.length, errorCountBeforeAbort, 'a stale rejection must not commit an error');

  const commitCountBeforeMutationRaces = commits.length;
  const pendingMutation = deferred();
  let refreshAfterStaleMutation = 0;
  const mutationRaceOwner = coordinator.start('item-h');
  const mutationRace = coordinator.mutateAndRefresh({
    owner: mutationRaceOwner,
    selectedId: 'item-h',
    mutate: () => pendingMutation.promise,
    refresh: async () => { refreshAfterStaleMutation += 1; return { id: 'item-h' }; },
  });
  coordinator.start('item-i');
  pendingMutation.resolve();
  await mutationRace;
  assert.equal(refreshAfterStaleMutation, 0, 'owner changes during mutation must suppress refresh');
  assert.equal(commits.length, commitCountBeforeMutationRaces);

  const pendingRefresh = deferred();
  const refreshStarted = deferred();
  const refreshRaceOwner = coordinator.start('item-j');
  const refreshRace = coordinator.mutateAndRefresh({
    owner: refreshRaceOwner,
    selectedId: 'item-j',
    mutate: async () => {},
    refresh: () => { refreshStarted.resolve(); return pendingRefresh.promise; },
  });
  await refreshStarted.promise;
  coordinator.start('item-k');
  pendingRefresh.resolve({ id: 'item-j', stale: true });
  await refreshRace;
  assert.equal(commits.length, commitCountBeforeMutationRaces, 'owner changes during refresh must suppress commit');
}
