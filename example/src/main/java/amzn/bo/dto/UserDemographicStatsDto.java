package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

@Data
public class UserDemographicStatsDto {
    private String country;
    private String ageGroup;
    private Long userCount;
    private BigDecimal avgSpent;
    private BigDecimal totalSpent;
    private Long totalOrders;
    private BigDecimal avgOrderValue;
    private Integer countryGrouping;
    private Integer ageGroupGrouping;
}
