package amzn.bo.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/test")
public class TestController {

    @Autowired
    private DataSource dataSource;

    @GetMapping("/db-connection")
    public Map<String, Object> testDbConnection() {
        Map<String, Object> result = new HashMap<>();
        
        try (Connection conn = dataSource.getConnection()) {
            result.put("status", "SUCCESS");
            result.put("connection", "OK");
            
            // 간단한 쿼리 테스트
            try (PreparedStatement ps = conn.prepareStatement("SELECT SYSDATE FROM DUAL");
                 ResultSet rs = ps.executeQuery()) {
                
                if (rs.next()) {
                    result.put("current_time", rs.getTimestamp(1));
                }
            }
            
            // 사용자 테이블 존재 확인
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = 'USERS'");
                 ResultSet rs = ps.executeQuery()) {
                
                if (rs.next()) {
                    result.put("users_table_exists", rs.getInt(1) > 0);
                }
            }
            
        } catch (Exception e) {
            result.put("status", "ERROR");
            result.put("error", e.getMessage());
            result.put("error_class", e.getClass().getSimpleName());
        }
        
        return result;
    }

    @GetMapping("/simple-user-query")
    public Map<String, Object> testSimpleUserQuery() {
        Map<String, Object> result = new HashMap<>();
        
        try (Connection conn = dataSource.getConnection()) {
            // 간단한 사용자 카운트 쿼리
            try (PreparedStatement ps = conn.prepareStatement("SELECT COUNT(*) FROM USERS");
                 ResultSet rs = ps.executeQuery()) {
                
                if (rs.next()) {
                    result.put("total_users", rs.getInt(1));
                    result.put("status", "SUCCESS");
                }
            }
            
        } catch (Exception e) {
            result.put("status", "ERROR");
            result.put("error", e.getMessage());
            result.put("error_class", e.getClass().getSimpleName());
        }
        
        return result;
    }

    @GetMapping("/table-structure")
    public Map<String, Object> checkTableStructure() {
        Map<String, Object> result = new HashMap<>();
        
        try (Connection conn = dataSource.getConnection()) {
            // USERS 테이블 컬럼 확인
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT COLUMN_NAME, DATA_TYPE FROM USER_TAB_COLUMNS WHERE TABLE_NAME = 'USERS' ORDER BY COLUMN_ID");
                 ResultSet rs = ps.executeQuery()) {
                
                List<Map<String, String>> userColumns = new ArrayList<>();
                while (rs.next()) {
                    Map<String, String> col = new HashMap<>();
                    col.put("column_name", rs.getString("COLUMN_NAME"));
                    col.put("data_type", rs.getString("DATA_TYPE"));
                    userColumns.add(col);
                }
                result.put("users_columns", userColumns);
            }
            
            // ORDERS 테이블 컬럼 확인
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT COLUMN_NAME, DATA_TYPE FROM USER_TAB_COLUMNS WHERE TABLE_NAME = 'ORDERS' ORDER BY COLUMN_ID");
                 ResultSet rs = ps.executeQuery()) {
                
                List<Map<String, String>> orderColumns = new ArrayList<>();
                while (rs.next()) {
                    Map<String, String> col = new HashMap<>();
                    col.put("column_name", rs.getString("COLUMN_NAME"));
                    col.put("data_type", rs.getString("DATA_TYPE"));
                    orderColumns.add(col);
                }
                result.put("orders_columns", orderColumns);
            }
            
            // CATEGORIES 테이블 존재 확인
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = 'CATEGORIES'");
                 ResultSet rs = ps.executeQuery()) {
                
                if (rs.next()) {
                    result.put("categories_table_exists", rs.getInt(1) > 0);
                }
            }
            
            result.put("status", "SUCCESS");
            
        } catch (Exception e) {
            result.put("status", "ERROR");
            result.put("error", e.getMessage());
            result.put("error_class", e.getClass().getSimpleName());
        }
        
        return result;
    }

    @GetMapping("/test-activity-query")
    public Map<String, Object> testActivityQuery() {
        Map<String, Object> result = new HashMap<>();
        
        try (Connection conn = dataSource.getConnection()) {
            // 단계별로 쿼리 테스트
            
            // 1. 기본 사용자 정보만
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT USER_ID, EMAIL, FIRST_NAME, LAST_NAME, CREATED_AT FROM USERS WHERE USER_ID = 1");
                 ResultSet rs = ps.executeQuery()) {
                
                if (rs.next()) {
                    Map<String, Object> userInfo = new HashMap<>();
                    userInfo.put("user_id", rs.getLong("USER_ID"));
                    userInfo.put("email", rs.getString("EMAIL"));
                    userInfo.put("first_name", rs.getString("FIRST_NAME"));
                    userInfo.put("last_name", rs.getString("LAST_NAME"));
                    userInfo.put("created_at", rs.getTimestamp("CREATED_AT"));
                    result.put("user_info", userInfo);
                }
            }
            
            // 2. 주문 통계만
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT COUNT(*) as TOTAL_ORDERS, SUM(TOTAL_AMOUNT) as TOTAL_SPENT FROM ORDERS WHERE USER_ID = 1 AND ORDER_STATUS NOT IN ('CANCELLED', 'REFUNDED')");
                 ResultSet rs = ps.executeQuery()) {
                
                if (rs.next()) {
                    Map<String, Object> orderStats = new HashMap<>();
                    orderStats.put("total_orders", rs.getInt("TOTAL_ORDERS"));
                    orderStats.put("total_spent", rs.getBigDecimal("TOTAL_SPENT"));
                    result.put("order_stats", orderStats);
                }
            }
            
            result.put("status", "SUCCESS");
            
        } catch (Exception e) {
            result.put("status", "ERROR");
            result.put("error", e.getMessage());
            result.put("error_class", e.getClass().getSimpleName());
        }
        
        return result;
    }

    @GetMapping("/debug-activity-query")
    public Map<String, Object> debugActivityQuery() {
        Map<String, Object> result = new HashMap<>();
        
        try (Connection conn = dataSource.getConnection()) {
            
            // 카테고리 서브쿼리만 테스트
            String categoryQuery = """
                SELECT 
                    o.USER_ID,
                    c.CATEGORY_NAME as FAVORITE_CATEGORY,
                    COUNT(*) as CATEGORY_ORDER_COUNT
                FROM ORDERS o
                JOIN ORDER_ITEMS oi ON o.ORDER_ID = oi.ORDER_ID
                JOIN PRODUCTS p ON oi.PRODUCT_ID = p.PRODUCT_ID
                JOIN CATEGORIES c ON p.CATEGORY_ID = c.CATEGORY_ID
                WHERE o.ORDER_STATUS NOT IN ('CANCELLED', 'REFUNDED')
                AND o.USER_ID = 1
                GROUP BY o.USER_ID, c.CATEGORY_NAME
                """;
            
            try (PreparedStatement ps = conn.prepareStatement(categoryQuery);
                 ResultSet rs = ps.executeQuery()) {
                
                List<Map<String, Object>> categoryStats = new ArrayList<>();
                while (rs.next()) {
                    Map<String, Object> stat = new HashMap<>();
                    stat.put("user_id", rs.getLong("USER_ID"));
                    stat.put("category_name", rs.getString("FAVORITE_CATEGORY"));
                    stat.put("count", rs.getInt("CATEGORY_ORDER_COUNT"));
                    categoryStats.add(stat);
                }
                result.put("category_stats", categoryStats);
            }
            
            // 결제 방법 서브쿼리만 테스트
            String paymentQuery = """
                SELECT 
                    o.USER_ID,
                    o.PAYMENT_METHOD as PREFERRED_PAYMENT_METHOD,
                    COUNT(*) as PAYMENT_METHOD_COUNT
                FROM ORDERS o
                WHERE o.ORDER_STATUS NOT IN ('CANCELLED', 'REFUNDED')
                AND o.USER_ID = 1
                GROUP BY o.USER_ID, o.PAYMENT_METHOD
                """;
            
            try (PreparedStatement ps = conn.prepareStatement(paymentQuery);
                 ResultSet rs = ps.executeQuery()) {
                
                List<Map<String, Object>> paymentStats = new ArrayList<>();
                while (rs.next()) {
                    Map<String, Object> stat = new HashMap<>();
                    stat.put("user_id", rs.getLong("USER_ID"));
                    stat.put("payment_method", rs.getString("PREFERRED_PAYMENT_METHOD"));
                    stat.put("count", rs.getInt("PAYMENT_METHOD_COUNT"));
                    paymentStats.add(stat);
                }
                result.put("payment_stats", paymentStats);
            }
            
            result.put("status", "SUCCESS");
            
        } catch (Exception e) {
            result.put("status", "ERROR");
            result.put("error", e.getMessage());
            result.put("error_class", e.getClass().getSimpleName());
            e.printStackTrace();
        }
        
        return result;
    }
}
