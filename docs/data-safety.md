# Public test-data safety policy

This project currently accepts only datasets that are safe to use in a public portfolio.
An approved dataset must satisfy every requirement below:

1. The publisher explicitly identifies the data as synthetic or clearly licenses the real
   data for public redistribution and analysis.
2. The license permits the project's intended use.
3. The source is an official publisher-controlled HTTPS location.
4. A version or commit and cryptographic digest are pinned before use.
5. The archive is inspected before extraction and cannot write outside its destination.
6. Dataset code is not executed merely because it ships beside the data.
7. Raw downloaded data and generated results remain outside Git unless separately reviewed.
8. Credentials, private communications, proprietary documents, and real customer data are
   rejected.

## Current approved source

Stage 3 uses **DevRev Enterprise-Bench / Maple Payments**. DevRev describes every included
account, user, email, ticket, opportunity, transcript, article, and internal document as
synthetic benchmark data. The repository is published under Apache-2.0.

The importer pins:

```text
Repository: https://github.com/devrev/enterprise-bench
Commit:     c921345cb64f8045d70f79a3f99717008d68f366
Archive:    artifacts/data.zip
SHA-256:    24d6d134067ffc763c953fab8ec28022c98bb4da11aa0e4456798d7f9bb656bc
```

Before extraction it enforces compressed and expanded size limits; allows only known data
directories, one known root canary file, and `.json`, `.md`, or `.txt` files; and rejects
absolute paths, parent traversal, symbolic links, and unexpected directories or file types.
It also records and rechecks the SHA-256 digest of every extracted file, detecting later
modification or unexpected additions before qualification.

The benchmark's Docker images, MCP servers, agent runners, and cloud judging are not used in
Stage 3. We import only the data archive.

Sources: [official repository](https://github.com/devrev/enterprise-bench),
[data schema](https://github.com/devrev/enterprise-bench/blob/main/docs/data-schema.md), and
[Apache-2.0 license](https://github.com/devrev/enterprise-bench/blob/main/LICENSE).
