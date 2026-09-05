# Local test data

Downloaded datasets live here and are not committed to this repository.

Stage 3 uses the synthetic Maple Payments dataset from DevRev's Apache-2.0 licensed
[Enterprise-Bench](https://github.com/devrev/enterprise-bench). Reproduce the exact
verified archive with:

```bash
make data
```

Stage 6 derives a normalized local SQLite store with:

```bash
make database
```

The database lives in `data/derived/`, is ignored by Git, records its source commit and
archive digest, and is opened read-only by the analytics runtime. It can always be rebuilt
from the authenticated JSON snapshot.

The importer pins the upstream commit and SHA-256 digest, limits archive size, rejects
unexpected file types, path traversal, and symbolic links, and records the verified source
beside the extracted files.

Inspect which verified Maple assets are currently executable, available but not onboarded, or
missing and planned:

```bash
make testbed
make qualify-testbed
```

Stage 12 does not create the planned `maple_finance_extension/` files. Their locators are a
versioned coverage contract only and cannot be used by the investigation agent.

Do not place real customer or confidential business data in this directory.
