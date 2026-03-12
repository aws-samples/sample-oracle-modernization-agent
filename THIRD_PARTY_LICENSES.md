# Third Party Licenses

This document lists the third-party software dependencies used in Application SQL Transform Agent (part of OMA) and their respective licenses.

## All Dependencies (Installed)

| Name | Version | License | URL |
|------|---------|---------|-----|
| strands-agents | 1.26.0 | Apache Software License | https://github.com/strands-agents/sdk-python |
| boto3 | 1.42.52 | Apache-2.0 | https://github.com/boto/boto3 |
| botocore | 1.42.52 | Apache-2.0 | https://github.com/boto/botocore |
| s3transfer | 0.16.0 | Apache Software License | https://github.com/boto/s3transfer |
| watchdog | 6.0.0 | Apache Software License | https://github.com/gorakhargosh/watchdog |
| opentelemetry-api | 1.39.1 | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api |
| opentelemetry-sdk | 1.39.1 | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-sdk |
| opentelemetry-instrumentation | 0.60b1 | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/opentelemetry-instrumentation |
| opentelemetry-instrumentation-threading | 0.60b1 | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python-contrib/instrumentation/opentelemetry-instrumentation-threading |
| opentelemetry-semantic-conventions | 0.60b1 | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-semantic-conventions |
| python-multipart | 0.0.22 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| importlib_metadata | 8.7.1 | Apache-2.0 | https://github.com/python/importlib_metadata |
| python-dateutil | 2.9.0.post0 | Apache Software License; BSD License | https://github.com/dateutil/dateutil |
| packaging | 26.0 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |
| cryptography | 46.0.5 | Apache-2.0 OR BSD-3-Clause | https://github.com/pyca/cryptography |
| httpx | 0.28.1 | BSD License | https://github.com/encode/httpx |
| httpcore | 1.0.9 | BSD-3-Clause | https://www.encode.io/httpcore/ |
| wrapt | 1.17.3 | BSD License | https://github.com/GrahamDumpleton/wrapt |
| click | 8.3.1 | BSD-3-Clause | https://github.com/pallets/click/ |
| idna | 3.11 | BSD-3-Clause | https://github.com/kjd/idna |
| pycparser | 3.0 | BSD-3-Clause | https://github.com/eliben/pycparser |
| python-dotenv | 1.2.1 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| sse-starlette | 3.2.0 | BSD-3-Clause | https://github.com/sysid/sse-starlette |
| starlette | 0.52.1 | BSD-3-Clause | https://github.com/Kludex/starlette |
| uvicorn | 0.41.0 | BSD-3-Clause | https://uvicorn.dev/ |
| pydantic | 2.12.5 | MIT | https://github.com/pydantic/pydantic |
| pydantic-core | 2.41.5 | MIT | https://github.com/pydantic/pydantic-core |
| pydantic-settings | 2.13.0 | MIT | https://github.com/pydantic/pydantic-settings |
| mcp | 1.26.0 | MIT License | https://modelcontextprotocol.io |
| PyJWT | 2.11.0 | MIT | https://github.com/jpadilla/pyjwt |
| anyio | 4.12.1 | MIT | https://anyio.readthedocs.io/en/stable/versionhistory.html |
| attrs | 25.4.0 | MIT | https://www.attrs.org/en/stable/changelog.html |
| cffi | 2.0.0 | MIT | https://cffi.readthedocs.io/en/latest/whatsnew.html |
| httpx-sse | 0.4.3 | MIT | https://github.com/florimondmanca/httpx-sse |
| jsonschema | 4.26.0 | MIT | https://github.com/python-jsonschema/jsonschema |
| jsonschema-specifications | 2025.9.1 | MIT | https://github.com/python-jsonschema/jsonschema-specifications |
| referencing | 0.37.0 | MIT | https://github.com/python-jsonschema/referencing |
| rpds-py | 0.30.0 | MIT | https://github.com/crate-py/rpds |
| typing-inspection | 0.4.2 | MIT | https://github.com/pydantic/typing-inspection |
| urllib3 | 2.6.3 | MIT | https://github.com/urllib3/urllib3/blob/main/CHANGES.rst |
| zipp | 3.23.0 | MIT | https://github.com/jaraco/zipp |
| annotated-types | 0.7.0 | MIT License | https://github.com/annotated-types/annotated-types |
| docstring_parser | 0.17.0 | MIT License | https://github.com/rr-/docstring_parser |
| h11 | 0.16.0 | MIT License | https://github.com/python-hyper/h11 |
| jmespath | 1.1.0 | MIT License | https://github.com/jmespath/jmespath.py |
| six | 1.17.0 | MIT License | https://github.com/benjaminp/six |
| typing_extensions | 4.15.0 | PSF-2.0 | https://github.com/python/typing_extensions |
| certifi | 2026.1.4 | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/certifi/python-certifi |

## License Summary

| License Type | Count | Packages |
|--------------|-------|----------|
| Apache-2.0 / Apache Software License | 13 | strands-agents, boto3, botocore, s3transfer, watchdog, opentelemetry-*, python-multipart, importlib_metadata |
| MIT / MIT License | 24 | pydantic, mcp, PyJWT, anyio, attrs, cffi, httpx-sse, jsonschema, urllib3, zipp, etc. |
| BSD-3-Clause / BSD License | 10 | httpx, httpcore, wrapt, click, idna, pycparser, python-dotenv, sse-starlette, starlette, uvicorn |
| PSF-2.0 | 1 | typing_extensions |
| MPL 2.0 | 1 | certifi |
| Dual License | 3 | python-dateutil, packaging, cryptography |

## Runtime Dependencies (Not in pyproject.toml)

| Name | License | Description |
|------|---------|-------------|
| Python | PSF-2.0 | Python interpreter (3.10+) |
| SQLite | Public Domain | Embedded database |

## Development/Testing Tools (Not Distributed)

| Name | License | Description |
|------|---------|-------------|
| Java | GPL-2.0 with Classpath Exception | MyBatis test execution |
| PostgreSQL | PostgreSQL License | Target database |

## License Texts

### Apache License 2.0
Full text: https://www.apache.org/licenses/LICENSE-2.0

### MIT License
Full text: https://opensource.org/licenses/MIT

### BSD-3-Clause License
Full text: https://opensource.org/licenses/BSD-3-Clause

### PSF License 2.0
Full text: https://docs.python.org/3/license.html

### Mozilla Public License 2.0
Full text: https://www.mozilla.org/en-US/MPL/2.0/

---

**Note**: This list was generated from the actual installed packages in the virtual environment.

To regenerate this list:
```bash
source .venv/bin/activate
pip-licenses --format=markdown --with-urls --order=license
```

**Last Updated**: 2026-02-19
