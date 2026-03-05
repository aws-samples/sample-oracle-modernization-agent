package amzn.bo.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 프로모션 매퍼
 */
@Mapper
public interface PromotionMapper {
    
    /**
     * 프로모션 목록 조회
     */
    List<Map<String, Object>> selectPromotionList(Map<String, Object> params);
    
    /**
     * 프로모션 총 개수 조회
     */
    long selectPromotionCount(Map<String, Object> params);
    
    /**
     * 프로모션 상세 정보 조회
     */
    Map<String, Object> selectPromotionDetail(@Param("promotionId") Long promotionId);
    
    /**
     * 프로모션 성과 분석
     */
    List<Map<String, Object>> selectPromotionPerformanceAnalysis();
    
    /**
     * 쿠폰 사용 통계
     */
    List<Map<String, Object>> selectCouponUsageStatistics();
    
    /**
     * 할인 효과 분석
     */
    List<Map<String, Object>> selectDiscountEffectivenessAnalysis();
    
    /**
     * 프로모션별 매출 기여도
     */
    List<Map<String, Object>> selectPromotionRevenueContribution();
    
    /**
     * 시즌별 프로모션 트렌드
     */
    List<Map<String, Object>> selectSeasonalPromotionTrend();
    
    /**
     * 프로모션 등록
     */
    int insertPromotion(Map<String, Object> promotion);
    
    /**
     * 프로모션 업데이트
     */
    int updatePromotion(Map<String, Object> promotion);
    
    /**
     * 프로모션 상태 업데이트
     */
    int updatePromotionStatus(@Param("promotionId") Long promotionId, 
                             @Param("status") String status);
}
