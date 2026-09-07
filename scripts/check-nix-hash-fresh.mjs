#!/usr/bin/env node
// Use the branch diff as a fast path, then verify inconclusive lock-only changes
// against the committed dependency derivation. Rebuild fixed-output dependencies
// so a cached store path cannot hide a stale hash.
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

function git(args) {
  return execFileSync('git', args, { encoding: 'utf8' }).trim();
}

function resolveBaseRef() {
  for (const [ref, fullRef] of [
    ['origin/HEAD', 'refs/remotes/origin/HEAD'],
    ['origin/main', 'refs/remotes/origin/main'],
  ]) {
    try {
      git(['show-ref', '--verify', '--quiet', fullRef]);
      return ref;
    } catch {
      // ref is unavailable
    }
  }
  try {
    const upstream = git(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}']);
    return upstream || null;
  } catch {
    return null;
  }
}

const base = resolveBaseRef();
if (!base) {
  console.log('[nix-hash-freshness] no upstream/origin ref found, skipping (bootstrap push).');
  process.exit(0);
}

let changedFiles;
try {
  changedFiles = git(['diff', '--name-only', `${base}...HEAD`])
    .split('\n')
    .filter(Boolean);
} catch (error) {
  console.log(`[nix-hash-freshness] could not diff against ${base}, skipping. (${error.message})`);
  process.exit(0);
}

const lockChanged = changedFiles.includes('pnpm-lock.yaml');
const flakeChanged = changedFiles.includes('flake.nix');

if (!lockChanged || flakeChanged) {
  process.exit(0);
}

console.log('[nix-hash-freshness] lockfile changed without flake.nix; verifying the committed dependency hash.');
try {
  const source = pathToFileURL(git(['rev-parse', '--show-toplevel']));
  source.searchParams.set('rev', git(['rev-parse', 'HEAD']));
  source.hash = 'pythinker-code.pnpmDeps';
  execFileSync('nix', ['build', `git+${source.href}`, '--rebuild', '--no-link'], {
    stdio: 'inherit',
    timeout: 600_000,
  });
} catch (error) {
  console.error(
    '[nix-hash-freshness] could not verify the committed dependency hash. ' +
      'Install Nix if unavailable, resolve build errors, or refresh flake.nix with the reported hash.',
  );
  console.error(error.message);
  process.exit(1);
}
