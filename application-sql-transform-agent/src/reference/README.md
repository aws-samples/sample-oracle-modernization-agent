# src/reference/

Conversion rules, Java test harness, and supporting libraries for OMA.

## lib/ — Vendored JARs

The `lib/` directory contains 7 JAR files required by the Java-based MyBatis bulk
test executor (Phase 1 of the Test step). They are vendored in-repo because the
test harness must run offline without a build tool (no Maven/Gradle in scope).

| JAR | Maven Central Coordinates | Purpose |
|-----|---------------------------|---------|
| `ojdbc8-21.9.0.0.jar` | `com.oracle.database.jdbc:ojdbc8:21.9.0.0` | Oracle JDBC driver (source DB connectivity) |
| `postgresql-42.7.1.jar` | `org.postgresql:postgresql:42.7.1` | PostgreSQL JDBC driver (target DB) |
| `mysql-connector-j-8.2.0.jar` | `com.mysql:mysql-connector-j:8.2.0` | MySQL JDBC driver (target DB) |
| `mybatis-3.5.13.jar` | `org.mybatis:mybatis:3.5.13` | MyBatis SQL mapper framework |
| `jackson-core-2.18.6.jar` | `com.fasterxml.jackson.core:jackson-core:2.18.6` | JSON processing (test result output) |
| `jackson-databind-2.18.6.jar` | `com.fasterxml.jackson.core:jackson-databind:2.18.6` | JSON data binding |
| `jackson-annotations-2.18.6.jar` | `com.fasterxml.jackson.core:jackson-annotations:2.18.6` | JSON annotations |
