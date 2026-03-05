package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

/**
 * 재고 최적화 DTO
 */
@Data
public class InventoryOptimizationDto {
    private Long productId;
    private String productName;
    private String category;
    private Integer currentStock;
    private Integer recommendedStock;
    private BigDecimal turnoverRate;
    private Integer daysOfSupply;
    private BigDecimal reorderPoint;
    private BigDecimal economicOrderQuantity;
    private String stockStatus;
    private BigDecimal potentialSavings;
    private String recommendation;
}
