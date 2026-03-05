package amzn.bo.mapper;

import org.apache.ibatis.annotations.Mapper;

import java.util.List;
import java.util.Map;

@Mapper
public interface AnalyticsMapper {
    
    List<Map<String, Object>> selectSalesDashboard(Map<String, Object> params);
    
    List<Map<String, Object>> selectRevenueTrend(Map<String, Object> params);
    
    List<Map<String, Object>> selectProductRevenueAnalysis(Map<String, Object> params);
    
    List<Map<String, Object>> selectCategoryRevenueAnalysis();
    
    List<Map<String, Object>> selectCustomerSegmentAnalysis();
    
    List<Map<String, Object>> selectRegionalRevenueAnalysis();
    
    List<Map<String, Object>> selectHourlyOrderPattern();
    
    List<Map<String, Object>> selectWeeklyOrderPattern();
    
    List<Map<String, Object>> selectMonthlyGrowthRate(Map<String, Object> params);
    
    List<Map<String, Object>> selectCohortAnalysis(Map<String, Object> params);
    
    List<Map<String, Object>> selectRFMAnalysis();
}
