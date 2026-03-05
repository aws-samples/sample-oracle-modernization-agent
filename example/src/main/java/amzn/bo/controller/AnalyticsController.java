package amzn.bo.controller;

import amzn.bo.service.AnalyticsService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/analytics")
public class AnalyticsController {

    @Autowired
    private AnalyticsService analyticsService;

    @GetMapping("/sales-dashboard")
    public ResponseEntity<Map<String, Object>> getSalesDashboard() {
        try {
            List<Map<String, Object>> data = analyticsService.getSalesDashboard();
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/revenue-trend")
    public ResponseEntity<Map<String, Object>> getRevenueTrend(@RequestParam(defaultValue = "MONTH") String groupBy) {
        try {
            List<Map<String, Object>> data = analyticsService.getRevenueTrend(groupBy);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/product-revenue")
    public ResponseEntity<Map<String, Object>> getProductRevenueAnalysis(@RequestParam(defaultValue = "10") Integer limit) {
        try {
            List<Map<String, Object>> data = analyticsService.getProductRevenueAnalysis(limit);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/category-revenue")
    public ResponseEntity<Map<String, Object>> getCategoryRevenueAnalysis() {
        try {
            List<Map<String, Object>> data = analyticsService.getCategoryRevenueAnalysis();
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/customer-segment")
    public ResponseEntity<Map<String, Object>> getCustomerSegmentAnalysis() {
        try {
            List<Map<String, Object>> data = analyticsService.getCustomerSegmentAnalysis();
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/regional-revenue")
    public ResponseEntity<Map<String, Object>> getRegionalRevenueAnalysis() {
        try {
            List<Map<String, Object>> data = analyticsService.getRegionalRevenueAnalysis();
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/hourly-pattern")
    public ResponseEntity<Map<String, Object>> getHourlyOrderPattern() {
        try {
            List<Map<String, Object>> data = analyticsService.getHourlyOrderPattern();
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/weekly-pattern")
    public ResponseEntity<Map<String, Object>> getWeeklyOrderPattern() {
        try {
            List<Map<String, Object>> data = analyticsService.getWeeklyOrderPattern();
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/monthly-growth")
    public ResponseEntity<Map<String, Object>> getMonthlyGrowthRate(@RequestParam(defaultValue = "12") Integer months) {
        try {
            List<Map<String, Object>> data = analyticsService.getMonthlyGrowthRate(months);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/cohort-analysis")
    public ResponseEntity<Map<String, Object>> getCohortAnalysis(@RequestParam(defaultValue = "12") Integer months) {
        try {
            List<Map<String, Object>> data = analyticsService.getCohortAnalysis(months);
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }

    @GetMapping("/rfm-analysis")
    public ResponseEntity<Map<String, Object>> getRFMAnalysis() {
        try {
            List<Map<String, Object>> data = analyticsService.getRFMAnalysis();
            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("data", data);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", e.getMessage());
            return ResponseEntity.status(500).body(response);
        }
    }
}
