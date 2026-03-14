package amzn.bo.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * AMZN 백오피스 상품 DTO
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ProductDto {
    
    private Long productId;
    private String productName;
    private String sku;
    private String brand;
    private Long categoryId;
    private String categoryName;
    private String description;
    private BigDecimal price;
    private BigDecimal costPrice;
    private String currency;
    private String status;
    private Integer stockQuantity;
    private Integer minStockLevel;
    private String imageUrl;
    private Double weight;
    private String dimensions;
    
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime createdAt;
    
    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime updatedAt;
    
    // 검색 및 필터링용 필드들
    private String searchKeyword;
    private String statusFilter;
    private Long categoryFilter;
    private String brandFilter;
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
    private Boolean lowStock;
    private String sortBy;
    private String sortDirection;
    private Integer page;
    private Integer size;
}
