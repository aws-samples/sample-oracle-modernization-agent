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
```sql
-- Oracle
WHERE a.id = b.id(+)

-- PostgreSQL
FROM a LEFT JOIN b ON a.id = b.id
```

**Add NULL-safety for dynamic conditions on outer-joined tables:**
```sql
<if test="param != null">
   AND (t2.column = #{param}::type OR t2.column IS NULL)
</if>
```
**Exception**: If the condition already uses COALESCE/NVL conversion (e.g., `COALESCE(t2.column, 'default') = #{param}`), do NOT add `OR t2.column IS NULL` — COALESCE already handles NULL.

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
| NVL(a, b) | COALESCE(a, b) |
| NVL2(a, b, c) | CASE WHEN a IS NOT NULL THEN b ELSE c END |
| DECODE(a,b,c,d) | CASE WHEN a = b THEN c ELSE d END |
| SYSDATE | CURRENT_TIMESTAMP |
| SYSTIMESTAMP | CURRENT_TIMESTAMP |
| USER | CURRENT_USER |
| SYS_GUID() | gen_random_uuid() |
| SUBSTR(s,p,l) | SUBSTRING(s,p,l) |
| INSTR(s,sub) | POSITION(sub IN s) |
| LENGTHB(s) | OCTET_LENGTH(s) |
| LPAD(s,len,pad) | LPAD(s::text,len,pad) |
| LISTAGG(col,delim) | STRING_AGG(col,delim) |
| WM_CONCAT(col) | STRING_AGG(col, ',') |
| TO_NUMBER(s) | CAST(s AS NUMERIC) |
| DBMS_LOB.GETLENGTH(col) | LENGTH(col) or OCTET_LENGTH(col) |
| ROWID | ctid (or remove) |
| MINUS | EXCEPT |

#### 2-1. Regular Expression Functions
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
| TO_DATE(s,'YYYY-MM-DD') | s::date |
| TO_DATE(s,'YYYY-MM-DD HH24:MI:SS') | to_timestamp(s,'YYYY-MM-DD HH24:MI:SS') |
| ADD_MONTHS(date,n) | date + INTERVAL 'n months' |
| TRUNC(date,'DD') | DATE_TRUNC('day',date) |
| TRUNC(date,'MM') | DATE_TRUNC('month',date) |
| MONTHS_BETWEEN(d1,d2) | (EXTRACT(YEAR FROM AGE(d1::date,d2::date))*12 + EXTRACT(MONTH FROM AGE(d1::date,d2::date))) |
| TRUNC(MONTHS_BETWEEN(d1,d2)/12) | EXTRACT(YEAR FROM AGE(d1::date,d2::date)) |
| LAST_DAY(date) | (DATE_TRUNC('month', date) + INTERVAL '1 month - 1 day')::date |
| NEXT_DAY(date, 'day') | (date + (dow - EXTRACT(DOW FROM date) + 7)::int % 7 * INTERVAL '1 day') |

#### 4. Date Arithmetic (CRITICAL)
- `DATE - DATE` → Returns integer (days) in PostgreSQL. No interval cast needed.
- `TRUNC(SYSDATE) - TRUNC(date_col)` → `(CURRENT_DATE - date_col::date)`
- `SYSDATE - date_col` → `(CURRENT_DATE - date_col::date)`
- `NVL(SYSDATE - date_col, default)` → `COALESCE((CURRENT_DATE - date_col::date), default)`
- **NEVER use**: `(DATE - DATE)::interval` — causes errors

#### 5. EXTRACT with Date Arithmetic
- `EXTRACT(DAY FROM date1 - date2)` → `EXTRACT(DAY FROM (date1 - date2)::interval)`
- Always wrap date arithmetic in parentheses before `::interval`
- Applies in all contexts: AVG(), CASE, SUM(), etc.

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

### 1. Redundant OR IS NULL with COALESCE
```sql
-- ❌ WRONG: OR IS NULL is redundant — COALESCE already handles NULL
WHERE COALESCE(col, 'default') = #{param} OR col IS NULL

-- ✅ RIGHT: COALESCE alone is sufficient
WHERE COALESCE(col, 'default') = #{param}
```

### 2. Date Subtraction Cast to Interval
```sql
-- ❌ WRONG: date - date returns integer in PostgreSQL, NOT interval
(CURRENT_DATE - col::date)::interval

-- ✅ RIGHT: result is already integer (days)
(CURRENT_DATE - col::date)
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

### 5. Incorrect Date Format in to_timestamp
```sql
-- ❌ WRONG: Oracle format used in PostgreSQL
to_timestamp(str, 'YYYY/MM/DD HH24:MI:SS')  -- check format matches actual data

-- ✅ RIGHT: verify format string matches input pattern exactly
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
