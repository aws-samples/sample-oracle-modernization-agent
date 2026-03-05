package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

/**
 * 창고 재고 DTO
 */
@Data
public class WarehouseInventoryDto {
    private String warehouseId;
    private String warehouseName;
    private String location;
    private Integer totalProducts;
    private Integer totalStock;
    private BigDecimal totalValue;
    private BigDecimal utilizationRate;
    private Integer lowStockItems;
    private Integer overstockItems;
    private BigDecimal averageTurnover;
    private String status;
}
