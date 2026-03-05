package amzn.bo.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 결제 매퍼
 */
@Mapper
public interface PaymentMapper {
    
    /**
     * 결제 목록 조회
     */
    List<Map<String, Object>> selectPaymentList(Map<String, Object> params);
    
    /**
     * 결제 총 개수 조회
     */
    long selectPaymentCount(Map<String, Object> params);
    
    /**
     * 결제 상세 정보 조회
     */
    Map<String, Object> selectPaymentDetail(@Param("paymentId") Long paymentId);
    
    /**
     * 결제 방법별 통계
     */
    List<Map<String, Object>> selectPaymentMethodStatistics();
    
    /**
     * 결제 상태별 통계
     */
    List<Map<String, Object>> selectPaymentStatusStatistics();
    
    /**
     * 일별 결제 트렌드
     */
    List<Map<String, Object>> selectDailyPaymentTrend(@Param("startDate") String startDate,
                                                      @Param("endDate") String endDate);
    
    /**
     * 결제 실패 분석
     */
    List<Map<String, Object>> selectPaymentFailureAnalysis();
    
    /**
     * 환불 통계
     */
    List<Map<String, Object>> selectRefundStatistics();
    
    /**
     * 결제 처리 시간 분석
     */
    List<Map<String, Object>> selectPaymentProcessingTimeAnalysis();
    
    /**
     * 결제 상태 업데이트
     */
    int updatePaymentStatus(@Param("paymentId") Long paymentId, 
                           @Param("status") String status);
}
