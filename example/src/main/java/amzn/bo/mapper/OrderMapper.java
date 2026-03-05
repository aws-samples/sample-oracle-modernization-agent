package amzn.bo.mapper;

import amzn.bo.dto.OrderAnalysisDto;
import amzn.bo.dto.OrderDto;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 주문 매퍼
 */
@Mapper
public interface OrderMapper {
    
    /**
     * 주문 목록 조회 (복합 검색 및 고급 분석)
     */
    List<OrderAnalysisDto> selectOrderListWithAnalysis(Map<String, Object> params);
    
    /**
     * 주문 총 개수 조회
     */
    long selectOrderCount(Map<String, Object> params);
    
    /**
     * 주문 상세 정보 조회
     */
    OrderDto selectOrderDetail(@Param("orderId") Long orderId);
    
    /**
     * 주문 상태별 통계
     */
    List<Map<String, Object>> selectOrderStatusStatistics();
    
    /**
     * 주문 트렌드 분석 (일별/월별/분기별)
     */
    List<Map<String, Object>> selectOrderTrendAnalysis(@Param("startDate") String startDate,
                                                       @Param("endDate") String endDate,
                                                       @Param("groupBy") String groupBy);
    
    /**
     * 결제 방법별 주문 통계
     */
    List<Map<String, Object>> selectPaymentMethodStatistics();
    
    /**
     * 주문 처리 시간 분석
     */
    List<Map<String, Object>> selectOrderProcessingTimeAnalysis();
    
    /**
     * 고객별 주문 패턴 분석
     */
    List<Map<String, Object>> selectCustomerOrderPatternAnalysis(Map<String, Object> params);
    
    /**
     * 주문 아이템 상세 조회
     */
    List<Map<String, Object>> selectOrderItems(@Param("orderId") Long orderId);
    
    /**
     * 주문 배송 정보 조회
     */
    Map<String, Object> selectOrderShippingInfo(@Param("orderId") Long orderId);
    
    /**
     * 주문 상태 업데이트
     */
    int updateOrderStatus(@Param("orderId") Long orderId, @Param("status") String status);
    
    /**
     * 주문 배송 정보 업데이트
     */
    int updateOrderShippingInfo(@Param("orderId") Long orderId, 
                               @Param("trackingNumber") String trackingNumber,
                               @Param("carrier") String carrier);
    
    /**
     * 주문 취소
     */
    int cancelOrder(@Param("orderId") Long orderId, @Param("reason") String reason);
    
    /**
     * 주문 환불 처리
     */
    int refundOrder(@Param("params") Map<String, Object> params);
    
    /**
     * 주문 일괄 상태 업데이트
     */
    int updateOrderStatusBatch(@Param("orderIds") List<Long> orderIds, @Param("status") String status);
}
