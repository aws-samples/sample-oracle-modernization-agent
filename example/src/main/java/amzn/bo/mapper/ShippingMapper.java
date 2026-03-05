package amzn.bo.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 배송 매퍼
 */
@Mapper
public interface ShippingMapper {
    
    /**
     * 배송 목록 조회
     */
    List<Map<String, Object>> selectShippingList(Map<String, Object> params);
    
    /**
     * 배송 총 개수 조회
     */
    long selectShippingCount(Map<String, Object> params);
    
    /**
     * 배송 상세 정보 조회
     */
    Map<String, Object> selectShippingDetail(@Param("shippingId") Long shippingId);
    
    /**
     * 배송 상태별 통계
     */
    List<Map<String, Object>> selectShippingStatusStatistics();
    
    /**
     * 배송 업체별 성과 분석
     */
    List<Map<String, Object>> selectCarrierPerformanceAnalysis();
    
    /**
     * 지역별 배송 분석
     */
    List<Map<String, Object>> selectRegionalShippingAnalysis();
    
    /**
     * 배송 시간 분석
     */
    List<Map<String, Object>> selectDeliveryTimeAnalysis();
    
    /**
     * 배송비 분석
     */
    List<Map<String, Object>> selectShippingCostAnalysis();
    
    /**
     * 배송 지연 분석
     */
    List<Map<String, Object>> selectDeliveryDelayAnalysis();
    
    /**
     * 배송 정보 업데이트
     */
    int updateShippingInfo(Map<String, Object> shipping);
    
    /**
     * 배송 상태 업데이트
     */
    int updateShippingStatus(@Param("shippingId") Long shippingId, 
                            @Param("status") String status);
    
    /**
     * 추적 정보 업데이트
     */
    int updateTrackingInfo(@Param("shippingId") Long shippingId, 
                          @Param("trackingNumber") String trackingNumber);
}
