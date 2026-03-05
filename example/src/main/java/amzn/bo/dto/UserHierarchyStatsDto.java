package amzn.bo.dto;

import lombok.Data;
import java.math.BigDecimal;

@Data
public class UserHierarchyStatsDto {
    private String userGrade;
    private String status;
    private String country;
    private Long userCount;
    private BigDecimal avgSpent;
    private BigDecimal totalSpent;
    private BigDecimal avgOrderCount;
    private Integer userGradeGrouping;
    private Integer statusGrouping;
    private Integer countryGrouping;
}
