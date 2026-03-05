package amzn.bo.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 고객서비스 매퍼
 */
@Mapper
public interface CustomerServiceMapper {
    
    /**
     * 고객 문의 목록 조회
     */
    List<Map<String, Object>> selectInquiryList(Map<String, Object> params);
    
    /**
     * 고객 문의 총 개수 조회
     */
    long selectInquiryCount(Map<String, Object> params);
    
    /**
     * 고객 문의 상세 정보 조회
     */
    Map<String, Object> selectInquiryDetail(@Param("inquiryId") Long inquiryId);
    
    /**
     * 문의 유형별 통계
     */
    List<Map<String, Object>> selectInquiryTypeStatistics();
    
    /**
     * 응답 시간 분석
     */
    List<Map<String, Object>> selectResponseTimeAnalysis();
    
    /**
     * 고객 만족도 분석
     */
    List<Map<String, Object>> selectCustomerSatisfactionAnalysis();
    
    /**
     * 상담원별 성과 분석
     */
    List<Map<String, Object>> selectAgentPerformanceAnalysis();
    
    /**
     * 월별 문의 트렌드
     */
    List<Map<String, Object>> selectMonthlyInquiryTrend(@Param("year") Integer year);
    
    /**
     * FAQ 효과성 분석
     */
    List<Map<String, Object>> selectFAQEffectivenessAnalysis();
    
    /**
     * 문의 등록
     */
    int insertInquiry(Map<String, Object> inquiry);
    
    /**
     * 문의 상태 업데이트
     */
    int updateInquiryStatus(@Param("inquiryId") Long inquiryId, 
                           @Param("status") String status);
    
    /**
     * 문의 답변 등록
     */
    int insertInquiryResponse(Map<String, Object> response);
}
