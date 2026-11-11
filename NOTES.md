# NOTES: lineage-lab

Rules: under 150 lines. Current state, open questions, last two steps' result + additions. Older sections go to `NOTES-archive.md` (the factory rotates).

## Current state
L1 is done (11 Nov 2026). Both stacks are running: lineagelab_om is OpenMetadata 2.0.5 (UI and API http://localhost:8585, ingestion container openmetadata_ingestion) and lineagelab_marquez is Marquez 0.51.1 (API http://localhost:5000, UI http://localhost:3000). Image tags, ports, and URLs are in stack/versions.yaml; the Docker engine version is null because it could not be queried. The OpenMetadata release compose file is git-ignored and is not re-downloaded by stack up yet. lineagelab.stack and lineagelab.om are in place; the catalogue is empty for L2. The governor test bed was not changed.

## Open questions
- Docker engine / compose version not recorded: `docker version` / `docker compose version` were blocked by the factory session's permission rules (`docker ps` was allowed). `stack/versions.yaml` has `docker_engine: null`.
- OM compose binds `./docker-volume/db-data-postgres` (relative to `stack/openmetadata/`) for its Postgres data; git-ignored. `down` keeps it and the named volumes.
- OM compose uses fixed `container_name`s (`openmetadata_server`, `openmetadata_ingestion`, ...): L2's `docker exec` target is `openmetadata_ingestion`.

## Relocks
- 11 Nov 2026 23:07: L1 stop secret_in_diff: the OpenMetadata release compose file holds upstream default keys; it is now git-ignored and L2 makes stack up download it (via supervise, by Claude, delegated by Amir via chat 11 Nov) (changed: plan/accept/accept_l2.py, plan/prompts/L2.md)

## L1 result
*The two stacks (OpenMetadata 2.0.5, Marquez) and the OpenMetadata client, 11 Nov 2026 23:12.*

Implementer `claude-tc-opus`; reviewers `cursor-grok`: pass; 0 fix loop(s); branch `factory/L1`.

| check | ok | detail |
|---|---|---|
| OpenMetadata compose file names its release URL | yes |  |
| OpenMetadata images are 2.0.5 | yes |  |
| Marquez compose file exists with pinned tags | yes |  |
| stack/versions.yaml exists | yes |  |
| no token in the repo files | yes |  |
| OpenMetadata is up | yes | {'up': True, 'version': '2.0.5', 'url': 'http://localhost:8585'} |
| Marquez is up | yes | {'up': True, 'url': 'http://localhost:5000'} |
| OpenMetadata reports version 2.0.x | yes | 2.0.5 |
| Marquez API answers | yes | 200 |
| om.client() logs in and an unknown table is None | yes |  |
| pytest tests | yes | 5 passed in 0.22s |
| required tests present | yes | 4 found |

Review: L1 is in place and the acceptance pass is consistent with the code. Image tags are pinned and listed in stack/versions.yaml. The OpenMetadata compose file is the 2.0.5 release file plus a dated source comment, git-ignored so upstream default keys stay out of the commit. Marquez 0.51.1 is pinned; its database port is not published. stack.py uses only compose projects lineagelab_om and lineagelab_marquez with -p, and down keeps volumes. om.table and om.upstream reshape API fields (paging.total, edges by id) and return None for an unknown table. Docker engine version is recorded as null.

For Amir: plan/prompts/L2.md and plan/accept/accept_l2.py were edited so the next step downloads the git-ignored OpenMetadata compose file. That edit is outside L1's allowed paths; NOTES records it as delegated after the secret_in_diff stop. This review did not re-download the release file to byte-compare it. Committed files contain only documented local defaults (OpenMetadata admin, Marquez dev database). Docker engine version is still null.

## Additions for L2
The OpenMetadata compose file is git-ignored (stack/openmetadata/docker-compose.yml) because the release file contains upstream default keys. It is present on this machine with a first comment line dated 2026-11-11; stack up does not download it yet. L2's prompt item 0 is already updated to download it from stacks.om.source in stack/versions.yaml when missing, and accept_l2.py requires test_missing_compose_file_is_downloaded_from_the_recorded_url. Both stacks are left running: OpenMetadata 2.0.5 at http://localhost:8585 (project lineagelab_om, ingestion container openmetadata_ingestion, Airflow 8080, search 9200, its Postgres published on 5432) and Marquez 0.51.1 at http://localhost:5000 with UI on 3000 (project lineagelab_marquez; DB port not published). Use 0.51.1, not the older GitHub release 0.50.0. om.client() keeps the ingestion-bot JWT in memory; bot_token() returns it for the workflow file under work/. Login is POST /api/v1/users/login with a base64 password; the bot JWT is GET /api/v1/bots/name/ingestion-bot then GET /api/v1/users/auth-mechanism/{id}. table() uses paging.total; upstream() joins upstreamEdges by entity id. The catalogue is empty. docker_engine in versions.yaml is null. Do not start, stop, or change the governor test bed (host port 55432).
