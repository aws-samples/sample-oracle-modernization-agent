package amzn.bo.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;

/**
 * 데이터베이스 연결 테스트 클래스
 */
@Slf4j
@Component
public class DatabaseConnectionTest implements CommandLineRunner {

    @Autowired
    private DataSource dataSource;

    @Override
    public void run(String... args) throws Exception {
        testDatabaseConnection();
        listTables();
    }

    private void testDatabaseConnection() {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metaData = connection.getMetaData();
            
            log.info("=== 데이터베이스 연결 정보 ===");
            log.info("Database Product Name: {}", metaData.getDatabaseProductName());
            log.info("Database Product Version: {}", metaData.getDatabaseProductVersion());
            log.info("Driver Name: {}", metaData.getDriverName());
            log.info("Driver Version: {}", metaData.getDriverVersion());
            log.info("URL: {}", metaData.getURL());
            log.info("Username: {}", metaData.getUserName());
            log.info("Connection Valid: {}", connection.isValid(5));
            log.info("=== 데이터베이스 연결 성공! ===");
            
        } catch (Exception e) {
            log.error("데이터베이스 연결 실패!", e);
        }
    }

    private void listTables() {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metaData = connection.getMetaData();
            
            log.info("=== 테이블 목록 조회 ===");
            
            // OMA 스키마의 테이블들 조회
            try (ResultSet tables = metaData.getTables(null, "OMA", "%", new String[]{"TABLE"})) {
                int count = 0;
                while (tables.next() && count < 10) { // 처음 10개만 출력
                    String tableName = tables.getString("TABLE_NAME");
                    log.info("Table {}: {}", count + 1, tableName);
                    count++;
                }
                log.info("총 {}개의 테이블이 조회되었습니다 (처음 10개만 표시)", count);
            }
            
        } catch (Exception e) {
            log.error("테이블 목록 조회 실패!", e);
        }
    }
}
