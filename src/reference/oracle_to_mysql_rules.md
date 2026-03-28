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

#### 6. Stored Procedure Conversion
- `{call PROC()}` → `CALL PROC()`
- `SCHEMA.PACKAGE.PROC()` → `PACKAGE_PROC()`

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

#### 3. Subquery Alias (Required in MySQL)
- `FROM (SELECT...)` → `FROM (SELECT...) AS sub1` (only when alias is missing)
- MySQL requires aliases for derived tables
- Preserve existing aliases

---

### PHASE 3: FUNCTIONS & OPERATORS

Convert expression-level functions and operators.

#### 1. String Concatenation (CRITICAL)
**MySQL `||` is logical OR. Always use `CONCAT()`.**

```sql
-- Oracle
col1 || col2 || col3

-- MySQL
CONCAT(col1, col2, col3)

-- LIKE pattern
LIKE '%' || #{param} || '%'  →  LIKE CONCAT('%', #{param}, '%')
```

**MySQL CONCAT with NULL:**
`CONCAT(NULL, 'text')` returns `NULL` in MySQL (same as Oracle `||`).
Use `CONCAT_WS` or `IFNULL` for NULL safety:
```sql
CONCAT(IFNULL(col1, ''), col2)
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

**Note**: MySQL does not support `CUBE` — use UNION of multiple ROLLUP queries.
**Note**: MySQL does not support `NULLS FIRST / NULLS LAST` directly — use:
```sql
ORDER BY CASE WHEN col IS NULL THEN 0 ELSE 1 END, col
```

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
MySQL does not have an `interval` data type like PostgreSQL. Use `DATE_ADD` / `DATE_SUB`:
```sql
-- Oracle: date + INTERVAL '5' DAY
-- MySQL:
DATE_ADD(date, INTERVAL 5 DAY)

-- Dynamic parameter:
DATE_ADD(date, INTERVAL #{param} DAY)
```

#### 5-1. ROUND with Integer Arithmetic
MySQL `ROUND(value, precision)` accepts integer values (no cast needed):
```sql
-- This works directly in MySQL (unlike PostgreSQL):
ROUND(DATEDIFF(date1, date2) * 24, 2)
```

#### 6. Sequence Functions
MySQL does not have sequences in the same way as Oracle.

| Oracle | MySQL |
|--------|-------|
| SEQ_NAME.NEXTVAL | Use AUTO_INCREMENT column (for INSERT PK) |
| SEQ_NAME.CURRVAL | LAST_INSERT_ID() (session-specific) |

For explicit sequence behavior, use a sequence table:
```sql
-- Create sequence table
CREATE TABLE sequences (name VARCHAR(100) PRIMARY KEY, val BIGINT DEFAULT 0);

-- Get next value
UPDATE sequences SET val = LAST_INSERT_ID(val + 1) WHERE name = 'seq_name';
SELECT LAST_INSERT_ID();
```

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

**Recursive CTE rules (same as PostgreSQL):**
- Base case must NOT reference CTE name
- Exactly one UNION ALL between base and recursive
- MySQL has default recursion limit of 1000 (`cte_max_recursion_depth`)

**CONNECT BY related functions:**
| Oracle | MySQL (in WITH RECURSIVE) |
|--------|--------------------------|
| LEVEL | Add `1 as level` in base, `h.level + 1` in recursive |
| PRIOR col | Use JOIN condition: `c.parent_id = h.id` |
| SYS_CONNECT_BY_PATH(col,'/') | Accumulate string: base `CAST(col AS CHAR(1000)) as path`, recursive `CONCAT(h.path, '/', c.col)` |
| CONNECT_BY_ROOT col | Carry from base case: `col as root_col`, recursive `h.root_col` |
| CONNECT_BY_ISLEAF | `CASE WHEN NOT EXISTS (SELECT 1 FROM t WHERE t.parent_id = h.id) THEN 1 ELSE 0 END` |
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
These Oracle PL/SQL constructs may appear in MyBatis mappers:

| Oracle | MySQL |
|--------|-------|
| `BULK COLLECT INTO` | Remove — use plain `SELECT` (MyBatis handles result collection) |
| `RETURNING ... INTO :var` | Remove entirely — MySQL `INSERT` does not support `RETURNING`. Use `LAST_INSERT_ID()` for auto-increment PKs |
| `%ROWTYPE` | Remove — use explicit column types |
| `%TYPE` | Remove — use explicit types |

```sql
-- Oracle: RETURNING INTO
INSERT INTO orders (id, status) VALUES (seq.NEXTVAL, 'NEW')
RETURNING id INTO :order_id

-- MySQL: no RETURNING — use LAST_INSERT_ID() if needed
INSERT INTO orders (status) VALUES ('NEW')
-- then: SELECT LAST_INSERT_ID()
```

---

## XML Special Character Handling (MyBatis)

**⚠️ Problem**: Using `<` operator outside CDATA causes XML parsing errors. (`>` is safe in XML.)

**What MUST be escaped (outside CDATA):**
- `<` → `&lt;`
- `<=` → `&lt;=`

**What does NOT need escaping:**
- `>` and `>=` — safe in XML, keep as-is
- Anything inside `<![CDATA[]]>` — keep as-is

**Decision criteria during conversion:**

1. **If original uses CDATA → keep CDATA**
2. **If original uses entity escapes → keep escapes**
3. **If conversion introduces `<` or `<=` → must escape or wrap in CDATA**

---

## Reference Rule: Parameter Handling

**MySQL does NOT require explicit parameter casting** like PostgreSQL (no `::type` syntax).
MyBatis `#{param}` parameters are bound via PreparedStatement and JDBC handles type conversion.

**Exception**: When explicit type conversion is needed:
```sql
-- Cast string to date
STR_TO_DATE(#{param}, '%Y-%m-%d')

-- Cast to specific numeric type
CAST(#{param} AS DECIMAL(10,2))
CAST(#{param} AS SIGNED)
```

**Remove PostgreSQL-style casts**: If migrating from already-converted PostgreSQL SQL:
```sql
-- Remove these PostgreSQL-specific casts:
#{param}::integer  →  #{param}
#{param}::bigint   →  #{param}
#{param}::date     →  #{param}  (or STR_TO_DATE if format conversion needed)
#{param}::numeric  →  #{param}
```

---

## MyBatis Dynamic SQL (Keep As-Is)
- `#{param}`, `${param}` → no change
- `<if>`, `<choose>`, `<when>`, `<otherwise>` → no change
- `<foreach>`, `<where>`, `<set>`, `<trim>` → no change

## Dynamic WHERE Condition Scope (IMPORTANT)
When converting comma JOINs to explicit JOINs with subqueries:
- Analyze which tables each `<if test>` condition references
- Move conditions to correct scope (main query vs subquery)
- Add `WHERE 1=1` at each scope level with dynamic conditions
- Split mixed-scope `<if test>` blocks by table reference

---

## Common Wrong Conversions (AVOID THESE)

### 1. Using `||` for String Concatenation
```sql
-- ❌ WRONG: || is OR in MySQL
col1 || col2

-- ✅ RIGHT: always use CONCAT
CONCAT(col1, col2)
```

### 2. Redundant OR IS NULL (see Decision Tree in Phase 2 §2)
```sql
-- ❌ WRONG: LIKE on outer-joined column — OR IS NULL changes semantics
WHERE (UPPER(u.EMAIL) LIKE CONCAT('%', #{kw}, '%') OR u.EMAIL IS NULL)

-- ✅ RIGHT: NULL LIKE → NULL → falsy, identical in both DBs
WHERE UPPER(u.EMAIL) LIKE CONCAT('%', #{kw}, '%')

-- ❌ WRONG: IFNULL already handles NULL
WHERE IFNULL(addr.COUNTRY, 'UNKNOWN') = #{country} OR addr.COUNTRY IS NULL

-- ✅ RIGHT: IFNULL alone is sufficient
WHERE IFNULL(addr.COUNTRY, 'UNKNOWN') = #{country}

-- ❌ WRONG: column from INNER-joined table — never NULL from join
WHERE (u.EMAIL = #{email} OR u.EMAIL IS NULL)

-- ✅ RIGHT: only for direct comparison on LEFT-joined column
WHERE (addr.STATUS = #{status} OR addr.STATUS IS NULL)
```
**Rule**: Follow the Decision Tree in Phase 2 §2. `OR col IS NULL` is ONLY needed for **direct equality comparison** on **outer-joined table** columns. Never for LIKE, COALESCE/IFNULL, or INNER-joined columns.

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

---

## Critical Rules
1. **Process ALL SQL IDs** — do not skip any
2. **Follow 4-phase order** — Phase 1(Structural) → Phase 2(Syntax) → Phase 3(Functions) → Phase 4(Advanced)
3. **Preserve MyBatis tags** — `<if>`, `<foreach>`, etc. must remain intact
4. **Preserve parameter references** — `#{param}`, `${param}` unchanged
5. **Always use CONCAT()** — never leave `||` for string concatenation
6. **Add notes for complex conversions** — CONNECT BY, MERGE, complex patterns
7. **Flag MANUAL_REVIEW** — when conversion accuracy is uncertain
8. **NO optimization** — convert syntax only, do not change logic or structure
