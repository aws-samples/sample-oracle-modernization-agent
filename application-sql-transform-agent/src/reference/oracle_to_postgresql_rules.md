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

#### 3. Subquery Alias (Mandatory in PostgreSQL)
- `FROM (SELECT...)` → `FROM (SELECT...) AS sub1` (only when alias is missing)
- Preserve existing aliases

---

### PHASE 3: FUNCTIONS & OPERATORS

Convert expression-level functions and operators.

#### 1. String Concatenation
**`||` works in PostgreSQL (SQL standard operator). Converting to `CONCAT()` is optional.**

The only difference: `NULL || 'text'` returns `NULL` in PostgreSQL (Oracle returns `'text'`).
Use `CONCAT()` only when NULL handling matters.

```sql
-- Both are valid in PostgreSQL:
col1 || col2                          -- OK as-is
CONCAT(col1, col2)                    -- also OK

-- LIKE pattern — both work:
LIKE '%' || #{param} || '%'           -- OK as-is
LIKE CONCAT('%', #{param}, '%')       -- also OK

-- Use CONCAT when NVL columns are involved (NULL safety):
NVL(col1,'') || col2 → CONCAT(COALESCE(col1,''), col2)
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
| LENGTHB(s) | OCTET_LENGTH(s) |
| LPAD(s,len,pad) | LPAD(s::text,len,pad) |
| LISTAGG(col,delim) WITHIN GROUP (ORDER BY x) | STRING_AGG(col, delim ORDER BY x) — move ORDER BY inside function |
| WM_CONCAT(col) | STRING_AGG(col, ',') |
| TO_NUMBER(s) | CAST(s AS NUMERIC) |
| DBMS_LOB.GETLENGTH(col) | LENGTH(col) or OCTET_LENGTH(col) |
| ROWID | **remove or replace with PK** — ctid changes after VACUUM, unsafe as identifier |
| MINUS | EXCEPT |

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

**KEEP (DENSE_RANK FIRST/LAST):**
```sql
-- Oracle
MAX(col) KEEP (DENSE_RANK FIRST ORDER BY date_col)

-- PostgreSQL: use subquery approach
(SELECT col FROM table ORDER BY date_col LIMIT 1)
-- Or DISTINCT ON when selecting full rows:
SELECT DISTINCT ON (group_col) * FROM table ORDER BY group_col, date_col
```

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

**PostgreSQL returns DIFFERENT types depending on operand types:**

| Operation | Return Type | `::interval` cast |
|-----------|-------------|-------------------|
| `date - date` | **integer** (days) | Do NOT add — type mismatch |
| `timestamp - timestamp` | **interval** | Do NOT add — already interval (redundant no-op) |
| `date - integer` | **date** | N/A |
| `timestamp - interval` | **timestamp** | N/A |

**date - date → integer:**
- `TRUNC(SYSDATE) - TRUNC(date_col)` → `(CURRENT_DATE - date_col::date)` — returns integer
- `SYSDATE - date_col` → `(CURRENT_DATE - date_col::date)` — returns integer
- `NVL(SYSDATE - date_col, default)` → `COALESCE((CURRENT_DATE - date_col::date), default)`
- **NEVER use**: `(date - date)::interval` — unnecessary type conversion

**timestamp - timestamp → interval:**
- `SYSTIMESTAMP - created_at` → `(CURRENT_TIMESTAMP - created_at)` — already returns interval
- Do NOT add `::interval` — it is redundant (no-op, harmless but unnecessary)

#### 5. EXTRACT with Date/Timestamp Arithmetic

**Choose the right pattern based on operand type:**
- `EXTRACT(DAY FROM timestamp1 - timestamp2)` → `EXTRACT(DAY FROM (timestamp1 - timestamp2))` — already interval, no cast needed
- `EXTRACT(DAY FROM date1 - date2)` → `(date1 - date2)` — already integer days, EXTRACT not needed
- `EXTRACT(HOUR FROM timestamp1 - timestamp2)` → `EXTRACT(HOUR FROM (timestamp1 - timestamp2))` — interval supports HOUR/MINUTE/SECOND
- Always wrap arithmetic in parentheses for clarity

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
  -- Base case: no CTE self-reference (START WITH → WHERE)
  SELECT id, parent_id, name, 1 as level
  FROM categories WHERE parent_id IS NULL
  UNION ALL
  -- Recursive case: must reference CTE
  SELECT c.id, c.parent_id, c.name, h.level + 1
  FROM categories c JOIN hierarchy h ON c.parent_id = h.id
)
SELECT id, parent_id, name FROM hierarchy
```

**Recursive CTE rules:**
- Base case must NOT reference CTE name
- Exactly one UNION ALL between base and recursive
- Multiple UNION ALL inside recursive: wrap in parentheses
- Enforce type consistency: cast recursive term to match base term types
  - `CONCAT(...)::character varying` — when string grows in recursive term

**CONNECT BY related functions:**
| Oracle | PostgreSQL (in WITH RECURSIVE) |
|--------|-------------------------------|
| LEVEL | Add `1 as level` in base, `h.level + 1` in recursive |
| PRIOR col | Use JOIN condition: `c.parent_id = h.id` |
| SYS_CONNECT_BY_PATH(col,'/') | Accumulate string: base `col::text as path`, recursive `h.path \|\| '/' \|\| c.col` |
| CONNECT_BY_ROOT col | Carry from base case: `col as root_col`, recursive `h.root_col` |
| CONNECT_BY_ISLEAF | `CASE WHEN NOT EXISTS (SELECT 1 FROM t WHERE t.parent_id = h.id) THEN 1 ELSE 0 END` |
| ORDER SIBLINGS BY col | `ORDER BY path` (use accumulated path column for sibling order) |

```sql
-- Oracle (complex)
SELECT LEVEL, SYS_CONNECT_BY_PATH(name, '/'), CONNECT_BY_ISLEAF
FROM categories
START WITH parent_id IS NULL
CONNECT BY PRIOR id = parent_id
ORDER SIBLINGS BY name

-- PostgreSQL
WITH RECURSIVE h AS (
  SELECT id, parent_id, name, 1 as level,
         name::text as path,
         name::text as root_name
  FROM categories WHERE parent_id IS NULL
  UNION ALL
  SELECT c.id, c.parent_id, c.name, h.level + 1,
         (h.path || '/' || c.name)::character varying,
         h.root_name
  FROM categories c JOIN h ON c.parent_id = h.id
)
SELECT level, '/' || path as sys_path,
       CASE WHEN NOT EXISTS (
         SELECT 1 FROM categories x WHERE x.parent_id = h.id
       ) THEN 1 ELSE 0 END as is_leaf
FROM h
ORDER BY path
```

#### 2. MERGE Statement
```sql
-- Oracle
MERGE INTO target USING source ON (condition)
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...

-- PostgreSQL
INSERT INTO target (...) SELECT ... FROM source
ON CONFLICT (key) DO UPDATE SET ...
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
| `XMLFOREST(a AS "col1", b AS "col2")` | `XMLFOREST(a AS "col1", b AS "col2")` — same syntax |
| `col.EXTRACT('/path')` | `xpath('/path', col)` |
| `EXISTSNODE(xml, '/path')` | `(xpath('/path', xml))[1] IS NOT NULL` |

```sql
-- Oracle
SELECT XMLELEMENT("employee", XMLFOREST(name AS "name", dept AS "dept"))
FROM employees

-- PostgreSQL
SELECT XMLELEMENT(NAME "employee", XMLFOREST(name AS "name", dept AS "dept"))
FROM employees
```

#### 7. PL/SQL Constructs in SQL
These Oracle PL/SQL constructs may appear in MyBatis mappers (usually in `<select>` with stored procedure calls):

| Oracle | PostgreSQL |
|--------|-----------|
| `BULK COLLECT INTO` | Remove — use plain `SELECT` (MyBatis handles result collection) |
| `RETURNING ... INTO :var` | `RETURNING col1, col2` (remove `INTO :var`, MyBatis maps results) |
| `%ROWTYPE` | Remove — use explicit column types |
| `%TYPE` | Remove — use explicit types |

```sql
-- Oracle: RETURNING INTO
INSERT INTO orders (id, status) VALUES (seq.NEXTVAL, 'NEW')
RETURNING id INTO :order_id

-- PostgreSQL
INSERT INTO orders (id, status) VALUES (nextval('seq'), 'NEW')
RETURNING id
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
   ```xml
   <![CDATA[ WHERE age <= 30 AND salary > 50000 ]]>
   ```

2. **If original uses entity escapes → keep escapes**
   ```xml
   WHERE age &lt;= #{maxAge}  →  WHERE age &lt;= #{maxAge}
   ```

3. **If conversion introduces `<` or `<=` → must escape or wrap in CDATA**
   ```xml
   WHERE qty &lt; 10 AND amount >= 1000
   ```

---

## Reference Rule: Parameter Casting (apply during each Phase)

**Principle**: Cast parameters to match the compared column's data type.
**With metadata**: Use `lookup_column_type(table_name, column_name)` for actual type.
**Without metadata**: Use context clues (column name patterns, SQL context). Skip if uncertain.

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

## Dynamic WHERE Condition Scope (IMPORTANT)
When converting comma JOINs to explicit JOINs with subqueries:
- Analyze which tables each `<if test>` condition references
- Move conditions to correct scope (main query vs subquery)
- Add `WHERE 1=1` at each scope level with dynamic conditions
- Split mixed-scope `<if test>` blocks by table reference

---

## Common Wrong Conversions (AVOID THESE)

These are frequently observed incorrect conversion patterns. Check your output against this list.

### 1. Redundant OR IS NULL (see Decision Tree in Phase 2 §2)
```sql
-- ❌ WRONG: LIKE on outer-joined column — OR IS NULL changes semantics
WHERE (UPPER(u.EMAIL) LIKE '%' || #{kw} || '%' OR u.EMAIL IS NULL)

-- ✅ RIGHT: NULL LIKE → NULL → falsy, identical in both DBs
WHERE UPPER(u.EMAIL) LIKE '%' || #{kw} || '%'

-- ❌ WRONG: COALESCE already handles NULL
WHERE COALESCE(addr.COUNTRY, 'UNKNOWN') = #{country} OR addr.COUNTRY IS NULL

-- ✅ RIGHT: COALESCE alone is sufficient
WHERE COALESCE(addr.COUNTRY, 'UNKNOWN') = #{country}

-- ❌ WRONG: column from INNER-joined table — never NULL from join
WHERE (u.EMAIL = #{email}::varchar OR u.EMAIL IS NULL)
-- (u is JOIN, not LEFT JOIN → u.EMAIL cannot be NULL from the join)

-- ✅ RIGHT: only for direct comparison on LEFT-joined column
WHERE (addr.STATUS = #{status}::varchar OR addr.STATUS IS NULL)
-- (addr is LEFT JOIN → addr.STATUS can be NULL when no matching row)
```
**Rule**: Follow the Decision Tree in Phase 2 §2. `OR col IS NULL` is ONLY needed for **direct equality comparison** on **outer-joined table** columns. Never for LIKE, COALESCE, or INNER-joined columns.

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

---

## Critical Rules
1. **Process ALL SQL IDs** — do not skip any
2. **Follow 4-phase order** — Phase 1(Structural) → Phase 2(Syntax) → Phase 3(Functions) → Phase 4(Advanced)
3. **Preserve MyBatis tags** — `<if>`, `<foreach>`, etc. must remain intact
4. **Preserve parameter references** — `#{param}`, `${param}` unchanged
5. **Add notes for complex conversions** — CONNECT BY, MERGE, complex patterns
6. **Flag MANUAL_REVIEW** — when conversion accuracy is uncertain
7. **NO optimization** — convert syntax only, do not change logic or structure
