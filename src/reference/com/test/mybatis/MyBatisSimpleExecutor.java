package com.test.mybatis;

import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;

import java.io.*;
import java.util.*;

/**
 * Simple SQL execution program using MyBatis
 * Automatically handles dynamic conditions with just a parameter file.
 */
public class MyBatisSimpleExecutor {
    
    private static final String PARAMETERS_FILE = "parameters.properties";
    
    public static void main(String[] args) {
        if (args.length < 2) {
            System.out.println("Usage: java MyBatisSimpleExecutor <XML_file_path> <SQL_ID>");
            System.out.println("Example: java MyBatisSimpleExecutor /path/to/mapper.xml selectInventoryStatusAnalysis");
            System.out.println("Oracle environment variables must be set (ORACLE_SVC_USER, ORACLE_SVC_PASSWORD).");
            System.out.println("Must be able to connect to orcl from tnsnames.");
            return;
        }
        
        String xmlFilePath = args[0];
        String sqlId = args[1];
        
        MyBatisSimpleExecutor executor = new MyBatisSimpleExecutor();
        executor.executeWithMyBatis(xmlFilePath, sqlId);
    }
    
    public void executeWithMyBatis(String xmlFilePath, String sqlId) {
        try {
            System.out.println("=== MyBatis Simple Execution Program ===");
            System.out.println("XML file: " + xmlFilePath);
            System.out.println("SQL ID: " + sqlId);
            
            // 1. Parameter loading
            Map<String, Object> parameters = loadParameters();
            System.out.println("\n=== Loaded parameters ===");
            parameters.forEach((key, value) -> 
                System.out.println(key + " = " + value));
            
            // 2. Create MyBatis configuration
            SqlSessionFactory sqlSessionFactory = createSqlSessionFactory(xmlFilePath);
            
            // 3. Execute SQL
            try (SqlSession session = sqlSessionFactory.openSession()) {
                System.out.println("\n=== Execute SQL ===");
                
                // Execute directly with SQL ID (MyBatis automatically handles dynamic conditions)
                List<Map<String, Object>> results = session.selectList(sqlId, parameters);
                
                System.out.println("Execution result:");
                if (results.isEmpty()) {
                    System.out.println("No results found.");
                } else {
                    // Output column names from first row
                    Map<String, Object> firstRow = results.get(0);
                    System.out.println("Columns: " + String.join(", ", firstRow.keySet()));
                    System.out.println("─".repeat(80));
                    
                    // Output data (maximum 10 rows)
                    int count = 0;
                    for (Map<String, Object> row : results) {
                        if (count >= 10) {
                            System.out.println("... (showing first 10 rows only, total " + results.size() + " rows)");
                            break;
                        }
                        
                        // Output each column value separated by tabs
                        List<String> values = new ArrayList<>();
                        for (Object value : row.values()) {
                            values.add(value != null ? value.toString() : "NULL");
                        }
                        System.out.println(String.join("\t", values));
                        count++;
                    }
                    System.out.println("\nTotal " + results.size() + " rows retrieved.");
                }
            }
            
        } catch (Exception e) {
            System.err.println("Error occurred: " + e.getMessage());
            e.printStackTrace();
        }
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
                // Check if it's a number
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

    private String modifyXmlForTesting(String xmlFilePath) throws IOException {
        StringBuilder content = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(xmlFilePath))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.contains("resultType="))   line = line.replaceAll("resultType=\"[^\"]*\"",   "resultType=\"map\"");
                if (line.contains("parameterType=")) line = line.replaceAll("parameterType=\"[^\"]*\"", "parameterType=\"map\"");
                content.append(line).append("\n");
            }
        }
        return content.toString();
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
}
