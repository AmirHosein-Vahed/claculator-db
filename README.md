# calc

A containerized calculator that evaluates arithmetic expressions and stores every
result in SQLite. It runs as a single idle container that you submit calculations
to with `docker exec`.

Pure Python standard library — `sqlite3`, `ast`, `argparse`, `dataclasses`. No
dependencies, no `pip install`, no network access at build time.

## Quick start

```sh
docker compose build
docker compose up -d
docker exec calc calc "2+3*4"
```

```
14
stored as #1 at 2026-10-18T11:14:28.741Z
```

## Usage

The whole interface is the `calc` command inside the container:

```sh
docker exec calc calc "2+3*4"      # 14        evaluate, store, print
docker exec calc calc "7/2"        # 3.5
docker exec calc calc "2 ** 10"    # 1024
docker exec calc calc list         # recent calculations, newest first
docker exec calc calc list -n 5    # just the five most recent
docker exec calc calc show 3       # one record in full
docker exec calc calc clear --yes  # delete the entire history
docker exec calc calc --help
```

`docker compose exec calc calc "2+3*4"` works identically; `container_name: calc`
in the compose file exists so the shorter `docker exec calc ...` form works too.

### Output streams

The result is printed to **stdout** on its own line. The `stored as #id`
confirmation goes to **stderr**, so stdout stays script-friendly:

```sh
RESULT=$(docker exec calc calc "6*7")
echo "$RESULT"   # 42
```

### Exit codes

| Code | Meaning                                                       |
|------|---------------------------------------------------------------|
| `0`  | Success                                                       |
| `1`  | Bad expression, unknown id, or storage failure                 |
| `2`  | No arguments given                                            |

## Expression language

Supported: numeric literals (integers and floats, including `1e5` and `0x10`),
parentheses, and the operators `+`, `-`, `*`, `/`, `//`, `%`, `**`, plus unary
`+` and `-`.

**Expressions are never passed to `eval()`.** Input is parsed with the `ast`
module and walked against an explicit allowlist of node types. Names, function
calls, attribute access, subscripts, comprehensions, lambdas, strings, and
booleans are all rejected before anything can execute:

```
$ docker exec calc calc "__import__('os').system('rm -rf /')"
calc: cannot evaluate "__import__('os').system('rm -rf /')": unsupported syntax: Call
```

Two guards cover abuse that the node allowlist alone would miss:

- **Length cap** of 200 characters, bounding nesting depth and input size.
- **Exponent cap** of `1000`, because `2**999999999` is a single `Pow` node that
  would otherwise pin a CPU and exhaust memory.

Errors — division by zero, overflow, syntax errors — are reported as a one-line
message with exit code `1`. A traceback is never printed, and **a failed
expression writes nothing to the database**.

## Storage

```sql
CREATE TABLE calculations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    expression TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
```

The table is created on demand (`CREATE TABLE IF NOT EXISTS`) at the start of
every invocation, so there is no migration step and no init container.

`result` is stored as **text rather than `REAL`** so that large integers keep
full precision — `2**60` round-trips as `1152921504606846976`, which a float
column would silently round. The cost is that numeric aggregation needs an
explicit cast. The `sqlite3` command line tool is *not* in the image (the base
image links the SQLite library into Python but does not ship the CLI), so query
via Python:

```sh
docker exec calc python -c "
import sqlite3
rows = sqlite3.connect('/data/calc.db').execute(
    'SELECT SUM(CAST(result AS REAL)) FROM calculations'
)
print(rows.fetchone()[0])
"
```

Alternatively, bind-mount the volume and open the file from the host.

### Data location and persistence

| Setting   | Value            |
|-----------|------------------|
| Database  | `/data/calc.db`  |
| Volume    | `calc-data` (named Docker volume) |
| Override  | `CALC_DB` environment variable |

History survives `docker compose restart`, `docker compose down`, and image
rebuilds. `docker compose down -v` deletes the volume along with the history.

## Running without Docker

Python 3.10+ is required; there is nothing to install.

```sh
cd /home/ah/dev/temp
PYTHONPATH=src CALC_DB=./local.db python3 -m calc "2+3*4"
PYTHONPATH=src CALC_DB=./local.db python3 -m calc list
```

`CALC_DB` defaults to `./calc.db` when unset, which is why compose sets it
explicitly.

## Project layout

```
.
├── Dockerfile            # python:3.12-slim, non-root user, `calc` wrapper on PATH
├── docker-compose.yml    # one service, one named volume
├── .dockerignore
├── README.md
└── src/
    └── calc/
        ├── __init__.py
        ├── __main__.py   # CLI: dispatch, table rendering, exit codes
        ├── evaluator.py  # AST allowlist, length and exponent caps
        └── db.py         # schema, save, history, get, clear
```

## Troubleshooting

**`calc: could not open database at /data/calc.db: unable to open database file`**

The named volume is owned by root, so the unprivileged `app` user cannot write
to it. This should not happen on a fresh volume: the Dockerfile creates `/data`
owned by `app`, and Docker copies that directory's ownership into a fresh
volume. It does happen if the volume already existed from an earlier build.
Recreate the volume:

```sh
docker compose down -v
docker compose up -d
```

**`Error response from daemon: No such container: calc`**

The container is not running. Check `docker compose ps` and start it with
`docker compose up -d`. Note that `docker exec` requires a *running* container;
`docker compose run` does not, but it would use a different container each time.
