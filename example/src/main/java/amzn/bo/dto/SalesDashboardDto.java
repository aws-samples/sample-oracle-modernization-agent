package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDate;

@Data
public class SalesDashboardDto {
    private LocalDate salesDate;
    private String period;
    private String category;
    private String region;
    private Long totalOrders;
    private BigDecimal totalRevenue;
    private BigDecimal avgOrderValue;
    private Long uniqueCustomers;
    private BigDecimal conversionRate;
    private BigDecimal growthRate;
    private Long rank;
}
