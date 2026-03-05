package amzn.bo.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 판매자 매퍼
 */
@Mapper
public interface SellerMapper {
    
    /**
     * 판매자 목록 조회
     */
    List<Map<String, Object>> selectSellerList(Map<String, Object> params);
    
    /**
     * 판매자 총 개수 조회
     */
    long selectSellerCount(Map<String, Object> params);
    
    /**
     * 판매자 상세 정보 조회
     */
    Map<String, Object> selectSellerDetail(@Param("sellerId") Long sellerId);
    
    /**
     * 판매자 성과 분석
     */
    List<Map<String, Object>> selectSellerPerformanceAnalysis();
    
    /**
     * 판매자별 매출 통계
     */
    List<Map<String, Object>> selectSellerRevenueStatistics();
    
    /**
     * 판매자 등급별 분석
     */
    List<Map<String, Object>> selectSellerTierAnalysis();
    
    /**
     * 판매자 상품 카테고리 분석
     */
    List<Map<String, Object>> selectSellerCategoryAnalysis(@Param("sellerId") Long sellerId);
    
    /**
     * 판매자 정산 내역
     */
    List<Map<String, Object>> selectSellerSettlementHistory(@Param("sellerId") Long sellerId,
                                                            @Param("startDate") String startDate,
                                                            @Param("endDate") String endDate);
    
    /**
     * 판매자 등록
     */
    int insertSeller(Map<String, Object> seller);
    
    /**
     * 판매자 정보 업데이트
     */
    int updateSeller(Map<String, Object> seller);
    
    /**
     * 판매자 상태 업데이트
     */
    int updateSellerStatus(@Param("sellerId") Long sellerId, 
                          @Param("status") String status);
}
