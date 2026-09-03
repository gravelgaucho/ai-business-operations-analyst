# Local test data

Downloaded datasets live here and are not committed to this repository.

Stage 3 uses the synthetic Maple Payments dataset from DevRev's Apache-2.0 licensed
[Enterprise-Bench](https://github.com/devrev/enterprise-bench). Reproduce the exact
verified archive with:

```bash
make data
```

The importer pins the upstream commit and SHA-256 digest, limits archive size, rejects
unexpected file types, path traversal, and symbolic links, and records the verified source
beside the extracted files.

Do not place real customer or confidential business data in this directory.
