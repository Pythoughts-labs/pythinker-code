import { execFileSync, spawnSync, type SpawnSyncReturns } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

const checkScript = resolve(import.meta.dirname, '../../../../scripts/check-nix-hash-fresh.mjs');
const tempRoots: string[] = [];

afterEach(() => {
  for (const root of tempRoots.splice(0)) rmSync(root, { recursive: true, force: true });
});

describe('check-nix-hash-fresh', () => {
  it('uses current origin/main when a release branch tracks a stale upstream', () => {
    const root = makeRepository('changeset-release/main');
    const staleRelease = revParse(root, 'HEAD');
    setRemoteRef(root, 'changeset-release/main', staleRelease);

    git(root, ['switch', '-c', 'main']);
    writeFileSync(join(root, 'pnpm-lock.yaml'), 'lock from current main\n');
    commit(root, 'update lock on main');
    const currentMain = revParse(root, 'HEAD');
    setRemoteRef(root, 'main', currentMain);

    git(root, ['switch', 'changeset-release/main']);
    git(root, ['reset', '--hard', currentMain]);
    writeFileSync(join(root, 'package.json'), '{"version":"1.0.1"}\n');
    commit(root, 'version packages');

    const result = runCheck(root);
    expect(result.status, result.stderr).toBe(0);
  });

  it('keeps a lock-only branch change gated after that change reaches its upstream', () => {
    const root = makeRepository('feature');
    const currentMain = revParse(root, 'HEAD');
    setRemoteRef(root, 'main', currentMain);

    writeFileSync(join(root, 'pnpm-lock.yaml'), 'unmatched lock change\n');
    commit(root, 'update lock without flake');
    setRemoteRef(root, 'feature', revParse(root, 'HEAD'));
    writeFileSync(join(root, 'README.md'), 'follow-up\n');
    commit(root, 'add follow-up');

    const result = runCheck(root);
    expect(result.status, result.stderr).toBe(1);
    expect(result.stderr).toContain('could not verify the committed dependency hash');
  });

  it('accepts a lock-only change when the dependency rebuild verifies its hash', () => {
    const root = makeRepository('feature');
    setRemoteRef(root, 'main', revParse(root, 'HEAD'));
    writeFileSync(join(root, 'pnpm-lock.yaml'), 'equivalent dependency closure\n');
    commit(root, 'update lock without changing fetched dependencies');

    const result = runCheck(root, 0);
    expect(result.status, result.stderr).toBe(0);
  });
});

function makeRepository(branch: string): string {
  const root = mkdtempSync(join(tmpdir(), 'pythinker-nix-hash-check-'));
  tempRoots.push(root);
  git(root, ['init', '--initial-branch', branch]);
  git(root, ['config', 'core.hooksPath', '.git/no-hooks']);
  git(root, ['config', 'user.name', 'Test User']);
  git(root, ['config', 'user.email', 'test@example.test']);
  git(root, ['config', 'commit.gpgSign', 'false']);
  git(root, ['remote', 'add', 'origin', join(root, 'unused-origin.git')]);
  writeFileSync(join(root, 'pnpm-lock.yaml'), 'initial lock\n');
  writeFileSync(join(root, 'flake.nix'), 'initial flake\n');
  commit(root, 'initial');
  return root;
}

function commit(root: string, message: string): void {
  git(root, ['add', '.']);
  git(root, ['commit', '-m', message]);
}

function setRemoteRef(root: string, branch: string, sha: string): void {
  git(root, ['update-ref', `refs/remotes/origin/${branch}`, sha]);
  git(root, ['config', `branch.${branch}.remote`, 'origin']);
  git(root, ['config', `branch.${branch}.merge`, `refs/heads/${branch}`]);
}

function revParse(root: string, ref: string): string {
  return git(root, ['rev-parse', ref]);
}

function git(root: string, args: string[]): string {
  return execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
}

function runCheck(root: string, nixExitCode = 1): SpawnSyncReturns<string> {
  writeFileSync(join(root, 'nix'), `#!/bin/sh\nexit ${nixExitCode}\n`, { mode: 0o755 });
  return spawnSync(process.execPath, [checkScript], {
    cwd: root,
    encoding: 'utf8',
    env: { ...process.env, PATH: `${root}:${process.env['PATH']}` },
  });
}
