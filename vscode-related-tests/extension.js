const childProcess = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const vscode = require("vscode");

const CONTROLLER_ID = "relatedTests";
const CONTROLLER_LABEL = "Related Tests";
const COVERAGE_DETAILS = new WeakMap();

function activate(context) {
  const workspaceFolder = getWorkspaceFolder();
  if (!workspaceFolder) {
    return;
  }

  const controller = vscode.tests.createTestController(CONTROLLER_ID, CONTROLLER_LABEL);
  const state = {
    controller,
    workspaceFolder,
    metadataScriptPath: path.join(context.extensionPath, "python", "related_tests_metadata.py"),
    scanData: null,
  };

  controller.resolveHandler = async (item) => {
    if (!item) {
      await refreshController(state);
      return;
    }

    const descriptor = decodeId(item.id);
    if (!descriptor) {
      return;
    }

    if (descriptor.type === "source") {
      await resolveSource(state, item, descriptor.source);
    }
  };

  controller.createRunProfile(
    "Run",
    vscode.TestRunProfileKind.Run,
    (request, token) => runRelatedTests(state, request, token),
    true,
  );
  controller.createRunProfile(
    "Debug",
    vscode.TestRunProfileKind.Debug,
    (request, token) => debugRelatedTests(state, request, token),
    true,
  );
  const coverageProfile = controller.createRunProfile(
    "Coverage",
    vscode.TestRunProfileKind.Coverage,
    (request, token) => runRelatedCoverage(state, request, token),
    true,
  );
  coverageProfile.loadDetailedCoverage = async (run, fileCoverage) => {
    const detailsByFile = COVERAGE_DETAILS.get(run);
    return detailsByFile?.get(fileCoverage) || [];
  };

  context.subscriptions.push(
    controller,
    vscode.commands.registerCommand("relatedTests.refreshController", async () => {
      await vscode.commands.executeCommand("workbench.view.testing");
      await refreshController(state);
    }),
    vscode.commands.registerCommand("relatedTests.refreshItem", async (item) => {
      await refreshSelectedItem(state, item);
    }),
    vscode.window.onDidChangeActiveTextEditor(() => {
      void refreshController(state);
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (document.uri.scheme !== "file") {
        return;
      }
      if (!isInsideWorkspace(document.uri.fsPath, state.workspaceFolder.uri.fsPath)) {
        return;
      }
      invalidateScan(state);
      if (getActiveSourcePath(state)) {
        void refreshController(state);
      }
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("relatedTests")) {
        invalidateScan(state);
        void refreshController(state);
      }
    }),
  );

  void refreshController(state);
}

async function refreshController(state) {
  try {
    const activeSourcePath = getActiveSourcePath(state);
    if (!activeSourcePath) {
      invalidateScan(state);
      clearCollection(state.controller.items);
      return;
    }

    const metadata = await inspectSource(state, activeSourcePath);
    replaceRootItems(state, hasMetadata(metadata) ? [metadata] : []);
    if (!hasMetadata(metadata)) {
      clearCollection(state.controller.items);
      return;
    }

    const sourceItem = state.controller.items.get(encodeId({ type: "source", source: metadata.source }));
    if (sourceItem) {
      await resolveSource(state, sourceItem, metadata.source);
    }
  } catch (error) {
    clearCollection(state.controller.items);
    vscode.window.showErrorMessage(`Related Tests failed to load: ${errorMessage(error)}`);
  }
}

async function refreshSelectedItem(state, item) {
  if (!item) {
    await refreshController(state);
    return;
  }

  const descriptor = decodeId(item.id);
  if (!descriptor) {
    await refreshController(state);
    return;
  }

  if (descriptor.type !== "source") {
    await refreshController(state);
    return;
  }

  try {
    const metadata = await inspectSource(state, descriptor.source);
    if (!hasMetadata(metadata)) {
      removeSourceItem(state, descriptor.source);
      return;
    }

    const sourceItem = getOrCreateSourceItem(state, metadata);
    await resolveSource(state, sourceItem, descriptor.source);
  } catch (error) {
    item.error = errorMessage(error);
    vscode.window.showErrorMessage(`Related Tests failed to refresh ${descriptor.source}: ${errorMessage(error)}`);
  }
}

function replaceRootItems(state, scanData) {
  clearCollection(state.controller.items);
  for (const metadata of scanData) {
    state.controller.items.add(createSourceItem(state, metadata));
  }
}

async function resolveSource(state, sourceItem, sourcePath) {
  const metadata = await inspectSource(state, sourcePath);
  if (!hasMetadata(metadata)) {
    removeSourceItem(state, sourcePath);
    return;
  }

  clearCollection(sourceItem.children);
  applyMetadataState(sourceItem, metadata);

  for (const testPath of metadata.tests) {
    const child = state.controller.createTestItem(
      encodeId({ type: "test", source: metadata.source, test: testPath }),
      testPath.replace(/^tests\//, ""),
      vscode.Uri.file(path.join(state.workspaceFolder.uri.fsPath, testPath)),
    );
    child.description = "pytest";
    sourceItem.children.add(child);
  }
}

async function runRelatedTests(state, request, token) {
  const run = state.controller.createTestRun(request);
  try {
    const plan = await buildExecutionPlan(state, request);
    markStarted(
      run,
      Array.from(plan.sourceEntries.values())
        .filter((entry) => entry.finalize)
        .map((entry) => entry.item),
    );
    markStarted(run, collectChildItems(plan.testTargets));

    for (const [testPath, target] of plan.testTargets.entries()) {
      if (token.isCancellationRequested) {
        markSkipped(run, remainingTargets(plan.testTargets, testPath));
        break;
      }

      const startedAt = Date.now();
      const outcome = await runPytestFile(state, run, testPath, token);
      const duration = Date.now() - startedAt;
      const message = buildFailureMessage(testPath, outcome.output);

      for (const childItem of target.childItems) {
        childItem.relatedExitCode = outcome.exitCode;
        if (outcome.exitCode === 0) {
          run.passed(childItem, duration);
        } else {
          run.failed(childItem, message, duration);
        }
      }
    }

    finalizeSourceResults(run, plan.sourceEntries);
  } catch (error) {
    vscode.window.showErrorMessage(`Related Tests failed: ${errorMessage(error)}`);
  } finally {
    run.end();
  }
}

async function debugRelatedTests(state, request, token) {
  const plan = await buildExecutionPlan(state, request);
  const testPaths = Array.from(plan.testTargets.keys());
  if (!testPaths.length || token.isCancellationRequested) {
    return;
  }

  const configuration = getConfiguration();
  const started = await vscode.debug.startDebugging(state.workspaceFolder, {
    name: "Related Tests Debug",
    type: "debugpy",
    request: "launch",
    module: "pytest",
    args: [...configuration.pytestArgs, ...testPaths],
    cwd: state.workspaceFolder.uri.fsPath,
    console: "integratedTerminal",
    justMyCode: false,
    python: configuration.pythonCommand,
    env: processEnv(),
  });

  if (!started) {
    vscode.window.showErrorMessage("Related Tests failed: Could not start debug session.");
  }
}

async function runRelatedCoverage(state, request, token) {
  const run = state.controller.createTestRun(request);
  const detailsByFile = new Map();
  COVERAGE_DETAILS.set(run, detailsByFile);

  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "related-tests-coverage-"));
  const coverageDataFile = path.join(tempDir, ".coverage");
  const coverageJsonFile = path.join(tempDir, "coverage.json");

  void run.onDidDispose?.(() => {
    COVERAGE_DETAILS.delete(run);
    void fs.promises.rm(tempDir, { recursive: true, force: true });
  });

  try {
    const plan = await buildExecutionPlan(state, request);
    markStarted(
      run,
      Array.from(plan.sourceEntries.values())
        .filter((entry) => entry.finalize)
        .map((entry) => entry.item),
    );
    markStarted(run, collectChildItems(plan.testTargets));

    let appendCoverage = false;
    for (const [testPath, target] of plan.testTargets.entries()) {
      if (token.isCancellationRequested) {
        markSkipped(run, remainingTargets(plan.testTargets, testPath));
        break;
      }

      const startedAt = Date.now();
      const outcome = await runPytestWithCoverageFile(
        state,
        run,
        testPath,
        token,
        coverageDataFile,
        appendCoverage,
      );
      appendCoverage = appendCoverage || outcome.exitCode === 0 || outcome.output.length > 0;
      const duration = Date.now() - startedAt;
      const message = buildFailureMessage(testPath, outcome.output);

      for (const childItem of target.childItems) {
        childItem.relatedExitCode = outcome.exitCode;
        if (outcome.exitCode === 0) {
          run.passed(childItem, duration);
        } else {
          run.failed(childItem, message, duration);
        }
      }
    }

    finalizeSourceResults(run, plan.sourceEntries);

    if (!token.isCancellationRequested && fs.existsSync(coverageDataFile)) {
      const exportOutcome = await runPythonModule(
        state,
        run,
        ["coverage", "json", "--data-file", coverageDataFile, "-o", coverageJsonFile],
        token,
      );
      if (exportOutcome.exitCode !== 0) {
        throw new Error(
          exportOutcome.output.trim()
            || "Coverage export failed. Ensure coverage.py is installed in the selected interpreter.",
        );
      }

      addCoverageToRun(state, run, coverageJsonFile, detailsByFile);
    }
  } catch (error) {
    vscode.window.showErrorMessage(buildCoverageErrorMessage(state, error));
  } finally {
    run.end();
  }
}

async function buildExecutionPlan(state, request) {
  const scanData = state.scanData || [];

  const sourceEntries = new Map();
  const testTargets = new Map();
  const excludedIds = new Set((request.exclude || []).map((item) => item.id));
  const excludedTestIds = new Set();
  for (const item of request.exclude || []) {
    const descriptor = decodeId(item.id);
    if (descriptor && descriptor.type === "test") {
      excludedTestIds.add(descriptor.test);
    }
  }

  const runAll = !request.include || request.include.length === 0;
  const selectedItems = runAll
    ? scanData.map((metadata) => getOrCreateSourceItem(state, metadata))
    : request.include;

  for (const item of selectedItems) {
    const descriptor = decodeId(item.id);
    if (!descriptor || excludedIds.has(item.id)) {
      continue;
    }

    if (descriptor.type === "source") {
      const entry = await ensureSourceEntry(state, descriptor.source, sourceEntries);
      entry.finalize = true;
      addAllTestsToTargets(entry, testTargets, excludedTestIds);
      continue;
    }

    if (descriptor.type === "test") {
      if (excludedTestIds.has(descriptor.test)) {
        continue;
      }
      const entry = await ensureSourceEntry(state, descriptor.source, sourceEntries);
      addTestToTargets(entry, descriptor.test, testTargets);
    }
  }

  return { sourceEntries, testTargets };
}

async function ensureSourceEntry(state, sourcePath, sourceEntries) {
  if (sourceEntries.has(sourcePath)) {
    return sourceEntries.get(sourcePath);
  }

  const metadata = await inspectSource(state, sourcePath);
  if (!hasMetadata(metadata)) {
    throw new Error(`No related test metadata found for ${sourcePath}.`);
  }

  const sourceItem = getOrCreateSourceItem(state, metadata);
  await resolveSource(state, sourceItem, sourcePath);

  const testItems = new Map();
  sourceItem.children.forEach((child) => {
    const descriptor = decodeId(child.id);
    if (descriptor && descriptor.type === "test") {
      testItems.set(descriptor.test, child);
    }
  });

  const entry = {
    item: sourceItem,
    metadata,
    testItems,
    selectedTests: new Set(),
    finalize: false,
  };
  sourceEntries.set(sourcePath, entry);
  return entry;
}

function addAllTestsToTargets(entry, testTargets, excludedTestIds) {
  for (const [testPath, childItem] of entry.testItems.entries()) {
    if (excludedTestIds.has(testPath)) {
      continue;
    }
    const target = ensureTarget(testTargets, testPath);
    target.childItems.add(childItem);
    entry.selectedTests.add(testPath);
  }
}

function addTestToTargets(entry, testPath, testTargets) {
  const childItem = entry.testItems.get(testPath);
  if (!childItem) {
    return;
  }
  const target = ensureTarget(testTargets, testPath);
  target.childItems.add(childItem);
  entry.selectedTests.add(testPath);
}

function getOrCreateSourceItem(state, metadata) {
  const sourceId = encodeId({ type: "source", source: metadata.source });
  const existing = state.controller.items.get(sourceId);
  if (existing) {
    applyMetadataState(existing, metadata);
    return existing;
  }

  const item = createSourceItem(state, metadata);
  state.controller.items.add(item);
  return item;
}

function createSourceItem(state, metadata) {
  const sourceUri = vscode.Uri.file(path.join(state.workspaceFolder.uri.fsPath, metadata.source));
  const item = state.controller.createTestItem(
    encodeId({ type: "source", source: metadata.source }),
    metadata.source,
    sourceUri,
  );
  item.canResolveChildren = true;
  applyMetadataState(item, metadata);
  return item;
}

function applyMetadataState(item, metadata) {
  item.description = `${metadata.tests.length} related test${metadata.tests.length === 1 ? "" : "s"}`;
  const problems = [];
  for (const error of metadata.errors) {
    problems.push(error);
  }
  for (const missing of metadata.missing_tests) {
    problems.push(`Missing related test file: ${missing}`);
  }
  item.error = problems.length > 0 ? problems.join("\n") : undefined;
}

function removeSourceItem(state, sourcePath) {
  state.controller.items.delete(encodeId({ type: "source", source: sourcePath }));
}

async function inspectSource(state, sourcePath) {
  const metadata = await runPythonJson(state, ["inspect", "--workspace", ".", sourcePath]);
  if (!state.scanData) {
    state.scanData = [];
  }

  const index = state.scanData.findIndex((item) => item.source === metadata.source);
  if (!hasMetadata(metadata)) {
    if (index >= 0) {
      state.scanData.splice(index, 1);
    }
    return metadata;
  }

  if (index >= 0) {
    state.scanData[index] = metadata;
  } else {
    state.scanData.push(metadata);
    state.scanData.sort((left, right) => left.source.localeCompare(right.source));
  }

  return metadata;
}

function invalidateScan(state) {
  state.scanData = null;
}

function hasMetadata(metadata) {
  return (metadata.tests && metadata.tests.length > 0) || (metadata.errors && metadata.errors.length > 0);
}

function encodeId(value) {
  return JSON.stringify(value);
}

function decodeId(value) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function clearCollection(collection) {
  const ids = [];
  collection.forEach((item) => ids.push(item.id));
  for (const id of ids) {
    collection.delete(id);
  }
}

function collectionHasItems(collection) {
  return countCollectionItems(collection) > 0;
}

function countCollectionItems(collection) {
  let count = 0;
  collection.forEach(() => {
    count += 1;
  });
  return count;
}

function ensureTarget(targets, testPath) {
  const existing = targets.get(testPath);
  if (existing) {
    return existing;
  }
  const created = { childItems: new Set() };
  targets.set(testPath, created);
  return created;
}

function collectChildItems(testTargets) {
  const items = [];
  for (const target of testTargets.values()) {
    for (const childItem of target.childItems) {
      items.push(childItem);
    }
  }
  return items;
}

function remainingTargets(testTargets, currentTestPath) {
  const remaining = [];
  let foundCurrent = false;
  for (const [testPath, target] of testTargets.entries()) {
    if (!foundCurrent) {
      foundCurrent = testPath === currentTestPath;
      continue;
    }
    for (const childItem of target.childItems) {
      remaining.push(childItem);
    }
  }
  return remaining;
}

function markStarted(run, items) {
  for (const item of items) {
    run.started(item);
  }
}

function markSkipped(run, items) {
  for (const item of items) {
    run.skipped(item);
  }
}

function finalizeSourceResults(run, sourceEntries) {
  for (const entry of sourceEntries.values()) {
    if (!entry.finalize) {
      continue;
    }

    const exitCodes = Array.from(entry.selectedTests)
      .map((testPath) => entry.testItems.get(testPath))
      .filter(Boolean)
      .map((item) => item.relatedExitCode)
      .filter((value) => value !== undefined && value !== null);

    if (exitCodes.length === 0) {
      run.skipped(entry.item);
      continue;
    }

    if (exitCodes.some((code) => code !== 0)) {
      run.failed(entry.item, buildFailureMessage(entry.metadata.source, "One or more related tests failed."));
    } else {
      run.passed(entry.item);
    }
  }
}

async function runPytestFile(state, run, testPath, token) {
  const configuration = getConfiguration();
  return runPythonModule(
    state,
    run,
    ["pytest", ...configuration.pytestArgs, testPath],
    token,
    `Failed to start pytest for ${testPath}:`,
  );
}

async function runPytestWithCoverageFile(state, run, testPath, token, coverageDataFile, appendCoverage) {
  const configuration = getConfiguration();
  const args = [
    "coverage",
    "run",
    "--data-file",
    coverageDataFile,
  ];
  if (appendCoverage) {
    args.push("--append");
  }
  args.push("-m", "pytest", ...configuration.pytestArgs, testPath);
  return runPythonModule(
    state,
    run,
    args,
    token,
    `Failed to start pytest coverage for ${testPath}:`,
  );
}

async function runPythonModule(state, run, moduleArgs, token, startErrorPrefix = "Failed to start Python module:") {
  const configuration = getConfiguration();
  const workspaceRoot = state.workspaceFolder.uri.fsPath;

  return new Promise((resolve, reject) => {
    const process = childProcess.spawn(configuration.pythonCommand, ["-m", ...moduleArgs], {
      cwd: workspaceRoot,
      env: processEnv(),
    });

    let output = "";
    let settled = false;

    const finish = (value, isError = false) => {
      if (settled) {
        return;
      }
      settled = true;
      if (isError) {
        reject(value);
      } else {
        resolve(value);
      }
    };

    process.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      output += text;
      run.appendOutput(text);
    });

    process.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      output += text;
      run.appendOutput(text);
    });

    process.on("error", (error) => {
      finish(new Error(`${startErrorPrefix} ${error.message}`), true);
    });

    process.on("close", (exitCode) => {
      finish({ exitCode: exitCode === null ? 1 : exitCode, output });
    });

    token.onCancellationRequested(() => {
      process.kill();
    });
  });
}

function buildFailureMessage(label, output) {
  const trimmed = output.trim();
  const text = trimmed ? trimmed.slice(0, 12000) : `${label} failed.`;
  return new vscode.TestMessage(text);
}

function buildCoverageErrorMessage(state, error) {
  const base = `Related Tests coverage failed: ${errorMessage(error)}`;
  const details = String(errorMessage(error));
  if (!details.includes("No module named coverage")) {
    return base;
  }

  const interpreter = getConfiguration().pythonCommand;
  return `${base}. Install coverage in the selected interpreter (${interpreter}) or switch VS Code to a workspace interpreter that has it.`;
}

function addCoverageToRun(state, run, coverageJsonFile, detailsByFile) {
  const raw = fs.readFileSync(coverageJsonFile, "utf-8");
  const report = JSON.parse(raw || "{}");
  const files = report.files && typeof report.files === "object" ? report.files : {};

  for (const [filePath, fileCoverageData] of Object.entries(files)) {
    const fileUri = resolveCoverageUri(state, filePath);
    if (!fileUri) {
      continue;
    }

    const summary = fileCoverageData.summary || {};
    const covered = Number(summary.covered_lines || 0);
    const total = Number(summary.num_statements || 0);
    if (total <= 0) {
      continue;
    }

    const coverage = new vscode.FileCoverage(
      fileUri,
      new vscode.TestCoverageCount(covered, total),
    );
    const details = buildStatementCoverage(fileCoverageData);
    detailsByFile.set(coverage, details);
    run.addCoverage(coverage);
  }
}

function resolveCoverageUri(state, reportedPath) {
  const workspaceRoot = state.workspaceFolder.uri.fsPath;
  const candidate = path.isAbsolute(reportedPath)
    ? reportedPath
    : path.join(workspaceRoot, reportedPath);
  const normalized = path.resolve(candidate);
  if (!isInsideWorkspace(normalized, workspaceRoot)) {
    return null;
  }
  if (!fs.existsSync(normalized) || !normalized.endsWith(".py")) {
    return null;
  }
  return vscode.Uri.file(normalized);
}

function buildStatementCoverage(fileCoverageData) {
  const executedLines = new Set(Array.isArray(fileCoverageData.executed_lines) ? fileCoverageData.executed_lines : []);
  const missingLines = Array.isArray(fileCoverageData.missing_lines) ? fileCoverageData.missing_lines : [];
  const allLines = new Set([...executedLines, ...missingLines]);
  return Array.from(allLines)
    .filter((line) => Number.isInteger(line) && line > 0)
    .sort((left, right) => left - right)
    .map((line) => new vscode.StatementCoverage(
      executedLines.has(line) ? 1 : 0,
      new vscode.Position(line - 1, 0),
    ));
}

function getConfiguration() {
  const config = vscode.workspace.getConfiguration("relatedTests");
  return {
    pythonCommand: resolvePythonCommand(config),
    pytestArgs: config.get("pytestArgs", []),
  };
}

function resolvePythonCommand(config) {
  const configured = config.get("pythonCommand", "");
  if (typeof configured === "string" && configured.trim()) {
    const resolvedConfigured = expandConfiguredPath(configured.trim());
    if (isRunnablePythonCommand(resolvedConfigured)) {
      return resolvedConfigured;
    }
  }

  const workspaceVenvPython = findWorkspaceVenvPython();
  if (workspaceVenvPython) {
    return workspaceVenvPython;
  }

  const pythonConfig = vscode.workspace.getConfiguration("python");
  const interpreterPath = pythonConfig.get("defaultInterpreterPath", "");
  if (typeof interpreterPath === "string" && interpreterPath.trim()) {
    const resolvedInterpreterPath = expandConfiguredPath(interpreterPath.trim());
    if (isRunnablePythonCommand(resolvedInterpreterPath)) {
      return resolvedInterpreterPath;
    }
  }

  const workspaceFolder = getWorkspaceFolder();
  return "python3";
}

function findWorkspaceVenvPython() {
  const workspaceFolder = getWorkspaceFolder();
  if (!workspaceFolder) {
    return null;
  }

  const workspaceRoot = workspaceFolder.uri.fsPath;
  const candidates = process.platform === "win32"
    ? [
        path.join(workspaceRoot, ".venv", "Scripts", "python.exe"),
        path.join(workspaceRoot, "venv", "Scripts", "python.exe"),
      ]
    : [
        path.join(workspaceRoot, ".venv", "bin", "python"),
        path.join(workspaceRoot, "venv", "bin", "python"),
      ];

  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function expandConfiguredPath(value) {
  const workspaceFolder = getWorkspaceFolder();
  let resolved = value;

  if (workspaceFolder) {
    resolved = resolved.replaceAll("${workspaceFolder}", workspaceFolder.uri.fsPath);
    resolved = resolved.replaceAll(
      "${workspaceFolderBasename}",
      path.basename(workspaceFolder.uri.fsPath),
    );
  }

  resolved = resolved.replace(/\$\{env:([^}]+)\}/g, (_, variableName) => process.env[variableName] || "");
  return resolved;
}

function isRunnablePythonCommand(command) {
  if (!command) {
    return false;
  }

  const looksLikePath = command.includes(path.sep) || path.isAbsolute(command);
  if (!looksLikePath) {
    return true;
  }

  return fs.existsSync(command);
}

function runPythonJson(state, args) {
  const configuration = getConfiguration();
  const workspaceRoot = state.workspaceFolder.uri.fsPath;

  return new Promise((resolve, reject) => {
    const process = childProcess.spawn(
      configuration.pythonCommand,
      [state.metadataScriptPath, ...args],
      {
        cwd: workspaceRoot,
        env: processEnv(),
      },
    );

    let stdout = "";
    let stderr = "";

    process.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    process.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    process.on("error", (error) => {
      reject(new Error(`Failed to start metadata inspection: ${error.message}`));
    });

    process.on("close", (exitCode) => {
      if (exitCode !== 0) {
        reject(new Error(stderr.trim() || stdout.trim() || `Metadata inspection exited with code ${exitCode}.`));
        return;
      }

      try {
        resolve(JSON.parse(stdout || "null"));
      } catch (error) {
        reject(new Error(`Metadata inspection did not return valid JSON: ${error.message}`));
      }
    });
  });
}

function processEnv() {
  return { ...process.env };
}

function getActiveSourcePath(state) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.uri.scheme !== "file") {
    return null;
  }

  const workspaceRoot = state.workspaceFolder.uri.fsPath;
  const filePath = editor.document.uri.fsPath;
  if (!isInsideWorkspace(filePath, workspaceRoot)) {
    return null;
  }

  const relativePath = path.relative(workspaceRoot, filePath).replace(/\\/g, "/");
  return relativePath.endsWith(".py") ? relativePath : null;
}

function isInsideWorkspace(filePath, workspaceRoot) {
  const relative = path.relative(workspaceRoot, filePath);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function getWorkspaceFolder() {
  const folders = vscode.workspace.workspaceFolders || [];
  return folders[0] || null;
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
};
