package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 재고 이동 DTO
 */
@Data
public class InventoryMovementDto {
    private Long productId;
    private String productName;
    private String warehouseLocation;
    private String movementType;
    private Integer quantityChanged;
    private Integer currentStock;
    private BigDecimal unitCost;
    private BigDecimal totalValue;
    private LocalDateTime movementDate;
    private String reason;
    private String batchNumber;
}
