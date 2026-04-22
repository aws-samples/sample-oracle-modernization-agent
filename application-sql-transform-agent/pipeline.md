# Pipeline: Oracle → Target DB

## Steps
1. analyze    | run_source_analyzer.py | required
2. transform  | run_sql_transform.py | required
3. review     | run_sql_review.py | optional
4. validate   | run_sql_validate.py | optional
5. merge      | run_sql_merge.py | required
6. test       | run_sql_test.py | required
