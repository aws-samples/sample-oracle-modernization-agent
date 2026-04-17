# Oracle → MySQL Conversion Rules (Static, Common)

This document defines conversion rules common to all Oracle → MySQL migration projects.
**Target: MySQL 8.0+** (required for WITH RECURSIVE, EXCEPT, window functions).

---

## MySQL-Specific Warnings

### 1. `||` Operator
In MySQL, `||` is **logical OR** by default (unless `PIPES_AS_CONCAT` SQL mode is enabled).
**Always convert `||` to `CONCAT()`.**

### 2. Backtick Quoting
MySQL uses backticks for reserved word quoting: `` `order` ``, `` `group` ``.
PostgreSQL uses double quotes: `"order"`, `"group"`.
**Add backtick quoting when column/table names are MySQL reserved words.**

### 3. String vs NULL
Oracle treats `''` (empty string) as NULL. MySQL does NOT — same as PostgreSQL.
Handle NVL/COALESCE conversions accordingly.

### 4. Case Sensitivity
MySQL table/column names may be case-sensitive depending on `lower_case_table_names` setting.
Default on Linux: case-sensitive. Default on Windows/macOS: case-insensitive.

---

## 4-Phase Conversion Process

**IMPORTANT: Apply phases in strict order to prevent conflicts.**

### PHASE 1: STRUCTURAL PROCESSING

Remove Oracle-specific meta elements first.

#### 1. Schema Removal (Highest Priority)
- `SCHEMA_NAME.TABLE_NAME` → `TABLE_NAME`
- `SCHEMA.PACKAGE.PROCEDURE` → `PACKAGE_PROCEDURE`

#### 1-1. Identifier Case Handling
MySQL identifier case sensitivity depends on `lower_case_table_names` system variable:
- **0 (Linux default)**: Table/DB names are case-sensitive, stored as-is
- **1 (Windows/macOS default)**: Names stored lowercase, comparisons case-insensitive
- **2 (macOS alternative)**: Names stored as-is, comparisons case-insensitive

**Rule: Convert all identifiers (table, column, alias) to lowercase for maximum portability.**
- `TABLE_NAME` → `table_name`
- `COLUMN_NAME` → `column_name`
- `T1.COLUMN_NAME` → `t1.column_name`

**Do NOT lowercase:**
- String literals: `'Y'`, `'ACTIVE'` — keep as-is
- MyBatis parameters: `#{paramName}`, `${columnName}` — keep as-is
- SQL keywords: `SELECT`, `FROM`, `WHERE` — either case is fine
- Backtick-quoted reserved words: `` `order` ``, `` `group` `` — keep as-is

#### 2. Oracle Hint Removal
- Remove ALL: `/*+ INDEX(...) */`, `/*+ FULL(...) */`, `/*+ ORDERED */`, etc.
- MySQL has its own hint syntax but Oracle hints are incompatible.

#### 3. DUAL Table Removal
- `FROM DUAL` → remove completely (MySQL supports `SELECT expr` without FROM, or `FROM DUAL` is also valid)

#### 4. TABLE() Function Removal
- `TABLE(func())` → `func()`

#### 5. Database Link Removal
- `TABLE@DBLINK` → `TABLE`
- **Record the removed DB Link name in the `[OMA]` conversion comment** so the origin is traceable
  - e.g., `FROM TEST_01@NDS01 A` → `FROM test_01 a` + comment includes `@DBLINK removed(NDS01)`

#### 6. Stored Procedure / Package Function Conversion
- `{call PROC()}` → `CALL PROC()`
- `SCHEMA.PACKAGE.PROC()` → `PACKAGE_PROC()`
- `PACKAGE.FUNCTION(args)` → `package_function(args)` (flatten dot → underscore + lowercase)

**Only `DBMS_*`, `UTL_*` are Oracle standard** (see Phase 4 §6). ALL others are user-defined — flatten unconditionally. Do NOT map to built-in functions (`AES_ENCRYPT()`, etc.).
```sql
-- Oracle → MySQL
PKG_CRYPTO.ENCRYPT(col, 'key')   →  pkg_crypto_encrypt(col, 'key')
PKG_UTIL.IS_VALID(status)        →  pkg_util_is_valid(status)
```

---

### PHASE 2: SYNTAX CONVERSIONS

Convert data-flow-determining syntax structures.

#### 1. Comma JOIN → Explicit JOIN
```sql
-- Oracle
FROM table1 t1, table2 t2, table3 t3
WHERE t1.id = t2.id AND t2.ref_id = t3.id

-- MySQL
FROM table1 t1
JOIN table2 t2 ON t1.id = t2.id
JOIN table3 t3 ON t2.ref_id = t3.id
```

#### 2. Outer Join: (+) → LEFT/RIGHT JOIN

**Step 1 — Determine JOIN type from Oracle comma JOIN:**
```
Oracle comma JOIN → what JOIN type?
├─ WHERE clause has (+) on this table → LEFT JOIN (or RIGHT JOIN)
└─ WHERE clause has NO (+) on this table → INNER JOIN (never LEFT JOIN)
```
```sql
-- Oracle: (+) present → LEFT JOIN
FROM orders o, users u WHERE o.user_id = u.user_id(+)
-- MySQL
FROM orders o LEFT JOIN users u ON o.user_id = u.user_id

-- Oracle: no (+) → INNER JOIN (NOT LEFT JOIN)
FROM orders o, users u WHERE o.user_id = u.user_id
-- MySQL
FROM orders o JOIN users u ON o.user_id = u.user_id
```

**Step 2 — OR IS NULL Decision Tree for `<if>` dynamic conditions:**
```
Does this <if> condition need OR col IS NULL?
│
├─ Is the column from an outer-joined (LEFT/RIGHT JOIN) table?
│  ├─ NO → NEVER add OR IS NULL (stop)
│  └─ YES → What is the condition type?
│     ├─ LIKE / UPPER / LOWER pattern
│     │  → NEVER add OR IS NULL
│     │    (NULL LIKE anything → NULL → falsy in BOTH databases)
│     │
│     ├─ COALESCE/IFNULL(col, default) = #{param}
│     │  → NEVER add OR IS NULL
│     │    (COALESCE/IFNULL already converts NULL to default)
│     │
│     └─ Direct comparison: col = #{param}
│        → ADD OR col IS NULL
│        (Oracle (+) preserves outer rows, MySQL LEFT JOIN needs explicit NULL guard)
```

**Examples:**
```sql
-- ✅ CORRECT: direct comparison on outer-joined column → add OR IS NULL
<if test="statusFilter != null">
   AND (u.STATUS = #{statusFilter} OR u.STATUS IS NULL)
</if>

-- ✅ CORRECT: LIKE on outer-joined column → do NOT add OR IS NULL
<if test="searchKeyword != null">
   AND UPPER(u.EMAIL) LIKE CONCAT('%', UPPER(#{searchKeyword}), '%')
</if>

-- ✅ CORRECT: IFNULL on outer-joined column → do NOT add OR IS NULL
<if test="country != null">
   AND IFNULL(addr.COUNTRY, 'UNKNOWN') = #{country}
</if>

-- ✅ CORRECT: column from INNER-joined table → do NOT add OR IS NULL
<if test="searchKeyword != null">
   AND UPPER(u.EMAIL) LIKE CONCAT('%', UPPER(#{searchKeyword}), '%')
</if>
-- (u is INNER JOIN, so u.EMAIL is never NULL from the join)
```

#### 3. Multi-Column SET with Subquery (Oracle-specific)
`SET (col1, col2) = (SELECT ...)` → UPDATE ... JOIN pattern. Move subquery to JOIN, assign individually.
```sql
-- Oracle
UPDATE orders o SET (status, updated_at, updated_by) = (
    SELECT s.new_status, SYSDATE, s.user_id FROM status_changes s WHERE s.order_id = o.order_id)

-- MySQL
UPDATE orders o JOIN (SELECT order_id, new_status, user_id FROM status_changes) sub ON o.order_id = sub.order_id
SET o.status = sub.new_status, o.updated_at = NOW(), o.updated_by = sub.user_id
```

#### 4. Subquery Alias (Required in MySQL)
- `FROM (SELECT...)` → `FROM (SELECT...) AS sub1` (only when alias is missing)
- MySQL requires aliases for derived tables
- Preserve existing aliases

---

### PHASE 3: FUNCTIONS & OPERATORS

Convert expression-level functions and operators.

#### 1. String Concatenation (CRITICAL)
**MySQL `||` is logical OR. Always use `CONCAT()`.** `CONCAT(NULL, 'text')` → NULL. Use IFNULL for NULL safety.
```sql
col1 || col2 || col3                  →  CONCAT(col1, col2, col3)
LIKE '%' || #{param} || '%'           →  LIKE CONCAT('%', #{param}, '%')
NVL(col1,'') || col2                  →  CONCAT(IFNULL(col1, ''), col2)
```

#### 2. Basic Functions
| Oracle | MySQL |
|--------|-------|
| NVL(a, b) | IFNULL(a, b) or COALESCE(a, b) |
| NVL2(a, b, c) | CASE WHEN a IS NOT NULL THEN b ELSE c END (or IF(a IS NOT NULL, b, c)) |
| DECODE(a,b,c,...,default) | CASE a WHEN b THEN c ... ELSE default END |
| SYSDATE | NOW() or CURRENT_TIMESTAMP |
| SYSTIMESTAMP | NOW(6) (microsecond precision) |
| USER | CURRENT_USER() (note: parentheses required) |
| SYS_GUID() | UUID() (returns string with hyphens, or REPLACE(UUID(),'-','') for raw hex) |
| SUBSTR(s,p,l) | SUBSTRING(s,p,l) (or SUBSTR — MySQL supports both) |
| INSTR(s,sub) | INSTR(s,sub) — **same syntax, no change needed** |
| LENGTHB(s) | LENGTH(s) (MySQL LENGTH returns bytes for multi-byte strings) |
| LPAD(s,len,pad) | LPAD(s,len,pad) — **same syntax, no change needed** |
| LISTAGG(col,delim) WITHIN GROUP (ORDER BY x) | GROUP_CONCAT(col ORDER BY x SEPARATOR delim) |
| WM_CONCAT(col) | GROUP_CONCAT(col) |
| XMLAGG(XMLELEMENT(...)...).EXTRACT().GETSTRINGVAL() | GROUP_CONCAT() — see XMLAGG Idiom below |
| TO_NUMBER(s) | CAST(s AS DECIMAL) or s+0 |
| DBMS_LOB.GETLENGTH(col) | LENGTH(col) or OCTET_LENGTH(col) |
| ROWID | **remove or replace with PK** |
| MINUS | EXCEPT (MySQL 8.0.31+) or NOT EXISTS subquery |

**DECODE multi-condition:**
```sql
-- Oracle
DECODE(status, 'A', 'active', 'I', 'inactive', 'D', 'deleted', 'other')

-- MySQL
CASE status WHEN 'A' THEN 'active' WHEN 'I' THEN 'inactive'
            WHEN 'D' THEN 'deleted' ELSE 'other' END
```

#### 2-0a. Numeric TRUNC (NOT the same as ROUND)
```sql
-- Oracle: TRUNC truncates (floors) toward zero
TRUNC(1.2345, 3) = 1.234

-- MySQL: TRUNCATE() — DO NOT convert to ROUND
TRUNCATE(1.2345, 3) = 1.234   -- ✅ CORRECT
ROUND(1.2345, 3) = 1.235      -- ❌ WRONG: different result!
```
- `TRUNC(number, precision)` → `TRUNCATE(number, precision)`
- **NEVER convert TRUNC to ROUND** — they produce different results

#### 2-1. Aggregate & Analytic Functions (Additional)
| Oracle | MySQL |
|--------|-------|
| MEDIAN(col) | (SELECT col FROM t ORDER BY col LIMIT 1 OFFSET COUNT(*)/2) — or application-level |
| KEEP (DENSE_RANK FIRST ORDER BY x) | Use subquery approach |
| FETCH FIRST N ROWS ONLY | LIMIT N |
| ROWNUM | ROW_NUMBER() OVER() or LIMIT (context-dependent) |

#### 2-2. No Conversion Needed (MySQL 8.0+ supports directly)
| Feature | Note |
|---------|------|
| ROLLUP | Identical syntax in MySQL |
| OVER (PARTITION BY ... ORDER BY ...) | Window functions work in MySQL 8.0+ |
| UNION ALL / INTERSECT | Identical syntax |
| CASE WHEN ... END | Identical syntax |

**CRITICAL: XMLAGG String Aggregation Idiom** — `XMLAGG(XMLELEMENT(...)).EXTRACT('//text()').GETSTRINGVAL()` is string aggregation. Convert to `GROUP_CONCAT()`:
```sql
-- Oracle
SUBSTR(XMLAGG(XMLELEMENT(COL, ',', col_name) ORDER BY col_name).EXTRACT('//text()').GETSTRINGVAL(), 2) AS result
-- MySQL (SUBSTR not needed — GROUP_CONCAT has no leading delimiter)
GROUP_CONCAT(col_name ORDER BY col_name SEPARATOR ',') AS result
```

**Note**: MySQL has no `CUBE` (use UNION of ROLLUP). No `NULLS FIRST/LAST` — use `ORDER BY CASE WHEN col IS NULL THEN 0 ELSE 1 END, col`.

#### 2-3. Regular Expression Functions
| Oracle | MySQL |
|--------|-------|
| REGEXP_LIKE(s, pattern) | s REGEXP pattern |
| REGEXP_SUBSTR(s, pattern) | REGEXP_SUBSTR(s, pattern) (MySQL 8.0+) |
| REGEXP_REPLACE(s, pattern, repl) | REGEXP_REPLACE(s, pattern, repl) (MySQL 8.0+) |
| REGEXP_COUNT(s, pattern) | (LENGTH(s) - LENGTH(REGEXP_REPLACE(s, pattern, ''))) / LENGTH(match) — approximate |

#### 3. Date/Time Functions
| Oracle | MySQL |
|--------|-------|
| SYSDATE | NOW() or CURRENT_TIMESTAMP |
| TO_DATE(s,'YYYY-MM-DD') | STR_TO_DATE(s,'%Y-%m-%d') |
| TO_DATE(s,'YYYYMMDD') | STR_TO_DATE(s,'%Y%m%d') |
| TO_DATE(s,'YYYY-MM-DD HH24:MI:SS') | STR_TO_DATE(s,'%Y-%m-%d %H:%i:%s') |
| TO_CHAR(date,'YYYY-MM-DD') | DATE_FORMAT(date,'%Y-%m-%d') |
| TO_CHAR(date,'YYYYMMDD') | DATE_FORMAT(date,'%Y%m%d') |
| TO_CHAR(num) | CAST(num AS CHAR) |
| ADD_MONTHS(date,n) | DATE_ADD(date, INTERVAL n MONTH) |
| TRUNC(date,'DD') | DATE(date) |
| TRUNC(date,'MM') | DATE_FORMAT(date,'%Y-%m-01') or DATE(DATE_FORMAT(date,'%Y-%m-01')) |
| MONTHS_BETWEEN(d1,d2) | TIMESTAMPDIFF(MONTH, d2, d1) |
| TRUNC(MONTHS_BETWEEN(d1,d2)/12) | TIMESTAMPDIFF(YEAR, d2, d1) |
| LAST_DAY(date) | LAST_DAY(date) — **same syntax, no change needed** |
| NEXT_DAY(date, 'day') | DATE_ADD(date, INTERVAL (dow - DAYOFWEEK(date) + 7) % 7 DAY) |

**Oracle → MySQL date format mapping:**
| Oracle Format | MySQL Format |
|---------------|-------------|
| YYYY | %Y |
| MM | %m |
| DD | %d |
| HH24 | %H |
| HH | %h |
| MI | %i |
| SS | %s |
| AM/PM | %p |
| DAY | %W |
| DY | %a |
| MON | %b |
| MONTH | %M |

#### 4. Date/Timestamp Arithmetic

**MySQL date arithmetic differs significantly from Oracle:**

| Operation | MySQL Approach |
|-----------|---------------|
| `date - date` (days) | `DATEDIFF(date1, date2)` — returns integer days |
| `SYSDATE - date_col` | `DATEDIFF(NOW(), date_col)` |
| `date + n` (add days) | `DATE_ADD(date, INTERVAL n DAY)` |
| `date - n` (subtract days) | `DATE_SUB(date, INTERVAL n DAY)` |
| `timestamp - timestamp` | `TIMESTAMPDIFF(SECOND, ts2, ts1)` — returns integer |

```sql
-- Oracle: SYSDATE - date_col (returns days as number)
-- MySQL:
DATEDIFF(NOW(), date_col)

-- Oracle: date_col + 30
-- MySQL:
DATE_ADD(date_col, INTERVAL 30 DAY)
```

#### 5. Interval Construction
MySQL has no interval data type. Use `DATE_ADD`/`DATE_SUB`:
```sql
date + INTERVAL '5' DAY   →  DATE_ADD(date, INTERVAL 5 DAY)
date + #{param} days       →  DATE_ADD(date, INTERVAL #{param} DAY)
```

#### 5-1. ROUND with Integer Arithmetic
MySQL `ROUND(value, precision)` accepts integer values (no cast needed):
```sql
-- This works directly in MySQL (unlike PostgreSQL):
ROUND(DATEDIFF(date1, date2) * 24, 2)
```

#### 6. Sequence Functions
| Oracle | MySQL |
|--------|-------|
| SEQ_NAME.NEXTVAL | AUTO_INCREMENT (INSERT PK) or sequence table |
| SEQ_NAME.CURRVAL | LAST_INSERT_ID() |

For explicit sequence: `UPDATE sequences SET val = LAST_INSERT_ID(val + 1) WHERE name = 'seq_name'; SELECT LAST_INSERT_ID();`

---

### PHASE 4: ADVANCED PATTERNS

Convert complex Oracle-specific features.

#### 1. Hierarchical Query: CONNECT BY → WITH RECURSIVE (MySQL 8.0+)
```sql
-- Oracle
SELECT id, parent_id, name FROM categories
START WITH parent_id IS NULL
CONNECT BY PRIOR id = parent_id

-- MySQL
WITH RECURSIVE hierarchy AS (
  SELECT id, parent_id, name, 1 as level
  FROM categories WHERE parent_id IS NULL
  UNION ALL
  SELECT c.id, c.parent_id, c.name, h.level + 1
  FROM categories c JOIN hierarchy h ON c.parent_id = h.id
)
SELECT id, parent_id, name FROM hierarchy
```

**Recursive CTE rules:** Base case must NOT reference CTE name. Exactly one UNION ALL. MySQL recursion limit: 1000 (`cte_max_recursion_depth`).

| Oracle | MySQL (in WITH RECURSIVE) |
|--------|--------------------------|
| LEVEL | `1 as level` in base, `h.level + 1` in recursive |
| PRIOR col | JOIN condition: `c.parent_id = h.id` |
| SYS_CONNECT_BY_PATH(col,'/') | base `CAST(col AS CHAR(1000)) as path`, recursive `CONCAT(h.path, '/', c.col)` |
| CONNECT_BY_ROOT col | base `col as root_col`, recursive `h.root_col` |
| CONNECT_BY_ISLEAF | `CASE WHEN NOT EXISTS (...) THEN 1 ELSE 0 END` |
| ORDER SIBLINGS BY col | `ORDER BY path` |

#### 2. MERGE Statement
```sql
-- Oracle
MERGE INTO target USING source ON (condition)
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...

-- MySQL
INSERT INTO target (...)
SELECT ... FROM source
ON DUPLICATE KEY UPDATE col1 = VALUES(col1), col2 = VALUES(col2)
```

**Note**: `ON DUPLICATE KEY UPDATE` requires a unique key or primary key on the conflict columns.

#### 3. Pagination: ROWNUM → LIMIT/OFFSET
```sql
-- Oracle 3-depth paging
SELECT * FROM (
  SELECT A.*, ROWNUM RN FROM (
    SELECT ... ORDER BY ...
  ) A WHERE ROWNUM <= #{endRow}
) WHERE RN > #{startRow}

-- MySQL
SELECT ... ORDER BY ...
LIMIT #{pageSize} OFFSET #{startRow}
```

**Note**: MySQL LIMIT/OFFSET accept integer parameters without explicit casting.

#### 4. Set Operator
- `MINUS` → `EXCEPT` (MySQL 8.0.31+)
- For MySQL < 8.0.31: Rewrite as `NOT EXISTS` subquery

#### 5. FETCH FIRST (Oracle 12c+)
```sql
-- Oracle
SELECT * FROM orders ORDER BY amount DESC
FETCH FIRST 10 ROWS ONLY

-- MySQL
SELECT * FROM orders ORDER BY amount DESC
LIMIT 10
```
- `FETCH FIRST N ROWS ONLY` → `LIMIT N`
- `OFFSET M ROWS FETCH NEXT N ROWS ONLY` → `LIMIT N OFFSET M`

#### 6. PL/SQL Constructs in SQL
| Oracle | MySQL |
|--------|-------|
| `BULK COLLECT INTO` | Remove — use plain `SELECT` |
| `RETURNING ... INTO :var` | Remove — MySQL has no RETURNING. Use `LAST_INSERT_ID()` |
| `%ROWTYPE`, `%TYPE` | Remove — use explicit types |
| `UTL_HTTP.*`, `UTL_SMTP.*`, `DBMS_PIPE.*` | **MANUAL_REVIEW** |

```sql
-- Oracle                                          -- MySQL
INSERT INTO orders VALUES (seq.NEXTVAL, 'NEW')     INSERT INTO orders (status) VALUES ('NEW')
RETURNING id INTO :order_id                        -- then: SELECT LAST_INSERT_ID()
```

---

## XML Special Character Handling (MyBatis)

Outside CDATA: `<` → `&lt;`, `<=` → `&lt;=`. (`>` `>=` are safe — no escaping needed.)

1. **Original uses CDATA → keep CDATA**: `<![CDATA[ WHERE age <= 30 ]]>`
2. **Original uses entity escapes → keep**: `WHERE age &lt;= #{maxAge}`
3. **Conversion introduces `<`/`<=` → must escape or CDATA**: `WHERE qty &lt; 10`

---

## Reference Rule: Parameter Handling

MySQL does NOT need `::type` casting — JDBC handles type conversion. Use explicit conversion only when needed:
```sql
STR_TO_DATE(#{param}, '%Y-%m-%d')     -- string to date
CAST(#{param} AS DECIMAL(10,2))       -- explicit numeric
CAST(#{param} AS SIGNED)              -- explicit integer
```
**Remove PostgreSQL-style casts**: `#{param}::integer` → `#{param}`, `#{param}::date` → `#{param}` (or `STR_TO_DATE` if format needed).

---

## MyBatis Dynamic SQL (Keep As-Is)
- `#{param}`, `${param}` → no change
- `<if>`, `<choose>`, `<when>`, `<otherwise>` → no change
- `<foreach>`, `<where>`, `<set>`, `<trim>` → no change

## MyBatis resultMap: jdbcType Conversion
When converting `<resultMap>` elements, update Oracle jdbcType values:
| Oracle jdbcType | MySQL jdbcType |
|----------------|---------------|
| CLOB | LONGVARCHAR |
| BLOB | LONGVARBINARY |
| NUMBER | NUMERIC |
| VARCHAR2 | VARCHAR |
Other jdbcType values (VARCHAR, INTEGER, BIGINT, DATE, TIMESTAMP, etc.) remain unchanged.

## Dynamic WHERE Condition Scope (IMPORTANT)
When converting comma JOINs to explicit JOINs with subqueries:
- Analyze which tables each `<if test>` condition references
- Move conditions to correct scope (main query vs subquery)
- Add `WHERE 1=1` at each scope level with dynamic conditions
- Split mixed-scope `<if test>` blocks by table reference

---

## Common Wrong Conversions (AVOID THESE)

### 1. Using `||` for String Concatenation
See Phase 3 §1. `||` is OR in MySQL — always use `CONCAT()`.
```sql
-- ❌ col1 || col2
-- ✅ CONCAT(col1, col2)
```

### 2. Redundant OR IS NULL
**See Decision Tree in Phase 2 §2.** OR IS NULL is ONLY for direct equality on LEFT-joined columns. Never for LIKE, IFNULL, or INNER-joined.
```sql
-- ❌ WRONG                                          -- ✅ RIGHT
(UPPER(u.EMAIL) LIKE CONCAT('%',#{kw},'%') OR u.EMAIL IS NULL)  UPPER(u.EMAIL) LIKE CONCAT('%',#{kw},'%')
(IFNULL(addr.COUNTRY,'UNKNOWN')=#{c} OR addr.COUNTRY IS NULL)   IFNULL(addr.COUNTRY,'UNKNOWN')=#{c}
(u.EMAIL=#{email} OR u.EMAIL IS NULL) /*INNER*/      u.EMAIL=#{email}
```

### 3. Using PostgreSQL-style Casting
```sql
-- ❌ WRONG: :: is not valid MySQL syntax
col::integer
#{param}::date

-- ✅ RIGHT: use CAST()
CAST(col AS SIGNED)
CAST(#{param} AS DATE)
```

### 4. Wrong Date Arithmetic
```sql
-- ❌ WRONG: MySQL does not support date - date as integer
date1 - date2

-- ✅ RIGHT: use DATEDIFF
DATEDIFF(date1, date2)
```

### 5. Wrong Date Format Strings
```sql
-- ❌ WRONG: Oracle format in MySQL
STR_TO_DATE(str, 'YYYY-MM-DD')

-- ✅ RIGHT: MySQL format specifiers
STR_TO_DATE(str, '%Y-%m-%d')
```

### 6. GROUP_CONCAT Syntax Errors
```sql
-- ❌ WRONG: PostgreSQL STRING_AGG syntax
STRING_AGG(col, ',' ORDER BY col)

-- ✅ RIGHT: MySQL GROUP_CONCAT syntax
GROUP_CONCAT(col ORDER BY col SEPARATOR ',')
```

### 7. EXCEPT on Older MySQL
```sql
-- ❌ WRONG: EXCEPT not available before MySQL 8.0.31
SELECT ... EXCEPT SELECT ...

-- ✅ RIGHT (MySQL < 8.0.31): use NOT EXISTS
SELECT ... WHERE NOT EXISTS (SELECT 1 FROM (...) sub WHERE sub.id = main.id)
```

### 8. TO_DATE Blindly Converted to CAST
```sql
-- ❌ WRONG: CAST only works with standard date format
TO_DATE(#{param}, 'YYYYMMDD')  →  CAST(#{param} AS DATE)  -- FAILS for '20260315'

-- ✅ RIGHT: use STR_TO_DATE with correct format
TO_DATE(#{param}, 'YYYYMMDD')  →  STR_TO_DATE(#{param}, '%Y%m%d')
-- CAST(... AS DATE) is safe ONLY for ISO format ('2026-03-15')
```

### 9. User-Defined Package Function Mapped to Built-in
See Phase 1 §6. Flatten with underscore — NEVER map to built-in.
```sql
-- ❌ PKG_CRYPTO.ENCRYPT(col, key) → AES_ENCRYPT(col, key)
-- ✅ PKG_CRYPTO.ENCRYPT(col, key) → pkg_crypto_encrypt(col, key)
```

### 10. Original Name/Identifier Changed (Hallucination)
NEVER change ANY name. Copy verbatim (lowercase only). No prefixes, no typo "fixes", no renaming.
```sql
-- ❌ sql_putawayLocation → sql_selectPutawayLocation (added prefix)
-- ❌ sql_tWorkInfoIbat → sql_tWorkInfoIvat (typo "fix")
-- ✅ sql_putawaylocation, sql_tworkinfoibat, sql_waybillno (verbatim lowercase)
```

---

## Critical Rules
1. **Process ALL SQL IDs** — do not skip any
2. **Follow 4-phase order** — Phase 1(Structural) → Phase 2(Syntax) → Phase 3(Functions) → Phase 4(Advanced)
3. **Preserve MyBatis tags** — `<if>`, `<foreach>`, etc. must remain intact
4. **Preserve parameter references** — `#{param}`, `${param}` unchanged
5. **Always use CONCAT()** — never leave `||` for string concatenation
6. **Preserve ALL comments** — `--` and `/* */` comments must remain exactly as-is
7. **Preserve variable names** — only lowercase, NEVER change prefixes or naming (V_RETURN → v_return, NOT p_return)
8. **Preserve literal values** — string literals, email addresses, URLs, constants must NOT be masked, anonymized, or sanitized
9. **Add notes for complex conversions** — CONNECT BY, MERGE, complex patterns
10. **Flag MANUAL_REVIEW** — when conversion accuracy is uncertain
11. **NO optimization** — convert syntax only, do not change logic or structure
12. **Preserve ALL original names** — sql id, refid, resultMap id, aliases must match the original verbatim (lowercase only). NEVER add prefixes, fix typos, or rename
