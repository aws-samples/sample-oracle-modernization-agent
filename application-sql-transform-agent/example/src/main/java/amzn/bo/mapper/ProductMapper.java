package amzn.bo.mapper;

import amzn.bo.dto.CategoryHierarchyDto;
import amzn.bo.dto.ProductDto;
import amzn.bo.dto.ProductPerformanceDto;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 상품 매퍼
 */
@Mapper
public interface ProductMapper {
    
    /**
     * 상품 계층 카테고리 관리 (CONNECT BY 활용)
     */
    List<CategoryHierarchyDto> selectCategoryHierarchy();
    
    /**
     * 상품 성과 분석 (윈도우 함수 활용)
     */
    List<ProductPerformanceDto> selectProductPerformanceAnalysis(Map<String, Object> params);
    
    /**
     * 상품 목록 조회
     */
    List<ProductDto> selectProductList(Map<String, Object> params);
    
    /**
     * 상품 총 개수 조회
     */
    long selectProductCount(Map<String, Object> params);
    
    /**
     * 상품 상세 정보 조회
     */
    ProductDto selectProductDetail(@Param("productId") Long productId);
    
    /**
     * 상품 재고 현황 조회
     */
    List<Map<String, Object>> selectProductInventoryStatus(Map<String, Object> params);
    
    /**
     * 브랜드별 상품 통계
     */
    List<Map<String, Object>> selectBrandStatistics();
    
    /**
     * 카테고리별 상품 통계
     */
    List<Map<String, Object>> selectCategoryStatistics();
    
    /**
     * 상품 가격 히스토리 조회
     */
    List<Map<String, Object>> selectProductPriceHistory(@Param("productId") Long productId);
    
    /**
     * 상품 등록
     */
    int createProduct(ProductDto productDto);
    
    /**
     * 상품 정보 업데이트
     */
    int updateProduct(ProductDto productDto);
    
    /**
     * 상품 상태 업데이트
     */
    int updateProductStatus(@Param("productId") Long productId, @Param("status") String status);
    
    /**
     * 상품 재고 업데이트
     */
    int updateProductStock(@Param("productId") Long productId, @Param("stockQuantity") Integer stockQuantity);
    
    /**
     * 상품 삭제 (소프트 삭제)
     */
    int deleteProduct(@Param("productId") Long productId);
    
    /**
     * 상품 일괄 상태 업데이트
     */
    int updateProductStatusBatch(@Param("productIds") List<Long> productIds, @Param("status") String status);
}
