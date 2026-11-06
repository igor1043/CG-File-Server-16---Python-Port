# Visual cache lifecycle

Server16 performs asynchronous maintenance when it binds a FIFA installation and
after FIFA and its asset helpers terminate. A launch request cancels an in-flight
sweep before starting FIFA. No native model or texture is removed while FIFA is
running. Interrupted sessions are handled on the next Server16 launch.

The policy owns exact generated locations, not all files under `runtime`:

- Manager screen packages and renderer IPC jobs: discard after the session.
- Manager artwork: retain one recent ZIP, at most 256 MiB.
- Manager template: retain one BIG/JSON pair, at most 64 MiB.
- Converted manager textures: retain at most 128 MiB.
- Prepared animated models: retain complete units under a shared 768 MiB budget;
  material files have a separate 256 MiB budget.
- Published numeric `server16_club_xi/<PID>/` paths: discard after their process
  has ended. Hardlink accounting counts content only when its last name is removed.
- Frontend stadium copies: retain at most two, within 1536 MiB; only evict copies
  whose original library package still exists.
- Match stadium copies: invalidate the managed match routes while FIFA is closed,
  then discard immutable copies. Original stadium libraries and native slots remain.
- Old dressing-room generated hashes: retain every shipped path from
  `assets/cache_protected_assets.json`, every currently published resource and
  every geometry in the active V3 manifest. If policy/descriptors are missing or
  invalid, skip room pruning. Static shared assets are never selected by age.

Budgets are enforced between sessions. Resources used by a live game may exceed
them temporarily; the next maintenance removes superseded versions. Removing
reusable caches can slow their next generation, so recent valid units are retained.

Saves, SQL databases (including WAL/SHM), financial data, coach history, preferences,
calendar captures (`league_days`), native save receipts (`save_events`), source
assets, editable artwork, native recovery transactions and backups are excluded.
Directory junctions and file links are not traversed. Every mutation revalidates
the resolved path, and installations use a cross-process cleanup lock.

Locked generated files are moved, when permitted, to a sibling directory named
`FIFA16-cache-descartavel-<game folder>`. Moving files does not free disk space;
reports separate moved bytes from released content. Files that cannot be moved
are logged and retried at a subsequent session boundary.

The existing “Clean cache” button now queues this same maintenance. English,
Portuguese and Spanish messages explain when it will run. The latest outcome is
`runtime/cache_maintenance/last.json` and a brief entry in the Server16 log.

When shipping new room assets, regenerate the protected path list from the clean
distribution tree, never from a developer's generated runtime. The frozen build
must include this JSON; `--server16-selftest` verifies that it loads.
