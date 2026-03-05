package amzn.bo.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 재고 매퍼
 */
@Mapper
public interface InventoryMapper {
    
    /**
     * 재고 목록 조회
     */
    List<Map<String, Object>> selectInventoryList(Map<String, Object> params);
    
    /**
     * 재고 총 개수 조회
     */
    long selectInventoryCount(Map<String, Object> params);
    
    /**
     * 재고 상세 정보 조회
     */
    Map<String, Object> selectInventoryDetail(@Param("productId") Long productId);
    
    /**
     * 재고 부족 상품 조회
     */
    List<Map<String, Object>> selectLowStockProducts(@Param("threshold") Integer threshold);
    
    /**
     * 재고 회전율 분석
     */
    List<Map<String, Object>> selectInventoryTurnoverAnalysis();
    
    /**
     * 카테고리별 재고 현황
     */
    List<Map<String, Object>> selectInventoryByCategory();
    
    /**
     * 재고 가치 분석
     */
    List<Map<String, Object>> selectInventoryValueAnalysis();
    
    /**
     * 데드스톡 분석
     */
    List<Map<String, Object>> selectDeadStockAnalysis(@Param("days") Integer days);
    
    /**
     * 재고 입출고 이력
     */
    List<Map<String, Object>> selectInventoryTransactionHistory(@Param("productId") Long productId,
                                                               @Param("startDate") String startDate,
                                                               @Param("endDate") String endDate);
    
    /**
     * 재고 업데이트
     */
    int updateInventory(@Param("productId") Long productId, 
                       @Param("quantity") Integer quantity,
                       @Param("transactionType") String transactionType);
    
    /**
     * 재고 조정
     */
    int adjustInventory(@Param("productId") Long productId, 
                       @Param("adjustmentQuantity") Integer adjustmentQuantity,
                       @Param("reason") String reason);
    
    /**
     * 재고 알림 설정 업데이트
     */
    int updateStockAlert(@Param("productId") Long productId, 
                        @Param("minStockLevel") Integer minStockLevel);
}
