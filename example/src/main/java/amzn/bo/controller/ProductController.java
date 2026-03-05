package amzn.bo.controller;

import amzn.bo.dto.*;
import amzn.bo.service.ProductService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/**
 * AMZN 백오피스 상품 관리 컨트롤러
 */
@Slf4j
@RestController
@RequestMapping("/api/products")
@RequiredArgsConstructor
public class ProductController {
    
    private final ProductService productService;
    
    /**
     * 상품 계층 카테고리 조회
     */
    @GetMapping("/categories/hierarchy")
    public ApiResponse<List<CategoryHierarchyDto>> getCategoryHierarchy() {
        try {
            List<CategoryHierarchyDto> categories = productService.getCategoryHierarchy();
            return ApiResponse.success(categories);
        } catch (Exception e) {
            log.error("카테고리 계층 조회 중 오류 발생", e);
            return ApiResponse.error("카테고리 계층 조회에 실패했습니다.");
        }
    }
    
    /**
     * 상품 성과 분석
     */
    @GetMapping("/performance-analysis")
    public ApiResponse<List<ProductPerformanceDto>> getProductPerformanceAnalysis(
            @RequestParam(required = false) String period,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String brand) {
        try {
            Map<String, Object> params = Map.of(
                "period", period != null ? period : "30",
                "categoryId", categoryId != null ? categoryId : "",
                "brand", brand != null ? brand : ""
            );
            List<ProductPerformanceDto> analysis = productService.getProductPerformanceAnalysis(params);
            return ApiResponse.success(analysis);
        } catch (Exception e) {
            log.error("상품 성과 분석 중 오류 발생", e);
            return ApiResponse.error("상품 성과 분석에 실패했습니다.");
        }
    }
    
    /**
     * 상품 목록 조회
     */
    @GetMapping
    public ApiResponse<PageResponse<ProductDto>> getProductList(
            @RequestParam(required = false) String searchKeyword,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) String brand,
            @RequestParam(required = false) BigDecimal minPrice,
            @RequestParam(required = false) BigDecimal maxPrice,
            @RequestParam(required = false) Boolean lowStock,
            @RequestParam(required = false) String sortBy,
            @RequestParam(required = false) String sortDirection,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        
        try {
            ProductDto searchCondition = ProductDto.builder()
                    .searchKeyword(searchKeyword)
                    .statusFilter(status)
                    .categoryFilter(categoryId)
                    .brandFilter(brand)
                    .minPrice(minPrice)
                    .maxPrice(maxPrice)
                    .lowStock(lowStock)
                    .sortBy(sortBy)
                    .sortDirection(sortDirection)
                    .page(page)
                    .size(size)
                    .build();
            
            PageResponse<ProductDto> result = productService.getProductList(searchCondition);
            return ApiResponse.success(result);
            
        } catch (Exception e) {
            log.error("상품 목록 조회 중 오류 발생", e);
            return ApiResponse.error("상품 목록 조회에 실패했습니다.");
        }
    }
    
    /**
     * 상품 상세 정보 조회
     */
    @GetMapping("/{productId}")
    public ApiResponse<ProductDto> getProductDetail(@PathVariable Long productId) {
        try {
            ProductDto product = productService.getProductDetail(productId);
            return ApiResponse.success(product);
        } catch (Exception e) {
            log.error("상품 상세 정보 조회 중 오류 발생. productId: {}", productId, e);
            return ApiResponse.error("상품 정보를 찾을 수 없습니다.");
        }
    }
    
    /**
     * 상품 재고 현황 조회
     */
    @GetMapping("/inventory-status")
    public ApiResponse<List<Map<String, Object>>> getProductInventoryStatus(
            @RequestParam(required = false) Boolean lowStockOnly,
            @RequestParam(required = false) Long categoryId) {
        try {
            Map<String, Object> params = Map.of(
                "lowStockOnly", lowStockOnly != null ? lowStockOnly : false,
                "categoryId", categoryId != null ? categoryId : ""
            );
            List<Map<String, Object>> inventory = productService.getProductInventoryStatus(params);
            return ApiResponse.success(inventory);
        } catch (Exception e) {
            log.error("상품 재고 현황 조회 중 오류 발생", e);
            return ApiResponse.error("상품 재고 현황 조회에 실패했습니다.");
        }
    }
    
    /**
     * 브랜드별 상품 통계
     */
    @GetMapping("/statistics/brands")
    public ApiResponse<List<Map<String, Object>>> getBrandStatistics() {
        try {
            List<Map<String, Object>> stats = productService.getBrandStatistics();
            return ApiResponse.success(stats);
        } catch (Exception e) {
            log.error("브랜드별 상품 통계 조회 중 오류 발생", e);
            return ApiResponse.error("브랜드별 상품 통계 조회에 실패했습니다.");
        }
    }
    
    /**
     * 카테고리별 상품 통계
     */
    @GetMapping("/statistics/categories")
    public ApiResponse<List<Map<String, Object>>> getCategoryStatistics() {
        try {
            List<Map<String, Object>> stats = productService.getCategoryStatistics();
            return ApiResponse.success(stats);
        } catch (Exception e) {
            log.error("카테고리별 상품 통계 조회 중 오류 발생", e);
            return ApiResponse.error("카테고리별 상품 통계 조회에 실패했습니다.");
        }
    }
    
    /**
     * 상품 가격 히스토리 조회
     */
    @GetMapping("/{productId}/price-history")
    public ApiResponse<List<Map<String, Object>>> getProductPriceHistory(@PathVariable Long productId) {
        try {
            List<Map<String, Object>> priceHistory = productService.getProductPriceHistory(productId);
            return ApiResponse.success(priceHistory);
        } catch (Exception e) {
            log.error("상품 가격 히스토리 조회 중 오류 발생. productId: {}", productId, e);
            return ApiResponse.error("상품 가격 히스토리 조회에 실패했습니다.");
        }
    }
    
    /**
     * 상품 등록
     */
    @PostMapping
    public ApiResponse<Void> createProduct(@RequestBody ProductDto productDto) {
        try {
            productService.createProduct(productDto);
            return ApiResponse.success(null, "상품이 성공적으로 등록되었습니다.");
        } catch (Exception e) {
            log.error("상품 등록 중 오류 발생", e);
            return ApiResponse.error("상품 등록에 실패했습니다.");
        }
    }
    
    /**
     * 상품 정보 업데이트
     */
    @PutMapping("/{productId}")
    public ApiResponse<Void> updateProduct(
            @PathVariable Long productId,
            @RequestBody ProductDto productDto) {
        try {
            productDto.setProductId(productId);
            productService.updateProduct(productDto);
            return ApiResponse.success(null, "상품 정보가 성공적으로 업데이트되었습니다.");
        } catch (Exception e) {
            log.error("상품 정보 업데이트 중 오류 발생. productId: {}", productId, e);
            return ApiResponse.error("상품 정보 업데이트에 실패했습니다.");
        }
    }
    
    /**
     * 상품 상태 업데이트
     */
    @PutMapping("/{productId}/status")
    public ApiResponse<Void> updateProductStatus(
            @PathVariable Long productId,
            @RequestParam String status) {
        try {
            productService.updateProductStatus(productId, status);
            return ApiResponse.success(null, "상품 상태가 성공적으로 업데이트되었습니다.");
        } catch (Exception e) {
            log.error("상품 상태 업데이트 중 오류 발생. productId: {}, status: {}", productId, status, e);
            return ApiResponse.error("상품 상태 업데이트에 실패했습니다.");
        }
    }
    
    /**
     * 상품 재고 업데이트
     */
    @PutMapping("/{productId}/stock")
    public ApiResponse<Void> updateProductStock(
            @PathVariable Long productId,
            @RequestParam Integer stockQuantity) {
        try {
            productService.updateProductStock(productId, stockQuantity);
            return ApiResponse.success(null, "상품 재고가 성공적으로 업데이트되었습니다.");
        } catch (Exception e) {
            log.error("상품 재고 업데이트 중 오류 발생. productId: {}, stock: {}", productId, stockQuantity, e);
            return ApiResponse.error("상품 재고 업데이트에 실패했습니다.");
        }
    }
    
    /**
     * 상품 삭제
     */
    @DeleteMapping("/{productId}")
    public ApiResponse<Void> deleteProduct(@PathVariable Long productId) {
        try {
            productService.deleteProduct(productId);
            return ApiResponse.success(null, "상품이 성공적으로 삭제되었습니다.");
        } catch (Exception e) {
            log.error("상품 삭제 중 오류 발생. productId: {}", productId, e);
            return ApiResponse.error("상품 삭제에 실패했습니다.");
        }
    }
    
    /**
     * 상품 일괄 상태 업데이트
     */
    @PutMapping("/batch/status")
    public ApiResponse<Void> updateProductStatusBatch(
            @RequestParam List<Long> productIds,
            @RequestParam String status) {
        try {
            productService.updateProductStatusBatch(productIds, status);
            return ApiResponse.success(null, "상품 일괄 상태 업데이트가 성공적으로 완료되었습니다.");
        } catch (Exception e) {
            log.error("상품 일괄 상태 업데이트 중 오류 발생. status: {}", status, e);
            return ApiResponse.error("상품 일괄 상태 업데이트에 실패했습니다.");
        }
    }
}
