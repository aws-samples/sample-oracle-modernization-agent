package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 재고 상태 DTO
 */
@Data
public class InventoryStatusDto {
    private Long productId;
    private String productName;
    private String category;
    private String brand;
    private Integer currentStock;
    private Integer reservedStock;
    private Integer availableStock;
    private Integer minStockLevel;
    private Integer maxStockLevel;
    private BigDecimal unitCost;
    private BigDecimal totalValue;
    private String stockStatus;
    private LocalDateTime lastUpdated;
    private String warehouseLocation;
}
