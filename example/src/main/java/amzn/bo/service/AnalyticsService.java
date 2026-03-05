package amzn.bo.service;

import amzn.bo.mapper.AnalyticsMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class AnalyticsService {

    @Autowired
    private AnalyticsMapper analyticsMapper;

    public List<Map<String, Object>> getSalesDashboard() {
        return analyticsMapper.selectSalesDashboard(new HashMap<>());
    }

    public List<Map<String, Object>> getRevenueTrend(String groupBy) {
        Map<String, Object> params = new HashMap<>();
        params.put("groupBy", groupBy);
        return analyticsMapper.selectRevenueTrend(params);
    }

    public List<Map<String, Object>> getProductRevenueAnalysis(Integer limit) {
        Map<String, Object> params = new HashMap<>();
        params.put("limit", limit);
        return analyticsMapper.selectProductRevenueAnalysis(params);
    }

    public List<Map<String, Object>> getCategoryRevenueAnalysis() {
        return analyticsMapper.selectCategoryRevenueAnalysis();
    }

    public List<Map<String, Object>> getCustomerSegmentAnalysis() {
        return analyticsMapper.selectCustomerSegmentAnalysis();
    }

    public List<Map<String, Object>> getRegionalRevenueAnalysis() {
        return analyticsMapper.selectRegionalRevenueAnalysis();
    }

    public List<Map<String, Object>> getHourlyOrderPattern() {
        return analyticsMapper.selectHourlyOrderPattern();
    }

    public List<Map<String, Object>> getWeeklyOrderPattern() {
        return analyticsMapper.selectWeeklyOrderPattern();
    }

    public List<Map<String, Object>> getMonthlyGrowthRate(Integer months) {
        Map<String, Object> params = new HashMap<>();
        params.put("months", months);
        return analyticsMapper.selectMonthlyGrowthRate(params);
    }

    public List<Map<String, Object>> getCohortAnalysis(Integer months) {
        Map<String, Object> params = new HashMap<>();
        params.put("months", months);
        return analyticsMapper.selectCohortAnalysis(params);
    }

    public List<Map<String, Object>> getRFMAnalysis() {
        return analyticsMapper.selectRFMAnalysis();
    }
}
