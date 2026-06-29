# Social Network application (DeathStarBench)

Application **source and deployment files** for the `socialnet` suite.

## Layout

```text
apps/socialnet/
  source/          -> symlink to DeathStarBench/socialNetwork-tail
  deploy.sh        -> deploy the Swarm stack from source/
  README.md
```

Eval definitions (workloads, problems) live in `cloudperfeval/suites/socialnet/`.
Cluster URLs for running problems live in `config.yml` under `suites.socialnet`.

## Source

`source/` points at [DeathStarBench socialNetwork-tail](https://github.com/delimitrou/DeathStarBench/tree/master/socialNetwork-tail).
Replace the symlink with a git submodule or vendored copy if you prefer:

```bash
git submodule add https://github.com/delimitrou/DeathStarBench.git apps/socialnet/vendor/DeathStarBench
# then point source/ at vendor/DeathStarBench/socialNetwork-tail
```

## Deploy

From the cloudperfeval repo root:

```bash
./apps/socialnet/deploy.sh
```

This runs `docker stack deploy` using `source/docker-compose-swarm.yml` and stack
name `sn` (override with `STACK_NAME=...`).
