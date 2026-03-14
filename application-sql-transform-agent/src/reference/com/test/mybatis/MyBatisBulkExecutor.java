package com.test.mybatis;

import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;

import java.io.*;
import java.nio.file.*;
import java.sql.SQLException;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Program to recursively search MyBatis XML files and automatically test all SQL IDs
 */
public class MyBatisBulkExecutor {
    
    private static final String PARAMETERS_FILE = "parameters.properties";
    private static final Pattern SQL_ID_PATTERN = Pattern.compile("<(select|insert|update|delete)\\s+id=\"([^\"]+)\"");
    
    public static void main(String[] args) {
        if (args.length < 1) {
            System.out.println("Usage: java MyBatisBulkExecutor <directory_path> [options]");
            System.out.println("Options:");
            System.out.println("  --select-only    Execute SELECT statements only (default)");
            System.out.println("  --all           Execute all SQL statements (including INSERT/UPDATE/DELETE)");
            System.out.println("  --summary       Output summary information only");
            System.out.println("  --verbose       Output detailed information");
            System.out.println();
            System.out.println("Example: java MyBatisBulkExecutor /path/to/mapper/directory");
            System.out.println("Example: java MyBatisBulkExecutor /path/to/mapper/directory --all --verbose");
            return;
        }
        
        String directoryPath = args[0];
        boolean selectOnly = true;
        boolean summaryOnly = false;
        boolean verbose = false;
        
        // Option parsing
        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--all":
                    selectOnly = false;
                    break;
                case "--summary":
                    summaryOnly = true;
                    break;
                case "--verbose":
                    verbose = true;
                    break;
                case "--select-only":
                    selectOnly = true;
                    break;
            }
        }
        
        MyBatisBulkExecutor executor = new MyBatisBulkExecutor();
        executor.executeAllSql(directoryPath, selectOnly, summaryOnly, verbose);
    }
    
    public void executeAllSql(String directoryPath, boolean selectOnly, boolean summaryOnly, boolean verbose) {
        try {
            System.out.println("=== MyBatis Bulk SQL Execution Test ===");
            System.out.println("Search directory: " + directoryPath);
            System.out.println("Execution mode: " + (selectOnly ? "SELECT only" : "All SQL"));
            System.out.println("Output mode: " + (summaryOnly ? "Summary only" : verbose ? "Detailed" : "Basic"));
            
            // 1. Load parameters
            Map<String, Object> parameters = loadParameters();
            if (!summaryOnly) {
                System.out.println("\n=== Loaded Parameters ===");
                System.out.println("Total " + parameters.size() + " parameters loaded");
                if (verbose) {
                    parameters.forEach((key, value) -> 
                        System.out.println("  " + key + " = " + (value != null ? value : "null")));
                }
            }
            
            // 2. Find XML files recursively
            List<Path> xmlFiles = findXmlFiles(Paths.get(directoryPath));
            System.out.println("\nXML files found: " + xmlFiles.size());
            
            // 3. Collect all SQL information
            List<SqlTestInfo> allSqlTests = new ArrayList<>();
            for (Path xmlFile : xmlFiles) {
                List<SqlTestInfo> sqlTests = collectSqlTests(xmlFile, selectOnly);
                allSqlTests.addAll(sqlTests);
            }
            
            System.out.println("SQL count to execute: " + allSqlTests.size());
            
            // 4. Execute SQL tests
            TestResults results = executeTests(allSqlTests, parameters, summaryOnly, verbose);
            
            // 5. Results summary
            printSummary(results);
            
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
            e.printStackTrace();
        }
    }
    
    /**
     * Find XML files recursively in directory
     */
    private List<Path> findXmlFiles(Path directory) throws IOException {
        List<Path> xmlFiles = new ArrayList<>();
        
        Files.walk(directory)
            .filter(path -> path.toString().toLowerCase().endsWith(".xml"))
            .filter(Files::isRegularFile)
            .forEach(xmlFiles::add);
        
        return xmlFiles;
    }
    
    /**
     * Collect SQL test information from XML file
     */
    private List<SqlTestInfo> collectSqlTests(Path xmlFile, boolean selectOnly) {
        List<SqlTestInfo> sqlTests = new ArrayList<>();
        
        try {
            String content = Files.readString(xmlFile);
            Matcher matcher = SQL_ID_PATTERN.matcher(content);
            
            while (matcher.find()) {
                String sqlType = matcher.group(1).toLowerCase();
                String sqlId = matcher.group(2);
                
                // Filter when executing SELECT only
                if (selectOnly && !sqlType.equals("select")) {
                    continue;
                }
                
                SqlTestInfo testInfo = new SqlTestInfo();
                testInfo.xmlFile = xmlFile;
                testInfo.sqlId = sqlId;
                testInfo.sqlType = sqlType;
                
                sqlTests.add(testInfo);
            }
            
        } catch (IOException e) {
            System.err.println("File read error: " + xmlFile + " - " + e.getMessage());
        }
        
        return sqlTests;
    }
    
    /**
     * Execute all SQL tests
     */
    private TestResults executeTests(List<SqlTestInfo> sqlTests, Map<String, Object> parameters, 
                                   boolean summaryOnly, boolean verbose) {
        TestResults results = new TestResults();
        
        System.out.println("\n=== SQL Execution Test Started ===");
        
        for (int i = 0; i < sqlTests.size(); i++) {
            SqlTestInfo testInfo = sqlTests.get(i);
            
            if (!summaryOnly) {
                System.out.println("\n[" + (i + 1) + "/" + sqlTests.size() + "] " + 
                    testInfo.xmlFile.getFileName() + ":" + testInfo.sqlId + 
                    " (" + testInfo.sqlType.toUpperCase() + ")");
            }
            
            TestResult result = executeSingleTest(testInfo, parameters, summaryOnly, verbose);
            results.addResult(result);
            
            if (!summaryOnly) {
                if (result.success) {
                    System.out.println("  ✅ Success - " + result.rowCount + " rows");
                } else {
                    System.out.println("  ❌ Failed - " + result.errorMessage);
                }
            }
        }
        
        return results;
    }
    
    /**
     * Execute single SQL test
     */
    private TestResult executeSingleTest(SqlTestInfo testInfo, Map<String, Object> parameters, 
                                       boolean summaryOnly, boolean verbose) {
        TestResult result = new TestResult();
        result.testInfo = testInfo;
        
        try {
            // Create MyBatis configuration
            SqlSessionFactory sqlSessionFactory = createSqlSessionFactory(testInfo.xmlFile.toString());
            
            // Execute SQL
            try (SqlSession session = sqlSessionFactory.openSession()) {
                if (testInfo.sqlType.equals("select")) {
                    List<Map<String, Object>> rows = session.selectList(testInfo.sqlId, parameters);
                    result.success = true;
                    result.rowCount = rows.size();
                    
                    if (verbose && !summaryOnly && !rows.isEmpty()) {
                        System.out.println("    Columns: " + String.join(", ", rows.get(0).keySet()));
                        if (rows.size() <= 3) {
                            for (Map<String, Object> row : rows) {
                                System.out.println("    Data: " + formatRowData(row));
                            }
                        }
                    }
                } else {
                    // For INSERT/UPDATE/DELETE, only check parsing without actual execution
                    session.selectList(testInfo.sqlId, parameters);
                    result.success = true;
                    result.rowCount = 0;
                }
            }
            
        } catch (Exception e) {
            result.success = false;
            result.errorMessage = e.getMessage();
            if (result.errorMessage.length() > 100) {
                result.errorMessage = result.errorMessage.substring(0, 100) + "...";
            }
        }
        
        return result;
    }
    
    /**
     * Format row data
     */
    private String formatRowData(Map<String, Object> row) {
        List<String> values = new ArrayList<>();
        for (Object value : row.values()) {
            String strValue = value != null ? value.toString() : "NULL";
            if (strValue.length() > 20) {
                strValue = strValue.substring(0, 20) + "...";
            }
            values.add(strValue);
        }
        return String.join(" | ", values);
    }
    
    /**
     * Print results summary
     */
    private void printSummary(TestResults results) {
        System.out.println("\n=== Execution Results Summary ===");
        System.out.println("Total tests: " + results.totalTests);
        System.out.println("Success: " + results.successCount);
        System.out.println("Failed: " + results.failureCount);
        System.out.println("Success rate: " + String.format("%.1f%%", results.getSuccessRate()));
        
        if (results.failureCount > 0) {
            System.out.println("\n=== Failed Tests ===");
            for (TestResult result : results.failures) {
                System.out.println("❌ " + result.testInfo.xmlFile.getFileName() + 
                    ":" + result.testInfo.sqlId + " - " + result.errorMessage);
            }
        }
        
        // Statistics by file
        System.out.println("\n=== Statistics by File ===");
        Map<String, Integer[]> fileStats = new HashMap<>(); // [Success, Failed]
        
        for (TestResult result : results.allResults) {
            String fileName = result.testInfo.xmlFile.getFileName().toString();
            fileStats.computeIfAbsent(fileName, k -> new Integer[]{0, 0});
            if (result.success) {
                fileStats.get(fileName)[0]++;
            } else {
                fileStats.get(fileName)[1]++;
            }
        }
        
        fileStats.entrySet().stream()
            .sorted(Map.Entry.comparingByKey())
            .forEach(entry -> {
                String fileName = entry.getKey();
                Integer[] stats = entry.getValue();
                int total = stats[0] + stats[1];
                double rate = total > 0 ? (stats[0] * 100.0 / total) : 0;
                System.out.println(String.format("  %s: %d/%d (%.1f%%)", 
                    fileName, stats[0], total, rate));
            });
    }
    
    /**
     * Load parameter file
     */
    private Map<String, Object> loadParameters() throws IOException {
        Map<String, Object> paramMap = new HashMap<>();
        Properties props = new Properties();
        
        File file = new File(PARAMETERS_FILE);
        if (!file.exists()) {
            System.out.println("Parameter file not found: " + PARAMETERS_FILE);
            return paramMap;
        }
        
        try (FileInputStream fis = new FileInputStream(file)) {
            props.load(fis);
        }
        
        // Convert Properties to Map with type conversion
        for (String key : props.stringPropertyNames()) {
            String value = props.getProperty(key);
            if (value == null || value.trim().isEmpty()) {
                paramMap.put(key, null);
            } else {
                // Check if numeric
                if (isNumeric(value)) {
                    try {
                        if (value.contains(".")) {
                            paramMap.put(key, Double.parseDouble(value));
                        } else {
                            paramMap.put(key, Long.parseLong(value));
                        }
                    } catch (NumberFormatException e) {
                        paramMap.put(key, value);
                    }
                } else {
                    paramMap.put(key, value);
                }
            }
        }
        
        return paramMap;
    }
    
    /**
     * Check if string is numeric
     */
    private boolean isNumeric(String str) {
        try {
            Double.parseDouble(str);
            return true;
        } catch (NumberFormatException e) {
            return false;
        }
    }
    
    /**
     * Create MyBatis SqlSessionFactory using Properties-based DataSource (no credentials in XML)
     */
    private SqlSessionFactory createSqlSessionFactory(String xmlFilePath) throws Exception {
        String oracleHome = System.getenv("ORACLE_HOME");
        if (oracleHome != null) System.setProperty("oracle.net.tns_admin", oracleHome + "/network/admin");

        String modifiedXmlContent = modifyXmlForTesting(xmlFilePath);
        File tempXmlFile = File.createTempFile("mapper", ".xml");
        tempXmlFile.deleteOnExit();
        try (FileWriter writer = new FileWriter(tempXmlFile)) { writer.write(modifiedXmlContent); }

        final String username = System.getenv("ORACLE_SVC_USER");
        final String password = System.getenv("ORACLE_SVC_PASSWORD");
        if (username == null || password == null)
            throw new RuntimeException("Oracle environment variables not set: ORACLE_SVC_USER, ORACLE_SVC_PASSWORD");

        final Properties jdbcProps = new Properties();
        jdbcProps.setProperty("user", username);
        jdbcProps.setProperty("password", password);
        String connectString = System.getenv("ORACLE_SVC_CONNECT_STRING");
        if (connectString != null) jdbcProps.setProperty("TNS_ENTRY", connectString);

        javax.sql.DataSource dataSource = new javax.sql.DataSource() {
            public java.sql.Connection getConnection() throws java.sql.SQLException {
                try { Class.forName("oracle.jdbc.driver.OracleDriver"); } catch (ClassNotFoundException e) { throw new java.sql.SQLException(e); }
                return java.sql.DriverManager.getConnection("jdbc:oracle:thin:", jdbcProps);
            }
            public java.sql.Connection getConnection(String u, String p) throws java.sql.SQLException { return getConnection(); }
            public <T> T unwrap(Class<T> i) throws java.sql.SQLException { throw new java.sql.SQLException("Not a wrapper"); }
            public boolean isWrapperFor(Class<?> i) { return false; }
            public java.io.PrintWriter getLogWriter() { return null; }
            public void setLogWriter(java.io.PrintWriter pw) {}
            public void setLoginTimeout(int s) {}
            public int getLoginTimeout() { return 0; }
            public java.util.logging.Logger getParentLogger() { return java.util.logging.Logger.getLogger(java.util.logging.Logger.GLOBAL_LOGGER_NAME); }
        };

        Environment environment = new Environment("development", new JdbcTransactionFactory(), dataSource);
        Configuration configuration = new Configuration(environment);
        configuration.setMapUnderscoreToCamelCase(true);
        try (InputStream ms = new FileInputStream(tempXmlFile)) {
            new XMLMapperBuilder(ms, configuration, tempXmlFile.getAbsolutePath(), configuration.getSqlFragments()).parse();
        }
        return new SqlSessionFactoryBuilder().build(configuration);
    }

    /**
     * Modify XML file's resultType for testing
     */
    private String modifyXmlForTesting(String xmlFilePath) throws IOException {
        StringBuilder content = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(xmlFilePath))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.contains("resultType="))  line = line.replaceAll("resultType=\"[^\"]*\"",  "resultType=\"map\"");
                if (line.contains("parameterType=")) line = line.replaceAll("parameterType=\"[^\"]*\"", "parameterType=\"map\"");
                content.append(line).append("\n");
            }
        }
        return content.toString();
    }

    // Inner classes
    private static class SqlTestInfo {
        Path xmlFile;
        String sqlId;
        String sqlType;
    }

    private static class TestResult {
        SqlTestInfo testInfo;
        boolean success;
        int rowCount;
        String errorMessage;
    }

    private static class TestResults {
        List<TestResult> allResults = new ArrayList<>();
        List<TestResult> failures = new ArrayList<>();
        int totalTests = 0;
        int successCount = 0;
        int failureCount = 0;
        
        void addResult(TestResult result) {
            allResults.add(result);
            totalTests++;
            if (result.success) {
                successCount++;
            } else {
                failureCount++;
                failures.add(result);
            }
        }
        
        double getSuccessRate() {
            return totalTests > 0 ? (successCount * 100.0 / totalTests) : 0;
        }
    }
}
