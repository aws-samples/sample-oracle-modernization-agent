# Oracle → PostgreSQL Conversion Rules (Static, Common)

This document defines conversion rules common to all Oracle → PostgreSQL migration projects.

---

## 4-Phase Conversion Process

**IMPORTANT: Apply phases in strict order to prevent conflicts.**

### PHASE 1: STRUCTURAL PROCESSING

Remove Oracle-specific meta elements first.

#### 1. Schema Removal (Highest Priority)
- `SCHEMA_NAME.TABLE_NAME` → `TABLE_NAME`
- `SCHEMA.PACKAGE.PROCEDURE` → `PACKAGE_PROCEDURE`

#### 1-1. Identifier Case Folding (CRITICAL)
Oracle stores unquoted identifiers in UPPERCASE; PostgreSQL folds them to lowercase.
Target PostgreSQL schemas are created with unquoted identifiers (all lowercase).

**Rule: Convert ALL identifiers (table, column, alias, function) to lowercase.**
- `TABLE_NAME` → `table_name`
- `COLUMN_NAME` → `column_name`
- `T1.COLUMN_NAME` → `t1.column_name`
- `NVL(A.STATUS, 'N')` → `nvl(a.status, 'N')` (only identifiers, not string literals)

**Do NOT lowercase:**
- String literals: `'Y'`, `'ACTIVE'`, `'%search%'` — keep as-is
- MyBatis parameters: `#{paramName}`, `${columnName}` — keep as-is
- SQL keywords: `SELECT`, `FROM`, `WHERE` — either case is fine (PostgreSQL ignores case for keywords)

#### 2. Oracle Hint Removal
- Remove ALL: `/*+ INDEX(...) */`, `/*+ FULL(...) */`, `/*+ ORDERED */`, etc.

#### 3. DUAL Table Removal
- `FROM DUAL` → remove completely

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

**Only `DBMS_*`, `UTL_*` are Oracle standard** (see Phase 4 §7). ALL others are user-defined — flatten unconditionally. Do NOT map to built-in functions (`pgcrypto`, `encrypt()`, etc.).
```sql
-- Oracle → PostgreSQL
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

-- PostgreSQL
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
-- PostgreSQL
FROM orders o LEFT JOIN users u ON o.user_id = u.user_id

-- Oracle: no (+) → INNER JOIN (NOT LEFT JOIN)
FROM orders o, users u WHERE o.user_id = u.user_id
-- PostgreSQL
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
│     ├─ COALESCE(col, default) = #{param}
│     │  → NEVER add OR IS NULL
│     │    (COALESCE already converts NULL to default)
│     │
│     └─ Direct comparison: col = #{param}
│        → ADD OR col IS NULL
│        (Oracle (+) preserves outer rows, PG LEFT JOIN needs explicit NULL guard)
```

**Examples:**
```sql
-- ✅ CORRECT: direct comparison on outer-joined column → add OR IS NULL
<if test="statusFilter != null">
   AND (u.STATUS = #{statusFilter}::varchar OR u.STATUS IS NULL)
</if>

-- ✅ CORRECT: LIKE on outer-joined column → do NOT add OR IS NULL
<if test="searchKeyword != null">
   AND UPPER(u.EMAIL) LIKE '%' || UPPER(#{searchKeyword}) || '%'
</if>

-- ✅ CORRECT: COALESCE on outer-joined column → do NOT add OR IS NULL
<if test="country != null">
   AND COALESCE(addr.COUNTRY, 'UNKNOWN') = #{country}::varchar
</if>

-- ✅ CORRECT: column from INNER-joined table → do NOT add OR IS NULL
<if test="searchKeyword != null">
   AND UPPER(u.EMAIL) LIKE '%' || UPPER(#{searchKeyword}) || '%'
</if>
-- (u is INNER JOIN, so u.EMAIL is never NULL from the join)
```

#### 2-1. WHERE Filter on Outer-Joined Table (CRITICAL)
When Oracle WHERE clause filters on an outer-joined (+) table column, this **excludes NULL rows**. Converting to LEFT JOIN ON clause **includes NULL rows** — different behavior!

```sql
-- Oracle: WHERE filter excludes rows where F is NULL
FROM orders A, items F
WHERE A.key = F.key(+) AND F.CLOSDATE >= #{sysdate}

-- ❌ WRONG: filter in ON clause → includes NULL rows
FROM orders A LEFT JOIN items F ON A.key = F.key AND F.CLOSDATE >= #{sysdate}

-- ✅ RIGHT: keep filter in WHERE → excludes NULL rows (same as Oracle)
FROM orders A LEFT JOIN items F ON A.key = F.key
WHERE F.CLOSDATE >= #{sysdate}
```
**Rule**: Non-join conditions on outer-joined tables stay in WHERE, not ON. Only the join relationship (`A.key = F.key`) goes into the ON clause.

#### 3. Multi-Column SET with Subquery (Oracle-specific)
`SET (col1, col2) = (SELECT ...)` → UPDATE ... FROM pattern. Move subquery to FROM, assign individually.
```sql
-- Oracle
UPDATE orders o SET (status, updated_at, updated_by) = (
    SELECT s.new_status, SYSDATE, s.user_id FROM status_changes s WHERE s.order_id = o.order_id)
WHERE EXISTS (SELECT 1 FROM status_changes s WHERE s.order_id = o.order_id)

-- PostgreSQL
UPDATE orders o SET status = sub.new_status, updated_at = CURRENT_TIMESTAMP, updated_by = sub.user_id
FROM (SELECT order_id, new_status, user_id FROM status_changes) sub
WHERE o.order_id = sub.order_id
```

#### 4. Subquery Alias (Mandatory in PostgreSQL)
- `FROM (SELECT...)` → `FROM (SELECT...) AS sub1` (only when alias is missing)
- Preserve existing aliases

---

### PHASE 3: FUNCTIONS & OPERATORS

Convert expression-level functions and operators.

#### 1. String Concatenation
`||` works in PostgreSQL (SQL standard). Use `CONCAT()` only for NULL safety (`NULL || 'text'` → `NULL`).
```sql
col1 || col2                          -- OK as-is
LIKE '%' || #{param} || '%'           -- OK as-is
NVL(col1,'') || col2 → CONCAT(COALESCE(col1,''), col2)  -- NULL safety
```

#### 2. Basic Functions
| Oracle | PostgreSQL |
|--------|-----------|
| NVL(a, b) | COALESCE(a, b) — **types must match** (see note below) |
| NVL2(a, b, c) | CASE WHEN a IS NOT NULL THEN b ELSE c END |
| DECODE(a,b,c,...,default) | CASE a WHEN b THEN c ... ELSE default END (see note below) |
| SYSDATE | CURRENT_TIMESTAMP |
| SYSTIMESTAMP | CURRENT_TIMESTAMP |
| USER | CURRENT_USER |
| SYS_GUID() | gen_random_uuid() |
| SUBSTR(s,p,l) | SUBSTRING(s,p,l) |
| INSTR(s,sub) | POSITION(sub IN s) |
| INSTR(s,sub,start,occurrence) | See note below — POSITION does not support occurrence |
| LENGTHB(s) | OCTET_LENGTH(s) |
| LPAD(s,len,pad) | LPAD(s::text,len,pad) |
| LISTAGG(col,delim) WITHIN GROUP (ORDER BY x) | STRING_AGG(col, delim ORDER BY x) — move ORDER BY inside function |
| WM_CONCAT(col) | STRING_AGG(col, ',') |
| TO_NUMBER(s) | CAST(s AS NUMERIC) |
| DBMS_LOB.GETLENGTH(col) | LENGTH(col) or OCTET_LENGTH(col) |
| ROWID | **remove or replace with PK** — ctid changes after VACUUM, unsafe as identifier |
| MINUS | EXCEPT |

**INSTR with occurrence parameter** (4-arg form): `INSTR(s, sub, start, occurrence)` — POSITION does not support occurrence. **Flag as complex conversion** and use regexp approach. Simple nested POSITION often produces wrong results.

**NVL → COALESCE type mismatch:**
Oracle NVL implicitly casts the second argument to match the first. PostgreSQL COALESCE requires matching types.
```sql
-- ❌ WRONG: types don't match
COALESCE(numeric_col, 'N/A')

-- ✅ RIGHT: explicit cast
COALESCE(numeric_col::text, 'N/A')
```

**DECODE multi-condition:**
```sql
-- Oracle
DECODE(status, 'A', '활성', 'I', '비활성', 'D', '삭제', '기타')

-- PostgreSQL
CASE status WHEN 'A' THEN '활성' WHEN 'I' THEN '비활성'
            WHEN 'D' THEN '삭제' ELSE '기타' END
```

#### 2-1. Aggregate & Analytic Functions (Additional)
| Oracle | PostgreSQL |
|--------|-----------|
| MEDIAN(col) | PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col) |
| KEEP (DENSE_RANK FIRST ORDER BY x) | Use subquery or DISTINCT ON (see note) |
| FETCH FIRST N ROWS ONLY | LIMIT N |
| ROWNUM | ROW_NUMBER() OVER() or LIMIT (context-dependent) |

**KEEP (DENSE_RANK FIRST/LAST)** = "one row per group" semantics. LAST=MAX, FIRST=MIN of ORDER BY column.
```sql
-- Oracle
SELECT group_key, MAX(err_code) KEEP (DENSE_RANK LAST ORDER BY detail_key) as last_err
FROM details GROUP BY group_key

-- ❌ WRONG: adding columns to GROUP BY → multiple rows per group
SELECT group_key, err_code FROM details GROUP BY group_key, err_code

-- ✅ RIGHT: DISTINCT ON
SELECT DISTINCT ON (group_key) group_key, err_code as last_err
FROM details ORDER BY group_key, detail_key DESC

-- ✅ RIGHT: ROW_NUMBER
SELECT group_key, err_code as last_err FROM (
    SELECT group_key, err_code, ROW_NUMBER() OVER (PARTITION BY group_key ORDER BY detail_key DESC) as rn
    FROM details
) sub WHERE rn = 1
```
Use `DISTINCT ON` or `ROW_NUMBER()` — NEVER just add columns to GROUP BY.

#### 2-1a. Numeric TRUNC (NOT the same as ROUND)
```sql
-- Oracle: TRUNC truncates (floors) toward zero
TRUNC(1.2345, 3) = 1.234

-- PostgreSQL: trunc() works the same — DO NOT convert to ROUND
trunc(1.2345, 3) = 1.234    -- ✅ CORRECT: same behavior
ROUND(1.2345, 3) = 1.235    -- ❌ WRONG: different result!
```
- `TRUNC(number, precision)` → `trunc(number::numeric, precision)` — keep as trunc, just lowercase + cast
- **NEVER convert TRUNC to ROUND** — they produce different results

#### 2-2. No Conversion Needed (PostgreSQL supports directly)
| Feature | Note |
|---------|------|
| CUBE / ROLLUP | Identical syntax in PostgreSQL |
| NULLS FIRST / NULLS LAST | Identical syntax in PostgreSQL |
| OVER (PARTITION BY ... ORDER BY ...) | Window functions work the same |
| UNION ALL / INTERSECT | Identical syntax |
| CASE WHEN ... END | Identical syntax |

#### 2-3. Regular Expression Functions
| Oracle | PostgreSQL |
|--------|-----------|
| REGEXP_LIKE(s, pattern) | s ~ pattern |
| REGEXP_SUBSTR(s, pattern) | SUBSTRING(s FROM pattern) |
| REGEXP_REPLACE(s, pattern, repl) | REGEXP_REPLACE(s, pattern, repl) (same syntax) |
| REGEXP_COUNT(s, pattern) | (SELECT count(*) FROM regexp_matches(s, pattern, 'g')) |

**Note**: Oracle regex flags differ — Oracle `'i'` (case-insensitive) → PostgreSQL `'i'` (same flag, pass as last arg).

#### 3. Date/Time Functions
| Oracle | PostgreSQL |
|--------|-----------|
| SYSDATE | CURRENT_TIMESTAMP |
| TO_DATE(s,'YYYY-MM-DD') | to_date(s,'YYYY-MM-DD') or s::date (only if s is ISO format literal) |
| TO_DATE(s,'YYYYMMDD') | to_date(s,'YYYYMMDD') (keep function — format-dependent) |
| TO_DATE(s,'YYYY-MM-DD HH24:MI:SS') | to_timestamp(s,'YYYY-MM-DD HH24:MI:SS') |
| ADD_MONTHS(date,n) | date + INTERVAL 'n months' |
| TRUNC(date,'DD') | DATE_TRUNC('day',date) |
| TRUNC(date,'MM') | DATE_TRUNC('month',date) |
| MONTHS_BETWEEN(d1,d2) | (EXTRACT(YEAR FROM AGE(d1::date,d2::date))*12 + EXTRACT(MONTH FROM AGE(d1::date,d2::date))) |
| TRUNC(MONTHS_BETWEEN(d1,d2)/12) | EXTRACT(YEAR FROM AGE(d1::date,d2::date)) |
| LAST_DAY(date) | (DATE_TRUNC('month', date) + INTERVAL '1 month - 1 day')::date |
| NEXT_DAY(date, 'day') | (date + (dow - EXTRACT(DOW FROM date) + 7)::int % 7 * INTERVAL '1 day') |

#### 4. Date/Timestamp Arithmetic (CRITICAL)

| Operation | Return Type | Note |
|-----------|-------------|------|
| `date - date` | **integer** (days) | NEVER add `::interval` |
| `timestamp - timestamp` | **interval** | Do NOT add `::interval` (redundant) |
| `date - integer` | **date** | |
| `timestamp - interval` | **timestamp** | |

```sql
TRUNC(SYSDATE) - date_col      →  (CURRENT_DATE - date_col::date)       -- integer
SYSTIMESTAMP - created_at       →  (CURRENT_TIMESTAMP - created_at)      -- interval
```

#### 5. EXTRACT with Date/Timestamp Arithmetic
- `EXTRACT(DAY FROM ts1 - ts2)` → `EXTRACT(DAY FROM (ts1 - ts2))` — already interval
- `EXTRACT(DAY FROM date1 - date2)` → `(date1 - date2)` — already integer, EXTRACT unneeded
- Always wrap arithmetic in parentheses

#### 6. Interval Construction (PostgreSQL 9.4+)
- `(#{param} || ' days')::interval` → `MAKE_INTERVAL(days => #{param}::integer)`
- `(#{param} || ' months')::interval` → `MAKE_INTERVAL(months => #{param}::integer)`

#### 6-1. ROUND with Integer Arithmetic
PostgreSQL `ROUND(value, precision)` requires `value` to be numeric, not integer.
- `ROUND(integer_expr, 2)` → `ROUND((integer_expr)::numeric, 2)`
- Example: `ROUND((date1::date - date2::date) * 24, 2)` → `ROUND(((date1::date - date2::date) * 24)::numeric, 2)`

#### 7. Sequence Functions
- `SEQ_NAME.NEXTVAL` → `nextval('seq_name')` (always lowercase)
- `SEQ_NAME.CURRVAL` → `currval('seq_name')` (always lowercase)

---

### PHASE 4: ADVANCED PATTERNS

Convert complex Oracle-specific features.

#### 1. Hierarchical Query: CONNECT BY → WITH RECURSIVE
```sql
-- Oracle
SELECT id, parent_id, name FROM categories
START WITH parent_id IS NULL
CONNECT BY PRIOR id = parent_id

-- PostgreSQL
WITH RECURSIVE hierarchy AS (
  SELECT id, parent_id, name, 1 as level
  FROM categories WHERE parent_id IS NULL
  UNION ALL
  SELECT c.id, c.parent_id, c.name, h.level + 1
  FROM categories c JOIN hierarchy h ON c.parent_id = h.id
)
SELECT id, parent_id, name FROM hierarchy
```

**Recursive CTE rules:** Base case must NOT reference CTE name. Exactly one UNION ALL. Cast recursive term types to match base (`CONCAT(...)::character varying`).

**CONNECT BY related functions:**
| Oracle | PostgreSQL (in WITH RECURSIVE) |
|--------|-------------------------------|
| LEVEL | `1 as level` in base, `h.level + 1` in recursive |
| PRIOR col | JOIN condition: `c.parent_id = h.id` |
| SYS_CONNECT_BY_PATH(col,'/') | base `col::text as path`, recursive `h.path \|\| '/' \|\| c.col` |
| CONNECT_BY_ROOT col | base `col as root_col`, recursive `h.root_col` |
| CONNECT_BY_ISLEAF | `CASE WHEN NOT EXISTS (SELECT 1 FROM t WHERE t.parent_id = h.id) THEN 1 ELSE 0 END` |
| ORDER SIBLINGS BY col | `ORDER BY path` |

#### 2. MERGE Statement

**Simple MERGE** (direct key match):
```sql
-- Oracle
MERGE INTO target USING source ON (target.key = source.key)
WHEN MATCHED THEN UPDATE SET col1 = source.val1
WHEN NOT MATCHED THEN INSERT (key, col1) VALUES (source.key, source.val1)

-- PostgreSQL
INSERT INTO target (key, col1) SELECT key, val1 FROM source
ON CONFLICT (key) DO UPDATE SET col1 = EXCLUDED.val1
```

**Complex MERGE** (subquery in ON clause, MAX): Use atomic writable CTE. **Flag as MANUAL_REVIEW.**
```sql
-- Oracle
MERGE INTO detail DT USING DUAL ON (DT.DTKEY = (SELECT MAX(DTKEY) FROM detail WHERE CTKEY=#{ctkey} AND QTY>0))
WHEN MATCHED THEN UPDATE SET QTY = QTY + #{qty}
WHEN NOT MATCHED THEN INSERT (...) VALUES (...)

-- PostgreSQL: atomic writable CTE (NEVER split into two statements)
WITH target_row AS (
    SELECT dtkey FROM detail WHERE ctkey = #{ctkey}::varchar AND qty > 0 ORDER BY dtkey DESC LIMIT 1
),
do_update AS (
    UPDATE detail SET qty = qty + #{qty}::integer WHERE dtkey = (SELECT dtkey FROM target_row) RETURNING dtkey
)
INSERT INTO detail (ctkey, qty) SELECT #{ctkey}::varchar, #{qty}::integer
WHERE NOT EXISTS (SELECT 1 FROM do_update) AND NOT EXISTS (SELECT 1 FROM target_row)
```

#### 3. Pagination: ROWNUM → LIMIT/OFFSET
```sql
-- Oracle 3-depth paging
SELECT * FROM (
  SELECT A.*, ROWNUM RN FROM (
    SELECT ... ORDER BY ...
  ) A WHERE ROWNUM <= #{endRow}
) WHERE RN > #{startRow}

-- PostgreSQL
SELECT ... ORDER BY ...
LIMIT #{pageSize}::bigint OFFSET #{startRow}::bigint
```

**LIMIT/OFFSET parameter casting:**
- `LIMIT #{param}` → `LIMIT #{param}::bigint`
- `OFFSET #{param}` → `OFFSET #{param}::bigint`

#### 4. Set Operator
- `MINUS` → `EXCEPT`

#### 5. FETCH FIRST (Oracle 12c+)
```sql
-- Oracle
SELECT * FROM orders ORDER BY amount DESC
FETCH FIRST 10 ROWS ONLY

-- PostgreSQL
SELECT * FROM orders ORDER BY amount DESC
LIMIT 10
```
- `FETCH FIRST N ROWS ONLY` → `LIMIT N`
- `FETCH FIRST N PERCENT ROWS ONLY` → subquery with `LIMIT CEIL(COUNT(*) * N / 100)` or application-level
- `OFFSET M ROWS FETCH NEXT N ROWS ONLY` → `LIMIT N OFFSET M`

#### 6. XML Functions
| Oracle | PostgreSQL |
|--------|-----------|
| `XMLTYPE(string)` | `string::xml` or `XMLPARSE(DOCUMENT string)` |
| `XMLELEMENT("name", value)` | `XMLELEMENT(NAME "name", value)` (add `NAME` keyword) |
| `XMLAGG(xml ORDER BY col)` | `XMLAGG(xml ORDER BY col)` — same syntax |
| `XMLFOREST(a AS "col1", b AS "col2")` | same syntax |
| `col.EXTRACT('/path')` | `xpath('/path', col)` |
| `EXISTSNODE(xml, '/path')` | `(xpath('/path', xml))[1] IS NOT NULL` |

**CRITICAL: XMLAGG String Aggregation Idiom** — `XMLAGG(XMLELEMENT(...)).EXTRACT('//text()').GETSTRINGVAL()` is string aggregation, NOT XML. Convert to `STRING_AGG()`:
```sql
-- Oracle
SUBSTR(XMLAGG(XMLELEMENT(COL, ',', col_name) ORDER BY col_name).EXTRACT('//text()').GETSTRINGVAL(), 2) AS result
-- PostgreSQL (SUBSTR not needed — STRING_AGG has no leading delimiter)
STRING_AGG(col_name, ',' ORDER BY col_name) AS result
```

#### 7. PL/SQL Constructs in SQL
| Oracle | PostgreSQL |
|--------|-----------|
| `BULK COLLECT INTO` | Remove — use plain `SELECT` |
| `RETURNING ... INTO :var` | `RETURNING col1, col2` (remove `INTO :var`) |
| `%ROWTYPE`, `%TYPE` | Remove — use explicit types |
| `UTL_HTTP.*`, `UTL_SMTP.*`, `DBMS_PIPE.*` | **MANUAL_REVIEW** |

```sql
-- Oracle                                          -- PostgreSQL
INSERT INTO orders VALUES (seq.NEXTVAL, 'NEW')     INSERT INTO orders VALUES (nextval('seq'), 'NEW')
RETURNING id INTO :order_id                        RETURNING id
```

---

## XML Special Character Handling (MyBatis)

Outside CDATA: `<` → `&lt;`, `<=` → `&lt;=`. (`>` `>=` are safe — no escaping needed.)

1. **Original uses CDATA → keep CDATA**: `<![CDATA[ WHERE age <= 30 ]]>`
2. **Original uses entity escapes → keep**: `WHERE age &lt;= #{maxAge}`
3. **Conversion introduces `<`/`<=` → must escape or CDATA**: `WHERE qty &lt; 10`

---

## Reference Rule: Parameter Casting (apply during each Phase)

Cast parameters to match column data type. Use `lookup_column_type()` when metadata available. Without metadata, use context clues; skip if uncertain.

#### Casting Decision Rules
```
Column data type         → Parameter cast
integer, int4            → #{param}::integer
bigint, int8             → #{param}::bigint
numeric, decimal         → #{param}::numeric
double precision         → #{param}::double precision
date                     → #{param}::date
timestamp                → #{param}::timestamp
timestamptz              → #{param}::timestamptz
boolean                  → #{param}::boolean
varchar, char, text      → no cast (string types)
```

#### Computed Column Casting
- `COUNT(*) > #{param}` → `COUNT(*) > #{param}::bigint`
- `SUM(col) >= #{param}` → `SUM(col) >= #{param}::numeric`
- `(date1::date - date2::date) = #{param}` → `... = #{param}::integer`
- `EXTRACT(YEAR FROM ...) = #{param}` → `... = #{param}::integer`
- `LENGTH(col) > #{param}` → `... > #{param}::integer`
- `ROW_NUMBER() OVER() <= #{param}` → `... <= #{param}::bigint`

#### CASE Expression Casting
- Analyze THEN/ELSE return types, cast parameter to match
- String CASE → `#{param}::text`
- Numeric CASE → `#{param}::integer`

#### Casting Inside CDATA Sections
Apply the same casting rules inside CDATA:
```xml
<![CDATA[ AND o.TOTAL_AMOUNT >= #{minAmount}::double precision ]]>
```

---

## MyBatis Dynamic SQL (Keep As-Is)
- `#{param}`, `${param}` → no change
- `<if>`, `<choose>`, `<when>`, `<otherwise>` → no change
- `<foreach>`, `<where>`, `<set>`, `<trim>` → no change

## MyBatis resultMap: jdbcType Conversion
When converting `<resultMap>` elements, update Oracle jdbcType values:
| Oracle jdbcType | PostgreSQL jdbcType |
|----------------|-------------------|
| CLOB | LONGVARCHAR |
| BLOB | LONGVARBINARY |
| NUMBER | NUMERIC |
| VARCHAR2 | VARCHAR |
| DATE | TIMESTAMP |
Other jdbcType values (VARCHAR, INTEGER, BIGINT, etc.) remain unchanged.

## Dynamic WHERE Condition Scope (IMPORTANT)
When converting comma JOINs to explicit JOINs with subqueries:
- Analyze which tables each `<if test>` condition references
- Move conditions to correct scope (main query vs subquery)
- Add `WHERE 1=1` at each scope level with dynamic conditions
- Split mixed-scope `<if test>` blocks by table reference

---

## Common Wrong Conversions (AVOID THESE)

These are frequently observed incorrect conversion patterns. Check your output against this list.

### 1. Redundant OR IS NULL
**See Decision Tree in Phase 2 §2.** OR IS NULL is ONLY for direct equality on LEFT-joined columns. Never for LIKE, COALESCE, or INNER-joined.
```sql
-- ❌ WRONG                                          -- ✅ RIGHT
(UPPER(u.EMAIL) LIKE '%'||#{kw}||'%' OR u.EMAIL IS NULL)   UPPER(u.EMAIL) LIKE '%'||#{kw}||'%'
(COALESCE(addr.COUNTRY,'UNKNOWN')=#{c} OR addr.COUNTRY IS NULL)  COALESCE(addr.COUNTRY,'UNKNOWN')=#{c}
(u.EMAIL=#{email}::varchar OR u.EMAIL IS NULL) /*INNER*/    u.EMAIL=#{email}::varchar
```

### 2. Redundant or Wrong ::interval Cast
```sql
-- ❌ WRONG: date - date returns integer, NOT interval
(CURRENT_DATE - col::date)::interval

-- ✅ RIGHT: result is already integer (days)
(CURRENT_DATE - col::date)

-- ⚠️ REDUNDANT: timestamp - timestamp already returns interval
(CURRENT_TIMESTAMP - created_at)::interval

-- ✅ RIGHT: no cast needed
(CURRENT_TIMESTAMP - created_at)
```

### 3. String Concatenation for Interval
```sql
-- ❌ WRONG: fragile string concatenation
(#{param} || ' days')::interval

-- ✅ RIGHT: use MAKE_INTERVAL
MAKE_INTERVAL(days => #{param}::integer)
```

### 4. ROUND Without Numeric Cast
```sql
-- ❌ WRONG: PostgreSQL ROUND(integer, n) is an error
ROUND((date1::date - date2::date) * 24, 2)

-- ✅ RIGHT: cast to numeric first
ROUND(((date1::date - date2::date) * 24)::numeric, 2)
```

### 5. NVL → COALESCE Type Mismatch
```sql
-- ❌ WRONG: Oracle NVL auto-casts, PostgreSQL COALESCE doesn't
COALESCE(numeric_col, 'N/A')           -- ERROR: incompatible types
COALESCE(date_col, 0)                  -- ERROR: incompatible types

-- ✅ RIGHT: explicit type cast to match
COALESCE(numeric_col::text, 'N/A')
COALESCE(date_col, '1970-01-01'::date)
```

### 6. LISTAGG WITHIN GROUP Syntax
```sql
-- ❌ WRONG: keeping Oracle WITHIN GROUP syntax
STRING_AGG(col, ',') WITHIN GROUP (ORDER BY col)

-- ✅ RIGHT: ORDER BY moves inside the function
STRING_AGG(col, ',' ORDER BY col)
```

### 7. Incorrect Date Format in to_timestamp
```sql
-- ❌ WRONG: Oracle format used in PostgreSQL
to_timestamp(str, 'YYYY/MM/DD HH24:MI:SS')  -- check format matches actual data

-- ✅ RIGHT: verify format string matches input pattern exactly
```

### 8. TO_DATE Blindly Converted to ::date Cast
```sql
-- ❌ RISKY: s::date only works with ISO format strings
TO_DATE(#{param}, 'YYYYMMDD')  →  #{param}::date   -- FAILS for '20260315'

-- ✅ RIGHT: preserve to_date function when format is non-ISO
TO_DATE(#{param}, 'YYYYMMDD')  →  to_date(#{param}, 'YYYYMMDD')
-- ::date cast is safe ONLY for ISO format ('2026-03-15') or date-typed values
```

### 9. User-Defined Package Function Mapped to Built-in
See Phase 1 §6. Flatten with underscore — NEVER map to built-in.
```sql
-- ❌ PKG_CRYPTO.ENCRYPT(col, key) → pgp_sym_encrypt(col, key)
-- ✅ PKG_CRYPTO.ENCRYPT(col, key) → pkg_crypto_encrypt(col, key)
```

### 10. TRUNC(number) Converted to ROUND
See Phase 3 §2-1a. TRUNC truncates, ROUND rounds — different results.
```sql
-- ❌ TRUNC(weight, 3) → ROUND(weight::numeric, 3)
-- ✅ TRUNC(weight, 3) → trunc(weight::numeric, 3)
```

### 11. JOIN Condition Changed (Column Name "Correction")
```sql
-- ❌ WRONG: agent "fixed" what looked like a bug in original
A.UPLDSEQ = B.UPLDKEY  →  a.upldseq = b.upldseq

-- ✅ RIGHT: preserve original join condition exactly (lowercase only)
A.UPLDSEQ = B.UPLDKEY  →  a.upldseq = b.upldkey
```
**NEVER change column names in JOIN conditions.** Only lowercase them. Even if it looks like a bug in the original, preserve the original logic.

### 12. Original Name/Identifier Changed (Hallucination)
NEVER change ANY name. Copy verbatim (lowercase only). No prefixes, no typo "fixes", no renaming.
```sql
-- ❌ sql_putawayLocation → sql_selectPutawayLocation (added prefix)
-- ❌ sql_tOrderCtgDiv (refid guessed from SQL ID)
-- ❌ sql_tWorkInfoIbat → sql_tWorkInfoIvat (typo "fix")
-- ✅ sql_putawaylocation, sql_tordermstadcdunion, sql_tworkinfoibat (verbatim lowercase)
```

---

## Critical Rules
1. **Process ALL SQL IDs** — do not skip any
2. **Follow 4-phase order** — Phase 1(Structural) → Phase 2(Syntax) → Phase 3(Functions) → Phase 4(Advanced)
3. **Preserve MyBatis tags** — `<if>`, `<foreach>`, etc. must remain intact
4. **Preserve parameter references** — `#{param}`, `${param}` unchanged
5. **Preserve ALL comments** — `--` and `/* */` comments must remain exactly as-is
6. **Preserve variable names** — only lowercase, NEVER change prefixes or naming (V_RETURN → v_return, NOT p_return)
7. **Preserve literal values** — string literals, email addresses, URLs, constants must NOT be masked, anonymized, or sanitized
8. **Add notes for complex conversions** — CONNECT BY, MERGE, complex patterns
9. **Flag MANUAL_REVIEW** — when conversion accuracy is uncertain
10. **NO optimization** — convert syntax only, do not change logic or structure
11. **Preserve ALL original names** — sql id, refid, resultMap id, aliases must match the original verbatim (lowercase only). NEVER add prefixes, fix typos, or rename
