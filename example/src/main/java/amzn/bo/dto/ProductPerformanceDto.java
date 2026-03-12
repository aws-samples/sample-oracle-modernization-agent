package amzn.bo.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * AMZN 백오피스 상품 성과 분석 DTO
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ProductPerformanceDto {
    
    private Long productId;
    private String productName;
    private String sku;
    private String brand;
    private String categoryName;
    private Long totalSold;
    private BigDecimal totalRevenue;
    private BigDecimal avgSellingPrice;
    private Integer salesRank;
    private Integer categorySalesRank;
    private Integer brandSalesRank;
    private BigDecimal avgRating;
    private Long reviewCount;
    private Integer currentStock;
    private BigDecimal stockTurnoverRate;
}
